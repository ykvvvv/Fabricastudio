"""Perfiles de creador: migración, cada clip con su perfil, API y casos límite."""
import io
import json

import pytest
from fastapi.testclient import TestClient

from fabrica_studio.config import AJUSTES_POR_DEFECTO
from fabrica_studio.db import DB
from fabrica_studio.errores import ErrorEtapa
from fabrica_studio.pipeline import CONTEXTO_GTA6
from fabrica_studio.server import crear_app

PC = ("127.0.0.1", 50000)


def _png(color="red") -> bytes:
    from PIL import Image
    salida = io.BytesIO()
    Image.new("RGBA", (40, 20), color).save(salida, "PNG")
    return salida.getvalue()


def test_migracion_crea_el_perfil_inicial_con_los_valores_en_uso(tmp_path):
    db = DB(tmp_path / "fabrica.db")
    # Base de antes de los perfiles: ajustes guardados, uno por defecto que nunca se guardó y un clip sin perfil.
    db.guardar_ajustes({"creador": "rdjavi", "firma": "@rdjavi", "tema": "gta6", "estilo": "dividido"})
    viejo = db.crear_trabajo("viejo", "archivo")
    with db._lock:
        db._c.execute("DELETE FROM perfiles")
    db.guardar_ajustes({"perfil_activo": ""})

    db2 = DB(tmp_path / "fabrica.db")
    [p] = db2.perfiles()
    assert (p["nombre"], p["firma"], p["tema"]) == ("rdjavi", "@rdjavi", "gta6")
    assert p["contexto_transcripcion"] == AJUSTES_POR_DEFECTO["vocabulario"]      # también lo que nunca se guardó
    assert p["hashtags_fijos"] == AJUSTES_POR_DEFECTO["hashtags_fijos"]
    assert p["estilo"] == ""                    # sigue al estilo general (dividido): para nadie cambia el encuadre
    assert db2.ajustes()["perfil_activo"] == p["id"]
    assert db2.trabajo(viejo["id"])["datos"]["perfil"] == p["id"]
    assert len(DB(tmp_path / "fabrica.db").perfiles()) == 1                       # arrancar otra vez no crea otro


def test_dos_perfiles_dan_textos_y_render_distintos(fabrica, clip):
    ana = fabrica.db.editar_perfil(fabrica.db.perfil_activo()["id"], {"nombre": "Ana", "firma": "@ana", "tema": ""})
    beto = fabrica.db.crear_perfil({"nombre": "Beto", "firma": "@beto_gta", "tema": "gta6",
                                    "hashtags_fijos": "#GTA6 #BetoClips"})
    t = fabrica.importar_archivo(clip, "a.mp4")                     # con el activo: Ana
    assert t["datos"]["perfil"] == ana["id"]
    fabrica._ejecutar(t)
    carpeta = fabrica.rutas.trabajo(t["id"])
    t1, capa1 = fabrica.db.trabajo(t["id"]), (carpeta / "capa.png").read_bytes()
    assert t1["estado"] == "renderizado"
    assert "GTA 6" not in t1["textos"]["titulo"] and "#BetoClips" not in t1["textos"]["descripcion"]
    assert CONTEXTO_GTA6 not in fabrica.transcripciones["vocabulario"]

    r = fabrica.cambiar_perfil(t["id"], beto["id"])
    assert r["contexto_cambia"] is True                 # con GTA 6 Whisper recibiría también el vocabulario del juego
    assert r["trabajo"]["estado"] == "pendiente" and r["trabajo"]["textos"] == {}
    fabrica._ejecutar(fabrica.db.trabajo(t["id"]))
    t2 = fabrica.db.trabajo(t["id"])
    assert t2["estado"] == "renderizado"
    assert "GTA 6" in t2["textos"]["titulo"] and "#BetoClips" in t2["textos"]["descripcion"]
    assert t2["textos"]["es_gaming"] is True
    assert (carpeta / "capa.png").read_bytes() != capa1          # la firma dibujada es otra
    assert t2["datos"]["huella_render"] != t1["datos"]["huella_render"]
    assert fabrica.transcripciones["n"] == 1                       # no se volvió a transcribir


def test_cambiar_el_perfil_activo_no_altera_clips_ya_importados(fabrica, clip):
    ana = fabrica.db.editar_perfil(fabrica.db.perfil_activo()["id"],
                                   {"firma": "@ana", "tema": "", "contexto_transcripcion": "Stream de Ana."})
    beto = fabrica.db.crear_perfil({"nombre": "Beto", "firma": "@beto", "tema": "gta6",
                                    "contexto_transcripcion": "Stream de Beto."})
    t = fabrica.importar_archivo(clip, "a.mp4")
    fabrica.activar_perfil(beto["id"])
    fabrica._ejecutar(fabrica.db.trabajo(t["id"]))
    t = fabrica.db.trabajo(t["id"])
    assert t["datos"]["perfil"] == ana["id"]
    assert fabrica.transcripciones["vocabulario"] == "Stream de Ana."
    assert "GTA 6" not in t["textos"]["titulo"]
    assert fabrica.ajustes_de(t)["firma"] == "@ana"
    assert fabrica.db.perfil_activo()["id"] == beto["id"]          # los nuevos sí reciben a Beto


def test_perfil_al_importar_y_heredado_por_los_momentos(fabrica, clip):
    beto = fabrica.db.crear_perfil({"nombre": "Beto"})
    e = fabrica.importar_enlace("https://kick.com/beto/clips/clip_01ABC", perfil=beto["id"])
    assert e["datos"]["perfil"] == beto["id"]
    with pytest.raises(ErrorEtapa):
        fabrica.importar_archivo(clip, "a.mp4", perfil="no-existe")
    assert not fabrica.db.trabajos()[1:]                          # el rechazo no dejó un trabajo a medias
    largo = fabrica.importar_archivo(clip, "vod.mp4", modo="largo", perfil=beto["id"])
    (fabrica.rutas.trabajo(largo["id"]) / "propiedades.json").write_text(json.dumps({"duracion": 3.0}))
    hijo = fabrica.crear_clip(largo["id"], 0, 3)
    assert hijo["datos"]["perfil"] == beto["id"]


def test_eliminar_perfil_en_uso_pide_confirmar_y_conserva_una_copia(fabrica, clip):
    ana = fabrica.db.perfil_activo()
    beto = fabrica.db.crear_perfil({"nombre": "Beto", "firma": "@beto", "tema": "gta6"})
    t = fabrica.importar_archivo(clip, "a.mp4", perfil=beto["id"])
    with pytest.raises(ErrorEtapa) as e:
        fabrica.eliminar_perfil(ana["id"])
    assert "activo" in str(e.value)
    with pytest.raises(ErrorEtapa) as e:
        fabrica.eliminar_perfil(beto["id"])
    assert e.value.tipo == "confirmar" and "1 clips" in str(e.value)
    fabrica.eliminar_perfil(beto["id"], confirmar=True)
    assert fabrica.db.perfil(beto["id"]) is None
    t = fabrica.db.trabajo(t["id"])
    assert t["datos"]["perfil_copia"]["nombre"] == "Beto"
    assert fabrica.ajustes_de(t)["firma"] == "@beto" and fabrica.ajustes_de(t)["tema"] == "gta6"
    fabrica._ejecutar(t)
    assert "GTA 6" in fabrica.db.trabajo(t["id"])["textos"]["titulo"]


def test_validacion_de_perfiles(fabrica):
    db = fabrica.db
    for malo in ({"nombre": ""}, {"nombre": "x" * 41}, {"nombre": "Ok", "tema": "fortnite"},
                 {"nombre": "Ok", "estilo": "raro"}, {"nombre": "Ok", "contexto_transcripcion": "x" * 601}):
        with pytest.raises(ErrorEtapa):
            db.crear_perfil(malo)
    beto = db.crear_perfil({"nombre": "Beto", "estilo": "completo", "desconocido": "se ignora"})
    with pytest.raises(ErrorEtapa) as e:
        db.crear_perfil({"nombre": "beto"})                          # sin distinguir mayúsculas
    assert e.value.tipo == "duplicado"
    assert db.editar_perfil(beto["id"], {"nombre": "Beto"})["estilo"] == "completo"   # su propio nombre no choca
    assert "desconocido" not in db.perfil(beto["id"])


def test_api_de_perfiles(fabrica, clip):
    pc = TestClient(crear_app(fabrica, iniciar_hilos=False), base_url="http://127.0.0.1:8765", client=PC)
    r = pc.get("/api/perfiles").json()
    [inicial] = r["perfiles"]
    assert r["activo"] == inicial["id"] and inicial["en_uso"] == 0 and inicial["logo"] is False

    assert pc.post("/api/perfiles", json={"nombre": ""}).status_code == 400
    assert pc.post("/api/perfiles", json=["no", "es", "objeto"]).status_code == 400
    beto = pc.post("/api/perfiles", json={"nombre": "Beto", "firma": "@beto", "tema": "gta6"}).json()
    assert pc.post("/api/perfiles", json={"nombre": "BETO"}).status_code == 409
    assert pc.put(f"/api/perfiles/{beto['id']}", json={"firma": "@beto_clips"}).json()["firma"] == "@beto_clips"
    assert pc.put("/api/perfiles/nada", json={"firma": "x"}).status_code == 400

    # Logo propio: se sirve, lo usa el render y se copia al duplicar.
    assert pc.get(f"/api/perfiles/{beto['id']}/logo").status_code == 404
    assert pc.post(f"/api/perfiles/{beto['id']}/logo", files={"archivo": ("l.png", b"no es imagen", "image/png")}).status_code == 400
    assert pc.post(f"/api/perfiles/{beto['id']}/logo", files={"archivo": ("l.png", _png(), "image/png")}).status_code == 200
    assert pc.get(f"/api/perfiles/{beto['id']}/logo").headers["content-type"] == "image/png"
    assert fabrica.carpeta_logo(fabrica.db.perfil(beto["id"])) == fabrica.rutas.perfiles / beto["id"]
    assert fabrica.carpeta_logo(inicial) == fabrica.rutas.recursos          # sin logo propio: el general
    copia = pc.post(f"/api/perfiles/{beto['id']}/duplicar").json()
    assert copia["nombre"] == "Beto (copia)" and copia["tema"] == "gta6"
    assert pc.post(f"/api/perfiles/{beto['id']}/duplicar").json()["nombre"] == "Beto (copia 2)"
    assert (fabrica.rutas.perfiles / copia["id"] / "logo.png").exists()

    # Activar solo por su ruta: PUT /api/ajustes no lo cambia.
    pc.put("/api/ajustes", json={"perfil_activo": copia["id"]})
    assert pc.get("/api/estado").json()["perfil_activo"] == inicial["id"]
    assert pc.post(f"/api/perfiles/{beto['id']}/activar").status_code == 200
    estado = pc.get("/api/estado").json()
    assert estado["perfil_activo"] == beto["id"]
    assert {p["nombre"] for p in estado["perfiles"]} == {inicial["nombre"], "Beto", "Beto (copia)", "Beto (copia 2)"}
    assert next(p for p in estado["perfiles"] if p["id"] == beto["id"])["logo"] is True

    # Importar eligiendo perfil y cambiarlo después (con «volver a transcribir»).
    with open(clip, "rb") as f:
        t = pc.post("/api/importar/archivo", files={"archivo": ("a.mp4", f, "video/mp4")},
                    data={"publicar": "false", "perfil": inicial["id"]}).json()
    assert t["perfil"] == inicial["id"]
    fabrica._ejecutar(fabrica.db.trabajo(t["id"]))
    r = pc.put(f"/api/trabajos/{t['id']}/perfil", json={"perfil": beto["id"], "retranscribir": True})
    assert r.status_code == 200 and r.json()["trabajo"]["perfil"] == beto["id"]
    assert not (fabrica.rutas.trabajo(t["id"]) / "transcripcion.json").exists()
    fabrica._ejecutar(fabrica.db.trabajo(t["id"]))
    assert fabrica.transcripciones["n"] == 2 and CONTEXTO_GTA6 in fabrica.transcripciones["vocabulario"]
    assert pc.put(f"/api/trabajos/{t['id']}/perfil", json={"perfil": "nada"}).status_code == 400

    # Eliminar: el activo no; uno en uso pide confirmar (409); confirmado, el clip guarda la copia.
    assert pc.delete(f"/api/perfiles/{beto['id']}").status_code == 400
    pc.post(f"/api/perfiles/{inicial['id']}/activar")
    r = pc.delete(f"/api/perfiles/{beto['id']}")
    assert r.status_code == 409 and r.json()["tipo"] == "confirmar"
    assert pc.delete(f"/api/perfiles/{beto['id']}?confirmar=true").status_code == 200
    assert not (fabrica.rutas.perfiles / beto["id"]).exists()
    assert pc.get(f"/api/trabajos/{t['id']}").json()["perfil_copia"] == "Beto"
    assert pc.delete(f"/api/perfiles/{copia['id']}").status_code == 200     # sin clips: no hace falta confirmar


def test_vista_de_la_plantilla_usa_el_perfil_activo(fabrica):
    pc = TestClient(crear_app(fabrica, iniciar_hilos=False), base_url="http://127.0.0.1:8765", client=PC)
    inicial = fabrica.db.perfil_activo()
    fabrica.db.editar_perfil(inicial["id"], {"firma": "@a"})
    beto = fabrica.db.crear_perfil({"nombre": "Beto", "firma": "@una_firma_mucho_mas_larga"})
    firma = lambda: next(e for e in pc.get("/api/diseno/disposicion").json()["elementos"] if e["id"] == "firma")["caja"]["w"]
    corta = firma()
    fabrica.activar_perfil(beto["id"])
    assert firma() > corta
    assert pc.get("/api/diseno/vista").status_code == 200
