"""«Clip de ejemplo» de la Plantilla: muestras en video que no tocan el clip y se guardan por huella."""
from fastapi.testclient import TestClient
from PIL import Image

from fabrica_studio import media, render
from fabrica_studio.server import crear_app


def _procesado(fabrica, clip):
    t = fabrica.importar_archivo(clip, "horizontal.mp4")
    fabrica._ejecutar(fabrica.db.trabajo(t["id"]))
    t = fabrica.db.trabajo(t["id"])
    assert t["estado"] == "renderizado", t["error"]
    return t


def _foto(fabrica, t):
    """Lo que define el estado del clip: su fila en la base y sus archivos (con el contenido de short.mp4)."""
    carpeta = fabrica.rutas.trabajo(t["id"])
    archivos = {str(f.relative_to(carpeta)): (f.stat().st_size, f.stat().st_mtime_ns) for f in carpeta.rglob("*") if f.is_file()}
    return fabrica.db.trabajo(t["id"]), archivos, media.sha256(carpeta / "short.mp4")


def _pedir(fabrica, valores=None, clip=None):
    """Como el panel, pero haciendo las muestras aquí mismo en vez de en el hilo de muestras."""
    fabrica.muestras.pedir(clip, valores or {})
    fabrica.muestras.atender(fabrica.muestras._pedido)
    return fabrica.muestras.ver()


def test_muestras_no_tocan_el_clip_y_solo_se_rehace_la_afectada(fabrica, clip, monkeypatch):
    t = _procesado(fabrica, clip)
    antes = _foto(fabrica, t)
    hechas = []
    original = render.renderizar

    def contar(*a, **k):
        enc = k["encuadre"]
        hechas.append("clasico" if enc is None else "dividido" if enc.get("dividido") else "completo")
        return original(*a, **k)

    monkeypatch.setattr(render, "renderizar", contar)
    e = _pedir(fabrica)                                   # sin clip: el último renderizado
    assert e["fase"] == "lista" and e["clip"]["id"] == t["id"], e
    assert e["auto"]["estilo"] in e["muestras"] and e["dividido"]["estilo"] in ("dividido", "completo")
    assert sorted(hechas) == sorted(e["muestras"]) and {"clasico", "completo"} <= set(hechas)
    for m in e["muestras"].values():
        assert m["estado"] == "lista" and m["url"].endswith(".mp4")
        p = media.sondear(fabrica.rutas.muestras / m["url"].rsplit("/", 1)[1])
        assert (p["ancho"], p["alto"], p["codec_video"]) == (540, 960, "h264") and not p["tiene_audio"]
        assert abs(p["duracion"] - 3.0) < 0.3                    # el clip dura 3 s: la muestra no pasa del final
    assert _foto(fabrica, t) == antes                          # ni short.mp4 ni los archivos ni el estado cambian
    assert not list(fabrica.rutas.muestras.glob("tmp-*"))

    # Los mismos ajustes: todo sale de la caché.
    hechas.clear()
    assert _pedir(fabrica)["muestras"] == e["muestras"] and hechas == []
    # Un ajuste de pantalla completa solo rehace esa muestra; uno del clásico, solo la del clásico.
    zoom = _pedir(fabrica, {"completo_zoom": 150})
    assert hechas == ["completo"] and zoom["muestras"]["clasico"] == e["muestras"]["clasico"]
    assert zoom["muestras"]["completo"]["url"] != e["muestras"]["completo"]["url"]
    hechas.clear()
    assert _pedir(fabrica, {"completo_zoom": 150, "video_alto_max": 700})["muestras"] == zoom["muestras"]
    assert hechas == []                     # con este clip (1280×720) manda el ancho: el alto máximo no cambia nada
    alto = _pedir(fabrica, {"completo_zoom": 150, "video_alto_max": 400})
    assert hechas == ["clasico"] and alto["muestras"]["completo"] == zoom["muestras"]["completo"]
    assert _foto(fabrica, t) == antes


def test_muestras_desde_el_servidor(fabrica, clip):
    pc = TestClient(crear_app(fabrica, iniciar_hilos=False), base_url="http://127.0.0.1:8765", client=("127.0.0.1", 1))
    r = pc.post("/api/diseno/muestras", json={"valores": {}})
    assert r.status_code == 400 and "Aún no hay clips" in r.json()["error"]
    t = _procesado(fabrica, clip)
    r = pc.post("/api/diseno/muestras", json={"valores": {"banner_tamano": 9999}})
    assert r.status_code == 400 and "entre" in r.json()["error"]          # se valida como al guardar
    r = pc.post("/api/diseno/muestras", json={"clip": t["id"], "valores": {"completo_zoom": "130", "youtube_canal_id": "x"}})
    assert r.status_code == 200 and r.json()["fase"] == "preparando"
    assert fabrica.muestras._pedido["ajustes"] == {"completo_zoom": 130}  # lo que no es de diseño no pasa
    fabrica.muestras.atender(fabrica.muestras._pedido)
    e = pc.get("/api/diseno/muestras?clips=1").json()
    assert e["fase"] == "lista" and [c["id"] for c in e["clips"]] == [t["id"]]
    video = pc.get(e["muestras"]["clasico"]["url"])
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4"
    assert pc.get("/api/diseno/muestras/..%2Ffabrica.db").status_code == 404
    assert pc.get("/api/diseno/muestras/" + "0" * 32 + ".mp4").status_code == 404


def test_logo_subido_sin_margenes(tmp_path):
    # Transparente alrededor: se quita lo transparente.
    img = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    img.paste((255, 0, 0, 255), (100, 50, 180, 90))
    assert render.recortar_margenes(img).size == (80, 40)
    # Sin transparencia, sobre un fondo liso (como un JPG con borde blanco): se quita el borde.
    img = Image.new("RGB", (300, 200), "white")
    img.paste((20, 120, 40), (40, 30, 260, 170))
    assert render.recortar_margenes(img).size == (220, 140)
    # Una foto (esquinas distintas) queda igual.
    img = Image.new("RGB", (300, 200), "white")
    img.paste((0, 0, 0), (0, 0, 10, 10))
    assert render.recortar_margenes(img).size == (300, 200)
