"""Rutas y ajustes. Todo lo que cambia entre equipos vive en la carpeta de datos.

La carpeta de datos (por defecto ./datos) queda fuera del repositorio: contiene
la base de datos, los clips, los modelos y las credenciales.
"""
from __future__ import annotations

import os
from pathlib import Path

PAQUETE = Path(__file__).resolve().parent
RAIZ = PAQUETE.parent
FUENTES = PAQUETE / "assets" / "fonts"
FUENTE_BOLD = FUENTES / "Inter-Bold.otf"
FUENTE_EXTRABOLD = FUENTES / "Inter-ExtraBold.otf"
WEB = PAQUETE / "web"


def carpeta_datos() -> Path:
    return Path(os.environ.get("FABRICA_DATOS", RAIZ / "datos")).resolve()


class Rutas:
    """Calcula las rutas a partir de la carpeta de datos (se puede cambiar en tests)."""

    def __init__(self, base: Path | None = None):
        self.base = Path(base) if base else carpeta_datos()
        self.db = self.base / "fabrica.db"
        self.trabajos = self.base / "trabajos"
        self.secretos = self.base / "secretos"
        self.modelos = self.base / "modelos"
        self.recursos = self.base / "recursos"  # logo subido por el usuario
        self.crudos = self.base / "1_clips_crudos"
        self.renderizados = self.base / "2_shorts_renderizados"
        self.procesados = self.base / "3_procesados_ok"

    def crear(self) -> None:
        for p in (self.base, self.trabajos, self.secretos, self.modelos, self.recursos,
                  self.crudos, self.renderizados, self.procesados):
            p.mkdir(parents=True, exist_ok=True)

    def trabajo(self, job_id: str) -> Path:
        return self.trabajos / job_id


# Ajustes editables desde el panel. Los valores iniciales están pensados para
# un clip horizontal 16:9 sobre un lienzo 1080x1920.
AJUSTES_POR_DEFECTO: dict = {
    # --- Diseño del video ---
    "creador": "Jongottii",
    "video_desplazamiento_y": -120,   # px; negativo sube el video respecto al centro
    "video_alto_max": 1000,           # alto máximo del video dentro del lienzo
    "banner_tamano": 76,              # tamaño de letra máximo del banner
    "banner_ancho": 980,              # ancho de la tarjeta blanca
    "banner_separacion": 40,          # espacio entre tarjeta y video
    "banner_color": "#E0101A",
    "sub_tamano": 62,
    "sub_desplazamiento": 36,         # px bajo el borde inferior del video (negativo = encima del video)
    "sub_palabras_max": 4,
    "sub_caracteres_max": 22,
    "logo_alto": 84,
    "logo_separacion": 28,
    "nombre_tamano": 42,
    "mostrar_logo": True,
    "mostrar_nombre": True,
    # --- Transcripción ---
    "whisper_modelo": "small",        # tiny, base, small, medium, large-v3...
    "whisper_dispositivo": "cpu",     # cpu (seguro), auto o cuda (GPU NVIDIA, requiere cuDNN)
    "idioma": "es",
    # --- Textos ---
    "proveedor_textos": "auto",       # auto (Gemini si hay clave, si no local), gemini, local
    "gemini_modelo": "",              # vacío = elegir entre los modelos que la API liste
    # --- Publicación ---
    "subida_automatica": False,       # False = esperar revisión antes de subir
    "youtube_canal_id": "",           # canal confirmado por el usuario
    "youtube_canal_nombre": "",
    "contenido_para_ninos": False,
    # --- Carpeta vigilada ---
    "vigilar_carpeta": True,
    "segundos_estable": 6,            # un archivo debe llevar este tiempo sin cambiar
}

# Ajustes que, al cambiar, obligan a renderizar de nuevo (pero no a transcribir).
AJUSTES_DE_DISENO = [k for k in AJUSTES_POR_DEFECTO if k.split("_")[0] in
                     ("video", "banner", "sub", "logo", "nombre", "mostrar")] + ["creador"]

LIENZO_ANCHO = 1080
LIENZO_ALTO = 1920
PUERTO = int(os.environ.get("FABRICA_PUERTO", "8765"))
