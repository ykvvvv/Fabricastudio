"""Importación por enlace (yt-dlp) y comprobación de archivos estables en la carpeta vigilada."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .errores import ErrorEtapa, sin_secretos

HOSTS_COMPATIBLES = ("kick.com",)


def validar_enlace(url: str) -> str:
    url = (url or "").strip()
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ErrorEtapa("El enlace no es una dirección web válida (debe empezar por https://).", "entrada")
    host = p.hostname.lower()
    if not any(host == h or host.endswith("." + h) for h in HOSTS_COMPATIBLES):
        raise ErrorEtapa(f"Fuente no compatible: {host}. Por ahora solo se aceptan enlaces públicos de Kick. "
                         "Puedes descargar el video por tu cuenta e importarlo como archivo.", "entrada")
    if not _es_video_de_kick(p):
        raise ErrorEtapa("Ese enlace no es de un clip ni de un video: parece una página del canal o de su lista "
                         "de clips. En Kick abre un clip concreto y copia su dirección; debe verse como "
                         "https://kick.com/canal/clips/clip_…", "entrada")
    return url


def _es_video_de_kick(p) -> bool:
    """Acepta solo enlaces a un clip o a un video concreto, no páginas de canal o listas."""
    from urllib.parse import parse_qs
    partes = [x for x in p.path.split("/") if x]
    if parse_qs(p.query).get("clip", [""])[0].startswith("clip_"):      # kick.com/canal?clip=clip_…
        return True
    if len(partes) == 3 and partes[1] == "clips" and partes[2].startswith("clip_"):   # /canal/clips/clip_…
        return True
    if len(partes) == 3 and partes[1] == "videos" and len(partes[2]) >= 8:          # /canal/videos/<id>
        return True
    if len(partes) == 2 and partes[0] == "video" and len(partes[1]) >= 8:           # /video/<id>
        return True
    return False


def descargar(url: str, carpeta: Path) -> Path:
    """Descarga el video del enlace a `carpeta/entrada.<ext>`. Nunca simula un éxito."""
    url = validar_enlace(url)
    try:
        import yt_dlp
    except ImportError:
        raise ErrorEtapa("Falta yt-dlp. Ejecuta scripts\\instalar.ps1.", "herramienta")
    opciones = {
        "outtmpl": str(carpeta / "entrada.%(ext)s"), "format": "bv*+ba/b", "merge_output_format": "mp4",
        "noplaylist": True, "playlistend": 1, "quiet": True, "no_warnings": True, "noprogress": True,
        "retries": 3, "socket_timeout": 30, "overwrites": True,
    }
    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("is_live"):
                raise ErrorEtapa("El enlace es una transmisión en directo. Importa un clip o un video terminado.", "entrada")
            ydl.download([url])
    except ErrorEtapa:
        raise
    except Exception as e:
        raise _traducir(str(e))
    archivos = sorted(carpeta.glob("entrada.*"), key=lambda p: p.stat().st_size, reverse=True)
    archivos = [a for a in archivos if a.suffix.lower() not in (".part", ".ytdl")]
    if not archivos or archivos[0].stat().st_size == 0:
        raise ErrorEtapa("La descarga terminó sin producir un archivo de video.", "entrada")
    return archivos[0]


def _traducir(mensaje: str) -> ErrorEtapa:
    m = sin_secretos(re.sub(r"\x1b\[[0-9;]*m", "", mensaje)).replace("ERROR: ", "")[:400]
    bajo = m.lower()
    if "unsupported url" in bajo:
        return ErrorEtapa("Este tipo de enlace de Kick no es compatible con el descargador. "
                          "Prueba con el enlace directo del clip o importa el archivo MP4.", "entrada")
    if any(x in bajo for x in ("login", "sign in", "private", "subscriber", "authentication", "cookies", "members")):
        return ErrorEtapa(f"El enlace requiere iniciar sesión o no es público; no se descargó nada. Detalle: {m}",
                          "autenticacion")
    if any(x in bajo for x in ("403", "forbidden", "cloudflare", "impersonat")):
        return ErrorEtapa("Kick bloqueó la descarga automática (403/Cloudflare). No se descargó nada. "
                          f"Descarga el clip manualmente e impórtalo como archivo. Detalle: {m}", "autenticacion")
    if any(x in bajo for x in ("404", "not found", "does not exist", "unavailable")):
        return ErrorEtapa(f"El enlace no existe o ya no está disponible. Detalle: {m}", "entrada")
    if any(x in bajo for x in ("timed out", "timeout", "connection", "temporary", "resolve", "network", "proxy")):
        return ErrorEtapa(f"Fallo de red al descargar; puedes reintentar. Detalle: {m}", "temporal")
    return ErrorEtapa(f"No se pudo descargar el enlace. Detalle: {m}", "entrada")


def esta_libre(ruta: Path) -> bool:
    """En Windows, un archivo que otro programa aún está escribiendo no se puede abrir para añadir."""
    try:
        with open(ruta, "ab"):
            return True
    except OSError:
        return False
