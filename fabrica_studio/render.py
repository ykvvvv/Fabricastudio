"""Composición del Short: lienzo 1080x1920, tarjeta con banner, video, subtítulos, logo y nombre.

Los elementos fijos (tarjeta, banner, logo, nombre) se dibujan una vez con Pillow
en un PNG transparente; FFmpeg coloca el video, superpone el PNG y quema los subtítulos.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

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


def calcular_disposicion_completo(a: dict, banner: dict | None = None) -> dict:
    """Estilo pantalla completa: el video ocupa todo el lienzo y el resto va encima."""
    d: dict = {"estilo": "completo", "video": {"x": 0, "y": 0, "w": LIENZO_ANCHO, "h": LIENZO_ALTO}}
    if banner:
        d["tarjeta"] = {"x": (LIENZO_ANCHO - banner["ancho"]) // 2, "y": int(a["completo_banner_y"]),
                        "w": banner["ancho"], "h": banner["alto"]}
    tamano = int(a["completo_sub_tamano"])
    sub_y = int(a["completo_sub_y"])
    sub_alto = round(tamano * 1.22 * 2)
    d["subtitulos"] = {"x": 60, "y": sub_y, "w": LIENZO_ANCHO - 120, "h": sub_alto, "tamano": tamano}
    y = int(a["completo_logo_y"])
    if a["mostrar_logo"]:
        d["logo"] = {"y": y, "h": int(a["completo_logo_alto"])}
        y += int(a["completo_logo_alto"])
    if a["mostrar_nombre"]:
        y += 8
        alto_nombre = round(int(a["nombre_tamano"]) * 1.2)
        d["nombre"] = {"y": y, "h": alto_nombre, "tamano": int(a["nombre_tamano"])}
        y += alto_nombre
    d["fin_contenido"] = y
    avisos = []
    if y > LIENZO_ALTO - 20:
        avisos.append("El logo o la firma se salen por abajo: súbelos o reduce su tamaño.")
    if banner and d["tarjeta"]["y"] + d["tarjeta"]["h"] > sub_y:
        avisos.append("El banner choca con los subtítulos.")
    if "logo" in d and sub_y + sub_alto > d["logo"]["y"]:
        avisos.append("Los subtítulos chocan con el logo: súbelos o baja el logo.")
    d["avisos"] = avisos
    return d


def calcular_disposicion_dividido(a: dict, banner: dict | None = None, proporcion: int | None = None) -> dict:
    """Vista dividida: dos paneles apilados; subtítulos, logo y (opcional) banner encima.
    `proporcion` (% del panel de arriba) sustituye al ajuste, p. ej. 50 % para dos sujetos."""
    arriba = int(round(LIENZO_ALTO * int(proporcion or a["dividido_proporcion"]) / 100)) // 2 * 2
    d: dict = {"estilo": "dividido", "video": {"x": 0, "y": 0, "w": LIENZO_ANCHO, "h": LIENZO_ALTO},
               "paneles": [{"id": "camara", "x": 0, "y": 0, "w": LIENZO_ANCHO, "h": arriba},
                           {"id": "contenido", "x": 0, "y": arriba, "w": LIENZO_ANCHO, "h": LIENZO_ALTO - arriba}]}
    if banner:
        d["tarjeta"] = {"x": (LIENZO_ANCHO - banner["ancho"]) // 2, "y": int(a["completo_banner_y"]),
                        "w": banner["ancho"], "h": banner["alto"]}
    tamano = int(a["dividido_sub_tamano"])
    sub_y = int(a["dividido_sub_y"])
    sub_alto = round(tamano * 1.22 * 2)
    d["subtitulos"] = {"x": 60, "y": sub_y, "w": LIENZO_ANCHO - 120, "h": sub_alto, "tamano": tamano}
    y = int(a["dividido_logo_y"])
    if a["mostrar_logo"]:
        d["logo"] = {"y": y, "h": int(a["dividido_logo_alto"])}
        y += int(a["dividido_logo_alto"])
    if a["mostrar_nombre"] and a["dividido_firma"]:
        y += 6
        alto_nombre = round(int(a["nombre_tamano"]) * 1.2)
        d["nombre"] = {"y": y, "h": alto_nombre, "tamano": int(a["nombre_tamano"])}
        y += alto_nombre
    d["fin_contenido"] = y
    avisos = []
    if y > LIENZO_ALTO - 10:
        avisos.append("El logo se sale por abajo: súbelo o reduce su tamaño.")
    if "logo" in d and sub_y + sub_alto > d["logo"]["y"]:
        avisos.append("Los subtítulos chocan con el logo.")
    d["avisos"] = avisos
    return d


def preparar_gancho(banner_texto: str, a: dict, d: dict, duracion: float) -> dict:
    """Banner pequeño de los primeros segundos: en la vista dividida, centrado sobre la línea que separa
    las dos partes; en pantalla completa, en la posición del banner."""
    a_g = {**a, "banner_tamano": int(a.get("gancho_tamano", 62)), "banner_ancho": 900}
    tarjeta = componer_banner(banner_texto, a_g)
    if d.get("estilo") == "dividido":
        y = d["paneles"][0]["h"] - tarjeta["alto"] // 2
    else:
        y = int(a["completo_banner_y"])
    y = max(20, min(y, LIENZO_ALTO - tarjeta["alto"] - 20))
    d_g = {"tarjeta": {"x": (LIENZO_ANCHO - tarjeta["ancho"]) // 2, "y": y, "w": tarjeta["ancho"], "h": tarjeta["alto"]}}
    imagen = dibujar_capa(d_g, tarjeta, a_g, Path("."))
    segundos = max(1.0, min(float(a.get("gancho_segundos", 3)), max(1.0, duracion - 0.5)))
    return {"imagen": imagen, "x": d_g["tarjeta"]["x"], "y": y, "h": tarjeta["alto"], "segundos": segundos}


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


def recortar_margenes(img: Image.Image) -> Image.Image:
    """Logo subido sin márgenes: los transparentes o, si no tiene transparencia, los de un fondo liso (las cuatro
    esquinas del mismo color). Una foto, sin fondo liso, queda igual."""
    img = img.convert("RGBA")
    caja = img.getchannel("A").getbbox()
    if not caja:
        raise ErrorEtapa("El logo es completamente transparente: no se vería nada.", "entrada")
    if caja != (0, 0, *img.size):
        return img.crop(caja)
    w, h = img.size
    fondo = img.getpixel((0, 0))
    esquinas = [img.getpixel(p) for p in ((w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    if any(max(abs(x - y) for x, y in zip(e, fondo)) > 16 for e in esquinas):
        return img
    # Mayor diferencia de color con el fondo, por encima del ruido de compresión (JPG): lo que queda es el logo.
    r, g, b, _ = ImageChops.difference(img, Image.new("RGBA", img.size, fondo)).split()
    caja = ImageChops.lighter(ImageChops.lighter(r, g), b).point(lambda v: 255 if v > 24 else 0).getbbox()
    return img.crop(caja) if caja else img


def dibujar_capa(d: dict, banner: dict, a: dict, recursos: Path) -> Image.Image:
    """Capa transparente con la tarjeta, el banner, el logo y el nombre."""
    capa = Image.new("RGBA", (LIENZO_ANCHO, LIENZO_ALTO), (0, 0, 0, 0))
    dib = ImageDraw.Draw(capa)
    if banner and "tarjeta" in d:
        t = d["tarjeta"]
        dib.rounded_rectangle((t["x"], t["y"], t["x"] + t["w"], t["y"] + t["h"]),
                              radius=int(a.get("banner_radio", 22)), fill="white")
        fuente = _fuente(FUENTE_BLACK, banner["tamano"])
        for i, linea in enumerate(banner["lineas"]):
            cy = t["y"] + banner["relleno_y"] + banner["alto_linea"] * i + banner["alto_linea"] // 2
            dib.text((LIENZO_ANCHO // 2, cy), linea, font=fuente, fill=a["banner_color"], anchor="mm")
    if "logo" in d:
        logo = cargar_logo(recursos, d["logo"]["h"])
        capa.alpha_composite(logo, ((LIENZO_ANCHO - logo.width) // 2, d["logo"]["y"]))
    firma = (a.get("firma") or a["creador"]).strip()
    if "nombre" in d and firma:
        sobre_video = d.get("estilo") in ("completo", "dividido")   # sobre la imagen hace falta contorno
        dib.text((LIENZO_ANCHO // 2, d["nombre"]["y"] + d["nombre"]["h"] // 2), firma,
                 font=_fuente(FUENTE_BOLD, d["nombre"]["tamano"]), fill=a.get("nombre_color", "#D9D9D9"), anchor="mm",
                 stroke_width=3 if sobre_video else 0, stroke_fill="black")
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
    for fuente in (FUENTE_BOLD, FUENTE_BLACK):
        archivo = destino / fuente.name
        if not archivo.exists():
            try:
                os.link(fuente, archivo)
            except OSError:
                shutil.copyfile(fuente, archivo)


def _nitidez(factor: float) -> str:
    """Enfoque suave cuando el recorte se amplía mucho, para que el zoom no se vea borroso."""
    if factor <= 1.25:
        return ""
    fuerza = min(1.0, 0.35 + (factor - 1.25) * 0.4)
    return f",unsharp=5:5:{fuerza:.2f}:5:5:0.0"


MUESTRA_ANCHO, MUESTRA_ALTO, MUESTRA_FPS, MUESTRA_CUADROS = 540, 960, 30, 180   # «Clip de ejemplo»: 6 s


def preparar(propiedades: dict, banner_texto: str, bloques: list[dict], a: dict, recursos: Path,
             recorte: dict | None = None, encuadre: dict | None = None, muestra: bool = False) -> dict:
    """Todo lo que define la imagen, sin escribir nada: la capa (Pillow), los subtítulos ASS, las órdenes de
    encuadre (sendcmd) y los filtros de FFmpeg. Con `muestra`, la salida es de 540×960 a 30 cuadros por segundo."""
    from . import reencuadre
    ancho, alto = (recorte["w"], recorte["h"]) if recorte else (propiedades["ancho"], propiedades["alto"])
    completo = encuadre is not None
    dividido = completo and bool(encuadre.get("dividido"))
    if dividido:
        banner = componer_banner(banner_texto, a) if a["dividido_banner"] else None
        d = calcular_disposicion_dividido(a, banner, encuadre["dividido"].get("proporcion"))
        if encuadre["dividido"].get("tipo") == "dos":
            d["paneles"][0]["id"], d["paneles"][1]["id"] = "sujeto1", "sujeto2"
        sub_kw = {"mayusculas": bool(a["completo_mayusculas"]), "borde": max(5, round(d["subtitulos"]["tamano"] * 0.1)),
                  "fuente": "Inter Black"}
    elif completo:
        banner = componer_banner(banner_texto, a) if a["completo_banner"] else None
        d = calcular_disposicion_completo(a, banner)
        sub_kw = {"mayusculas": bool(a["completo_mayusculas"]), "borde": max(4, round(d["subtitulos"]["tamano"] * 0.09)),
                  "fuente": "Inter Black"}
    else:
        banner = componer_banner(banner_texto, a)
        d = calcular_disposicion(ancho, alto, a, banner)
        sub_kw = {}
    gancho = None
    # El gancho solo se usa cuando no hay banner fijo (vista dividida o pantalla completa sin banner).
    if completo and a.get("gancho") and banner_texto.strip() and "tarjeta" not in d:
        gancho = preparar_gancho(banner_texto, a, d, propiedades["duracion"])
        d["gancho"] = {k: gancho[k] for k in ("x", "y", "h", "segundos")}
    capa = dibujar_capa(d, banner, a, recursos)
    ass = a_ass(bloques, d["subtitulos"]["tamano"], d["subtitulos"]["y"], resaltar=bool(a.get("sub_resaltar")),
                color_resalte=a.get("sub_color_resalte", "#53FC18"), **sub_kw)

    v = d["video"]
    ordenes_encuadre = None
    filtros = "[0:v]" + (f"fps={MUESTRA_FPS}," if muestra else "")
    if recorte:
        filtros += f"crop={recorte['w']}:{recorte['h']}:{recorte['x']}:{recorte['y']},"
    if dividido:
        plan = encuadre["dividido"]
        paneles = plan["paneles"]
        ordenes = []
        for pn in paneles:
            if len(pn["puntos"]) > 1:
                ordenes.append(reencuadre.comandos_sendcmd(pn["puntos"], pn["filtro"]))
        ordenes_encuadre = "".join(ordenes) or "0.000 crop@arriba x 0;\n"
        filtros += "sendcmd=f=encuadre.cmd,split=2[fa][fb];"
        salidas = []
        for k, (pn, etiqueta, lienzo_p) in enumerate(zip(paneles, ("fa", "fb"), d["paneles"])):
            x0 = int(pn["puntos"][0][1]) // 2 * 2
            nitidez = _nitidez(lienzo_p["h"] / pn["h"])
            filtros += (f"[{etiqueta}]{pn['filtro']}=w={pn['w']}:h={pn['h']}:x={x0}:y={pn['y']},"
                        f"scale={LIENZO_ANCHO}:{lienzo_p['h']}:flags=lanczos,setsar=1{nitidez}[p{k}];")
            salidas.append(f"[p{k}]")
        filtros += "".join(salidas) + "vstack=inputs=2"
        d["encuadre"] = {"tipo": plan.get("tipo", "camara"),
                         "paneles": [{"w": pn["w"], "h": pn["h"], "movimientos": len(pn["puntos"])} for pn in paneles]}
    elif completo:
        vw, vh = reencuadre.ventana(ancho, alto, int(a["completo_zoom"]) / 100)
        puntos = reencuadre.trayectoria(encuadre, vw)
        ordenes_encuadre = reencuadre.comandos_sendcmd(puntos)
        y0 = (alto - vh) // 2 // 2 * 2
        filtros += (f"sendcmd=f=encuadre.cmd,crop@encuadre=w={vw}:h={vh}:x={int(puntos[0][1]) // 2 * 2}:y={y0},"
                    f"scale={LIENZO_ANCHO}:{LIENZO_ALTO}:flags=lanczos,setsar=1{_nitidez(LIENZO_ALTO / vh)}")
        d["encuadre"] = {"ventana": [vw, vh], "movimientos": len(puntos)}
    else:
        filtros += f"scale={v['w']}:{v['h']}:flags=lanczos,setsar=1"
    if propiedades.get("fps", 0) > 60 and not muestra:
        filtros += ",fps=60"
    # La muestra conserva los tiempos del original (subtítulos y encuadre sincronizados) y los pone a cero al final.
    final = f"setpts=PTS-STARTPTS,scale={MUESTRA_ANCHO}:{MUESTRA_ALTO}," if muestra else ""
    filtros += f",pad={LIENZO_ANCHO}:{LIENZO_ALTO}:{v['x']}:{v['y']}:black[v];"
    if gancho:                     # tercera entrada: gancho.png, que aparece y se desvanece con su alfa
        s_g = gancho["segundos"]
        filtros += (f"[v][1:v]overlay=0:0[c0];[2:v]format=rgba,fade=t=in:st=0:d=0.25:alpha=1,"
                    f"fade=t=out:st={max(0.3, s_g - 0.45):.2f}:d=0.45:alpha=1[g];"
                    "[c0][g]overlay=0:0:eof_action=pass[c];")
    else:
        filtros += "[v][1:v]overlay=0:0[c];"
    filtros += f"[c]ass=subtitulos.ass:fontsdir=fuentes,{final}format=yuv420p[out]"
    return {"capa": capa, "ass": ass, "encuadre": ordenes_encuadre, "filtros": filtros, "disposicion": d, "gancho": gancho}


def renderizar(carpeta: Path, entrada: str, propiedades: dict, banner_texto: str, bloques: list[dict],
               a: dict, recursos: Path, salida: str = "short.mp4", recorte: dict | None = None,
               encuadre: dict | None = None, muestra: float | None = None) -> dict:
    """Genera `salida` dentro de `carpeta` y devuelve sus propiedades comprobadas.

    `recorte` ({w, h, x, y}) quita bordes negros del original antes de componer.
    `encuadre` (resultado de reencuadre.analizar) activa el estilo pantalla completa.
    `muestra` (segundo de inicio): solo 6 s, a 540×960 y calidad baja, sin audio ni miniatura."""
    p = preparar(propiedades, banner_texto, bloques, a, recursos, recorte, encuadre, muestra is not None)
    p["capa"].save(carpeta / "capa.png")
    (carpeta / "subtitulos.ass").write_text(p["ass"], encoding="utf-8")
    if p["encuadre"] is not None:
        (carpeta / "encuadre.cmd").write_text(p["encuadre"], encoding="utf-8")
    entradas = ["-i", entrada, "-i", "capa.png"]
    if p["gancho"]:
        p["gancho"]["imagen"].save(carpeta / "gancho.png")
        entradas += ["-loop", "1", "-t", f"{p['gancho']['segundos'] + 0.1:.2f}", "-i", "gancho.png"]
    _preparar_fuentes(carpeta)
    if muestra is None:
        antes, esperado = [], (LIENZO_ANCHO, LIENZO_ALTO)
        despues = ["-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "high",
                   "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-t", f"{propiedades['duracion']:.3f}"]
    else:
        antes, esperado = ["-ss", f"{muestra:.3f}", "-copyts", "-start_at_zero"], (MUESTRA_ANCHO, MUESTRA_ALTO)
        despues = ["-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-frames:v", str(MUESTRA_CUADROS)]
    temporal = "render_tmp.mp4"
    cmd = [herramienta("ffmpeg"), "-y", "-v", "error", *antes, *entradas,       # -ss solo afecta a la primera entrada
           "-filter_complex", p["filtros"], "-map", "[out]", *despues, "-movflags", "+faststart", temporal]
    ejecutar(cmd, cwd=carpeta)
    resultado = sondear(carpeta / temporal)
    if (resultado["ancho"], resultado["alto"]) != esperado or resultado["codec_video"] != "h264":
        raise ErrorEtapa(f"El render no tiene el formato esperado: {resultado}", "interno")
    reemplazar(carpeta / temporal, carpeta / salida)   # el archivo final solo aparece si está completo
    if muestra is None:
        ejecutar([herramienta("ffmpeg"), "-y", "-v", "error", "-ss", f"{min(1.0, resultado['duracion'] / 2):.2f}",
                  "-i", salida, "-frames:v", "1", "-vf", "scale=360:-2", "miniatura.jpg"], cwd=carpeta)
    return {"propiedades": resultado, "disposicion": p["disposicion"], "recorte": recorte}


def elementos_editables(d: dict, a: dict, recursos: Path) -> list[dict]:
    """Cajas de cada elemento en el lienzo de 1080×1920 y qué ajuste cambia al moverlo o agrandarlo.

    Para el editor visual del panel: al arrastrar `dy` píxeles del lienzo, el ajuste de `mover` cambia en
    `signo × dy`; al agrandar, el de `tamano` cambia proporcionalmente al alto de la caja. El panel debe
    volver a pedir la disposición tras cada cambio, porque el motor puede limitar posiciones."""
    from .config import LIMITES
    completo = d.get("estilo") in ("completo", "dividido")
    pre = "dividido" if d.get("estilo") == "dividido" else "completo"

    def regla(ajuste: str | None, signo: int = 1) -> dict | None:
        if not ajuste:
            return None
        lo, hi = LIMITES.get(ajuste, (None, None))
        return {"ajuste": ajuste, "signo": signo, "valor": a[ajuste], "min": lo, "max": hi}

    elementos = []
    if not completo:
        v = d["video"]
        elementos.append({"id": "video", "nombre": "Video", "caja": dict(v),
                          "mover": regla("video_desplazamiento_y"), "tamano": regla("video_alto_max"), "ancho": None})
    if "tarjeta" in d:
        t = d["tarjeta"]
        elementos.append({"id": "banner", "nombre": "Banner", "caja": {k: t[k] for k in ("x", "y", "w", "h")},
                          "mover": regla("completo_banner_y") if completo else regla("banner_separacion", -1),
                          "tamano": regla("banner_tamano"), "ancho": regla("banner_ancho")})
    sb = d["subtitulos"]
    elementos.append({"id": "subtitulos", "nombre": "Subtítulos", "caja": {k: sb[k] for k in ("x", "y", "w", "h")},
                      "mover": regla(f"{pre}_sub_y" if completo else "sub_desplazamiento"),
                      "tamano": regla(f"{pre}_sub_tamano" if completo else "sub_tamano"), "ancho": None})
    mover_marca = regla(f"{pre}_logo_y" if completo else "logo_separacion")
    if "logo" in d:
        logo = cargar_logo(recursos, d["logo"]["h"])
        elementos.append({"id": "logo", "nombre": "Logo",
                          "caja": {"x": (LIENZO_ANCHO - logo.width) // 2, "y": d["logo"]["y"], "w": logo.width, "h": logo.height},
                          "mover": mover_marca, "tamano": regla(f"{pre}_logo_alto" if completo else "logo_alto"),
                          "ancho": None})
    firma = (a.get("firma") or a["creador"]).strip()
    if "nombre" in d and firma:
        n = d["nombre"]
        dib = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        ancho = int(dib.textlength(firma, font=_fuente(FUENTE_BOLD, n["tamano"]))) + 8
        elementos.append({"id": "firma", "nombre": "Firma", "grupo": "logo",
                          "caja": {"x": (LIENZO_ANCHO - ancho) // 2, "y": n["y"], "w": ancho, "h": n["h"]},
                          "mover": mover_marca, "tamano": regla("nombre_tamano"), "ancho": None})
    return elementos
