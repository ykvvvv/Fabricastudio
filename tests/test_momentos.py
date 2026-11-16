import httpx
import pytest

from fabrica_studio import media, momentos, textos, transcribe
from fabrica_studio.errores import ErrorEtapa

# 40 frases de 4 s: un "video largo" de 160 s. Un tramo tiene más énfasis que el resto.
SEGMENTOS = [{"inicio": i * 4.0, "fin": i * 4.0 + 3.6,
              "texto": ("¡No puede ser, hermano! ¿Viste eso? ¡Mira, mira!" if 20 <= i < 28 else f"Frase tranquila número {i}.")}
             for i in range(40)]


def test_local_propone_tramos_validos_sin_solaparse():
    p = momentos.proponer_local(SEGMENTOS, cantidad=3)
    assert 1 <= len(p) <= 3
    assert all(momentos.DURACION_MIN <= x["fin"] - x["inicio"] <= momentos.DURACION_MAX for x in p)
    assert all(a["fin"] <= b["inicio"] for a, b in zip(p, p[1:]))
    mejor = max(p, key=lambda x: x["puntaje"])
    assert mejor["inicio"] < 112 and mejor["fin"] > 80          # cubre el tramo con énfasis
    assert "No puede ser" in mejor["texto"]                      # el texto es literal


def test_sin_voz_no_hay_propuestas():
    r = momentos.proponer([], "auto", "")
    assert r["propuestas"] == [] and r["origen"] == "local"


def _cliente(codigo, texto):
    def manejar(req):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"models": [{"name": "models/gemini-9-flash",
                                                         "supportedGenerationMethods": ["generateContent"]}]})
        if codigo != 200:
            return httpx.Response(codigo, json={"error": {"message": "fallo"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": texto}]}}]})
    return httpx.Client(transport=httpx.MockTransport(manejar))


def test_gemini_valida_indices_duracion_y_solapes():
    textos._modelos_cache.update(t=0)
    respuesta = ('[{"primer_segmento":20,"ultimo_segmento":27,"motivo":"Reacción  eufórica"},'
                 '{"primer_segmento":25,"ultimo_segmento":30,"motivo":"se solapa"},'
                 '{"primer_segmento":0,"ultimo_segmento":39,"motivo":"demasiado largo"},'
                 '{"primer_segmento":90,"ultimo_segmento":95,"motivo":"fuera de rango"},'
                 '{"primer_segmento":"x","ultimo_segmento":3,"motivo":"mal formado"}]')
    r = momentos.proponer(SEGMENTOS, "auto", "clave", cliente=_cliente(200, respuesta))
    assert r["origen"] == "gemini:gemini-9-flash"
    p = r["propuestas"]
    assert [(x["inicio"], x["fin"]) for x in p] == [(0.0, 71.6), (80.0, 111.6)]     # el largo se acortó a <= 75 s
    assert p[1]["motivo"] == "Reacción eufórica" and p[1]["id"] == 2


def test_gemini_falla_y_se_usa_la_heuristica_con_aviso(monkeypatch):
    textos._modelos_cache.update(t=0)
    r = momentos.proponer(SEGMENTOS, "auto", "clave", cliente=_cliente(429, ""))
    assert r["origen"] == "local" and "cuota" in r["aviso"] and r["propuestas"]


def test_recorte_de_transcripcion_desplaza_tiempos():
    tr = {"idioma": "es", "motor": "x", "segmentos": [],
          "palabras": [{"inicio": t, "fin": t + 0.4, "texto": f"p{t}"} for t in range(0, 20)]}
    r = momentos.recortar_transcripcion(tr, 5.0, 10.0)
    assert [p["texto"] for p in r["palabras"]] == ["p5", "p6", "p7", "p8", "p9"]
    assert r["palabras"][0]["inicio"] == 0.0 and r["palabras"][-1]["fin"] <= 5.0


@pytest.fixture
def largo(fabrica, tmp_path, monkeypatch):
    """Video de 24 s importado como «largo» y ya analizado."""
    import subprocess
    ruta = tmp_path / "largo.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=15:d=24",
                    "-f", "lavfi", "-i", "sine=f=300:d=24", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(ruta)], check=True)
    segs = [{"inicio": i * 2.0, "fin": i * 2.0 + 1.8, "texto": f"Frase número {i}."} for i in range(12)]
    palabras = [{"inicio": s["inicio"] + k * 0.5, "fin": s["inicio"] + k * 0.5 + 0.4, "texto": w}
                for s in segs for k, w in enumerate(s["texto"].split())]
    monkeypatch.setattr(transcribe, "transcribir", lambda *a: (fabrica.transcripciones.__setitem__("n", fabrica.transcripciones["n"] + 1),
                        {"idioma": "es", "motor": "prueba", "texto": " ".join(s["texto"] for s in segs),
                         "segmentos": segs, "palabras": palabras})[1])
    t = fabrica.importar_archivo(ruta, "largo.mp4", modo="largo")
    fabrica._ejecutar(t)
    return fabrica.db.trabajo(t["id"])


def test_video_largo_propone_y_no_renderiza(fabrica, largo):
    assert largo["estado"] == "propuestas" and largo["modo"] == "largo", largo["error"]
    d = fabrica.detalle(largo["id"])
    assert d["momentos"]["propuestas"] and d["entrada"] == "entrada.mp4"
    assert not (fabrica.rutas.trabajo(largo["id"]) / "short.mp4").exists()
    assert fabrica.db.siguiente() is None                       # queda esperando la decisión del usuario
    with pytest.raises(ErrorEtapa):
        fabrica.renderizar_de_nuevo(largo["id"])


def test_crear_clip_recorta_y_reutiliza_la_transcripcion(fabrica, largo):
    hijo = fabrica.crear_clip(largo["id"], 4.0, 12.0)
    with pytest.raises(ErrorEtapa) as e:
        fabrica.crear_clip(largo["id"], 4.0, 12.0)
    assert e.value.tipo == "duplicado"
    for malo in [(10, 11), (-1, 5), (0, 400), ("a", 3)]:
        with pytest.raises(ErrorEtapa):
            fabrica.crear_clip(largo["id"], *malo)
    fabrica._ejecutar(fabrica.db.siguiente())
    hijo = fabrica.db.trabajo(hijo["id"])
    assert hijo["estado"] == "renderizado", hijo["error"]
    carpeta = fabrica.rutas.trabajo(hijo["id"])
    assert abs(media.sondear(carpeta / "entrada.mp4")["duracion"] - 8.0) < 0.3
    salida = media.sondear(carpeta / "short.mp4")
    assert (salida["ancho"], salida["alto"]) == (1080, 1920) and abs(salida["duracion"] - 8.0) < 0.3
    assert fabrica.transcripciones["n"] == 1                    # solo se transcribió el video largo
    bloques = fabrica.detalle(hijo["id"])["bloques"]
    assert bloques and bloques[0]["texto"].startswith("Frase número 2") and bloques[-1]["fin"] <= 8.3
    assert fabrica.detalle(largo["id"])["clips"][0]["id"] == hijo["id"]


def test_clip_de_un_largo_eliminado_falla_con_explicacion(fabrica, largo):
    hijo = fabrica.crear_clip(largo["id"], 2.0, 10.0)
    fabrica.eliminar(largo["id"])
    fabrica._ejecutar(fabrica.db.siguiente())
    hijo = fabrica.db.trabajo(hijo["id"])
    assert hijo["estado"] == "error" and "ya no está disponible" in hijo["error"]
