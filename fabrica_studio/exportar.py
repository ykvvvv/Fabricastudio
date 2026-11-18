"""Exportar un Short para otras plataformas (TikTok, Instagram Reels, YouTube Shorts).

El video (1080×1920, H.264 + AAC) ya cumple el formato de las tres. La exportación:
- copia el MP4 a `4_exportados/<plataforma>/` con un nombre legible, para subirlo a mano;
- escribe al lado un .txt con el texto de la publicación (título + hashtags) adaptado a la plataforma;
- revisa si el banner, los subtítulos, el logo o la firma caen en la zona que la interfaz de la app
  tapa (botones, nombre de cuenta, descripción). Las zonas son APROXIMADAS: cada app cambia su diseño.
No publica nada: Fábrica Studio solo sube automáticamente a YouTube (en privado).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .errores import ErrorEtapa

# Márgenes aproximados (px en un lienzo 1080×1920) que tapa la interfaz de cada app.
ZONAS_SEGURAS = {
    "tiktok": {"nombre": "TikTok", "arriba": 150, "abajo": 420, "derecha": 140, "max_segundos": 600},
    "reels": {"nombre": "Instagram Reels", "arriba": 220, "abajo": 420, "derecha": 120, "max_segundos": 180},
    "shorts": {"nombre": "YouTube Shorts", "arriba": 120, "abajo": 380, "derecha": 120, "max_segundos": 180},
}
_NOMBRES = {"tarjeta": "El banner", "subtitulos": "Los subtítulos", "logo": "El logo", "nombre": "La firma"}


def revisar_zonas(disposicion: dict, plataforma: str) -> list[str]:
    """Avisos de elementos que quedan bajo la interfaz de la plataforma (solo en vertical)."""
    z = ZONAS_SEGURAS[plataforma]
    avisos = []
    for clave, nombre in _NOMBRES.items():
        caja = disposicion.get(clave)
        if not caja:
            continue
        arriba, abajo = caja["y"], caja["y"] + caja["h"]
        if arriba < z["arriba"]:
            avisos.append(f"{nombre} queda en la franja superior que tapa {z['nombre']} (encima de y={z['arriba']}).")
        if abajo > 1920 - z["abajo"]:
            avisos.append(f"{nombre} queda en la franja inferior que tapan los botones y la descripción de "
                          f"{z['nombre']} (bajo y={1920 - z['abajo']}).")
    return avisos


def texto_publicacion(textos: dict, plataforma: str) -> str:
    """Título sin #Shorts + descripción + hashtags. En TikTok y Reels #Shorts no aporta y se quita."""
    titulo = re.sub(r"\s*#Shorts\b", "", textos.get("titulo", ""), flags=re.I).strip()
    lineas = (textos.get("descripcion", "") or "").split("\n")
    descripcion = lineas[0].strip()
    hashtags = lineas[1].split() if len(lineas) > 1 else []
    if plataforma != "shorts":
        hashtags = [h for h in hashtags if h.lower() != "#shorts"]
    partes = [titulo]
    if descripcion and descripcion.lower() not in titulo.lower():
        partes.append(descripcion)
    partes.append(" ".join(hashtags))
    return "\n\n".join(p for p in partes if p) + "\n"


def nombre_archivo(nombre: str, jid: str) -> str:
    base = re.sub(r"[^\w\-. áéíóúüñÁÉÍÓÚÜÑ]", "_", nombre).strip(" ._")[:60] or "short"
    return f"{base}__{jid[-6:]}"


def exportar(trabajo: dict, carpeta_trabajo: Path, carpeta_exportados: Path, plataforma: str) -> dict:
    if plataforma not in ZONAS_SEGURAS:
        raise ErrorEtapa(f"Plataforma desconocida: {plataforma}. Usa tiktok, reels o shorts.", "entrada")
    video = carpeta_trabajo / "short.mp4"
    if not video.exists() or trabajo["estado"] not in ("renderizado", "subiendo", "publicado"):
        raise ErrorEtapa("El Short aún no está renderizado.", "entrada")
    z = ZONAS_SEGURAS[plataforma]
    destino = carpeta_exportados / plataforma
    destino.mkdir(parents=True, exist_ok=True)
    base = nombre_archivo(trabajo["nombre"], trabajo["id"])
    mp4, txt = destino / f"{base}.mp4", destino / f"{base}.txt"
    shutil.copyfile(video, mp4)
    texto = texto_publicacion(trabajo["textos"], plataforma)
    txt.write_text(texto, encoding="utf-8")
    avisos = revisar_zonas(trabajo["datos"].get("disposicion", {}), plataforma)
    duracion = (trabajo["datos"].get("salida") or {}).get("duracion", 0)
    if duracion > z["max_segundos"]:
        avisos.append(f"Dura {duracion:.0f} s: {z['nombre']} admite como máximo {z['max_segundos']} s en este formato.")
    return {"plataforma": z["nombre"], "video": str(mp4), "texto_archivo": str(txt), "texto": texto,
            "avisos": avisos, "zonas_aproximadas": True}
