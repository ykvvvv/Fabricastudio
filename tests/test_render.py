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
