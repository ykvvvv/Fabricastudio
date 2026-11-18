from fabrica_studio import subtitulos
from fabrica_studio.config import AJUSTES_POR_DEFECTO


def _p(*textos):
    return [{"inicio": i * 0.5, "fin": i * 0.5 + 0.4, "texto": t} for i, t in enumerate(textos)]


def test_leer_correcciones():
    r = subtitulos.leer_correcciones("Jongoti => Jongottii\npoh = po\n\nlinea sin flecha\n weon, => weón")
    assert r == {"jongoti": "Jongottii", "poh": "po", "weon": "weón"}


def test_corregir_conserva_puntuacion_mayuscula_y_cantidad():
    reglas = {"jongoti": "Jongottii", "poh": "po", "weon": "weón"}
    r = subtitulos.corregir_palabras(_p("¡Weon!", "ya", "poh,", "Jongoti:", "nada"), reglas)
    assert [p["texto"] for p in r] == ["¡Weón!", "ya", "po,", "Jongottii:", "nada"]
    assert [p["inicio"] for p in r] == [p["inicio"] for p in _p(*"abcde")]      # tiempos intactos
    assert subtitulos.corregir_palabras(_p("hola"), {}) == _p("hola")


def test_contexto_por_defecto_es_una_frase_con_jerga_y_creador():
    v = AJUSTES_POR_DEFECTO["vocabulario"]
    for palabra in ("Jongottii", "Cachai", "weón", "altiro", "fome"):
        assert palabra in v
    assert v.count(".") >= 2 and "¿" in v                 # frase con puntuación, no una lista


def test_el_vocabulario_llega_a_whisper_y_las_correcciones_a_subtitulos(fabrica, clip):
    fabrica.db.guardar_ajustes({"vocabulario": "cachai, altiro", "correcciones": "chat => CHAT"})
    t = fabrica.importar_archivo(clip, "a.mp4")
    fabrica._ejecutar(t)
    assert fabrica.transcripciones["vocabulario"] == "cachai, altiro"
    texto = " ".join(b["texto"] for b in fabrica.detalle(t["id"])["bloques"])
    assert "CHAT," in texto and "chat," not in texto
    assert "chat," in fabrica.detalle(t["id"])["transcripcion"]       # la transcripción guardada sigue literal


def test_retranscribir(fabrica, clip):
    import pytest
    from fabrica_studio.errores import ErrorEtapa
    t = fabrica.importar_archivo(clip, "a.mp4")
    fabrica._ejecutar(t)
    fabrica.retranscribir(t["id"])
    fabrica._ejecutar(fabrica.db.trabajo(t["id"]))
    assert fabrica.transcripciones["n"] == 2 and fabrica.db.trabajo(t["id"])["estado"] == "renderizado"
    (fabrica.rutas.trabajo(t["id"]) / "edicion.json").write_text("{}")
    with pytest.raises(ErrorEtapa):
        fabrica.retranscribir(t["id"])


def test_modo_gta6_suma_vocabulario_del_juego_a_whisper(fabrica, clip):
    from fabrica_studio.pipeline import CONTEXTO_GTA6, contexto_transcripcion
    assert contexto_transcripcion({"vocabulario": "Hola.", "tema": ""}) == "Hola."
    assert contexto_transcripcion({"vocabulario": "Hola.", "tema": "gta6"}) == f"Hola. {CONTEXTO_GTA6}"
    fabrica.db.guardar_ajustes({"tema": "gta6"})
    fabrica._ejecutar(fabrica.importar_archivo(clip, "a.mp4"))
    assert "Vice City" in fabrica.transcripciones["vocabulario"] and "GTA 5" in fabrica.transcripciones["vocabulario"]
