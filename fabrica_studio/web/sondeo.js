"use strict";
// Sondeo del panel, sin DOM (probado en tests/test_sondeo_js.py):
// - una sola consulta a la vez: quien llama mientras hay una en curso espera a que se repita y termine;
// - al terminar se pinta una vez y se programa la siguiente con el intervalo que toque (o ninguna si no puede).
// alEmpezar() devuelve lo que alTerminar(ctx) necesita (p. ej. el último estado mostrado), aunque se encadenen consultas.
function crearSondeo({ consultar, alEmpezar = () => null, alTerminar = () => {}, intervalo, puede,
                       reloj = { poner: (f, ms) => setTimeout(f, ms), quitar: (id) => clearTimeout(id) } }) {
  let temporizador = 0, enCurso = null, otraVez = false;
  const detener = () => { reloj.quitar(temporizador); temporizador = 0; };
  // puede() se vuelve a mirar al dispararse: entre medias pudo cerrarse la sesión u ocultarse la pestaña.
  const programar = () => { detener(); if (puede()) temporizador = reloj.poner(() => { temporizador = 0; if (puede()) refrescar(); }, intervalo()); };
  function refrescar() {
    if (enCurso) { otraVez = true; return enCurso; }
    detener();
    enCurso = (async () => {
      const ctx = alEmpezar();
      try {
        do { otraVez = false; await consultar(); } while (otraVez && puede());   // oculta a medias: al volver se pide de nuevo
      } finally {
        enCurso = null;                                      // desde aquí, una llamada nueva abre otra consulta
        try { alTerminar(ctx); } finally { programar(); }    // un fallo al pintar no detiene el sondeo
      }
    })();
    return enCurso;
  }
  return { refrescar, programar, detener, programado: () => !!temporizador };
}
if (typeof module !== "undefined") module.exports = crearSondeo;
