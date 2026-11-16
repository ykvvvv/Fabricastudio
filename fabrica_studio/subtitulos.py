"""Subtítulos: agrupa palabras con tiempos en bloques cortos y los escribe en formato ASS."""
from __future__ import annotations

from .config import LIENZO_ALTO, LIENZO_ANCHO


def agrupar(palabras: list[dict], palabras_max: int = 4, caracteres_max: int = 22,
            pausa: float = 0.6, duracion_max: float = 2.8) -> list[dict]:
    """Bloques de pocas palabras, cortando en pausas y signos de puntuación."""
    bloques, actual = [], []

    def cerrar():
        if actual:
            bloques.append({"inicio": actual[0]["inicio"], "fin": actual[-1]["fin"],
                            "texto": " ".join(p["texto"] for p in actual)})
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


def a_ass(bloques: list[dict], tamano: int, y_superior: int, margen_lateral: int = 70) -> str:
    """ASS con alineación superior-centro: `y_superior` es donde empieza la primera línea."""
    borde = max(3, round(tamano * 0.09))
    cabecera = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {LIENZO_ANCHO}
PlayResY: {LIENZO_ALTO}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Inter,{tamano},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,{borde},2,8,{margen_lateral},{margen_lateral},{y_superior},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lineas = [f"Dialogue: 0,{_t(b['inicio'])},{_t(b['fin'])},Sub,,0,0,0,,{_escapar(b['texto'])}"
              for b in bloques if b.get("texto", "").strip() and b["fin"] > b["inicio"]]
    return cabecera + "\n".join(lineas) + "\n"
