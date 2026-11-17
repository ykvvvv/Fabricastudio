"""Subtítulos: agrupa palabras con tiempos en bloques cortos y los escribe en formato ASS."""
from __future__ import annotations

from .config import LIENZO_ALTO, LIENZO_ANCHO


def leer_correcciones(texto: str) -> dict[str, str]:
    """«mal => bien» por línea (también acepta «mal = bien»). Claves en minúsculas, sin puntuación."""
    reglas: dict[str, str] = {}
    for linea in (texto or "").splitlines():
        if "=>" in linea:
            mal, bien = linea.split("=>", 1)
        elif "=" in linea:
            mal, bien = linea.split("=", 1)
        else:
            continue
        mal, bien = mal.strip().lower().strip(".,;:!?¡¿\"'"), bien.strip()
        if mal and bien:
            reglas[mal] = bien
    return reglas


def corregir_palabras(palabras: list[dict], reglas: dict[str, str]) -> list[dict]:
    """Corrige la escritura de palabras sueltas conservando puntuación y mayúscula inicial.
    No agrega ni quita palabras: solo cambia cómo se escribe cada una."""
    if not reglas:
        return palabras
    salida = []
    for p in palabras:
        t = p["texto"]
        inicio = len(t) - len(t.lstrip(".,;:!?¡¿\"'«(-"))
        fin = len(t.rstrip(".,;:!?¡¿\"'»)-"))
        nucleo = t[inicio:fin]
        nuevo = reglas.get(nucleo.lower())
        if nuevo is not None:
            if nucleo[:1].isupper() and nuevo[:1].islower():
                nuevo = nuevo[:1].upper() + nuevo[1:]
            t = t[:inicio] + nuevo + t[fin:]
        salida.append({**p, "texto": t})
    return salida


def agrupar(palabras: list[dict], palabras_max: int = 4, caracteres_max: int = 22,
            pausa: float = 0.6, duracion_max: float = 2.8) -> list[dict]:
    """Bloques de pocas palabras, cortando en pausas y signos de puntuación."""
    bloques, actual = [], []

    def cerrar():
        if actual:
            bloques.append({"inicio": actual[0]["inicio"], "fin": actual[-1]["fin"],
                            "texto": " ".join(p["texto"] for p in actual),
                            "palabras": [{"inicio": p["inicio"], "fin": p["fin"], "texto": p["texto"]} for p in actual]})
            actual.clear()

    for p in palabras:
        if actual:
            largo = len(" ".join(x["texto"] for x in actual)) + 1 + len(p["texto"])
            if (len(actual) >= palabras_max or largo > caracteres_max
                    or p["inicio"] - actual[-1]["fin"] > pausa
                    or p["fin"] - actual[0]["inicio"] > duracion_max
                    or actual[-1]["texto"][-1:] in ".?!…"
                    or (actual[-1]["texto"][-1:] in ",;:" and len(actual) >= 2)):
                cerrar()
        actual.append(p)
    cerrar()
    # Cada bloque permanece hasta el siguiente si la pausa es breve; nunca se solapan.
    for i, b in enumerate(bloques):
        b["fin"] = max(b["fin"], b["inicio"] + 0.35)
        if i + 1 < len(bloques):
            sig = bloques[i + 1]["inicio"]
            b["fin"] = sig if sig - b["fin"] < 0.25 else b["fin"]
            b["fin"] = min(b["fin"], sig)
        b["inicio"], b["fin"] = round(b["inicio"], 3), round(b["fin"], 3)
    return bloques


def _t(seg: float) -> str:
    cs = max(0, int(round(seg * 100)))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _escapar(texto: str) -> str:
    return texto.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def _color_ass(hexa: str) -> str:
    """#RRGGBB -> &H00BBGGRR& (ASS usa el orden inverso)."""
    h = hexa.lstrip("#")
    if len(h) != 6:
        h = "53FC18"
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def _eventos(b: dict, resaltar: bool, color: str, mayusculas: bool = False) -> list[tuple[float, float, str]]:
    """Un evento por bloque o, con resaltado, uno por palabra con la palabra activa en color."""
    def esc(t: str) -> str:
        return _escapar(t.upper() if mayusculas else t)
    texto = esc(b["texto"])
    palabras = b.get("palabras") or []
    if not resaltar or not palabras or " ".join(p["texto"] for p in palabras) != b["texto"]:
        return [(b["inicio"], b["fin"], texto)]
    trozos = [esc(p["texto"]) for p in palabras]
    eventos = []
    if palabras[0]["inicio"] > b["inicio"] + 0.01:
        eventos.append((b["inicio"], palabras[0]["inicio"], texto))
    for i, p in enumerate(palabras):
        ini = max(p["inicio"], b["inicio"])
        fin = palabras[i + 1]["inicio"] if i + 1 < len(palabras) else b["fin"]
        if fin <= ini:
            continue
        linea = " ".join(f"{{\\c{color}}}{t}{{\\c&H00FFFFFF&}}" if j == i else t for j, t in enumerate(trozos))
        eventos.append((ini, fin, linea))
    return eventos


def a_ass(bloques: list[dict], tamano: int, y_superior: int, margen_lateral: int = 70,
          resaltar: bool = False, color_resalte: str = "#53FC18", mayusculas: bool = False,
          borde: int | None = None, fuente: str = "Inter") -> str:
    """ASS con alineación superior-centro: `y_superior` es donde empieza la primera línea."""
    borde = borde if borde is not None else max(2, round(tamano * 0.06))
    cabecera = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {LIENZO_ANCHO}
PlayResY: {LIENZO_ALTO}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{fuente},{tamano},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,{borde},1,8,{margen_lateral},{margen_lateral},{y_superior},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    color = _color_ass(color_resalte)
    lineas = []
    for b in bloques:
        if not b.get("texto", "").strip() or b["fin"] <= b["inicio"]:
            continue
        for ini, fin, txt in _eventos(b, resaltar, color, mayusculas):
            lineas.append(f"Dialogue: 0,{_t(ini)},{_t(fin)},Sub,,0,0,0,,{txt}")
    return cabecera + "\n".join(lineas) + "\n"
