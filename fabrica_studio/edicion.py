"""Edición de tiempos de un clip: conservar solo los tramos elegidos.

La edición no es destructiva:
- El archivo original (entrada.*) nunca se modifica.
- Los tramos elegidos se guardan en edicion.json y se renderizan en editado.mp4.
- La transcripción original se conserva en transcripcion_original.json; la del clip editado
  se recalcula desplazando los tiempos de cada palabra (no se vuelve a transcribir).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .errores import ErrorEtapa
from .media import ejecutar, herramienta

TRAMO_MIN = 0.3          # segundos
TOTAL_MIN = 3.0
TOTAL_MAX = 180.0


def validar_tramos(tramos, duracion: float) -> list[list[float]]:
    """Tramos [[inicio, fin], ...] en segundos del original: ordenados, sin solaparse y dentro del video.
    Tramos que se tocan o se solapan se unen. Una lista vacía significa «sin edición»."""
    if not isinstance(tramos, list):
        raise ErrorEtapa("La edición debe ser una lista de tramos [inicio, fin].", "entrada")
    limpios = []
    for t in tramos:
        try:
            ini, fin = round(max(0.0, float(t[0])), 3), round(min(float(duracion), float(t[1])), 3)
        except (TypeError, ValueError, IndexError):
            raise ErrorEtapa("Cada tramo debe tener inicio y fin en segundos.", "entrada")
        if fin - ini >= TRAMO_MIN:
            limpios.append([ini, fin])
    limpios.sort()
    unidos: list[list[float]] = []
    for ini, fin in limpios:
        if unidos and ini <= unidos[-1][1] + 0.05:
            unidos[-1][1] = max(unidos[-1][1], fin)
        else:
            unidos.append([ini, fin])
    if not unidos:
        return []
    total = sum(f - i for i, f in unidos)
    if total < TOTAL_MIN:
        raise ErrorEtapa(f"El clip editado dura {total:.1f} s: debe durar al menos {TOTAL_MIN:.0f} s.", "entrada")
    if total > TOTAL_MAX:
        raise ErrorEtapa(f"El clip editado dura {total:.0f} s: un Short admite como máximo {TOTAL_MAX:.0f} s.", "entrada")
    return unidos


def es_completo(tramos: list[list[float]], duracion: float) -> bool:
    return len(tramos) == 1 and tramos[0][0] <= 0.05 and tramos[0][1] >= duracion - 0.05


def huella(tramos: list[list[float]]) -> str:
    return hashlib.sha256(json.dumps(tramos).encode()).hexdigest()[:16]


def nuevo_tiempo(t: float, tramos: list[list[float]]) -> float | None:
    """Tiempo en el clip editado de un instante del original (None si cae en una parte cortada)."""
    acumulado = 0.0
    for ini, fin in tramos:
        if ini - 1e-6 <= t <= fin + 1e-6:
            return round(acumulado + min(max(t, ini), fin) - ini, 3)
        acumulado += fin - ini
    return None


def remapear_transcripcion(tr: dict, tramos: list[list[float]]) -> dict:
    """Transcripción del clip editado: solo las palabras que quedan, con sus tiempos nuevos.
    Una palabra se conserva si su centro cae dentro de un tramo."""
    palabras = []
    for p in tr.get("palabras", []):
        centro = (p["inicio"] + p["fin"]) / 2
        for ini, fin in tramos:
            if ini <= centro <= fin:
                a = nuevo_tiempo(max(p["inicio"], ini), tramos)
                b = nuevo_tiempo(min(p["fin"], fin), tramos)
                if a is not None and b is not None and b > a:
                    palabras.append({**p, "inicio": a, "fin": b})
                break
    segmentos = []
    for s in tr.get("segmentos", []):
        a, b = nuevo_tiempo(s["inicio"], tramos), nuevo_tiempo(s["fin"], tramos)
        if a is not None and b is not None and b > a:
            segmentos.append({**s, "inicio": a, "fin": b})
    return {**tr, "motor": tr.get("motor", "") + " (editado)", "texto": " ".join(p["texto"] for p in palabras),
            "palabras": palabras, "segmentos": segmentos}


def cortar(original: Path, tramos: list[list[float]], carpeta: Path, tiene_audio: bool,
           salida: str = "editado.mp4") -> Path:
    """Une los tramos del original en un solo archivo (recodifica para cortar al fotograma exacto)."""
    partes, etiquetas = [], []
    for i, (ini, fin) in enumerate(tramos):
        partes.append(f"[0:v]trim=start={ini}:end={fin},setpts=PTS-STARTPTS[v{i}]")
        etiquetas.append(f"[v{i}]")
        if tiene_audio:
            partes.append(f"[0:a]atrim=start={ini}:end={fin},asetpts=PTS-STARTPTS[a{i}]")
            etiquetas.append(f"[a{i}]")
    n = len(tramos)
    partes.append("".join(etiquetas) + f"concat=n={n}:v=1:a={1 if tiene_audio else 0}[v]" + ("[a]" if tiene_audio else ""))
    temporal = "editado_tmp.mp4"
    cmd = [herramienta("ffmpeg"), "-y", "-v", "error", "-i", original.name, "-filter_complex", ";".join(partes),
           "-map", "[v]"] + (["-map", "[a]", "-c:a", "aac", "-b:a", "192k"] if tiene_audio else []) + [
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", temporal]
    ejecutar(cmd, cwd=carpeta)
    from .render import reemplazar
    reemplazar(carpeta / temporal, carpeta / salida)
    return carpeta / salida


def picos_audio(video: Path, puntos: int = 400) -> list[float]:
    """Forma de onda simplificada (0–1) para dibujar la línea de tiempo del editor."""
    import subprocess
    import numpy as np
    cmd = [herramienta("ffmpeg"), "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "8000",
           "-f", "s16le", "-"]
    r = subprocess.run(cmd, capture_output=True, timeout=300)
    datos = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32)
    if datos.size == 0:
        return []
    bloques = np.array_split(np.abs(datos), min(puntos, datos.size))
    valores = np.array([b.max() if b.size else 0 for b in bloques])
    maximo = valores.max() or 1.0
    return [round(float(v / maximo), 3) for v in valores]
