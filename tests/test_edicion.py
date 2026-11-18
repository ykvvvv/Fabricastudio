import subprocess

import pytest
from fastapi.testclient import TestClient

from fabrica_studio import edicion, media
from fabrica_studio.errores import ErrorEtapa
from fabrica_studio.server import crear_app


def test_validar_tramos():
    assert edicion.validar_tramos([[5, 9], [0, 4.5]], 20) == [[0.0, 4.5], [5.0, 9.0]]          # ordena
    assert edicion.validar_tramos([[0, 5], [4.99, 8]], 20) == [[0.0, 8.0]]                      # une solapes
    assert edicion.validar_tramos([[-3, 4], [18, 40]], 20) == [[0.0, 4.0], [18.0, 20.0]]       # recorta a la duración
    assert edicion.validar_tramos([[1, 1.1], [2, 6]], 20) == [[2.0, 6.0]]                       # descarta tramos mínimos
    assert edicion.validar_tramos([], 20) == []
    with pytest.raises(ErrorEtapa):
        edicion.validar_tramos([[0, 2]], 20)                                                     # menos de 3 s
    with pytest.raises(ErrorEtapa):
        edicion.validar_tramos([[0, 200]], 400)                                                  # más de 180 s
    with pytest.raises(ErrorEtapa):
        edicion.validar_tramos([["a", 2]], 20)


def test_remapear_transcripcion():
    tramos = [[0.0, 2.0], [5.0, 8.0]]
    assert edicion.nuevo_tiempo(1.0, tramos) == 1.0
    assert edicion.nuevo_tiempo(6.0, tramos) == 3.0          # 2 s del primer tramo + 1 s del segundo
    assert edicion.nuevo_tiempo(3.0, tramos) is None          # parte cortada
    tr = {"motor": "x", "palabras": [{"inicio": 0.5, "fin": 0.9, "texto": "hola"},
                                     {"inicio": 3.0, "fin": 3.4, "texto": "cortada"},
                                     {"inicio": 5.5, "fin": 6.0, "texto": "chat"}], "segmentos": []}
    r = edicion.remapear_transcripcion(tr, tramos)
    assert [p["texto"] for p in r["palabras"]] == ["hola", "chat"] and r["texto"] == "hola chat"
    assert r["palabras"][1]["inicio"] == 2.5 and r["palabras"][1]["fin"] == 3.0


@pytest.fixture
def clip8(tmp_path):
    ruta = tmp_path / "ocho.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=8",
                    "-f", "lavfi", "-i", "sine=f=440:d=8", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(ruta)], check=True)
    return ruta


def test_editar_tiempos_de_punta_a_punta(fabrica, clip8):
    t = fabrica.importar_archivo(clip8, "ocho.mp4")
    fabrica._ejecutar(t)
    carpeta = fabrica.rutas.trabajo(t["id"])
    with pytest.raises(ErrorEtapa):                                  # no se edita mientras se procesa
        fabrica.db.actualizar(t["id"], estado="procesando"); fabrica.editar_tiempos(t["id"], [[0, 4]])
    fabrica.db.actualizar(t["id"], estado="renderizado")
    t = fabrica.editar_tiempos(t["id"], [[0.0, 2.0], [4.0, 7.0]])   # quitar 2–4 s y el final
    assert t["estado"] == "pendiente"
    fabrica._ejecutar(t)
    t = fabrica.db.trabajo(t["id"])
    assert t["estado"] == "renderizado", t["error"]
    assert t["etapas"]["importar"]["estado"] == "hecho"              # no queda «en curso» tras aplicar la edición
    assert abs(media.sondear(carpeta / "editado.mp4")["duracion"] - 5.0) < 0.2
    assert abs(media.sondear(carpeta / "short.mp4")["duracion"] - 5.0) < 0.2
    assert (carpeta / "entrada.mp4").exists() and (carpeta / "transcripcion_original.json").exists()
    assert fabrica.transcripciones["n"] == 1                         # no se volvió a transcribir
    linea = fabrica.linea_de_tiempo(t["id"])
    assert linea["editado"] and linea["tramos"] == [[0.0, 2.0], [4.0, 7.0]] and abs(linea["duracion"] - 8) < 0.2
    assert len(linea["picos"]) > 50 and max(linea["picos"]) == 1.0
    # Volver al clip completo deshace la edición.
    t = fabrica.editar_tiempos(t["id"], [])
    fabrica._ejecutar(t)
    assert not (carpeta / "edicion.json").exists() and not (carpeta / "transcripcion_original.json").exists()
    assert abs(media.sondear(carpeta / "short.mp4")["duracion"] - 8.0) < 0.2


def test_api_de_edicion(fabrica, clip8):
    pc = TestClient(crear_app(fabrica, iniciar_hilos=False), base_url="http://127.0.0.1:8765", client=("127.0.0.1", 1))
    t = fabrica.importar_archivo(clip8, "ocho.mp4")
    fabrica._ejecutar(t)
    linea = pc.get(f"/api/trabajos/{t['id']}/linea").json()
    assert linea["tramos"] == [[0.0, linea["duracion"]]] and not linea["editado"]
    assert abs(pc.get(f"/api/trabajos/{t['id']}").json()["duracion"] - 8) < 0.2
    assert pc.get(f"/api/trabajos/{t['id']}").json()["editado"] is False
    assert pc.put(f"/api/trabajos/{t['id']}/edicion", json={"tramos": [[0, 1]]}).status_code == 400
    r = pc.put(f"/api/trabajos/{t['id']}/edicion", json={"tramos": [[1, 6]]})
    assert r.status_code == 200 and r.json()["estado"] == "pendiente"
    assert pc.get(f"/api/trabajos/{t['id']}").json()["editado"]          # el panel deshabilita «Volver a transcribir»
    fabrica._ejecutar(fabrica.db.trabajo(t["id"]))
    assert abs(pc.get(f"/api/trabajos/{t['id']}").json()["duracion"] - 5) < 0.2     # la ficha no muestra la del original


def test_clip_demasiado_largo_se_recorta_solo(fabrica, clip8):
    # El mínimo validado es 0; para la prueba se fuerza un límite de 5 s directamente en la base.
    fabrica.db._c.execute("INSERT INTO ajustes (clave, valor) VALUES ('recorte_auto_segundos', '5') "
                          "ON CONFLICT(clave) DO UPDATE SET valor='5'")
    t = fabrica.importar_archivo(clip8, "ocho.mp4")
    fabrica._ejecutar(t)
    t = fabrica.db.trabajo(t["id"])
    assert t["estado"] == "renderizado", t["error"]
    assert t["datos"]["recorte_auto"]["fin"] - t["datos"]["recorte_auto"]["inicio"] <= 5.01
    assert abs(media.sondear(fabrica.rutas.trabajo(t["id"]) / "short.mp4")["duracion"] - 5.0) < 0.3
    assert any("se conservó el tramo" in a for a in t["avisos"])
    assert fabrica.transcripciones["n"] == 1                        # no se volvió a transcribir
    # Deshacer desde el editor no vuelve a recortar.
    t = fabrica.editar_tiempos(t["id"], [])
    fabrica._ejecutar(t)
    assert abs(media.sondear(fabrica.rutas.trabajo(t["id"]) / "short.mp4")["duracion"] - 8.0) < 0.3
