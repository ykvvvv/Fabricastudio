"""Sondeo del panel (web/sondeo.js) ejecutado con Node y un reloj falso, si Node está instalado."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SONDEO = Path(__file__).resolve().parent.parent / "fabrica_studio" / "web" / "sondeo.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="Node no está instalado")

# Escenario común: reloj falso, consultas que se resuelven a mano y registro de lo que pasa.
PREAMBULO = f"""
const crearSondeo = require({json.dumps(str(SONDEO))});
const log = [], pendientes = [];
let visible = true, activo = false, enVuelo = 0, maxEnVuelo = 0, siguiente = 1;
const timers = new Map();
const reloj = {{ poner: (f, ms) => {{ const id = siguiente++; timers.set(id, {{ f, ms }}); return id; }}, quitar: (id) => timers.delete(id) }};
const consultar = () => new Promise((ok) => {{
  enVuelo++; maxEnVuelo = Math.max(maxEnVuelo, enVuelo); log.push("consulta");
  pendientes.push(() => {{ enVuelo--; ok(); }});
}});
let mostrado = 0, estado = 0;
const s = crearSondeo({{
  consultar: () => consultar().then(() => {{ estado++; }}),
  alEmpezar: () => mostrado,
  alTerminar: (antes) => {{ log.push(`pinta ${{antes}}->${{estado}}`); mostrado = estado; }},
  intervalo: () => (activo ? 2000 : 15000),
  puede: () => visible,
  reloj,
}});
const tic = () => new Promise((ok) => setImmediate(ok));
const resolver = async () => {{ while (pendientes.length) {{ pendientes.shift()(); await tic(); await tic(); }} }};
const programados = () => [...timers.values()].map((t) => t.ms);
"""


def _js(cuerpo: str):
    codigo = PREAMBULO + f"(async () => {{ {cuerpo} }})().then((r) => console.log(JSON.stringify(r)));"
    return json.loads(subprocess.run(["node", "-e", codigo], capture_output=True, text=True, check=True).stdout)


def test_llamadas_solapadas_esperan_la_consulta_pedida_sin_consultas_simultaneas():
    r = _js("""
      const p1 = s.refrescar(); await tic();
      const p2 = s.refrescar(), p3 = s.refrescar();   // llegan mientras la primera está en curso
      let hecho2 = false; p2.then(() => { hecho2 = true; });
      pendientes.shift()(); await tic(); await tic();
      const antesDeLaSegunda = hecho2;                 // aún no: falta la consulta que pidieron
      await resolver();
      await p2;
      return { misma: p1 === p2 && p2 === p3, antesDeLaSegunda, log, maxEnVuelo };
    """)
    assert r["misma"] and r["antesDeLaSegunda"] is False
    assert r["maxEnVuelo"] == 1
    # Dos consultas (la pedida durante la primera se agrupa) y un solo pintado que compara con lo mostrado antes.
    assert r["log"] == ["consulta", "consulta", "pinta 0->2"]


def test_intervalo_segun_actividad_y_pestana_oculta():
    r = _js("""
      s.refrescar(); await resolver();
      const reposo = programados();
      activo = true; s.programar(); const activoMs = programados();
      visible = false; s.detener(); s.programar(); const oculto = programados();
      visible = true; const p = s.refrescar(); await resolver(); await p;
      return { reposo, activoMs, oculto, alVolver: log.filter((x) => x === "consulta").length, despues: programados() };
    """)
    assert r["reposo"] == [15000] and r["activoMs"] == [2000]
    assert r["oculto"] == []                       # con la pestaña oculta no queda nada programado
    assert r["alVolver"] == 2 and r["despues"] == [2000]


def test_un_fallo_al_pintar_no_detiene_el_sondeo():
    r = _js("""
      const s2 = crearSondeo({ consultar: async () => {}, alTerminar: () => { throw new Error("pintar"); },
                               intervalo: () => 15000, puede: () => true, reloj });
      await s2.refrescar().catch(() => {});
      return { programados: programados() };
    """)
    assert r["programados"] == [15000]


def test_el_temporizador_vuelve_a_mirar_si_puede_consultar():
    """Si la sesión se cierra (o la pestaña se oculta) con un sondeo ya programado, al dispararse no consulta."""
    r = _js("""
      s.refrescar(); await resolver();
      const [t] = [...timers.values()];
      visible = false; t.f(); await tic();
      const sinPermiso = log.filter((x) => x === "consulta").length;
      visible = true; [...timers.values()].forEach((x) => x.f()); s.programar(); [...timers.values()][0].f(); await tic();
      return { sinPermiso, conPermiso: log.filter((x) => x === "consulta").length };
    """)
    assert r["sinPermiso"] == 1 and r["conPermiso"] == 2


def test_no_repite_la_consulta_si_la_pestana_se_oculto_mientras_tanto():
    r = _js("""
      const p = s.refrescar(); await tic();
      s.refrescar();                 // se pide otra mientras la primera está en curso…
      visible = false; s.detener();  // …y la pestaña se oculta
      await resolver(); await p;
      return { consultas: log.filter((x) => x === "consulta").length, programados: programados() };
    """)
    assert r["consultas"] == 1 and r["programados"] == []
