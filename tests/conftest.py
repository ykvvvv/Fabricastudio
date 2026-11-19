import subprocess

import pytest

from fabrica_studio import textos, transcribe
from fabrica_studio.config import Rutas
from fabrica_studio.pipeline import Fabrica

PALABRAS = [{"inicio": i * 0.4, "fin": i * 0.4 + 0.35, "texto": p} for i, p in enumerate(
    "Oye chat, no lo van a creer. Encontré la paltita más grande de Chile, hermano.".split())]


@pytest.fixture(autouse=True)
def _gemini_sin_memoria():
    """Cada prueba empieza sin modelos de Gemini marcados como saturados o sin cuota (textos._saturados)."""
    textos._saturados.clear()
    yield
    textos._saturados.clear()


@pytest.fixture(scope="session")
def clip(tmp_path_factory):
    """Clip horizontal de 3 s con audio, generado con FFmpeg."""
    ruta = tmp_path_factory.mktemp("clips") / "horizontal.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=3",
                    "-f", "lavfi", "-i", "sine=f=440:d=3", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(ruta)], check=True)
    return ruta


@pytest.fixture
def fabrica(tmp_path, monkeypatch):
    """Fábrica con datos temporales y una transcripción fija (no descarga Whisper)."""
    llamadas = {"n": 0}

    def falsa(audio, modelo, dispositivo, idioma, carpeta, vocabulario=""):
        llamadas["n"] += 1
        llamadas["vocabulario"] = vocabulario
        return {"idioma": "es", "motor": "prueba", "texto": " ".join(p["texto"] for p in PALABRAS),
                "segmentos": [], "palabras": PALABRAS}

    monkeypatch.setattr(transcribe, "transcribir", falsa)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    f = Fabrica(Rutas(tmp_path / "datos"))
    f.transcripciones = llamadas
    return f
