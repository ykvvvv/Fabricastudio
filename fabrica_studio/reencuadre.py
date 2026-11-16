"""Estilo «pantalla completa»: recorta el video a 9:16 siguiendo los rostros.

Funcionamiento:
1. `analizar()` extrae fotogramas a baja resolución (5 por segundo) con FFmpeg y
   detecta rostros con YuNet (OpenCV). El resultado se guarda en encuadre.json,
   así que cambiar el diseño no repite el análisis.
2. `trayectoria()` convierte esas detecciones en el movimiento de una «cámara»
   virtual: sigue al rostro principal, ignora temblores pequeños (zona muerta),
   se desplaza suave en movimientos medianos y corta de golpe en saltos grandes
   (cambio de plano o de persona), como hace un editor.
3. `comandos_sendcmd()` traduce la trayectoria a órdenes que FFmpeg aplica al
   filtro crop durante el render.

Si OpenCV o el modelo no están disponibles, el encuadre queda centrado y se
avisa: nunca se detiene el trabajo por esto.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .config import PAQUETE
from .errores import ErrorEtapa
from .media import herramienta

log = logging.getLogger("fabrica.reencuadre")

MODELO = PAQUETE / "assets" / "modelos" / "face_detection_yunet_2023mar.onnx"
FPS_ANALISIS = 5
ANCHO_ANALISIS = 640


def disponible() -> tuple[bool, str]:
    try:
        import cv2
    except ImportError:
        return False, "Falta opencv-python-headless (ejecuta scripts\\instalar.ps1)."
    if not hasattr(cv2, "FaceDetectorYN"):
        return False, f"OpenCV {cv2.__version__} no incluye el detector YuNet (se necesita 4.8 o superior)."
    if not MODELO.exists():
        return False, "Falta el modelo de rostros en fabrica_studio/assets/modelos."
    return True, f"OpenCV {cv2.__version__} · YuNet"


def ventana(ancho: int, alto: int, zoom: float = 1.0) -> tuple[int, int]:
    """Tamaño (par) de la ventana 9:16 que se recorta del video fuente."""
    zoom = max(1.0, min(zoom, 3.0))
    if ancho / alto > 9 / 16:                      # fuente más ancha que 9:16: se recorta a los lados
        h = alto / zoom
        w = h * 9 / 16
    else:                                           # fuente igual o más estrecha: se recorta arriba y abajo
        w = ancho / zoom
        h = w * 16 / 9
    return max(2, int(w) // 2 * 2), max(2, int(min(h, alto)) // 2 * 2)


def analizar(video: Path, propiedades: dict, recorte: dict | None = None) -> dict:
    """Detecta rostros en el video. Devuelve {ancho, alto, fps, muestras:[{t, rostros:[[cx, cy, w, h, conf]]}]}
    con coordenadas en píxeles del video fuente (después del recorte de bordes)."""
    ok, motivo = disponible()
    ancho, alto = (recorte["w"], recorte["h"]) if recorte else (propiedades["ancho"], propiedades["alto"])
    base = {"ancho": ancho, "alto": alto, "fps": FPS_ANALISIS, "muestras": [], "motor": motivo}
    if not ok:
        base["aviso"] = f"Encuadre centrado sin seguimiento de rostros: {motivo}"
        return base
    import cv2
    import numpy as np

    escala = ANCHO_ANALISIS / ancho
    w_a, h_a = ANCHO_ANALISIS, max(2, int(round(alto * escala / 2)) * 2)
    filtro = f"crop={ancho}:{alto}:{recorte['x']}:{recorte['y']}," if recorte else ""
    filtro += f"fps={FPS_ANALISIS},scale={w_a}:{h_a}"
    cmd = [herramienta("ffmpeg"), "-v", "error", "-i", str(video), "-vf", filtro, "-an",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    detector = cv2.FaceDetectorYN.create(str(MODELO), "", (w_a, h_a), 0.6, 0.3, 50)
    tam = w_a * h_a * 3
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        i = 0
        while True:
            datos = proc.stdout.read(tam)
            if len(datos) < tam:
                break
            cuadro = np.frombuffer(datos, np.uint8).reshape(h_a, w_a, 3)
            _, caras = detector.detect(cuadro)
            rostros = []
            for c in caras if caras is not None else []:
                x, y, w, h, conf = float(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[-1])
                rostros.append([round((x + w / 2) / escala, 1), round((y + h / 2) / escala, 1),
                                round(w / escala, 1), round(h / escala, 1), round(conf, 3)])
            base["muestras"].append({"t": round(i / FPS_ANALISIS, 3), "rostros": rostros})
            i += 1
    finally:
        proc.stdout.close()
        error = proc.stderr.read().decode("utf-8", "replace")[-400:]
        proc.stderr.close()
        proc.wait()
    if proc.returncode != 0 and not base["muestras"]:
        raise ErrorEtapa(f"No se pudo leer el video para el encuadre: {error}", "herramienta")
    con = sum(1 for m in base["muestras"] if m["rostros"])
    if base["muestras"] and con / len(base["muestras"]) < 0.2:
        base["aviso"] = ("Se detectaron rostros en pocas partes del clip: el encuadre se mantiene centrado "
                         "donde no hay nadie visible. Revisa el resultado o usa el estilo clásico.")
    return base


def _objetivo(rostros: list, ancho_ventana: float, previo: float | None) -> float | None:
    """Centro horizontal deseado para un instante. Si caben varios rostros, centra el grupo;
    si no, sigue al más grande (normalmente quien está más cerca de la cámara)."""
    if not rostros:
        return None
    rostros = sorted(rostros, key=lambda r: r[2] * r[3] * r[4], reverse=True)
    principal = rostros[0]
    grupo = [r for r in rostros if r[2] * r[3] >= principal[2] * principal[3] * 0.35]
    izq = min(r[0] - r[2] / 2 for r in grupo)
    der = max(r[0] + r[2] / 2 for r in grupo)
    if der - izq <= ancho_ventana * 0.85:
        return (izq + der) / 2
    # No caben todos: si el anterior encuadre seguía a alguien que sigue visible, mantenerlo
    # (evita saltar de una persona a otra en cada fotograma).
    if previo is not None:
        cercano = min(grupo, key=lambda r: abs(r[0] - previo))
        if abs(cercano[0] - previo) < ancho_ventana * 0.3:
            return cercano[0]
    return principal[0]


def trayectoria(analisis: dict, ancho_ventana: int, zona_muerta: float = 0.06, salto: float = 0.28,
                suavizado: float = 0.22) -> list[tuple[float, float]]:
    """Lista de (t, x_izquierda) de la ventana de recorte, ya suavizada y dentro de los límites."""
    ancho = analisis["ancho"]
    muestras = analisis["muestras"]
    centro_imagen = ancho / 2
    limite = max(0.0, ancho - ancho_ventana)
    if not muestras or limite == 0:
        return [(0.0, round(limite / 2))]

    # 1. Objetivo por muestra, manteniendo el último conocido en los huecos sin rostros.
    objetivos, previo = [], None
    for m in muestras:
        o = _objetivo(m["rostros"], ancho_ventana, previo)
        if o is None:
            o = previo if previo is not None else None
        objetivos.append(o)
        if o is not None:
            previo = o
    primero = next((o for o in objetivos if o is not None), centro_imagen)
    objetivos = [primero if o is None else o for o in objetivos]

    # 2. Mediana móvil (≈1 s) para descartar detecciones sueltas.
    k = 2
    filtrados = [sorted(objetivos[max(0, i - k):i + k + 1])[len(objetivos[max(0, i - k):i + k + 1]) // 2]
                 for i in range(len(objetivos))]

    # 3. Cámara virtual: zona muerta, desplazamiento suave y corte en saltos grandes.
    pos = filtrados[0]
    puntos = []
    for m, o in zip(muestras, filtrados):
        dif = o - pos
        if abs(dif) > ancho_ventana * salto:
            pos = o
        elif abs(dif) > ancho_ventana * zona_muerta:
            pos += dif * suavizado
        x = min(max(pos - ancho_ventana / 2, 0.0), limite)
        puntos.append((m["t"], round(x)))

    # 4. Quitar puntos repetidos para que el archivo de órdenes sea corto.
    compactos = [puntos[0]]
    for p in puntos[1:]:
        if p[1] != compactos[-1][1]:
            compactos.append(p)
    return compactos


def comandos_sendcmd(puntos: list[tuple[float, float]], filtro: str = "crop@encuadre",
                     paso: float = 1 / 15) -> str:
    """Órdenes para el filtro sendcmd de FFmpeg. Interpola entre puntos cercanos para que el
    desplazamiento sea fluido; un salto grande (corte) se aplica en un único fotograma."""
    lineas = []
    for (t0, x0), (t1, x1) in zip(puntos, puntos[1:] + [puntos[-1]]):
        lineas.append(f"{t0:.3f} {filtro} x {int(x0) // 2 * 2};")
        hueco = t1 - t0
        if 0 < hueco <= 0.5 and abs(x1 - x0) > 2:
            n = int(hueco / paso)
            for j in range(1, n):
                t = t0 + j * paso
                x = x0 + (x1 - x0) * j / n
                lineas.append(f"{t:.3f} {filtro} x {int(x) // 2 * 2};")
    return "\n".join(lineas) + "\n"
