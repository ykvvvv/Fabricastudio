"""Punto de entrada del programa de Windows (FabricaStudio.exe).

    FabricaStudio.exe                       abre el panel en el navegador (y lo arranca si no está abierto)
    FabricaStudio.exe --sin-navegador       arranca el panel sin abrir el navegador
    FabricaStudio.exe --diagnostico         comprueba el equipo (incluye un render de prueba)
    FabricaStudio.exe --mcp                 servidor MCP para Claude Code (stdio)
    FabricaStudio.exe --restablecer-contrasena
    FabricaStudio.exe --version
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
import urllib.request
import webbrowser

from . import __version__
from .config import PUERTO


def _responde(timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/api/sesion", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _abrir_cuando_responda() -> None:
    for _ in range(120):
        if _responde():
            webbrowser.open(f"http://127.0.0.1:{PUERTO}")
            return
        time.sleep(0.5)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="FabricaStudio", description="Fábrica Studio: clips a YouTube Shorts.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--diagnostico", action="store_true")
    g.add_argument("--mcp", action="store_true")
    g.add_argument("--restablecer-contrasena", action="store_true")
    g.add_argument("--version", action="store_true")
    p.add_argument("--sin-navegador", action="store_true")
    a = p.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure") and not a.mcp:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.version:
        print(f"Fábrica Studio {__version__}")
        return 0
    if a.diagnostico:
        from .diagnostico import main as diag
        r = diag()
        if sys.stdin is not None and sys.stdin.isatty():
            input("\n  Pulsa Enter para cerrar…")
        return r
    if a.mcp:
        from .mcp_servidor import main as mcp
        mcp()
        return 0
    if a.restablecer_contrasena:
        sys.argv = ["cuentas", "--restablecer"]
        from .cuentas import main as cuentas
        return cuentas()

    if _responde():                       # ya hay un panel abierto: solo mostrarlo
        print("  Fábrica Studio ya está abierto; abriendo el panel en el navegador…")
        if not a.sin_navegador:
            webbrowser.open(f"http://127.0.0.1:{PUERTO}")
        return 0
    if not a.sin_navegador:
        threading.Thread(target=_abrir_cuando_responda, daemon=True).start()
    from .server import main as servidor
    servidor()
    return 0


if __name__ == "__main__":
    sys.exit(main())
