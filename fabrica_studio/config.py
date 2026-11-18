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
FUENTE_BLACK = FUENTES / "Inter-Black.otf"
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
        self.exportados = self.base / "4_exportados"

    def crear(self) -> None:
        for p in (self.base, self.trabajos, self.secretos, self.modelos, self.recursos,
                  self.crudos, self.renderizados, self.procesados, self.exportados):
            p.mkdir(parents=True, exist_ok=True)

    def trabajo(self, job_id: str) -> Path:
        return self.trabajos / job_id


# Ajustes editables desde el panel. Los valores iniciales están pensados para
# un clip horizontal 16:9 sobre un lienzo 1080x1920.
AJUSTES_POR_DEFECTO: dict = {
    # --- Diseño del video (valores medidos sobre el Short de referencia de PaltitaClips) ---
    "creador": "Jongottii",           # nombre usado en títulos y descripciones
    "firma": "@jongottii",            # texto bajo el logo (vacío = usar el nombre del creador)
    "recortar_bordes": True,          # quitar franjas negras que traiga el clip original
    "video_desplazamiento_y": -80,    # px; negativo sube el video respecto al centro
    "video_alto_max": 1000,           # alto máximo del video dentro del lienzo
    "banner_tamano": 92,              # tamaño de letra máximo del banner
    "banner_ancho": 1044,             # ancho de la tarjeta blanca
    "banner_separacion": 10,          # espacio entre tarjeta y video (negativo = se superpone)
    "banner_radio": 22,               # redondeo de las esquinas de la tarjeta
    "banner_color": "#E3222A",
    "sub_tamano": 66,
    "sub_desplazamiento": 30,         # px bajo el borde inferior del video (negativo = encima del video)
    "sub_palabras_max": 3,
    "sub_caracteres_max": 20,
    "sub_resaltar": True,             # la palabra que se está diciendo cambia de color
    "sub_color_resalte": "#53FC18",
    "logo_alto": 126,
    "logo_separacion": 4,
    "nombre_tamano": 40,
    "nombre_color": "#D9D9D9",
    "mostrar_logo": True,
    "mostrar_nombre": True,
    # --- Estilo de encuadre ---
    # clasico: video completo centrado con tarjeta (siempre disponible).
    # completo: pantalla completa 9:16 que sigue los rostros, subtítulos sobre el video.
    "estilo": "clasico",
    "completo_zoom": 100,             # % sobre el recorte 9:16 mínimo (100 = sin zoom extra)
    "completo_banner": True,          # mostrar la tarjeta del banner arriba
    "completo_banner_y": 150,
    "completo_sub_y": 1250,           # posición de los subtítulos sobre el video
    "completo_sub_tamano": 84,
    "completo_mayusculas": True,
    "completo_logo_alto": 80,
    "completo_logo_y": 1610,
    # dividido: cámara del streamer arriba (zoom) y contenido abajo; sin banner ni firma por defecto.
    "dividido_proporcion": 45,        # % del alto para la cámara
    "dividido_sub_y": 1430,
    "dividido_sub_tamano": 96,
    "dividido_logo_alto": 52,
    "dividido_logo_y": 1810,
    "dividido_banner": False,
    "dividido_firma": False,
    # --- Transcripción ---
    "whisper_modelo": "small",        # tiny, base, small, medium, large-v3...
    "whisper_dispositivo": "cpu",     # cpu (seguro), auto o cuda (GPU NVIDIA, requiere cuDNN)
    "idioma": "es",
    # Frase de contexto para Whisper: orienta el reconocimiento (jerga, nombres) sin insertar nada.
    # Debe estar escrita como se habla, con puntuación: una lista de palabras sueltas empeora la transcripción
    # (comprobado: pierde tildes y puntuación).
    "vocabulario": "Stream de Jongottii en Kick, en español de Chile. ¿Cachai? Ya po, altiro. ¡Qué fome, weón! Estuvo bacán.",
    # Correcciones de escritura para subtítulos y textos, una por línea: «como sale => como debe verse».
    "correcciones": "",
    # --- Textos ---
    "proveedor_textos": "auto",       # auto (Gemini si hay clave, si no local), gemini, local
    "gemini_modelo": "",              # vacío = elegir entre los modelos que la API liste
    # Tema fijo del canal. "gta6": el usuario declara que todo el contenido es de GTA 6 → títulos con «GTA 6»,
    # hashtags fijos y categoría Gaming. "" = detectar por la transcripción.
    "tema": "",
    "hashtags_fijos": "#GTA6 #GTAVI #GTA #Gaming",  # se añaden a la descripción solo con tema = "gta6"
    "momentos_cantidad": 6,           # propuestas por video largo
    "momentos_auto": False,           # crear Shorts de las propuestas sin esperar a que el usuario elija
    "momentos_auto_solo_ia": True,    # automático solo si las propuestas vienen de Gemini (la heurística es débil)
    # --- Publicación ---
    "subida_automatica": False,       # False = esperar revisión antes de subir
    "youtube_canal_id": "",           # canal confirmado por el usuario
    "youtube_canal_nombre": "",
    "contenido_para_ninos": False,
    "subidas_pausadas_hasta": 0,      # estado interno: hora (epoch) en que se reanudan las subidas tras el límite diario
    # --- Carpeta vigilada ---
    "vigilar_carpeta": True,
    "segundos_estable": 6,            # un archivo debe llevar este tiempo sin cambiar
}

# Rangos válidos (mín, máx) de los ajustes numéricos, y valores permitidos de las listas.
LIMITES: dict = {
    "video_desplazamiento_y": (-800, 800), "video_alto_max": (300, 1920),
    "banner_tamano": (30, 200), "banner_ancho": (300, 1080), "banner_separacion": (-200, 300),
    "banner_radio": (0, 80), "sub_tamano": (24, 160), "sub_desplazamiento": (-600, 600),
    "sub_palabras_max": (1, 12), "sub_caracteres_max": (8, 60), "logo_alto": (20, 400),
    "logo_separacion": (-100, 300), "nombre_tamano": (12, 120),
    "completo_zoom": (100, 300), "completo_banner_y": (0, 1700), "completo_sub_y": (200, 1850),
    "completo_sub_tamano": (24, 180), "completo_logo_alto": (20, 400), "completo_logo_y": (200, 1900),
    "dividido_proporcion": (30, 60), "dividido_sub_y": (200, 1850), "dividido_sub_tamano": (24, 180),
    "dividido_logo_alto": (20, 300), "dividido_logo_y": (200, 1900),
    "momentos_cantidad": (1, 20), "segundos_estable": (0, 600),
}
OPCIONES: dict = {
    "estilo": ("clasico", "completo", "dividido", "auto"), "whisper_dispositivo": ("auto", "cpu", "cuda"),
    "proveedor_textos": ("auto", "gemini", "local"), "tema": ("", "gta6"),
}
COLORES = ("banner_color", "sub_color_resalte", "nombre_color")

# Ajustes que, al cambiar, obligan a renderizar de nuevo (pero no a transcribir).
AJUSTES_DE_DISENO = [k for k in AJUSTES_POR_DEFECTO if k.split("_")[0] in
                     ("video", "banner", "sub", "logo", "nombre", "mostrar", "completo", "dividido")] + [
                         "creador", "firma", "recortar_bordes", "estilo"]

LIENZO_ANCHO = 1080
LIENZO_ALTO = 1920
PUERTO = int(os.environ.get("FABRICA_PUERTO", "8765"))
