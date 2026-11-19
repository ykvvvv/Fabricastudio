from fabrica_studio import render, subtitulos
from fabrica_studio.config import AJUSTES_POR_DEFECTO as A, LIENZO_ALTO


def test_disposicion_inicial_sin_choques():
    for ancho, alto in [(1920, 1080), (1280, 720), (1440, 1080), (1080, 1080), (1080, 1920)]:
        b = render.componer_banner("LA PALTITA MÁS GRANDE DE CHILE", A)
        d = render.calcular_disposicion(ancho, alto, A, b)
        assert d["avisos"] == [], (ancho, alto, d["avisos"])
        s = d["subtitulos"]
        assert d["tarjeta"]["y"] + d["tarjeta"]["h"] <= d["video"]["y"]          # banner sobre el video
        assert s["y"] >= d["video"]["y"] + d["video"]["h"]                       # subtítulos bajo el video
        assert d["logo"]["y"] >= s["y"] + s["h"]                                 # logo bajo los subtítulos
        assert d["nombre"]["y"] >= d["logo"]["y"] + d["logo"]["h"]               # nombre bajo el logo
        assert d["fin_contenido"] <= LIENZO_ALTO
        assert d["video"]["w"] % 2 == 0 and d["video"]["h"] % 2 == 0
        assert abs(d["video"]["w"] / d["video"]["h"] - ancho / alto) < 0.01      # conserva proporciones


def test_banner_largo_cabe_en_dos_lineas():
    b = render.componer_banner("EXTRAORDINARIAMENTE INCREÍBLE REACCIÓN INESPERADA COMPLETAMENTE VIRALIZADA", A)
    assert len(b["lineas"]) <= 2


def test_logo_recorta_margenes_transparentes(tmp_path):
    from PIL import Image
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    img.paste((0, 255, 0, 255), (150, 180, 250, 220))        # contenido real: 100x40
    img.save(tmp_path / "logo.png")
    logo = render.cargar_logo(tmp_path, 80)
    assert logo.size == (200, 80)


def test_subtitulos_no_se_solapan_y_respetan_limites():
    palabras = [{"inicio": i * 0.3, "fin": i * 0.3 + 0.28, "texto": p} for i, p in enumerate(
        "esta es una frase bastante larga para comprobar que los bloques quedan cortos y ordenados".split())]
    bloques = subtitulos.agrupar(palabras, 4, 22)
    assert all(len(b["texto"].split()) <= 4 for b in bloques)
    assert all(a["fin"] <= b["inicio"] for a, b in zip(bloques, bloques[1:]))
    assert " ".join(b["texto"] for b in bloques) == " ".join(p["texto"] for p in palabras)
    ass = subtitulos.a_ass(bloques, 60, 1200)
    assert ass.count("Dialogue:") == len(bloques) and "PlayResY: 1920" in ass


def test_resaltado_de_la_palabra_activa():
    palabras = [{"inicio": 0.0, "fin": 0.4, "texto": "Mi"}, {"inicio": 0.5, "fin": 0.9, "texto": "gente"},
                {"inicio": 1.0, "fin": 1.5, "texto": "linda,"}]
    bloques = subtitulos.agrupar(palabras, 3, 22)
    assert len(bloques) == 1 and bloques[0]["palabras"]
    ass = subtitulos.a_ass(bloques, 66, 1200, resaltar=True, color_resalte="#53FC18")
    eventos = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(eventos) == 3                                     # un evento por palabra
    assert "{\\c&H0018FC53&}linda,{\\c&H00FFFFFF&}" in eventos[2]    # verde en orden BGR de ASS
    assert eventos[0].split(",")[2] == "0:00:00.50"               # cada palabra dura hasta la siguiente
    sin = subtitulos.a_ass(bloques, 66, 1200, resaltar=False)
    assert sin.count("Dialogue:") == 1 and "\\c" not in sin
    editado = [{**bloques[0], "texto": "Mi gente bonita"}]          # texto editado: sin resaltado
    assert subtitulos.a_ass(editado, 66, 1200, resaltar=True).count("Dialogue:") == 1


def test_detecta_y_recorta_franjas_negras(tmp_path):
    import subprocess
    from fabrica_studio import media
    con = tmp_path / "con_bordes.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=15:d=2",
                    "-vf", "pad=720:1280:40:300:black", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", str(con)], check=True)
    r = media.detectar_bordes(con, media.sondear(con))
    assert r and abs(r["w"] - 640) <= 8 and abs(r["h"] - 360) <= 8 and abs(r["x"] - 40) <= 8 and abs(r["y"] - 300) <= 8
    sin = tmp_path / "sin_bordes.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=15:d=2",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(sin)], check=True)
    assert media.detectar_bordes(sin, media.sondear(sin)) is None


def _disp(pc, **params):
    r = pc.get("/api/diseno/disposicion", params=params)
    assert r.status_code == 200, r.text
    return {e["id"]: e for e in r.json()["elementos"]}


def test_disposicion_para_el_editor_visual(fabrica):
    from fastapi.testclient import TestClient
    from fabrica_studio.server import crear_app
    pc = TestClient(crear_app(fabrica, iniciar_hilos=False), base_url="http://127.0.0.1:8765", client=("127.0.0.1", 1))
    e = _disp(pc)
    assert set(e) == {"video", "banner", "subtitulos", "logo", "firma"}
    for x in e.values():
        c = x["caja"]
        assert 0 <= c["x"] and c["x"] + c["w"] <= 1080 and 0 <= c["y"] and c["y"] + c["h"] <= 1920
    # Mover según la regla devuelta desplaza la caja lo mismo en el lienzo.
    for id_, dy in (("subtitulos", 40), ("logo", 30), ("banner", -20), ("video", 50)):
        m = e[id_]["mover"]
        nuevo = _disp(pc, **{m["ajuste"]: m["valor"] + m["signo"] * dy})
        assert nuevo[id_]["caja"]["y"] - e[id_]["caja"]["y"] == dy, id_
    # Agrandar los subtítulos cambia su tamaño.
    t = e["subtitulos"]["tamano"]
    assert _disp(pc, **{t["ajuste"]: t["valor"] + 20})["subtitulos"]["caja"]["h"] > e["subtitulos"]["caja"]["h"]
    # Pantalla completa: sin caja de video y con posiciones absolutas.
    c = _disp(pc, estilo="completo")
    assert "video" not in c and c["subtitulos"]["mover"]["ajuste"] == "completo_sub_y"
    assert c["logo"]["mover"] == c["firma"]["mover"]                      # logo y firma se mueven juntos
    assert pc.get("/api/diseno/disposicion", params={"sub_tamano": 999}).status_code == 400


def test_editor_visual_en_vista_dividida(fabrica):
    from fastapi.testclient import TestClient
    from fabrica_studio.server import crear_app
    pc = TestClient(crear_app(fabrica, iniciar_hilos=False), base_url="http://127.0.0.1:8765", client=("127.0.0.1", 1))
    e = _disp(pc, estilo="dividido")
    assert set(e) == {"subtitulos", "logo"}                       # sin banner, firma ni video arrastrable
    assert e["subtitulos"]["mover"]["ajuste"] == "dividido_sub_y" and e["logo"]["tamano"]["ajuste"] == "dividido_logo_alto"
    assert pc.get("/api/diseno/vista", params={"estilo": "dividido"}).headers["content-type"] == "image/jpeg"


def test_gancho_aparece_al_inicio_y_se_desvanece(tmp_path):
    """Vista dividida: el banner pequeño se ve sobre la unión de las dos partes y desaparece a los segundos."""
    import subprocess
    from PIL import Image
    from fabrica_studio.config import Rutas
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=5",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest", "-pix_fmt", "yuv420p",
                    str(tmp_path / "entrada.mp4")], check=True)
    encuadre = {"dividido": {"tipo": "camara", "proporcion": 40, "paneles": [
        {"w": 320, "h": 180, "y": 0, "puntos": [(0.0, 0)], "filtro": "crop@arriba"},
        {"w": 202, "h": 360, "y": 0, "puntos": [(0.0, 200)], "filtro": "crop@abajo"}]}}
    a = {**A, "gancho": True, "gancho_segundos": 2}
    props = {"ancho": 640, "alto": 360, "duracion": 5.0, "fps": 30}
    res = render.renderizar(tmp_path, "entrada.mp4", props, "UN GANCHO DE PRUEBA", [], a,
                            Rutas(tmp_path / "datos").recursos, encuadre=encuadre)
    g = res["disposicion"]["gancho"]
    assert g["segundos"] == 2 and (tmp_path / "gancho.png").exists()
    y = g["y"] + g["h"] // 2
    for t, blanco in ((1.0, True), (3.5, False)):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(tmp_path / "short.mp4"),
                        "-frames:v", "1", str(tmp_path / f"f{t}.png")], check=True)
        r, gr, b = Image.open(tmp_path / f"f{t}.png").convert("RGB").getpixel((g["x"] + 12, y))
        assert (min(r, gr, b) > 200) == blanco, (t, r, gr, b)


def test_sin_gancho_si_hay_banner_fijo(tmp_path):
    d = render.calcular_disposicion_completo(A, render.componer_banner("HOLA", A))
    assert "tarjeta" in d          # pantalla completa con banner fijo: el gancho no se añade
