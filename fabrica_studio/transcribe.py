"""Transcripción local con faster-whisper, con tiempos por palabra.

La transcripción refleja lo que se dijo: no se corrige ni se reescribe. El
modelo se carga una sola vez y se reutiliza entre trabajos.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from .errores import ErrorEtapa

# Descarga del modelo por HTTP normal: el protocolo "xet" de Hugging Face usa hosts
# adicionales que algunas redes bloquean.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

log = logging.getLogger("fabrica.transcribe")
_lock = threading.Lock()
_cache: dict = {}


def _cargar(modelo: str, dispositivo: str, carpeta_modelos: Path):
    """Devuelve (modelo, descripción). Con 'auto' prueba la GPU y cae a CPU si falla."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ErrorEtapa("Falta faster-whisper. Ejecuta scripts\\instalar.ps1.", "herramienta")

    intentos = []
    if dispositivo in ("auto", "cuda"):
        # int8_float16 cabe con holgura en 4 GB de VRAM (GTX 1650).
        intentos.append(("cuda", "int8_float16"))
    if dispositivo in ("auto", "cpu"):
        intentos.append(("cpu", "int8"))
    ultimo = None
    for dev, tipo in intentos:
        clave = (modelo, dev)
        if clave in _cache:
            return _cache[clave], f"{modelo} en {dev}"
        try:
            try:
                # Si el modelo ya está descargado se usa sin tocar internet (funciona sin conexión).
                m = WhisperModel(modelo, device=dev, compute_type=tipo, download_root=str(carpeta_modelos),
                                 local_files_only=True)
            except Exception:
                m = WhisperModel(modelo, device=dev, compute_type=tipo, download_root=str(carpeta_modelos))
            _cache.clear()
            _cache[clave] = m
            return m, f"{modelo} en {dev}"
        except Exception as e:  # CUDA ausente, sin red para descargar, modelo inexistente...
            ultimo = e
            log.warning("No se pudo cargar Whisper %s en %s: %s", modelo, dev, e)
    raise ErrorEtapa(
        f"No se pudo cargar el modelo de Whisper '{modelo}': {ultimo}. "
        "La primera vez se descarga de internet; comprueba la conexión y el nombre del modelo.", "modelo")


def _leer_wav(ruta: Path):
    """Lee el WAV mono de 16 kHz que genera FFmpeg, sin depender del decodificador de PyAV."""
    import wave

    import numpy as np
    with wave.open(str(ruta), "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ErrorEtapa("El audio extraído no tiene el formato esperado (16 kHz mono).", "interno")
        datos = w.readframes(w.getnframes())
    return np.frombuffer(datos, dtype=np.int16).astype(np.float32) / 32768.0


def transcribir(audio: Path, modelo: str, dispositivo: str, idioma: str, carpeta_modelos: Path) -> dict:
    with _lock:
        m, descripcion = _cargar(modelo, dispositivo, carpeta_modelos)
        try:
            segmentos, info = m.transcribe(
                _leer_wav(audio), language=idioma or None, word_timestamps=True,
                vad_filter=True, beam_size=5, condition_on_previous_text=False)
            palabras, segs = [], []
            for s in segmentos:
                segs.append({"inicio": round(s.start, 3), "fin": round(s.end, 3), "texto": s.text.strip()})
                for w in s.words or []:
                    t = w.word.strip()
                    if t:
                        palabras.append({"inicio": round(w.start, 3), "fin": round(w.end, 3), "texto": t})
        except Exception as e:
            if "cuda" in descripcion and dispositivo == "auto":
                # La GPU cargó pero falló al ejecutar (típico: faltan cuDNN/cuBLAS). Reintenta en CPU.
                log.warning("Fallo en GPU, reintento en CPU: %s", e)
                _cache.clear()
                return _transcribir_cpu(audio, modelo, idioma, carpeta_modelos)
            raise ErrorEtapa(f"Falló la transcripción: {e}", "interno")
    return {"idioma": info.language, "motor": f"faster-whisper {descripcion}",
            "texto": " ".join(s["texto"] for s in segs).strip(), "segmentos": segs, "palabras": palabras}


def _transcribir_cpu(audio: Path, modelo: str, idioma: str, carpeta_modelos: Path) -> dict:
    _lock.release()
    try:
        return transcribir(audio, modelo, "cpu", idioma, carpeta_modelos)
    finally:
        _lock.acquire()
