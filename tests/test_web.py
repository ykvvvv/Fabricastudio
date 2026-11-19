"""Comprobaciones estáticas del panel: sin recursos externos y con las piezas del acceso enlazadas."""
import re
from pathlib import Path

import pytest
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
    for js in ("app.js", "editor.js", "sondeo.js"):
        assert not re.search(r"""import\s*\(\s*["']https?:|<script[^>]+https?:|fetch\(\s*["'`]https?:""", _texto(js)), js


def test_pantallas_de_acceso_servidas_y_enlazadas(fabrica):
    html = TestClient(crear_app(fabrica, iniciar_hilos=False), base_url="http://127.0.0.1:8765").get("/").text
    for pieza in ('id="form-crear"', 'id="form-login"', 'id="vincular"', 'id="l-bloqueo"', 'id="menu-usuario"',
                  'autocomplete="current-password"', 'autocomplete="new-password"'):
        assert pieza in html, pieza
    js = _texto("app.js")
    assert html.index('src="sondeo.js"') < html.index('src="app.js"')
    # El editor de tiempos no se carga al abrir el panel: app.js lo descarga al primer uso.
    assert 'src="editor.js"' not in html and 's.src = "editor.js"' in js
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
    # Reordenar listas no depende de GSAP y respeta «reducir movimiento».
    assert "const mover = () => !calma.matches && !!Element.prototype.animate;" in js
    assert "if (mover() && viejos.size" in js.split("function ponerLista(")[1].split("\n}")[0]


def test_vista_previa_de_la_biblioteca():
    """El Short se pide solo al reproducir la vista previa, sin sonido, y nunca con «reducir movimiento»."""
    js = _texto("app.js")
    previa = js.split("function verPrevia(pieza) {")[1].split("\n}")[0]
    assert 'v.preload = "none"' in previa and "v.muted = " in previa
    assert "/media/${" in previa and "/short.mp4" in previa
    assert "calma.matches) return;" in previa
    assert "pararPrevia();" in js.split("function navegar() {")[1].split("\n}")[0]       # salir de la vista la detiene


def test_campos_de_la_plantilla_son_ajustes_reales():
    """Un campo con la clave mal escrita se guardaría en vacío: el servidor ignora claves desconocidas."""
    from fabrica_studio.config import AJUSTES_POR_DEFECTO
    bloque = _texto("app.js").split("const SECCIONES_PLANTILLA = [")[1].split("\n];")[0]
    claves = [c for c in re.findall(r'\["([a-z_]+)", "', bloque) if c not in ("auto", "clasico", "completo", "dividido")]   # opciones de «estilo»
    assert len(claves) > 20 and len(claves) == len(set(claves))
    assert set(claves) <= set(AJUSTES_POR_DEFECTO), set(claves) - set(AJUSTES_POR_DEFECTO)


def test_campos_de_proveedores_son_ajustes_reales():
    """Contexto, correcciones, tema y hashtags ya no están en Proveedores: son de cada perfil de creador."""
    from fabrica_studio.config import AJUSTES_POR_DEFECTO
    bloque = _texto("app.js").split('id="form-prov"')[1].split("</form>")[0]
    nombres = set(re.findall(r'name="([a-z_]+)"', bloque))
    assert not nombres & {"vocabulario", "correcciones", "tema", "hashtags_fijos"}
    assert nombres <= set(AJUSTES_POR_DEFECTO), nombres - set(AJUSTES_POR_DEFECTO)
    assert 'href="#perfiles"' in bloque


def test_editor_de_perfiles_usa_los_campos_y_opciones_del_servidor():
    """El formulario del perfil envía exactamente los campos que acepta el servidor, con sus opciones y largos."""
    from fabrica_studio.config import CAMPOS_PERFIL, OPCIONES
    js = _texto("app.js")
    bloque = js.split('<form id="form-perfil"')[1].split("</form>")[0]
    assert set(re.findall(r'name="([a-z_]+)"', bloque)) == set(CAMPOS_PERFIL)
    for campo, (_, largo) in CAMPOS_PERFIL.items():
        if largo:
            assert f'name="{campo}" rows="3" maxlength="{largo}"' in bloque or f'name="{campo}" maxlength="{largo}"' in bloque, campo
    temas = re.search(r"const TEMAS = \{([^}]*)\}", js).group(1)
    assert set(re.findall(r'"?([a-z0-9]*)"?: "', temas)) == set(OPCIONES["tema"])
    estilos = re.search(r"const ESTILO_CORTO = \{([^}]*)\}", js).group(1)
    assert set(re.findall(r'"?([a-z]*)"?: "', estilos)) == {""} | set(OPCIONES["estilo"])
    # La plantilla ya no edita el nombre ni la firma (son del perfil).
    plantilla = js.split("const SECCIONES_PLANTILLA = [")[1].split("\n];")[0]
    assert '["creador"' not in plantilla and '["firma"' not in plantilla
    html = _texto("index.html")
    assert 'id="boton-perfil"' in html and 'aria-haspopup="menu"' in html and 'href="#perfiles"' in html


def test_campos_de_publicacion_son_ajustes_reales():
    """Ritmo de subidas y recorte automático: claves reales y valores dentro de los límites del servidor."""
    from fabrica_studio.config import AJUSTES_POR_DEFECTO, LIMITES
    js = _texto("app.js")
    bloque = js.split('id="form-pub"')[1].split("</form>")[0]
    nombres = set(re.findall(r'name="([a-z_]+)"', bloque))
    assert {"subidas_max_dia", "subidas_intervalo_min", "recorte_auto_segundos"} <= nombres <= set(AJUSTES_POR_DEFECTO)
    for clave in ("subidas_max_dia", "subidas_intervalo_min"):
        lo, hi = LIMITES[clave]
        assert f'name="{clave}" min="{lo}" max="{hi}"' in bloque, clave
    lo, hi = LIMITES["recorte_auto_segundos"]
    assert all(lo <= x <= hi for x in (0, 60, 180)) and "[0, 60, 180, v.recorte_auto_segundos]" in bloque
    # El Resumen solo muestra la próxima subida si la API trae una hora futura (0 = se puede subir ya).
    assert "e.proxima_subida > 0 ? ` Próxima subida: ${horaSubida(e.proxima_subida)}.`" in js


def test_subidas_sin_limites_del_programa_y_limites_de_youtube_explicados():
    """«Subir ahora», «Subir todos», quitar de la cola, importar una carpeta y el aviso de los límites de YouTube."""
    js = _texto("app.js")
    assert "const LIMITES_YOUTUBE =" in js and "no controla" in js
    publicacion = js.split('id="form-pub"')[1].split("</form>")[0]
    assert "${LIMITES_YOUTUBE}" in publicacion and "= sin máximo" in publicacion and "= sin espera" in publicacion
    for accion in ("subir-ahora", "subir-todos", "elegir-subida", "cancelar-subida"):
        assert f'data-accion="{accion}"' in js, accion
    assert '"/api/subir-todos"' in js and "/subir-ahora`" in js and "/cancelar-subida`" in js
    assert "webkitdirectory" in js and "Sin límite" in js


def _funcion_js(nombre: str) -> str:
    """El código de una función de app.js (de «function nombre(» a la llave que la cierra en su columna)."""
    js = _texto("app.js")
    return f"function {nombre}(" + js.split(f"\nfunction {nombre}(", 1)[1].split("\n}\n", 1)[0] + "\n}"


def test_vista_previa_tiktok_igual_que_exportar():
    """La vista previa del panel arma el texto de TikTok igual que «Exportar» (exportar.texto_publicacion)."""
    import json
    import shutil
    import subprocess
    if not shutil.which("node"):
        pytest.skip("Node no está instalado")
    from fabrica_studio.exportar import texto_publicacion
    casos = [{"titulo": "Lo persiguen en GTA 6 🚓 #Shorts", "descripcion": "Huye de la policía.\n#Shorts #GTA6 #Policia"},
             {"titulo": "Mismo texto #shorts", "descripcion": "mismo texto\n#Shorts"},
             {"titulo": "Sin descripción #Shorts", "descripcion": ""},
             {"titulo": "Familia \U0001F468\u200D\U0001F469\u200D\U0001F467 #Shorts", "descripcion": "Una frase.\n#Shorts #A  #B"}]
    for plataforma in ("tiktok", "reels", "shorts"):
        codigo = (_funcion_js("textoPublicacion") + f"\nconst casos = {json.dumps(casos)};"
                  f"\nconsole.log(JSON.stringify(casos.map((c) => textoPublicacion(c, {json.dumps(plataforma)}))));")
        salida = subprocess.run(["node", "-e", codigo], capture_output=True, text=True, encoding="utf-8", check=True).stdout
        assert json.loads(salida) == [texto_publicacion(c, plataforma) for c in casos], plataforma


def test_regenerar_textos_en_lote_y_vista_previa_en_el_panel():
    js = _texto("app.js")
    for accion in ("regenerar-elegidos", "regenerar-todos", "quitar-seleccion", "cerrar-lote"):
        assert f'data-accion="{accion}"' in js, accion
    assert '"/api/textos/regenerar"' in js and '"/api/textos/lote"' in js
    assert 'id="sel-todos"' in js and "data-sel=" in js and "pintarLoteTextos()" in js
    assert "previasPublicacion(t)" in js and "Vista previa aproximada" in js
    # El contador del título cuenta como el servidor (caracteres, no unidades UTF-16) y cuenta emojis completos.
    assert "[...ft.titulo.value].length" in js and "Extended_Pictographic" in js


def test_el_panel_se_revalida_tras_actualizar(fabrica):
    """Sin esto el navegador seguía usando un app.js viejo después de un git pull."""
    pc = TestClient(crear_app(fabrica, iniciar_hilos=False), base_url="http://127.0.0.1:8765")
    for ruta in ("/", "/app.js", "/editor.js", "/estilo.css"):
        assert pc.get(ruta).headers["cache-control"] == "no-cache", ruta


def test_sondeo_activo_mientras_se_copia_a_la_carpeta(fabrica):
    """El panel usa el campo `copiando` de /api/estado (no compara el texto) y el servidor lo envía."""
    from fabrica_studio.pipeline import MENSAJE_COPIANDO
    js = _texto("app.js")
    assert "pendientes.some((p) => p.copiando)" in js and MENSAJE_COPIANDO.rstrip("…") not in js
    fabrica.carpeta_estado.update({"a.mp4": MENSAJE_COPIANDO, "b.mp4": "Este archivo ya se importó."})
    pc = TestClient(crear_app(fabrica, iniciar_hilos=False), base_url="http://127.0.0.1:8765", client=("127.0.0.1", 1))
    pendientes = {p["archivo"]: p["copiando"] for p in pc.get("/api/estado").json()["carpeta"]["pendientes"]}
    assert pendientes == {"a.mp4": True, "b.mp4": False}


def test_maqueta_del_resumen_pide_el_tamano_que_muestra():
    assert "/api/diseno/vista?ancho=352" in _texto("app.js")      # se ve a 176×313 (352 para pantallas 2×)


def test_exportar_desde_el_detalle_muestra_la_ruta_sin_la_carpeta_del_pc():
    js = _texto("app.js")
    assert "/exportar`" in js and 'data-accion="exportar"' in js
    assert "rutaCorta(r.video)" in js and "rutaCorta(r.texto_archivo)" in js and "r.avisos" in js
    assert "document.execCommand(\"copy\")" in js        # copiar también desde la tablet (http en la red de casa)
