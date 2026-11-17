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
        previo = None
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
            movimiento, corte, previo = _movimiento_y_corte(cuadro, previo, escala)
            base["muestras"].append({"t": round(i / FPS_ANALISIS, 3), "rostros": rostros,
                                     "movimiento": movimiento, "corte": corte})
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


def _movimiento_y_corte(cuadro, previo, escala: float):
    """Regiones que se mueven (para seguir sujetos sin cara, como un robot) y si hubo un corte de escena.

    Devuelve (regiones [[cx, cy, w, h, fraccion_area]] en px del video fuente, corte, estado para el
    siguiente cuadro). Si casi todo el cuadro se mueve, es la cámara la que se mueve (IRL): no se reportan
    regiones."""
    import cv2
    import numpy as np
    gris = cv2.cvtColor(cv2.resize(cuadro, (160, max(2, int(160 * cuadro.shape[0] / cuadro.shape[1])))),
                        cv2.COLOR_BGR2GRAY)
    gris = cv2.GaussianBlur(gris, (5, 5), 0)
    hist = cv2.calcHist([gris], [0], None, [32], [0, 256]).ravel()
    hist /= max(1.0, hist.sum())
    if previo is None:
        return [], False, (gris, hist)
    g0, h0 = previo
    corte = float(np.abs(hist - h0).sum()) > 0.6
    if corte:
        return [], True, (gris, hist)
    dif = cv2.absdiff(gris, g0)
    _, masc = cv2.threshold(dif, 22, 255, cv2.THRESH_BINARY)
    masc = cv2.dilate(masc, np.ones((5, 5), np.uint8), iterations=2)
    fraccion = float(masc.mean() / 255)
    regiones = []
    if 0.004 < fraccion < 0.45:
        n, _, stats, centros = cv2.connectedComponentsWithStats(masc)
        f = (cuadro.shape[1] / 160) / escala        # px del cuadro reducido → px del video fuente
        total = masc.shape[0] * masc.shape[1]
        cand = sorted(range(1, n), key=lambda k: stats[k, cv2.CC_STAT_AREA], reverse=True)[:3]
        for k in cand:
            area = stats[k, cv2.CC_STAT_AREA] / total
            if area < 0.008:
                continue
            x, y, w, h = (stats[k, cv2.CC_STAT_LEFT], stats[k, cv2.CC_STAT_TOP],
                          stats[k, cv2.CC_STAT_WIDTH], stats[k, cv2.CC_STAT_HEIGHT])
            regiones.append([round((x + w / 2) * f, 1), round((y + h / 2) * f, 1), round(w * f, 1),
                             round(h * f, 1), round(area, 4)])
    return regiones, False, (gris, hist)


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
        if m.get("corte") or abs(dif) > ancho_ventana * salto:      # corte de escena o salto grande: cortar
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


# ----------------------------------------------------------------------------- vista dividida

def _grupos_de_rostros(analisis: dict) -> list[dict]:
    """Agrupa los rostros de todas las muestras por posición y tamaño parecidos.
    Cada grupo: {cx, cy, w, h (medianas), presencia (fracción de muestras), dispersion (px), indices}."""
    ancho = analisis["ancho"]
    grupos: list[dict] = []
    for i, m in enumerate(analisis["muestras"]):
        for r in m["rostros"]:
            cx, cy, w, h = r[0], r[1], r[2], r[3]
            destino = None
            for g in grupos:
                gx, gy, gh = g["_cx"] / g["_n"], g["_cy"] / g["_n"], g["_h"] / g["_n"]
                if abs(cx - gx) < ancho * 0.07 and abs(cy - gy) < ancho * 0.07 and 0.6 < h / gh < 1.6:
                    destino = g
                    break
            if destino is None:
                destino = {"_cx": 0.0, "_cy": 0.0, "_h": 0.0, "_n": 0, "puntos": [], "muestras": set()}
                grupos.append(destino)
            destino["_cx"] += cx; destino["_cy"] += cy; destino["_h"] += h; destino["_n"] += 1
            destino["puntos"].append((cx, cy, w, h))
            destino["muestras"].add(i)
    total = max(1, len(analisis["muestras"]))
    resultado = []
    for g in grupos:
        pts = g["puntos"]
        med = lambda k: sorted(p[k] for p in pts)[len(pts) // 2]
        cx, cy = med(0), med(1)
        dispersion = (sum((p[0] - cx) ** 2 + (p[1] - cy) ** 2 for p in pts) / len(pts)) ** 0.5
        resultado.append({"cx": cx, "cy": cy, "w": med(2), "h": med(3), "presencia": len(g["muestras"]) / total,
                          "dispersion": dispersion, "muestras": g["muestras"]})
    return sorted(resultado, key=lambda g: g["presencia"], reverse=True)


def detectar_camara(analisis: dict) -> dict | None:
    """Busca la cámara del streamer: un rostro que aparece en casi todo el clip, casi inmóvil,
    pequeño respecto al cuadro y fuera del centro (el recuadro de facecam de un stream).
    Devuelve el grupo o None si no hay ninguno convincente (p. ej. un IRL de una sola cámara)."""
    ancho, alto = analisis["ancho"], analisis["alto"]
    for g in _grupos_de_rostros(analisis):
        if g["presencia"] < 0.5:
            break
        quieto = g["dispersion"] < ancho * 0.03
        pequeno = g["h"] < alto * 0.3
        borde = (g["cx"] < ancho * 0.36 or g["cx"] > ancho * 0.64 or g["cy"] < alto * 0.36 or g["cy"] > alto * 0.64)
        if quieto and pequeno and borde:
            return g
    return None


def caja_camara(camara: dict, ancho: int, alto: int, aspecto: float, factor: float = 3.2) -> dict:
    """Recuadro alrededor del rostro de la cámara con la proporción del panel (ancho/alto)."""
    h = min(alto, camara["h"] * factor)
    w = h * aspecto
    if w > ancho:
        w, h = ancho, ancho / aspecto
    x = min(max(camara["cx"] - w / 2, 0), ancho - w)
    y = min(max(camara["cy"] - h * 0.45, 0), alto - h)        # la cara algo por encima del centro
    return {"x": int(x) // 2 * 2, "y": int(y) // 2 * 2, "w": int(w) // 2 * 2, "h": int(h) // 2 * 2}


def zona_contenido(camara_caja: dict, ancho: int) -> tuple[int, int]:
    """Franja horizontal [x0, x1) del contenido: el lado del cuadro que no ocupa la cámara."""
    izq = camara_caja["x"]
    der = ancho - (camara_caja["x"] + camara_caja["w"])
    if camara_caja["x"] + camara_caja["w"] / 2 < ancho / 2:      # cámara a la izquierda
        return (camara_caja["x"] + camara_caja["w"], ancho) if der > ancho * 0.4 else (0, ancho)
    return (0, camara_caja["x"]) if izq > ancho * 0.4 else (0, ancho)


def plan_dividido(analisis: dict, alto_arriba: int, alto_abajo: int, ancho_lienzo: int = 1080) -> dict | None:
    """Calcula el panel de arriba (cámara, fijo) y la trayectoria del panel de abajo (contenido).
    None si no se encontró una cámara fija."""
    ancho, alto = analisis["ancho"], analisis["alto"]
    camara = detectar_camara(analisis)
    if not camara:
        return None
    arriba = caja_camara(camara, ancho, alto, ancho_lienzo / alto_arriba)
    x0, x1 = zona_contenido(arriba, ancho)
    aspecto_abajo = ancho_lienzo / alto_abajo
    vh = alto
    vw = int(min(vh * aspecto_abajo, x1 - x0)) // 2 * 2
    vh = int(min(alto, vw / aspecto_abajo)) // 2 * 2
    # Rostros del contenido: los que no son la cámara y caen dentro de la franja.
    sub = {"ancho": x1 - x0, "alto": alto, "fps": analisis.get("fps", FPS_ANALISIS), "muestras": []}
    for m in analisis["muestras"]:
        otros = [[r[0] - x0, *r[1:]] for r in m["rostros"]
                 if not (abs(r[0] - camara["cx"]) < ancho * 0.07 and abs(r[1] - camara["cy"]) < ancho * 0.07)
                 and x0 <= r[0] < x1]
        sub["muestras"].append({"t": m["t"], "rostros": otros})
    puntos = [(t, x + x0) for t, x in trayectoria(sub, vw)]
    abajo = {"w": vw, "h": vh, "y": (alto - vh) // 2 // 2 * 2, "zona": [x0, x1]}
    # Si en el contenido hay un sujeto claro y constante (persona u objeto en movimiento), acercarse a él.
    protagonista = next((s for s in sujetos(analisis) if s["presencia"] >= 0.4 and x0 <= s["cx"] < x1
                         and not (abs(s["cx"] - camara["cx"]) < ancho * 0.07 and abs(s["cy"] - camara["cy"]) < ancho * 0.07)),
                        None)
    if protagonista:
        w, h, y = _ventana_sujeto(protagonista, ancho, alto, aspecto_abajo)
        panel = _panel_que_sigue(analisis, protagonista, w, h, y, "crop@abajo")
        if w <= x1 - x0:          # no invadir la cámara
            panel["puntos"] = [(t, min(max(x, x0), x1 - w)) for t, x in panel["puntos"]]
        abajo = {"w": w, "h": h, "y": y, "zona": [x0, x1], "sigue": protagonista["tipo"]}
        puntos = panel["puntos"]
    return {"tipo": "camara", "arriba": arriba, "abajo": abajo, "puntos": puntos,
            "camara": {k: round(camara[k], 1) for k in ("cx", "cy", "h", "presencia")},
            "paneles": [{"w": arriba["w"], "h": arriba["h"], "y": arriba["y"], "puntos": [(0.0, arriba["x"])],
                         "filtro": "crop@arriba"},
                        {**abajo, "puntos": puntos, "filtro": "crop@abajo"}]}


# ----------------------------------------------------------------------------- modo automático

def _pistas(analisis: dict, campo: str, max_hueco: int = 10) -> list[dict]:
    """Sigue cada sujeto de un cuadro al siguiente (rostros o regiones en movimiento).
    Cada pista: {pts: {indice_muestra: [cx, cy, w, h]}, presencia, cx, cy, w, h (medianas)}."""
    ancho = analisis["ancho"]
    pistas: list[dict] = []
    for i, m in enumerate(analisis["muestras"]):
        if m.get("corte"):
            for p in pistas:
                p["cerrada"] = True          # tras un corte de escena, nadie continúa una pista anterior
        for r in m.get(campo, []):
            cx, cy, w, h = r[0], r[1], r[2], r[3]
            mejor, dist_mejor = None, ancho * 0.12
            for p in pistas:
                if p.get("cerrada") or i - p["ultimo_i"] > max_hueco or i in p["pts"]:
                    continue
                lx, ly, lw, lh = p["ultimo"]
                d = ((cx - lx) ** 2 + (cy - ly) ** 2) ** 0.5
                if d < dist_mejor and 0.4 < h / max(lh, 1) < 2.5:
                    mejor, dist_mejor = p, d
            if mejor is None:
                mejor = {"pts": {}, "ultimo": None, "ultimo_i": i}
                pistas.append(mejor)
            mejor["pts"][i] = [cx, cy, w, h]
            mejor["ultimo"], mejor["ultimo_i"] = (cx, cy, w, h), i
    total = max(1, len(analisis["muestras"]))
    for p in pistas:
        vals = list(p["pts"].values())
        for k, nombre in enumerate(("cx", "cy", "w", "h")):
            p[nombre] = sorted(v[k] for v in vals)[len(vals) // 2]
        p["presencia"] = len(vals) / total
        p["tipo"] = "rostro" if campo == "rostros" else "movimiento"
    return pistas


def sujetos(analisis: dict) -> list[dict]:
    """Sujetos de interés ordenados por importancia: personas (rostros) y cosas que se mueven sin rostro
    (por ejemplo, un robot). El movimiento que coincide con una persona se considera de esa persona."""
    ancho = analisis["ancho"]
    caras = [p for p in _pistas(analisis, "rostros") if p["presencia"] >= 0.25]
    otros = []
    for p in _pistas(analisis, "movimiento"):
        if p["presencia"] < 0.3:
            continue
        # El cuerpo de una persona mide ~2,5 veces el ancho de su cara: el movimiento dentro de esa franja es suyo.
        cerca = any(abs(p["cx"] - c["cx"]) < c["w"] * 1.3 + p["w"] * 0.25 for c in caras)
        if not cerca:
            otros.append(p)
    todos = caras + otros
    return sorted(todos, key=lambda p: p["presencia"] * (2.0 if p["tipo"] == "rostro" else 1.0), reverse=True)


def _ventana_sujeto(s: dict, ancho: int, alto: int, aspecto: float) -> tuple[int, int, int]:
    """(w, h, y) del recorte para un sujeto en un panel de proporción `aspecto` (ancho/alto)."""
    if s["tipo"] == "rostro":
        h = min(alto, max(alto * 0.5, s["h"] * 4.2))
    else:
        h = min(alto, max(alto * 0.5, s["h"] * 1.7))
    w = h * aspecto
    if w > ancho:
        w, h = ancho, ancho / aspecto
    centro_y = s["cy"] + (s["h"] * 0.6 if s["tipo"] == "rostro" else 0)   # cara en el tercio superior
    y = min(max(centro_y - h / 2, 0), alto - h)
    return int(w) // 2 * 2, int(h) // 2 * 2, int(y) // 2 * 2


def _panel_que_sigue(analisis: dict, s: dict, w: int, h: int, y: int, filtro: str) -> dict:
    sub = {"ancho": analisis["ancho"], "alto": analisis["alto"], "fps": analisis.get("fps", FPS_ANALISIS),
           "muestras": [{"t": m["t"], "corte": m.get("corte", False),
                         "rostros": [[*s["pts"][i], 1.0]] if i in s["pts"] else []}
                        for i, m in enumerate(analisis["muestras"])]}
    puntos = trayectoria(sub, w)
    return {"w": w, "h": h, "y": y, "puntos": puntos, "filtro": filtro}


def decidir(analisis: dict, alto_arriba: int, alto_abajo: int, ancho_lienzo: int = 1080) -> dict:
    """Elige el encuadre de un clip:
    - "camara": cámara del streamer fija en una esquina → cámara arriba, contenido abajo.
    - "dos": dos sujetos que no caben juntos en 9:16 → cada uno en su mitad.
    - "seguir": un sujeto principal → pantalla completa siguiéndolo.
    - "clasico": nada claro → video completo (lo más seguro).
    Devuelve {tipo, motivo, plan (para camara/dos)}."""
    ancho, alto = analisis["ancho"], analisis["alto"]
    if not analisis.get("muestras"):
        return {"tipo": "clasico", "motivo": "no se pudo analizar el video"}
    plan = plan_dividido(analisis, alto_arriba, alto_abajo, ancho_lienzo)
    if plan:
        sigue = plan["abajo"].get("sigue")
        motivo = "persona fija a un lado (cámara del streamer o invitado)" + (
            {"rostro": " y otra persona en el contenido", "movimiento": " y algo que se mueve en el contenido"}.get(sigue, ""))
        return {"tipo": "camara", "motivo": motivo, "plan": plan}
    ss = sujetos(analisis)
    vw, _ = ventana(ancho, alto)
    if len(ss) >= 2:
        a, b = ss[0], ss[1]
        juntos = set(a["pts"]) & set(b["pts"])
        total = max(1, len(analisis["muestras"]))
        separacion = abs(a["cx"] - b["cx"]) + (a["w"] + b["w"]) / 2
        if len(juntos) / total >= 0.3 and separacion > vw * 0.9:
            arriba_s, abajo_s = sorted((a, b), key=lambda s: s["cx"])       # el de la izquierda va arriba
            paneles = []
            for s, alto_panel, filtro in ((arriba_s, 960, "crop@arriba"), (abajo_s, 960, "crop@abajo")):
                w, h, y = _ventana_sujeto(s, ancho, alto, ancho_lienzo / alto_panel)
                paneles.append(_panel_que_sigue(analisis, s, w, h, y, filtro))
            nombres = " y ".join("persona" if s["tipo"] == "rostro" else "objeto en movimiento"
                                 for s in (arriba_s, abajo_s))
            return {"tipo": "dos", "motivo": f"dos sujetos separados ({nombres})",
                    "plan": {"tipo": "dos", "proporcion": 50, "paneles": paneles}}
    if ss:
        return {"tipo": "seguir", "motivo": "un sujeto principal" +
                ("" if ss[0]["tipo"] == "rostro" else " (sin rostro, por movimiento)")}
    return {"tipo": "clasico", "motivo": "no se detectaron personas ni movimiento claro"}
