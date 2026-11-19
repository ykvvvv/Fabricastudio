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


def _stream(n=30, camara=True, contenido=True):
    """Muestras de un stream 1920×1080: facecam fija arriba a la izquierda y una persona que se mueve."""
    muestras = []
    for i in range(n):
        rostros = []
        if camara:
            rostros.append([150 + (i % 3), 160, 110, 120, 0.95])          # casi inmóvil, pequeña, en la esquina
        if contenido and i % 4:
            rostros.append([900 + i * 15, 600, 200, 220, 0.9])            # se desplaza por el contenido
        muestras.append({"t": round(i * 0.2, 3), "rostros": rostros})
    return {"ancho": 1920, "alto": 1080, "fps": 5, "muestras": muestras}


def test_detecta_la_camara_del_streamer():
    c = reencuadre.detectar_camara(_stream())
    assert c and abs(c["cx"] - 151) < 5 and c["presencia"] == 1.0


def test_irl_de_una_camara_no_es_vista_dividida():
    irl = {"ancho": 1920, "alto": 1080, "fps": 5,
           "muestras": [{"t": i * 0.2, "rostros": [[960 + (i % 5) * 4, 520, 380, 420, 0.95]]} for i in range(30)]}
    assert reencuadre.detectar_camara(irl) is None                        # rostro grande y centrado
    assert reencuadre.detectar_camara(_stream(camara=False)) is None      # el que se mueve no es cámara


def test_plan_dividido_separa_camara_y_contenido():
    plan = reencuadre.plan_dividido(_stream(), 864, 1056)
    c, b = plan["arriba"], plan["abajo"]
    assert c["x"] <= 150 - 55 and c["x"] + c["w"] >= 150 + 55                  # la cara de la cámara cabe arriba
    assert abs(c["w"] / c["h"] - 1080 / 864) < 0.02                            # proporción del panel superior
    x0, x1 = b["zona"]
    assert x0 >= c["x"] + c["w"] and x1 == 1920                                # el contenido excluye la cámara
    assert abs(b["w"] / b["h"] - 1080 / 1056) < 0.02
    xs = [x for _, x in plan["puntos"]]
    assert all(x0 <= x <= x1 - b["w"] for x in xs) and xs[-1] > xs[0]          # sigue a la persona y no invade la cámara
    assert reencuadre.plan_dividido(_stream(camara=False), 864, 1056) is None


def test_vista_dividida_de_punta_a_punta(fabrica, clip, monkeypatch):
    monkeypatch.setattr(reencuadre, "analizar", lambda *a, **k: {**_stream(15), "ancho": 1280, "alto": 720,
                        "muestras": [{"t": m["t"], "rostros": [[r[0] * 2 / 3, r[1] * 2 / 3, r[2] * 2 / 3, r[3] * 2 / 3, r[4]]
                                                                for r in m["rostros"]]} for m in _stream(15)["muestras"]]})
    fabrica.db.guardar_ajustes({"estilo": "dividido"})
    t = fabrica.importar_archivo(clip, "a.mp4")
    fabrica._ejecutar(t)
    t = fabrica.db.trabajo(t["id"])
    assert t["estado"] == "renderizado", t["error"]
    assert "vista dividida" in t["etapas"]["render"]["detalle"]
    s = media.sondear(fabrica.rutas.trabajo(t["id"]) / "short.mp4")
    assert (s["ancho"], s["alto"]) == (1080, 1920)
    d = t["datos"]["disposicion"]
    assert [p["h"] for p in d["paneles"]] == [864, 1056] and "nombre" not in d
    assert d["tarjeta"]["y"] < 864 < d["tarjeta"]["y"] + d["tarjeta"]["h"]     # banner de contexto sobre la unión


def test_sin_camara_vuelve_a_pantalla_completa_y_avisa(fabrica, clip, monkeypatch):
    monkeypatch.setattr(reencuadre, "analizar", lambda *a, **k: {**_stream(15, camara=False), "ancho": 1280, "alto": 720})
    fabrica.db.guardar_ajustes({"estilo": "dividido"})
    t = fabrica.importar_archivo(clip, "a.mp4")
    fabrica._ejecutar(t)
    t = fabrica.db.trabajo(t["id"])
    assert t["estado"] == "renderizado" and "pantalla completa" in t["etapas"]["render"]["detalle"]
    assert any("no se encontró la cámara" in a for a in t["avisos"])


def _escena(caras=(), movs=(), n=30, cortes=()):
    """Muestras sintéticas: `caras`/`movs` son funciones i -> [cx, cy, w, h] (o None si no aparece)."""
    muestras = []
    for i in range(n):
        rs = [[*f(i), 0.9] for f in caras if f(i)]
        ms = [[*f(i), 0.05] for f in movs if f(i)]
        muestras.append({"t": round(i * 0.2, 3), "rostros": rs, "movimiento": ms, "corte": i in cortes})
    return {"ancho": 1920, "alto": 1080, "fps": 5, "muestras": muestras}


def test_detecta_un_objeto_sin_cara_que_se_mueve():
    e = _escena(caras=[lambda i: [960, 500, 300, 340]], movs=[lambda i: [1650 + (i % 5) * 10, 600, 200, 300]])
    ss = reencuadre.sujetos(e)
    assert [s["tipo"] for s in ss] == ["rostro", "movimiento"]
    e2 = _escena(caras=[lambda i: [960, 500, 300, 340]], movs=[lambda i: [990, 650, 300, 400]])
    assert [s["tipo"] for s in reencuadre.sujetos(e2)] == ["rostro"]      # el movimiento de la persona es suyo


def test_decidir_dos_sujetos_separados():
    e = _escena(caras=[lambda i: [500 + i, 500, 330, 360], lambda i: [1450 - i, 520, 320, 350]])
    d = reencuadre.decidir(e, 864, 1056)
    assert d["tipo"] == "dos" and len(d["plan"]["paneles"]) == 2 and d["plan"]["proporcion"] == 50
    arriba, abajo = d["plan"]["paneles"]
    assert arriba["puntos"][0][1] < 500 < arriba["puntos"][0][1] + arriba["w"]          # izquierda arriba
    assert abajo["puntos"][0][1] < 1450 < abajo["puntos"][0][1] + abajo["w"]           # derecha abajo


def test_decidir_un_sujeto_y_nada():
    assert reencuadre.decidir(_escena(caras=[lambda i: [960 + i * 5, 500, 330, 360]]), 864, 1056)["tipo"] == "seguir"
    juntos = _escena(caras=[lambda i: [880, 500, 200, 220], lambda i: [1060, 500, 200, 220]])
    assert reencuadre.decidir(juntos, 864, 1056)["tipo"] == "seguir"                    # caben juntos en 9:16
    assert reencuadre.decidir(_escena(), 864, 1056)["tipo"] == "clasico"


def test_corte_de_escena_salta_sin_paneo():
    e = _escena(caras=[lambda i: [700, 500, 300, 340] if i < 15 else [960, 500, 300, 340]], cortes=(15,))
    xs = [x for _, x in reencuadre.trayectoria(e, 606)]
    assert len(set(xs)) == 2                       # sin pasos intermedios: corte limpio (sin corte habría paneo)


def test_nitidez_solo_al_ampliar_mucho():
    from fabrica_studio import render
    assert render._nitidez(1.1) == "" and render._nitidez(1.8).startswith(",unsharp=")


def test_modo_automatico_dos_sujetos_de_punta_a_punta(fabrica, clip, monkeypatch):
    escala = 1280 / 1920
    base = _escena(caras=[lambda i: [500 + i, 500, 330, 360], lambda i: [1450 - i, 520, 320, 350]], n=15)
    monkeypatch.setattr(reencuadre, "analizar", lambda *a, **k: {
        **base, "ancho": 1280, "alto": 720,
        "muestras": [{**m, "rostros": [[v * escala for v in r[:4]] + [r[4]] for r in m["rostros"]]} for m in base["muestras"]]})
    fabrica.db.guardar_ajustes({"estilo": "auto"})
    t = fabrica.importar_archivo(clip, "a.mp4")
    fabrica._ejecutar(t)
    t = fabrica.db.trabajo(t["id"])
    assert t["estado"] == "renderizado", t["error"]
    assert "automático: dos sujetos" in t["etapas"]["render"]["detalle"]
    assert " · vista dividida" in t["etapas"]["render"]["detalle"]          # el panel lo muestra como encuadre usado
    assert [p["h"] for p in t["datos"]["disposicion"]["paneles"]] == [960, 960]
    s = media.sondear(fabrica.rutas.trabajo(t["id"]) / "short.mp4")
    assert (s["ancho"], s["alto"]) == (1080, 1920)


def test_modo_automatico_sin_sujetos_usa_clasico_sin_aviso_de_seguimiento(fabrica, clip, monkeypatch):
    """El aviso del análisis habla del seguimiento de rostros: si «auto» elige el clásico, no se muestra."""
    monkeypatch.setattr(reencuadre, "analizar", lambda *a, **k: {
        "ancho": 1280, "alto": 720, "fps": 5, "muestras": [{"t": i * 0.2, "rostros": []} for i in range(15)],
        "aviso": "Se detectaron rostros en pocas partes del clip."})
    fabrica.db.guardar_ajustes({"estilo": "auto"})
    t = fabrica.importar_archivo(clip, "a.mp4")
    fabrica._ejecutar(t)
    t = fabrica.db.trabajo(t["id"])
    assert t["estado"] == "renderizado", t["error"]
    assert "automático:" in t["etapas"]["render"]["detalle"] and t["etapas"]["render"]["detalle"].endswith("clásico")
    assert not any("rostros" in a for a in t["avisos"])


def _ffmpeg_falso(tmp_path, avisos_kb: int, cuadros: int, colgar: bool = False):
    """Script que imita a FFmpeg: escribe muchos avisos por stderr y luego cuadros por stdout."""
    import sys
    s = tmp_path / "ffmpeg_falso.py"
    s.write_text(f"""#!{sys.executable}
import sys, time
sys.stderr.write("[aviso] marca de tiempo no monótona\\n" * ({avisos_kb} * 30)); sys.stderr.flush()
cuadro = bytes(640 * 360 * 3)
for _ in range({cuadros}):
    sys.stdout.buffer.write(cuadro)
sys.stdout.flush()
if {colgar}:
    time.sleep(60)
""")
    s.chmod(0o755)
    return str(s)


@pytest.mark.skipif(__import__("sys").platform == "win32" or not reencuadre.disponible()[0], reason="script POSIX / OpenCV")
def test_muchos_avisos_de_ffmpeg_no_bloquean_el_analisis(tmp_path, monkeypatch):
    monkeypatch.setattr(reencuadre, "herramienta", lambda n: _ffmpeg_falso(tmp_path, 2048, 10))
    r = reencuadre.analizar(tmp_path / "x.mp4", {"ancho": 640, "alto": 360, "duracion": 2.0})
    assert len(r["muestras"]) == 10


@pytest.mark.skipif(__import__("sys").platform == "win32" or not reencuadre.disponible()[0], reason="script POSIX / OpenCV")
def test_analisis_colgado_se_corta_por_tiempo(tmp_path, monkeypatch):
    import time
    monkeypatch.setattr(reencuadre, "herramienta", lambda n: _ffmpeg_falso(tmp_path, 1, 3, colgar=True))
    monkeypatch.setattr(reencuadre, "LIMITE_MINIMO", 2.0)                       # límite corto para la prueba
    t0 = time.time()
    r = reencuadre.analizar(tmp_path / "x.mp4", {"ancho": 640, "alto": 360, "duracion": 0.1})
    assert time.time() - t0 < 20 and "tiempo máximo" in r.get("aviso", "") and len(r["muestras"]) == 3
