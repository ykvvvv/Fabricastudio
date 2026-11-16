import pytest

from fabrica_studio import media, reencuadre


def _analisis(posiciones, ancho=1920, alto=1080, tam=200):
    """Una muestra cada 0,2 s con un rostro centrado en cada x (None = sin rostro)."""
    return {"ancho": ancho, "alto": alto, "fps": 5,
            "muestras": [{"t": round(i * 0.2, 3), "rostros": [] if x is None else [[x, 500, tam, tam, 0.9]]}
                         for i, x in enumerate(posiciones)]}


def test_ventana_9_16():
    assert reencuadre.ventana(1920, 1080) == (606, 1080)
    assert reencuadre.ventana(1920, 1080, 1.5) == (404, 720)
    assert reencuadre.ventana(720, 1280) == (720, 1280)              # ya es vertical: sin recorte lateral
    w, h = reencuadre.ventana(1080, 1080)
    assert (w, h) == (606, 1080)


def test_sigue_al_rostro_y_no_se_sale():
    puntos = reencuadre.trayectoria(_analisis([300] * 10 + [1600] * 10), 606)
    assert abs(puntos[0][1] - (300 - 303)) <= 2 or puntos[0][1] == 0     # empieza sobre el rostro (limitado a 0)
    assert puntos[-1][1] == 1600 - 303                                    # termina sobre el rostro nuevo
    assert all(0 <= x <= 1920 - 606 for _, x in puntos)


def test_salto_grande_es_corte_y_no_paneo():
    puntos = reencuadre.trayectoria(_analisis([400] * 10 + [1500] * 10), 606)
    xs = [x for _, x in puntos]
    assert len(set(xs)) == 2                                              # solo dos posiciones: corte limpio


def test_temblor_pequeno_no_mueve_la_camara():
    import random
    random.seed(1)
    puntos = reencuadre.trayectoria(_analisis([960 + random.randint(-20, 20) for _ in range(40)]), 606)
    assert len(puntos) == 1


def test_sin_rostros_queda_centrado():
    puntos = reencuadre.trayectoria(_analisis([None] * 10), 606)
    assert puntos == [(0.0, round((1920 - 606) / 2))]


def test_huecos_mantienen_la_ultima_posicion():
    puntos = reencuadre.trayectoria(_analisis([1500] * 5 + [None] * 10 + [1500] * 5), 606)
    assert {x for _, x in puntos} == {1500 - 303}


def test_dos_personas_que_caben_se_encuadran_juntas():
    a = {"ancho": 1920, "alto": 1080, "fps": 5,
         "muestras": [{"t": 0.0, "rostros": [[800, 500, 150, 150, 0.9], [1100, 500, 150, 150, 0.9]]}]}
    (_, x), = reencuadre.trayectoria(a, 606)
    assert abs((x + 303) - 950) <= 2                                      # centro del grupo


def test_ordenes_sendcmd():
    texto = reencuadre.comandos_sendcmd([(0.0, 100), (0.4, 160), (5.0, 900)])
    lineas = texto.strip().splitlines()
    assert lineas[0] == "0.000 crop@encuadre x 100;"
    assert all(l.endswith(";") and " crop@encuadre x " in l for l in lineas)
    assert any(l.startswith("0.4") for l in lineas) and lineas[-1] == "5.000 crop@encuadre x 900;"
    assert all(int(l.split()[-1].rstrip(";")) % 2 == 0 for l in lineas)  # coordenadas pares
    assert len(lineas) > 3                                                # interpola el paneo corto


@pytest.mark.skipif(not reencuadre.disponible()[0], reason="OpenCV/YuNet no disponible")
def test_analizar_video_sin_rostros(tmp_path):
    import subprocess
    ruta = tmp_path / "barras.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=15:d=2",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(ruta)], check=True)
    r = reencuadre.analizar(ruta, media.sondear(ruta))
    assert len(r["muestras"]) == 10 and r["ancho"] == 640 and "aviso" in r


def test_estilo_completo_de_punta_a_punta(fabrica, clip):
    fabrica.db.guardar_ajustes({"estilo": "completo"})
    t = fabrica.importar_archivo(clip, "a.mp4")
    fabrica._ejecutar(t)
    t = fabrica.db.trabajo(t["id"])
    assert t["estado"] == "renderizado", t["error"]
    salida = media.sondear(fabrica.rutas.trabajo(t["id"]) / "short.mp4")
    assert (salida["ancho"], salida["alto"]) == (1080, 1920)
    assert "pantalla completa" in t["etapas"]["render"]["detalle"]
    assert t["datos"]["disposicion"]["video"] == {"x": 0, "y": 0, "w": 1080, "h": 1920}
    # Cambiar a clásico solo en este trabajo: se renderiza de nuevo sin transcribir otra vez.
    t = fabrica.cambiar_estilo(t["id"], "clasico")
    fabrica._ejecutar(t)
    t = fabrica.db.trabajo(t["id"])
    assert "clásico" in t["etapas"]["render"]["detalle"] and fabrica.transcripciones["n"] == 1
    with pytest.raises(Exception):
        fabrica.cambiar_estilo(t["id"], "inventado")
