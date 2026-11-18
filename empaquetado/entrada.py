# Entrada de PyInstaller: un script fuera del paquete que llama al lanzador real.
import multiprocessing
import sys

from fabrica_studio.aplicacion import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
