import httpx
import pytest

from fabrica_studio import textos
from fabrica_studio.errores import ErrorEtapa, sin_secretos


def test_banner_maximo_seis_palabras_y_mayusculas():
    assert textos.normalizar_banner('  "no lo van a creer lo que pasó hoy"  ') == "NO LO VAN A CREER LO"


def test_titulo_siempre_cabe_en_80_con_shorts():
    t = textos.normalizar_titulo("Jongottii reacciona a algo increíble " * 5 + "#shorts")
    assert len(t) <= 80 and t.endswith(" #Shorts") and t.count("#Shorts") == 1


def test_descripcion_en_una_linea_se_reorganiza():
    d = textos.normalizar_descripcion("Jongottii encuentra una palta #Kick gigante #shorts #kick")
    linea, etiquetas = d.split("\n")
    assert linea == "Jongottii encuentra una palta gigante"
    assert etiquetas == "#Shorts #Kick"


def test_descripcion_con_saltos_y_espacios():
    d = textos.normalizar_descripcion("  Un momento\n\n divertido  \n#Uno\n#Dos ")
    assert d == "Un momento divertido\n#Shorts #Uno #Dos"


def test_gta6_solo_si_la_transcripcion_lo_menciona():
    p = {"banner": "mira esto", "titulo": "Mira esto", "descripcion": "Algo pasa #GTA6 #Kick"}
    assert "#GTA6" not in textos.normalizar(p, "hablando de comida")["descripcion"]
    assert "#GTA6" in textos.normalizar(p, "el trailer de GTA 6 salió")["descripcion"]
    assert "#GTA6" in textos.normalizar(p, "", manual=True)["descripcion"]


def test_propuesta_sin_titulo_falla_con_mensaje():
    with pytest.raises(ErrorEtapa):
        textos.normalizar({"banner": "hola", "titulo": "  ", "descripcion": "x"})


def test_local_no_inventa_usa_frases_de_la_transcripcion():
    tr = "Oye chat, no lo van a creer. Encontré la paltita más grande de Chile."
    t = textos.normalizar(textos.generar_local(tr, "Jongottii"), tr)
    assert all(p.lower().strip(".,") in tr.lower() for p in t["banner"].split())
    assert len(t["banner"].split()) <= 6 and len(t["titulo"]) <= 80


def _cliente(respuestas):
    """Cliente HTTP simulado: lista de modelos + respuestas sucesivas de generateContent."""
    cola = list(respuestas)

    def manejar(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"models": [
                {"name": "models/modelo-embedding", "supportedGenerationMethods": ["embedContent"]},
                {"name": "models/gemini-9-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-9-flash-lite", "supportedGenerationMethods": ["generateContent"]}]})
        codigo, cuerpo = cola.pop(0)
        return httpx.Response(codigo, json=cuerpo)
    return httpx.Client(transport=httpx.MockTransport(manejar))


def _respuesta(texto):
    return 200, {"candidates": [{"content": {"parts": [{"text": texto}]}}]}


def test_gemini_elige_modelo_listado_y_tolera_formato(monkeypatch):
    monkeypatch.setattr(textos.time, "sleep", lambda s: None)
    textos._modelos_cache.update(t=0)
    c = _cliente([(503, {"error": {"message": "sobrecarga"}}),
                  _respuesta('```json\n{"banner":"la palta gigante","titulo":"La palta más grande",'
                             '"descripcion":"Encuentra una palta. #Palta","hashtags":["Chile"],"es_gaming":false}\n```')])
    r = textos.generar("encontré una palta", "Jongottii", "auto", "clave-falsa", cliente=c)
    assert r["origen"] == "gemini:gemini-9-flash" and r["banner"] == "LA PALTA GIGANTE"
    assert r["descripcion"] == "Encuentra una palta.\n#Shorts #Palta #Chile"


def test_gemini_sin_cuota_cae_al_borrador_local_y_explica(monkeypatch):
    textos._modelos_cache.update(t=0)
    c = _cliente([(429, {"error": {"message": "Quota exceeded"}})])
    r = textos.generar("Encontré una palta enorme.", "Jongottii", "auto", "clave-falsa", cliente=c)
    assert r["origen"] == "local" and "cuota" in r["aviso"]


def test_los_secretos_no_llegan_a_los_mensajes():
    limpio = sin_secretos("fallo en https://x/y?key=AIzaSyA1234567890abcdefghijklmnop Bearer ya29.abc-def")
    assert "AIza" not in limpio and "ya29" not in limpio
