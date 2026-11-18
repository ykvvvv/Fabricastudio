# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: genera dist/FabricaStudio/ (modo carpeta: arranca más rápido y da menos falsos
# positivos de antivirus que un único .exe). Se ejecuta desde la raíz del repositorio:
#     pyinstaller empaquetado/FabricaStudio.spec --noconfirm
# FFmpeg no se incluye aquí: el flujo de GitHub Actions lo copia a dist/FabricaStudio/ffmpeg/.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

RAIZ = Path(SPECPATH).parent
datas = [
    (str(RAIZ / "fabrica_studio" / "web"), "fabrica_studio/web"),
    (str(RAIZ / "fabrica_studio" / "assets"), "fabrica_studio/assets"),
]
binaries = []
hiddenimports = collect_submodules("fabrica_studio") + collect_submodules("uvicorn") + ["multipart"]
# mcp: sin su herramienta de línea de comandos (mcp.cli necesita typer y no se usa).
hiddenimports += collect_submodules("mcp", filter=lambda n: not n.startswith("mcp.cli"))
datas += collect_data_files("mcp")
for paquete in ("faster_whisper", "ctranslate2", "onnxruntime", "av", "tokenizers", "yt_dlp", "curl_cffi"):
    try:
        d, b, h = collect_all(paquete)
    except Exception as e:                      # paquete opcional ausente: el programa avisa en el diagnóstico
        print(f"[spec] no se pudo recoger {paquete}: {e}")
        continue
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(RAIZ / "empaquetado" / "entrada.py")],
    pathex=[str(RAIZ)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "matplotlib", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
icono = RAIZ / "empaquetado" / "icono.ico"
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="FabricaStudio",
    console=True,                 # ventana con el estado del servidor; cerrarla detiene el programa
    icon=str(icono) if icono.exists() else None,
    version=str(RAIZ / "empaquetado" / "version.txt") if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="FabricaStudio")
