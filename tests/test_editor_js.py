"""Operaciones del editor de tiempos (web/editor.js) ejecutadas con Node, si está instalado."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fabrica_studio import edicion

EDITOR = Path(__file__).resolve().parent.parent / "fabrica_studio" / "web" / "editor.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="Node no está instalado")


def _js(expresion: str):
    codigo = f"const T = require({json.dumps(str(EDITOR))}); console.log(JSON.stringify({expresion}));"
    return json.loads(subprocess.run(["node", "-e", codigo], capture_output=True, text=True, check=True).stdout)


def test_limites_iguales_al_servidor():
    assert _js("[T.MIN, T.TOTAL_MIN, T.TOTAL_MAX]") == [edicion.TRAMO_MIN, edicion.TOTAL_MIN, edicion.TOTAL_MAX]


def test_restar_sumar_dividir_y_siguiente():
    # Cortar palabras en medio de un tramo lo parte en dos; restos de menos de 0,3 s desaparecen.
    assert _js("T.restar([[0, 10]], 4, 5)") == [[0, 4], [5, 10]]
    assert _js("T.restar([[0, 10]], 0.2, 5)") == [[5, 10]]
    assert _js("T.restar([[0, 3], [6, 9]], 2, 7)") == [[0, 2], [7, 9]]
    # Recuperar palabras une con los tramos vecinos.
    assert _js("T.sumar([[0, 4], [5, 10]], 4, 5)") == [[0, 10]]
    assert _js("T.sumar([[0, 2], [7, 9]], 3, 4)") == [[0, 2], [3, 4], [7, 9]]
    # Dividir exige al menos 0,3 s a cada lado y no actúa en una parte cortada.
    assert _js("T.dividir([[0, 4], [6, 9]], 7)") == [[0, 4], [6, 7], [7, 9]]
    assert _js("T.dividir([[0, 4]], 3.9)") is None
    assert _js("T.dividir([[0, 4], [6, 9]], 5)") is None
    # La vista previa salta lo cortado y se detiene al final.
    assert _js("[T.siguiente([[1, 2], [5, 6]], 0), T.siguiente([[1, 2], [5, 6]], 1.5), T.siguiente([[1, 2], [5, 6]], 3), T.siguiente([[1, 2], [5, 6]], 6)]") == [1, 1.5, 5, None]
    assert _js("T.total([[0, 2.5], [5, 6]])") == 3.5


def test_lo_que_envia_el_editor_lo_acepta_el_servidor():
    """Tramos partidos por «Dividir» llegan tocándose: el servidor los une sin cambiar la duración."""
    tramos = _js("T.restar(T.dividir([[0, 20]], 8), 12, 13)")
    assert tramos == [[0, 8], [8, 12], [13, 20]]
    assert edicion.validar_tramos(tramos, 20) == [[0, 12], [13, 20]]
