"""Comprobación del equipo: qué está instalado y qué funciona de verdad.

Uso:  python -m fabrica_studio.diagnostico          (añade --rapido para omitir la autoprueba)

Pensado para ejecutarse en el PC de destino y pegar la salida en el chat: así se
sabe qué funciona en esa máquina en lugar de suponerlo.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import AJUSTES_POR_DEFECTO, FUENTE_BLACK, FUENTE_BOLD, Rutas


def _salida(cmd: list[str], timeout: int = 20) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return ""


def revisar(rutas: Rutas | None = None, ajustes: dict | None = None, autoprueba: bool = True) -> list[dict]:
    """Lista de comprobaciones: {nombre, ok (True/False/None = opcional ausente), detalle}."""
    rutas = rutas or Rutas()
    a = ajustes or dict(AJUSTES_POR_DEFECTO)
    res: list[dict] = []

    def anotar(nombre: str, ok, detalle: str = "") -> None:
        res.append({"nombre": nombre, "ok": ok, "detalle": detalle})

    anotar("Sistema", True, f"{platform.system()} {platform.release()} · {platform.machine()}")
    v = sys.version_info
    anotar("Python", v >= (3, 10), f"{v.major}.{v.minor}.{v.micro}" + ("" if v >= (3, 10) else " (se necesita 3.10 o superior)"))

    from .media import encontrar
    ffmpeg, ffprobe = encontrar("ffmpeg"), encontrar("ffprobe")
    if ffmpeg and ffprobe:
        version = _salida([ffmpeg, "-version"]).splitlines()[0:1]
        anotar("FFmpeg", True, version[0][:70] if version else ffmpeg)
        filtros, codecs = _salida([ffmpeg, "-hide_banner", "-filters"]), _salida([ffmpeg, "-hide_banner", "-encoders"])
        anotar("FFmpeg: subtítulos (libass)", " ass " in filtros,
               "" if " ass " in filtros else "Esta compilación no trae el filtro «ass». Usa la de Gyan (winget install Gyan.FFmpeg).")
        anotar("FFmpeg: H.264 y AAC", "libx264" in codecs and " aac " in codecs,
               "" if "libx264" in codecs else "Falta el codificador libx264.")
    else:
        anotar("FFmpeg", False, "No está en el PATH. Windows: winget install Gyan.FFmpeg y reabrir PowerShell.")

    anotar("Fuentes incluidas", FUENTE_BOLD.exists() and FUENTE_BLACK.exists(), "Inter (OFL)")

    try:
        rutas.crear()
        prueba = rutas.base / ".prueba_escritura"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink()
        libre = shutil.disk_usage(rutas.base).free / 1e9
        anotar("Carpeta de datos", libre > 3, f"{rutas.base} · {libre:.0f} GB libres" + ("" if libre > 3 else " (poco espacio)"))
    except OSError as e:
        anotar("Carpeta de datos", False, f"No se puede escribir en {rutas.base}: {e}")

    try:
        import ctranslate2
        import faster_whisper
        anotar("faster-whisper", True, f"{faster_whisper.__version__} · ctranslate2 {ctranslate2.__version__}")
        try:
            gpus = ctranslate2.get_cuda_device_count()
        except Exception:
            gpus = 0
        smi = _salida(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]).strip() \
            if shutil.which("nvidia-smi") else ""
        if gpus:
            anotar("GPU para Whisper (opcional)", True, f"{smi or 'CUDA disponible'} · puedes probar Dispositivo = GPU en Ajustes")
        else:
            anotar("GPU para Whisper (opcional)", None,
                   (f"Tarjeta detectada ({smi}), pero CUDA no está disponible para Whisper; " if smi else "Sin GPU utilizable; ")
                   + "se usa CPU, que funciona igual aunque más lento.")
    except ImportError as e:
        anotar("faster-whisper", False, f"No instalado ({e}). Ejecuta scripts\\instalar.ps1.")

    modelo = a["whisper_modelo"]
    descargado = any(rutas.modelos.glob(f"*whisper-{modelo}*"))
    anotar(f"Modelo Whisper «{modelo}»", True if descargado else None,
           "Descargado" if descargado else "Se descargará en el primer clip (requiere internet esa vez).")

    from . import reencuadre
    ok, motivo = reencuadre.disponible()
    anotar("Seguimiento de rostros (pantalla completa)", True if ok else None,
           motivo if ok else motivo + " Sin esto, el estilo pantalla completa queda centrado.")

    try:
        import yt_dlp
        anotar("yt-dlp (enlaces de Kick)", True, yt_dlp.version.__version__)
    except ImportError:
        anotar("yt-dlp (enlaces de Kick)", None, "No instalado: la importación por enlace no funcionará.")

    if autoprueba and ffmpeg and ffprobe:
        res.append(_autoprueba(a))
    return res


def _autoprueba(a: dict) -> dict:
    """Renderiza un clip sintético de 2 s (sin Whisper ni red) y comprueba el resultado."""
    from . import render
    from .media import ejecutar, herramienta, sondear
    try:
        with tempfile.TemporaryDirectory(prefix="fabrica_diag_", ignore_cleanup_errors=True) as tmp:
            carpeta = Path(tmp)
            ejecutar([herramienta("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=2",
                      "-f", "lavfi", "-i", "sine=f=440:d=2", "-c:v", "libx264", "-preset", "ultrafast",
                      "-pix_fmt", "yuv420p", "-c:a", "aac", "entrada.mp4"], cwd=carpeta, timeout=120)
            r = render.renderizar(carpeta, "entrada.mp4", sondear(carpeta / "entrada.mp4"), "PRUEBA DE RENDER",
                                  [{"inicio": 0.2, "fin": 1.8, "texto": "subtítulo de prueba ñ á"}], a, carpeta)
            p = r["propiedades"]
            return {"nombre": "Autoprueba de render", "ok": True,
                    "detalle": f"{p['ancho']}×{p['alto']} · {p['codec_video']}/{p['codec_audio']} · {p['duracion']:.1f} s"}
    except Exception as e:
        return {"nombre": "Autoprueba de render", "ok": False, "detalle": str(e)[:400]}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):          # consolas de Windows sin UTF-8
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    resultados = revisar(autoprueba="--rapido" not in sys.argv)
    print("\n  Diagnóstico de Fábrica Studio\n")
    for r in resultados:
        marca = {True: "[ OK ]", False: "[FALLA]", None: "[ --  ]"}[r["ok"]]
        print(f"  {marca} {r['nombre']}: {r['detalle']}")
    fallos = [r for r in resultados if r["ok"] is False]
    print("\n  " + ("Todo lo necesario funciona." if not fallos else f"{len(fallos)} comprobación(es) fallan: revisa las líneas [FALLA].")
          + "\n  Las líneas [ -- ] son opcionales.\n")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
