"""Comprobaciones estáticas del panel: sin recursos externos y con las piezas del acceso enlazadas."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from fabrica_studio.server import crear_app

WEB = Path(__file__).resolve().parent.parent / "fabrica_studio" / "web"


def _texto(nombre: str) -> str:
    return (WEB / nombre).read_text(encoding="utf-8")


def test_el_panel_no_carga_nada_de_internet():
    """Regla 11 y plan del login: ni CDN ni fuentes remotas; todo se sirve desde el PC."""
    for archivo in WEB.rglob("*"):
        if archivo.suffix in (".html", ".css"):
            assert not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//|url\(\s*["']?(https?:)?//|@import""",
                                 archivo.read_text(encoding="utf-8")), archivo.name
    for js in ("app.js", "editor.js"):
        assert not re.search(r"""import\s*\(\s*["']https?:|<script[^>]+https?:|fetch\(\s*["'`]https?:""", _texto(js)), js


def test_pantallas_de_acceso_servidas_y_enlazadas(fabrica):
    html = TestClient(crear_app(fabrica, iniciar_hilos=False), base_url="http://127.0.0.1:8765").get("/").text
    for pieza in ('id="form-crear"', 'id="form-login"', 'id="vincular"', 'id="l-bloqueo"', 'id="menu-usuario"',
                  'autocomplete="current-password"', 'autocomplete="new-password"'):
        assert pieza in html, pieza
    js = _texto("app.js")
    assert '<script src="editor.js">' in html
    # Cada data-accion del HTML y del propio app.js tiene su función en `acciones`.
    definidas = set(re.findall(r'^  "?([a-z-]+)"?: ', js.split("const acciones = {")[1].split("\n};")[0], re.M))
    usadas = set(re.findall(r'data-accion="([a-z-]+)"', html + js))
    assert usadas <= definidas, usadas - definidas
    iconos = _texto("iconos.js")
    for nombre in set(re.findall(r'data-icono="([a-z-]+)"', html)) | set(re.findall(r'\b(?:ic|icono)\("([a-z-]+)"\)', js + _texto("editor.js"))):
        assert re.search(rf'^  "?{nombre}"?:', iconos, re.M), nombre


def test_gsap_local_referenciado_e_intacto():
    """La biblioteca se sirve desde el PC y es byte a byte la anotada en vendor/LICENCIAS.md."""
    import hashlib
    assert '<script src="vendor/gsap.min.js">' in _texto("index.html")
    huella = hashlib.sha256((WEB / "vendor" / "gsap.min.js").read_bytes()).hexdigest()
    assert huella in _texto("vendor/LICENCIAS.md")
    # Sin la biblioteca el panel debe seguir funcionando: todo uso pasa por animar() o comprueba window.gsap.
    js = _texto("app.js")
    assert "const animar = () => !!window.gsap && !calma.matches;" in js


def test_campos_de_la_plantilla_son_ajustes_reales():
    """Un campo con la clave mal escrita se guardaría en vacío: el servidor ignora claves desconocidas."""
    from fabrica_studio.config import AJUSTES_POR_DEFECTO
    bloque = _texto("app.js").split("const SECCIONES_PLANTILLA = [")[1].split("\n];")[0]
    claves = [c for c in re.findall(r'\["([a-z_]+)", "', bloque) if c not in ("clasico", "completo", "dividido")]   # opciones de «estilo»
    assert len(claves) > 20 and len(claves) == len(set(claves))
    assert set(claves) <= set(AJUSTES_POR_DEFECTO), set(claves) - set(AJUSTES_POR_DEFECTO)


def test_campos_de_proveedores_son_ajustes_reales():
    """Incluye «Contexto de transcripción» (vocabulario) y «Correcciones de escritura» (correcciones)."""
    from fabrica_studio.config import AJUSTES_POR_DEFECTO
    bloque = _texto("app.js").split('id="form-prov"')[1].split("</form>")[0]
    nombres = set(re.findall(r'name="([a-z_]+)"', bloque))
    assert {"vocabulario", "correcciones"} <= nombres
    assert nombres <= set(AJUSTES_POR_DEFECTO), nombres - set(AJUSTES_POR_DEFECTO)
