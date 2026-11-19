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
    c = _cliente([(429, {"error": {"message": "Quota exceeded"}}), (429, {"error": {"message": "Quota exceeded"}})])
    r = textos.generar("Encontré una palta enorme.", "Jongottii", "auto", "clave-falsa", cliente=c)
    assert r["origen"] == "local" and "cuota" in r["aviso"]
    assert set(textos._saturados) == {"gemini-9-flash", "gemini-9-flash-lite"}       # probó los dos de la lista


def test_gemini_saturado_o_sin_cuota_pasa_al_siguiente_modelo_y_lo_recuerda(monkeypatch):
    """Lo visto con la clave real: el modelo elegido respondía 503 «high demand» y luego 429 del plan gratuito."""
    monkeypatch.setattr(textos.time, "sleep", lambda s: None)
    textos._modelos_cache.update(t=0)
    bueno = '{"banner":"la persecución","titulo":"Lo persiguen en GTA 6 🚓","descripcion":"Huye.","hashtags":[],"es_gaming":true}'
    c = _cliente([(503, {"error": {"message": "high demand"}}), (503, {"error": {"message": "high demand"}}),
                  _respuesta(bueno)])
    r = textos.generar("me persigue la policía", "Cheta", "auto", "clave-falsa", cliente=c, tema="gta6")
    assert r["origen"] == "gemini:gemini-9-flash-lite" and "GTA 6" in r["titulo"]
    assert textos._saturados["gemini-9-flash"] > textos.time.time() + 60             # no se vuelve a pedir enseguida
    c = _cliente([_respuesta(bueno)])                                                  # el siguiente va directo al otro
    assert textos.generar("x", "C", "auto", "clave-falsa", cliente=c)["origen"] == "gemini:gemini-9-flash-lite"
    # Un modelo que la API lista pero ya no admite usuarios nuevos (404) no se vuelve a pedir en el día.
    textos._saturados.clear()
    c = _cliente([(404, {"error": {"message": "no longer available to new users"}}), _respuesta(bueno)])
    assert textos.generar("x", "C", "auto", "clave-falsa", cliente=c)["origen"] == "gemini:gemini-9-flash-lite"
    assert textos._saturados["gemini-9-flash"] > textos.time.time() + 20 * 3600
    # Un 429 con el tiempo que pide Gemini (RetryInfo o «retry in 6h46m7s»).
    detalle = {"error": {"message": "Quota exceeded", "details": [{"retryDelay": "3600s"}]}}
    assert textos._espera_pedida(textos.json.dumps(detalle), "") == 3600
    assert round(textos._espera_pedida("{}", "Please retry in 6h46m7.13s.")) == 6 * 3600 + 46 * 60 + 7
    # Con todos los modelos de la lista sin cuota, no se hace ningún pedido: se explica hasta cuándo.
    textos._saturados.update({"gemini-9-flash": textos.time.time() + 600, "gemini-9-flash-lite": textos.time.time() + 900})
    r = textos.generar("x", "C", "auto", "clave-falsa", cliente=_cliente([]))
    assert r["origen"] == "local" and "sin cuota o saturados hasta las" in r["aviso"]


def test_instrucciones_segun_el_modo():
    gta = textos.instrucciones_textos("gta6", "#GTA6 #GTAVI #Gaming", emojis=True)
    assert "SOLO 2 o 3" in gta and "#GTA6 #GTAVI #Gaming" in gta and "de 3 a 6" not in gta
    assert "UNA sola frase" in gta and "1 o 2 emojis" in gta and "No inventes misiones" in gta
    general = textos.instrucciones_textos()
    assert "de 3 a 6" in general and "GTA 6 (Grand Theft Auto VI)" not in general and "emojis" not in general


def test_los_secretos_no_llegan_a_los_mensajes():
    limpio = sin_secretos("fallo en https://x/y?key=AIzaSyA1234567890abcdefghijklmnop Bearer ya29.abc-def")
    assert "AIza" not in limpio and "ya29" not in limpio


def test_modo_gta6():
    p = {"banner": "lo persiguió la policía", "titulo": "Chetalonso escapa de la policía",
         "descripcion": "Escapa en una moto", "hashtags": ["#Persecucion"], "es_gaming": False}
    r = textos.normalizar(p, "me persigue la policía", tema="gta6", hashtags_fijos="#GTA6 #GTAVI #GTA #Gaming")
    assert r["titulo"].startswith("GTA 6 | ") and r["titulo"].endswith("#Shorts") and len(r["titulo"]) <= 80
    assert r["descripcion"].split("\n")[1] == "#Shorts #GTA6 #GTAVI #GTA #Gaming #Persecucion"
    assert r["es_gaming"] is True
    ya = textos.normalizar({**p, "titulo": "Su primera persecución en GTA 6"}, "", tema="gta6", hashtags_fijos="#GTA6")
    assert ya["titulo"] == "Su primera persecución en GTA 6 #Shorts"                    # no duplica
    sin = textos.normalizar({**p, "descripcion": "x #GTA6"}, "hablando de comida")
    assert "#GTA6" not in sin["descripcion"] and not sin["es_gaming"]                    # sin el modo, igual que antes


def test_modo_gta6_con_gemini_y_local(monkeypatch):
    textos._modelos_cache.update(t=0)
    vistas = []

    def falsa(clave, instr, contenido, esquema, *a, **k):
        vistas.append(instr)
        return {"banner": "huida", "titulo": "Se escapa", "descripcion": "Huye", "hashtags": [], "es_gaming": False}, "gemini-9"
    monkeypatch.setattr(textos, "pedir_json", falsa)
    r = textos.generar("me escapo de la policía", "Chetalonso", "auto", "clave", tema="gta6", hashtags_fijos="#GTA6")
    assert "GTA 6" in vistas[0] and "No inventes misiones" in vistas[0]
    assert r["titulo"].startswith("GTA 6 | ") and "#GTA6" in r["descripcion"]
    r = textos.generar("me escapo de la policía.", "Chetalonso", "local", "", tema="gta6", hashtags_fijos="#GTA6")
    assert "GTA 6" in r["titulo"] and r["es_gaming"]


def test_titulo_local_usa_frases_completas():
    tr = ("Aquí nada más se maneja con el joystick, creo que la gente a 5 era otra cosa. "
          "Como tuve la ciudad, ya lo lejo y me fui al mapa nuevo porque estaba lleno de policías.")
    t = textos.generar_local(tr, "rdjavi")["titulo"]
    cuerpo = t.split(": ", 1)[-1]
    assert len(t) <= 60 and cuerpo in tr.replace(".", "")                          # literal
    assert any(cuerpo == c.strip(" ,") for c in tr.replace(".", ",").split(","))   # cláusula completa, no cortada


def test_emojis_se_cuentan_completos_y_el_titulo_lleva_como_mucho_dos():
    familia, corredor = "\U0001F468\u200D\U0001F469\u200D\U0001F467", "\U0001F3C3\u200D♂\uFE0F"
    assert textos.contar_emojis(f"Huye 🚓 {familia} {corredor} ⭐ 👍🏽") == 5            # cada secuencia es uno
    t = textos.normalizar_titulo(f"😂 Se escapa {familia} de la policía 🚓 ⭐ en Vice City")
    assert textos.contar_emojis(t) == 2 and t.startswith("😂 Se escapa " + familia) and "⭐" not in t
    assert "  " not in t and t.endswith(" #Shorts")
    largo = textos.normalizar_titulo("🚓 " + "persecución eterna por toda la ciudad " * 4 + "😱")
    assert len(largo) <= 80 and largo.endswith(" #Shorts") and largo.startswith("🚓 ")
    # Un corte sin espacios no deja restos de un emoji (unión ZWJ, selector de variación o tono de piel).
    pegado = textos.normalizar_titulo("x" * 70 + corredor + "y" * 20)
    assert len(pegado) <= 80 and not any(c in pegado for c in "\u200D\uFE0F")


def test_descripcion_una_frase_y_hashtags_fijos_mas_tres_del_momento():
    p = {"banner": "persecución", "titulo": "La policía lo persigue en GTA 6 🚓",
         "descripcion": "Lo persigue la policía por toda la playa. Después choca. #Playa",
         "hashtags": ["#GTA6", "#Persecucion", "#Policia", "#Choque", "#Playa", "#Extra"], "es_gaming": True}
    r = textos.normalizar(p, "", tema="gta6", hashtags_fijos="#GTA6 #GTAVI #GTA #Gaming")
    linea, etiquetas = r["descripcion"].split("\n")
    assert linea == "Lo persigue la policía por toda la playa."                       # una sola frase
    assert etiquetas == "#Shorts #GTA6 #GTAVI #GTA #Gaming #Playa #Persecucion #Policia"   # fijos + 3 propios
    corta = textos.normalizar({**p, "descripcion": "¡Increíble! Se escapa de cinco patrullas sin chocar."}, "", tema="gta6")
    assert corta["descripcion"].split("\n")[0] == "¡Increíble! Se escapa de cinco patrullas sin chocar."
    muchos = ["#H" + str(i) for i in range(10)]
    r = textos.normalizar({**p, "hashtags": muchos}, "", tema="gta6", hashtags_fijos="#GTA6 #A #B #C #D #E")
    assert r["descripcion"].split("\n")[1].split()[-3:] == ["#Playa", "#H0", "#H1"]       # nunca más de 3 propios
    assert len(r["descripcion"].split("\n")[1].split()) == 1 + 6 + 3                     # #Shorts + 6 fijos + 3


def test_titulos_con_emojis(monkeypatch):
    vistas = []

    def falsa(clave, instr, contenido, esquema, *a, **k):
        vistas.append(instr)
        return {"banner": "huida 🚓 total", "titulo": "Escapa de la policía 🚓😱", "descripcion": "Huye",
                "hashtags": [], "es_gaming": True}, "gemini-9"
    monkeypatch.setattr(textos, "pedir_json", falsa)
    r = textos.generar("me escapo de la policía", "Chetalonso", "auto", "clave", tema="gta6",
                       hashtags_fijos="#GTA6", emojis=True)
    assert "1 o 2 emojis" in vistas[0]
    assert "🚓😱" in r["titulo"] and len(r["titulo"]) <= 80 and r["titulo"].endswith("#Shorts")
    assert r["banner"] == "HUIDA TOTAL"                                  # el banner nunca lleva emojis
    textos.generar("x", "C", "auto", "clave", emojis=False)
    assert "emojis" not in vistas[1]
