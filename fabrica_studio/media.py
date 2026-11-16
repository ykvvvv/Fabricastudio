"""Comprobación de archivos de video con ffprobe/ffmpeg."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .errores import ErrorEtapa

EXTENSIONES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def herramienta(nombre: str) -> str:
    ruta = shutil.which(nombre)
    if not ruta:
        raise ErrorEtapa(
            f"No se encontró {nombre}. Instala FFmpeg y comprueba que esté en el PATH "
            "(en Windows: winget install Gyan.FFmpeg y vuelve a abrir PowerShell).", "herramienta")
    return ruta


def ejecutar(cmd: list[str], cwd: Path | None = None, timeout: int = 3600) -> subprocess.CompletedProcess:
    """Ejecuta un comando y, si falla, conserva el final de stderr: ahí está la causa real."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ErrorEtapa(f"{Path(cmd[0]).name} superó el tiempo máximo ({timeout} s).", "temporal")
    if r.returncode != 0:
        cola = "\n".join((r.stderr or "").strip().splitlines()[-12:])
        raise ErrorEtapa(f"{Path(cmd[0]).name} terminó con código {r.returncode}:\n{cola}", "herramienta")
    return r


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def sondear(ruta: Path) -> dict:
    """Propiedades reales del archivo. Tiene en cuenta la rotación (videos de móvil)."""
    if not ruta.exists() or ruta.stat().st_size == 0:
        raise ErrorEtapa("El archivo no existe o está vacío.", "entrada")
    try:
        r = ejecutar([herramienta("ffprobe"), "-v", "error", "-print_format", "json",
                      "-show_format", "-show_streams", str(ruta)], timeout=120)
    except ErrorEtapa as e:
        if e.tipo == "herramienta" and "No se encontró" in str(e):
            raise
        raise ErrorEtapa(f"El archivo no es un video legible (¿copia incompleta o dañado?).\n{e}", "entrada")
    info = json.loads(r.stdout)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"
                  and s.get("disposition", {}).get("attached_pic", 0) != 1), None)
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not video:
        raise ErrorEtapa("El archivo no contiene una pista de video.", "entrada")
    ancho, alto = int(video["width"]), int(video["height"])
    rotacion = 0
    for sd in video.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotacion = int(float(sd["rotation"]))
    if abs(rotacion) % 180 == 90:
        ancho, alto = alto, ancho
    duracion = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    if duracion <= 0:
        raise ErrorEtapa("No se pudo determinar la duración del video.", "entrada")
    try:
        num, den = video.get("avg_frame_rate", "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    return {
        "ancho": ancho, "alto": alto, "duracion": round(duracion, 3), "fps": round(fps, 3),
        "codec_video": video.get("codec_name", ""), "codec_audio": audio.get("codec_name", "") if audio else "",
        "tiene_audio": bool(audio), "tamano_bytes": ruta.stat().st_size,
        "orientacion": "vertical" if alto > ancho else ("cuadrado" if alto == ancho else "horizontal"),
    }


def extraer_audio(video: Path, destino: Path) -> Path:
    """WAV mono a 16 kHz: el formato que espera Whisper."""
    ejecutar([herramienta("ffmpeg"), "-y", "-v", "error", "-i", str(video), "-vn",
              "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(destino)])
    return destino


def detectar_bordes(video: Path, propiedades: dict) -> dict | None:
    """Detecta franjas negras incrustadas en el video (p. ej. un clip horizontal dentro
    de un 9:16). Devuelve {w, h, x, y} del área útil o None si no hay nada que recortar.

    Analiza varios instantes y se queda con el área más grande: así una escena oscura
    puntual no provoca un recorte excesivo."""
    import re
    ancho, alto, dur = propiedades["ancho"], propiedades["alto"], propiedades["duracion"]
    areas = []
    for frac in (0.15, 0.4, 0.65, 0.9):
        try:
            r = ejecutar([herramienta("ffmpeg"), "-hide_banner", "-ss", f"{dur * frac:.2f}", "-i", str(video),
                          "-frames:v", "12", "-vf", "cropdetect=limit=16:round=2:reset=0", "-f", "null", "-"],
                         timeout=120)
        except ErrorEtapa:
            continue
        hallados = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", r.stderr)
        if hallados:
            areas.append(tuple(int(v) for v in hallados[-1]))
    if not areas:
        return None
    # Unión de las áreas detectadas: el rectángulo que contiene todas.
    x0 = min(a[2] for a in areas); y0 = min(a[3] for a in areas)
    x1 = max(a[2] + a[0] for a in areas); y1 = max(a[3] + a[1] for a in areas)
    w, h = (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2
    if w * h < ancho * alto * 0.08 or w < 64 or h < 64:   # casi todo negro: no fiarse
        return None
    if w * h > ancho * alto * 0.94:                  # bordes despreciables
        return None
    return {"w": w, "h": h, "x": x0, "y": y0}
