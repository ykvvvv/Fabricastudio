"""Composición del Short: lienzo 1080x1920, tarjeta con banner, video, subtítulos, logo y nombre.

Los elementos fijos (tarjeta, banner, logo, nombre) se dibujan una vez con Pillow
en un PNG transparente; FFmpeg coloca el video, superpone el PNG y quema los subtítulos.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import FUENTE_BLACK, FUENTE_BOLD, LIENZO_ALTO, LIENZO_ANCHO
from .errores import ErrorEtapa
from .media import ejecutar, herramienta, sondear
from .subtitulos import a_ass

MARGEN = 40          # margen mínimo respecto a los bordes del lienzo
VERDE_KICK = "#53FC18"


def _par(n: float) -> int:
    return max(2, int(round(n / 2)) * 2)


def _fuente(ruta: Path, tamano: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ruta), tamano)


def _partir(texto: str, fuente, ancho_max: int, dibujo: ImageDraw.ImageDraw) -> list[str]:
    """Reparte el texto en líneas que caben en `ancho_max`."""
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if dibujo.textlength(prueba, font=fuente) <= ancho_max or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def componer_banner(texto: str, a: dict) -> dict:
    """Elige el tamaño de letra más grande con el que el banner cabe en dos líneas."""
    dibujo = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    ancho_tarjeta = min(int(a["banner_ancho"]), LIENZO_ANCHO - 2 * 12)
    relleno_x, relleno_y = 26, 22
    interior = ancho_tarjeta - 2 * relleno_x
    tamano = int(a["banner_tamano"])
    while True:
        fuente = _fuente(FUENTE_BLACK, tamano)
        lineas = _partir(texto, fuente, interior, dibujo)
        cabe = len(lineas) <= 2 and all(dibujo.textlength(l, font=fuente) <= interior for l in lineas)
        if cabe or tamano <= 30:
            break
        tamano -= 2
    if len(lineas) == 2:
        # Reparte las palabras para que las dos líneas queden parejas (sin una palabra suelta).
        palabras = texto.split()
        cortes = [(" ".join(palabras[:i]), " ".join(palabras[i:])) for i in range(1, len(palabras))]
        validos = [c for c in cortes if max(dibujo.textlength(x, font=fuente) for x in c) <= interior]
        if validos:
            lineas = list(min(validos, key=lambda c: abs(dibujo.textlength(c[0], font=fuente)
                                                         - dibujo.textlength(c[1], font=fuente))))
    lineas = lineas[:2]
    alto_linea = round(tamano * 1.1)
    return {"lineas": lineas, "tamano": tamano, "alto_linea": alto_linea, "ancho": ancho_tarjeta,
            "alto": alto_linea * len(lineas) + 2 * relleno_y, "relleno_y": relleno_y}


def calcular_disposicion(ancho: int, alto: int, a: dict, banner: dict | None = None) -> dict:
    """Posiciones de todos los elementos. También detecta choques y desbordes."""
    escala = min(LIENZO_ANCHO / ancho, int(a["video_alto_max"]) / alto)
    vw, vh = min(_par(ancho * escala), LIENZO_ANCHO), _par(alto * escala)
    vx = (LIENZO_ANCHO - vw) // 2
    alto_banner = banner["alto"] if banner else 0
    minimo_y = MARGEN + (alto_banner + int(a["banner_separacion"]) if banner else 0)
    vy = (LIENZO_ALTO - vh) // 2 + int(a["video_desplazamiento_y"])
    vy = max(minimo_y, min(vy, LIENZO_ALTO - vh - MARGEN))

    d: dict = {"video": {"x": vx, "y": vy, "w": vw, "h": vh}}
    if banner:
        d["tarjeta"] = {"x": (LIENZO_ANCHO - banner["ancho"]) // 2, "y": vy - int(a["banner_separacion"]) - alto_banner,
                        "w": banner["ancho"], "h": alto_banner}
    sub_tamano = int(a["sub_tamano"])
    sub_y = vy + vh + int(a["sub_desplazamiento"])
    sub_alto = round(sub_tamano * 1.22 * 2)          # reserva para dos líneas
    d["subtitulos"] = {"x": 70, "y": sub_y, "w": LIENZO_ANCHO - 140, "h": sub_alto, "tamano": sub_tamano}
    y = max(vy + vh, sub_y + sub_alto)
    if a["mostrar_logo"]:
        y += int(a["logo_separacion"])
        d["logo"] = {"y": y, "h": int(a["logo_alto"])}
        y += int(a["logo_alto"])
    if a["mostrar_nombre"]:
        y += 10
        alto_nombre = round(int(a["nombre_tamano"]) * 1.2)
        d["nombre"] = {"y": y, "h": alto_nombre, "tamano": int(a["nombre_tamano"])}
        y += alto_nombre
    d["fin_contenido"] = y

    avisos = []
    if y > LIENZO_ALTO - MARGEN:
        avisos.append("El contenido inferior se sale del lienzo: sube el video o reduce tamaños.")
    if banner and d["tarjeta"]["y"] < 0:
        avisos.append("La tarjeta del banner se sale por arriba.")
    if "logo" in d and d["logo"]["y"] < sub_y + sub_alto:
        avisos.append("El logo choca con los subtítulos.")
    d["avisos"] = avisos
    return d


def cargar_logo(recursos: Path, alto: int) -> Image.Image:
    """Logo del usuario (recortando sus márgenes transparentes) o un rótulo de texto por defecto."""
    ruta = recursos / "logo.png"
    if ruta.exists():
        logo = Image.open(ruta).convert("RGBA")
        caja = logo.getchannel("A").getbbox()
        if caja:
            logo = logo.crop(caja)
    else:
        fuente = _fuente(FUENTE_BLACK, 160)
        caja = fuente.getbbox("KICK")
        logo = Image.new("RGBA", (caja[2] - caja[0] + 8, caja[3] - caja[1] + 8), (0, 0, 0, 0))
        ImageDraw.Draw(logo).text((4 - caja[0], 4 - caja[1]), "KICK", font=fuente, fill=VERDE_KICK)
    ancho = max(1, round(logo.width * alto / logo.height))
    if ancho > 620:
        alto, ancho = max(1, round(alto * 620 / ancho)), 620
    return logo.resize((ancho, alto), Image.LANCZOS)


def dibujar_capa(d: dict, banner: dict, a: dict, recursos: Path) -> Image.Image:
    """Capa transparente con la tarjeta, el banner, el logo y el nombre."""
    capa = Image.new("RGBA", (LIENZO_ANCHO, LIENZO_ALTO), (0, 0, 0, 0))
    dib = ImageDraw.Draw(capa)
    t = d["tarjeta"]
    dib.rounded_rectangle((t["x"], t["y"], t["x"] + t["w"], t["y"] + t["h"]), radius=int(a.get("banner_radio", 22)), fill="white")
    fuente = _fuente(FUENTE_BLACK, banner["tamano"])
    for i, linea in enumerate(banner["lineas"]):
        cy = t["y"] + banner["relleno_y"] + banner["alto_linea"] * i + banner["alto_linea"] // 2
        dib.text((LIENZO_ANCHO // 2, cy), linea, font=fuente, fill=a["banner_color"], anchor="mm")
    if "logo" in d:
        logo = cargar_logo(recursos, d["logo"]["h"])
        capa.alpha_composite(logo, ((LIENZO_ANCHO - logo.width) // 2, d["logo"]["y"]))
    firma = (a.get("firma") or a["creador"]).strip()
    if "nombre" in d and firma:
        dib.text((LIENZO_ANCHO // 2, d["nombre"]["y"] + d["nombre"]["h"] // 2), firma,
                 font=_fuente(FUENTE_BOLD, d["nombre"]["tamano"]), fill=a.get("nombre_color", "#D9D9D9"), anchor="mm")
    return capa


def reemplazar(origen: Path, destino: Path, intentos: int = 12) -> None:
    """Sustituye `destino` por `origen`. En Windows falla si el archivo está abierto
    (por ejemplo, reproduciéndose en la vista previa): se reintenta unos segundos."""
    for i in range(intentos):
        try:
            os.replace(origen, destino)
            return
        except PermissionError:
            if i == intentos - 1:
                raise ErrorEtapa(f"No se pudo actualizar {destino.name} porque otro programa lo tiene abierto. "
                                 "Cierra la vista previa o el reproductor y pulsa Reintentar.", "temporal")
            time.sleep(0.5)


def _preparar_fuentes(carpeta: Path) -> None:
    """libass busca la fuente en una carpeta relativa al trabajo: evita rutas con ':' en Windows."""
    destino = carpeta / "fuentes"
    destino.mkdir(exist_ok=True)
    archivo = destino / FUENTE_BOLD.name
    if not archivo.exists():
        try:
            os.link(FUENTE_BOLD, archivo)
        except OSError:
            shutil.copyfile(FUENTE_BOLD, archivo)


def renderizar(carpeta: Path, entrada: str, propiedades: dict, banner_texto: str, bloques: list[dict],
               a: dict, recursos: Path, salida: str = "short.mp4", recorte: dict | None = None) -> dict:
    """Genera `salida` dentro de `carpeta` y devuelve sus propiedades comprobadas.

    `recorte` ({w, h, x, y}) quita bordes negros del original antes de componer."""
    banner = componer_banner(banner_texto, a)
    ancho, alto = (recorte["w"], recorte["h"]) if recorte else (propiedades["ancho"], propiedades["alto"])
    d = calcular_disposicion(ancho, alto, a, banner)
    dibujar_capa(d, banner, a, recursos).save(carpeta / "capa.png")
    (carpeta / "subtitulos.ass").write_text(
        a_ass(bloques, d["subtitulos"]["tamano"], d["subtitulos"]["y"], resaltar=bool(a.get("sub_resaltar")),
              color_resalte=a.get("sub_color_resalte", "#53FC18")), encoding="utf-8")
    _preparar_fuentes(carpeta)

    v = d["video"]
    filtros = "[0:v]"
    if recorte:
        filtros += f"crop={recorte['w']}:{recorte['h']}:{recorte['x']}:{recorte['y']},"
    filtros += f"scale={v['w']}:{v['h']}:flags=lanczos,setsar=1"
    if propiedades.get("fps", 0) > 60:
        filtros += ",fps=60"
    filtros += (f",pad={LIENZO_ANCHO}:{LIENZO_ALTO}:{v['x']}:{v['y']}:black[v];"
                "[v][1:v]overlay=0:0[c];[c]ass=subtitulos.ass:fontsdir=fuentes,format=yuv420p[out]")
    temporal = "render_tmp.mp4"
    cmd = [herramienta("ffmpeg"), "-y", "-v", "error", "-i", entrada, "-i", "capa.png",
           "-filter_complex", filtros, "-map", "[out]", "-map", "0:a:0?",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "high",
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
           "-movflags", "+faststart", "-t", f"{propiedades['duracion']:.3f}", temporal]
    ejecutar(cmd, cwd=carpeta)
    resultado = sondear(carpeta / temporal)
    if (resultado["ancho"], resultado["alto"]) != (LIENZO_ANCHO, LIENZO_ALTO) or resultado["codec_video"] != "h264":
        raise ErrorEtapa(f"El render no tiene el formato esperado: {resultado}", "interno")
    reemplazar(carpeta / temporal, carpeta / salida)   # el archivo final solo aparece si está completo
    ejecutar([herramienta("ffmpeg"), "-y", "-v", "error", "-ss", f"{min(1.0, resultado['duracion'] / 2):.2f}",
              "-i", salida, "-frames:v", "1", "-vf", "scale=360:-2", "miniatura.jpg"], cwd=carpeta)
    return {"propiedades": resultado, "disposicion": d, "recorte": recorte}
