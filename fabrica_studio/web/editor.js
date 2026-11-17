"use strict";
// Editor de tiempos de un clip (API: GET /api/trabajos/<id>/linea y PUT /api/trabajos/<id>/edicion).
// Todos los tiempos son del original; los «tramos» [inicio, fin] son las partes que se conservan.
// Usa de app.js: $, h, crudo, ic, api, avisar, confirmar, refrescar, intentar, animar, reloj.

// ---------------------------------------------------------------- operaciones con tramos (sin DOM; probadas en tests/test_editor_js.py)
const Tramos = {
  MIN: 0.3, TOTAL_MIN: 3, TOTAL_MAX: 180,          // los mismos límites que edicion.py
  total: (ts) => ts.reduce((s, [a, b]) => s + b - a, 0),
  dentro: (ts, t) => ts.findIndex(([a, b]) => a <= t && t <= b),
  // Quita el intervalo [a, b]; los restos de menos de MIN segundos desaparecen (el servidor también los descarta).
  restar: (ts, a, b) => ts.flatMap(([x, y]) => [[x, Math.min(y, a)], [Math.max(x, b), y]]).filter(([x, y]) => y - x >= Tramos.MIN - 1e-9),
  // Vuelve a conservar [a, b]: se une a los tramos que toca.
  sumar: (ts, a, b) => {
    const r = [];
    for (const t of [...ts, [a, b]].map((x) => [...x]).sort((p, q) => p[0] - q[0])) {
      const u = r[r.length - 1];
      if (u && t[0] <= u[1] + 0.05) u[1] = Math.max(u[1], t[1]); else r.push(t);
    }
    return r;
  },
  // Parte en dos el tramo que contiene t, si ambas mitades miden al menos MIN.
  dividir: (ts, t) => {
    const i = ts.findIndex(([a, b]) => t - a >= Tramos.MIN && b - t >= Tramos.MIN);
    return i < 0 ? null : [...ts.slice(0, i), [ts[i][0], t], [t, ts[i][1]], ...ts.slice(i + 1)];
  },
  // Primer instante que se reproduce desde t: t mismo si está dentro, si no el inicio del tramo siguiente (null al final).
  siguiente: (ts, t) => {
    for (const [a, b] of ts) { if (t < a) return a; if (t < b - 0.03) return t; }
    return null;
  },
};
if (typeof module !== "undefined") module.exports = Tramos;

// ---------------------------------------------------------------- editor
const ZOOMS = [1, 2, 4, 8, 16, 32];
const PASOS_REGLA = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
const rd = (s) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;     // 1:05.3
const pct = (t, dur) => `${(t / dur) * 100}%`;
let editorAbierto = false;

async function abrirEditorTiempos(t) {
  if (editorAbierto) return;
  editorAbierto = true;
  let L;
  try { L = await api(`/api/trabajos/${t.id}/linea`); } catch (e) { editorAbierto = false; throw e; }
  const dur = L.duracion, palabras = L.palabras, guardado = JSON.stringify(L.tramos);
  let tramos = JSON.parse(guardado), hist = [guardado], pos = 0;
  let sel = null, selP = null, ancla = null, foco = 0, zoom = 0, arrastre = false;
  let antes = document.activeElement;

  const raiz = document.createElement("div");
  raiz.className = "et";
  raiz.setAttribute("role", "dialog"); raiz.setAttribute("aria-modal", "true"); raiz.setAttribute("aria-labelledby", "et-titulo");
  raiz.tabIndex = -1;          // un clic en la onda o la regla deja el foco aquí, y los atajos siguen funcionando
  const onda = L.picos.length ? `M0,50 ${L.picos.map((v, i) => `L${i + 0.5},${50 - v * 47}`).join(" ")} L${L.picos.length},50 ${L.picos.map((v, i) => `L${L.picos.length - i - 0.5},${50 + L.picos[L.picos.length - 1 - i] * 47}`).join(" ")} Z` : "";
  raiz.innerHTML = h`
    <header class="et-cabeza">
      <div class="et-nombre"><h2 id="et-titulo">Editar tiempos</h2><p class="tenue pequeno">${t.nombre}</p></div>
      <div class="fila et-historia"><button class="icono-boton" id="et-deshacer" aria-label="Deshacer" title="Deshacer (Ctrl+Z)">${ic("deshacer")}</button><button class="icono-boton" id="et-rehacer" aria-label="Rehacer" title="Rehacer (Ctrl+Y)">${ic("rehacer")}</button></div>
      <button class="icono-boton" id="et-cerrar" aria-label="Cerrar el editor de tiempos" title="Cerrar (Esc)">${ic("cerrar")}</button>
    </header>
    <div class="et-escena"><video id="et-video" src="/media/${t.id}/entrada" preload="auto" playsinline></video></div>
    <div class="et-mando">
      <button class="et-play" id="et-play" aria-label="Reproducir" title="Reproducir o pausar (espacio)">${ic("reproducir")}</button>
      <p class="et-reloj"><b id="et-t">0:00.0</b><span class="tenue"> / ${rd(dur)}</span></p>
      <p class="et-resultado" id="et-resultado"></p>
      <div class="et-zoom" role="group" aria-label="Zoom de la línea de tiempo">
        <button class="icono-boton" id="et-alejar" aria-label="Alejar" title="Alejar (−)">${ic("alejar")}</button><span id="et-zoom" aria-live="polite">1×</span><button class="icono-boton" id="et-acercar" aria-label="Acercar" title="Acercar (+)">${ic("acercar")}</button>
      </div>
    </div>
    <div class="et-herramientas">
      <button id="et-dividir" title="Dividir el tramo en el cabezal (S)">${ic("tijera")}Dividir<kbd>S</kbd></button>
      <button id="et-quitar" title="Quitar el tramo elegido o las palabras elegidas (Supr)">${ic("papelera")}<span id="et-quitar-t">Quitar tramo</span><kbd>Supr</kbd></button>
      <button class="texto" id="et-completo">Volver al clip completo</button>
    </div>
    <div class="et-linea" id="et-linea">
      <div class="et-lienzo" id="et-lienzo">
        <div class="et-regla" id="et-regla" aria-hidden="true"></div>
        <div class="et-onda" id="et-onda">
          <svg viewBox="0 0 ${L.picos.length || 1} 100" preserveAspectRatio="none" aria-hidden="true"><path d="${onda}"/></svg>
          <div id="et-cortes"></div><div id="et-tramos"></div>
        </div>
        <div class="et-palabras" id="et-palabras" role="group" aria-label="Palabras del clip: flechas para recorrerlas, Mayús para elegir varias, Supr para cortarlas">
          ${palabras.map((p, i) => crudo(h`<button class="et-palabra" data-i="${i}" tabindex="${i ? -1 : 0}" style="left:${pct(p.inicio, dur)};width:${pct(p.fin - p.inicio, dur)}" aria-label="${p.texto}, ${rd(p.inicio)}">${p.texto}</button>`))}
        </div>
        <div class="et-cabezal" id="et-cabezal"><span class="et-cabezal-asa" id="et-asa" tabindex="0" role="slider" aria-label="Cabezal de reproducción" aria-valuemin="0" aria-valuemax="${dur.toFixed(1)}"></span></div>
      </div>
    </div>
    <footer class="et-pie">
      <p class="pequeno tenue et-ayuda"><kbd>Espacio</kbd> reproduce <kbd>←</kbd><kbd>→</kbd> mueven el cabezal <kbd>Mayús</kbd> pasos de 1 s. Arrastra los bordes claros para recortar.</p>
      <button id="et-cancelar">Cancelar</button><button class="primario" id="et-guardar">Guardar y renderizar</button>
    </footer>
    <p class="solo-lector" id="et-voz" aria-live="polite"></p>`;
  document.body.append(raiz);
  $("#app").inert = true; document.body.style.overflow = "hidden";

  const q = (id) => raiz.querySelector(`#et-${id}`);
  const video = q("video"), linea = q("linea"), lienzo = q("lienzo"), palabrasEl = [...raiz.querySelectorAll(".et-palabra")];
  const decir = (texto) => { q("voz").textContent = texto; };
  const tiempoEn = (x) => { const r = lienzo.getBoundingClientRect(); return Math.min(dur, Math.max(0, ((x - r.left) / r.width) * dur)); };
  const redondo = (x) => Math.round(x * 1000) / 1000;
  const actual = () => video.currentTime || 0;
  const tramoActivo = () => (sel !== null && tramos[sel] ? sel : Tramos.dentro(tramos, actual()));

  // --- pintar
  let cortesAntes = new Set(), pintado = false;
  function pintarCortes() {
    const huecos = [];
    let x = 0;
    for (const [a, b] of tramos) { if (a - x > 0.001) huecos.push([x, a]); x = b; }
    if (dur - x > 0.001) huecos.push([x, dur]);
    q("cortes").innerHTML = huecos.map(([a, b]) => `<div class="et-corte" data-k="${a.toFixed(2)}-${b.toFixed(2)}" style="left:${pct(a, dur)};width:${pct(b - a, dur)}"></div>`).join("");
    // Solo un corte nuevo (quitar, cortar palabras) aparece con un fundido; al arrastrar un borde no.
    const nuevos = [...q("cortes").children].filter((c) => !cortesAntes.has(c.dataset.k));
    if (animar() && pintado && !arrastre && nuevos.length) gsap.from(nuevos, { opacity: 0, duration: 0.28, ease: "power2.out" });
    cortesAntes = new Set(huecos.map(([a, b]) => `${a.toFixed(2)}-${b.toFixed(2)}`)); pintado = true;
  }
  const asa = (i, lado) => h`<button class="et-asa ${lado ? "fin" : "ini"}" data-i="${i}" data-lado="${lado}" aria-label="${lado ? "Final" : "Inicio"} del tramo ${i + 1}: ${rd(tramos[i][lado])}"></button>`;
  function pintarTramos() {
    q("tramos").innerHTML = tramos.map(([a, b], i) => h`<div class="et-tramo ${sel === i ? "elegido" : ""}" data-i="${i}" style="left:${pct(a, dur)};width:${pct(b - a, dur)}">${crudo(asa(i, 0))}${crudo(asa(i, 1))}</div>`).join("");
  }
  let mostrado = null;
  function pintarResultado() {
    const total = Tramos.total(tramos), bien = total >= Tramos.TOTAL_MIN - 1e-6 && total <= Tramos.TOTAL_MAX + 1e-6;
    const el = q("resultado");
    el.classList.toggle("fuera", !bien);
    const texto = (v) => `Resultado <b>${rd(v)}</b>`;
    if (animar() && mostrado !== null && !arrastre && Math.abs(mostrado - total) > 0.05) {
      const p = { v: mostrado };
      gsap.to(p, { v: total, duration: 0.35, ease: "power2.out", overwrite: true, onUpdate: () => { el.firstElementChild.innerHTML = texto(p.v); } });
    }
    el.innerHTML = `<span>${texto(total)}</span>${bien ? "" : `<span class="et-aviso" role="alert">${total < Tramos.TOTAL_MIN ? "Muy corto: un Short dura al menos 3 s" : "Muy largo: un Short dura como máximo 3:00"}</span>`}`;
    mostrado = total;
    const sucio = JSON.stringify(tramos) !== guardado;
    q("guardar").disabled = !bien || !sucio || arrastre;
    q("deshacer").disabled = !pos; q("rehacer").disabled = pos === hist.length - 1;
    q("completo").disabled = tramos.length === 1 && tramos[0][0] <= 0.05 && tramos[0][1] >= dur - 0.05;
    sinPerderFoco();
  }
  // Un botón con foco que se desactiva lo dejaría en <body>: el foco vuelve al editor.
  const sinPerderFoco = () => { if (document.activeElement?.disabled) raiz.focus(); };
  function pintarPalabras() {
    palabrasEl.forEach((b, i) => {
      const p = palabras[i];
      b.classList.toggle("fuera", Tramos.dentro(tramos, (p.inicio + p.fin) / 2) < 0);
      b.classList.toggle("sel", !!selP && i >= selP[0] && i <= selP[1]);
    });
    const restaurar = selP && palabrasEl.slice(selP[0], selP[1] + 1).every((b) => b.classList.contains("fuera"));
    q("quitar-t").textContent = selP ? (restaurar ? "Recuperar palabras" : "Cortar palabras") : "Quitar tramo";
  }
  function pintarRegla() {
    const ancho = lienzo.clientWidth, paso = PASOS_REGLA.find((p) => (p / dur) * ancho >= 64) || 600;
    let html = "";
    for (let s = 0; s <= dur + 1e-6; s += paso) html += `<span style="left:${pct(s, dur)}">${paso < 1 ? rd(s) : reloj(s)}</span>`;
    q("regla").innerHTML = html;
  }
  function pintarCabezal(tt = actual()) {
    q("cabezal").style.left = pct(tt, dur);
    q("t").textContent = rd(tt);
    const a = q("asa"); a.setAttribute("aria-valuenow", tt.toFixed(1)); a.setAttribute("aria-valuetext", rd(tt));
  }
  function pintarTodo() { pintarCortes(); pintarTramos(); pintarPalabras(); pintarResultado(); }

  // --- historial: cada cambio terminado entra una vez
  function registrar(mensaje) {
    tramos = tramos.map(([a, b]) => [redondo(a), redondo(b)]);
    const j = JSON.stringify(tramos);
    if (j !== hist[pos]) { hist = hist.slice(0, pos + 1); hist.push(j); pos++; }
    pintarTodo();
    if (mensaje) decir(`${mensaje}. Resultado ${rd(Tramos.total(tramos))}.`);
  }
  function historia(d) {
    if (pos + d < 0 || pos + d >= hist.length) return;
    pos += d; tramos = JSON.parse(hist[pos]); sel = null; selP = null;
    pintarTodo(); decir(`${d < 0 ? "Deshecho" : "Rehecho"}. Resultado ${rd(Tramos.total(tramos))}.`);
  }

  // --- reproducción: las partes cortadas se saltan
  const ir = (tt) => { video.currentTime = Math.min(dur, Math.max(0, tt)); pintarCabezal(video.currentTime); seguir(true); };
  function alternar() {
    if (!video.paused) return video.pause();
    if (!tramos.length) return decir("No queda ningún tramo para reproducir.");
    const d = Tramos.siguiente(tramos, actual());
    if (d === null) video.currentTime = tramos[0][0]; else if (d !== actual()) video.currentTime = d;
    video.play().catch(() => {});
  }
  // Con zoom, la línea se desplaza para que el cabezal siga a la vista.
  function seguir(centrar) {
    const x = (actual() / dur) * lienzo.clientWidth, v = linea.scrollLeft, w = linea.clientWidth;
    if (x < v + 24 || x > v + w - 24) linea.scrollLeft = centrar ? x - w / 2 : x - w * 0.15;
  }
  function vigilar() {
    if (video.paused || video.seeking) return;
    const tt = actual(), d = Tramos.siguiente(tramos, tt);
    if (d === null) { video.pause(); if (tramos.length) video.currentTime = tramos[tramos.length - 1][1]; }
    else if (d - tt > 0.02) video.currentTime = d;
    seguir(false);
  }
  function cuadro() {
    if (!raiz.isConnected) return;
    vigilar();
    if (!arrastre) pintarCabezal();
    requestAnimationFrame(cuadro);
  }
  video.addEventListener("timeupdate", vigilar);       // por si el navegador frena los cuadros (pestaña o ventana en segundo plano)
  video.addEventListener("play", () => { q("play").innerHTML = icono("pausa"); q("play").setAttribute("aria-label", "Pausar"); });
  video.addEventListener("pause", () => { q("play").innerHTML = icono("reproducir"); q("play").setAttribute("aria-label", "Reproducir"); });
  video.addEventListener("loadedmetadata", () => { if (tramos.length) video.currentTime = tramos[0][0]; }, { once: true });
  video.addEventListener("error", () => {
    q("play").disabled = true;
    raiz.querySelector(".et-escena").innerHTML = `<p class="nota">Este navegador no puede reproducir el archivo original. Puedes recortar igual con la onda y las palabras.</p>`;
  });

  // --- acciones
  function dividir() {
    const tt = redondo(actual()), r = Tramos.dividir(tramos, tt);
    if (!r) return decir(Tramos.dentro(tramos, tt) < 0 ? "El cabezal está en una parte cortada." : "Muy cerca del borde: cada parte debe durar al menos 0,3 s.");
    tramos = r; sel = Tramos.dentro(tramos, tt + 0.01); registrar(`Tramo dividido en ${rd(tt)}`);
  }
  function quitar() {
    if (selP) {
      const [i, j] = selP, a = palabras[i].inicio, b = palabras[j].fin;
      const restaurar = palabrasEl.slice(i, j + 1).every((x) => x.classList.contains("fuera"));
      tramos = restaurar ? Tramos.sumar(tramos, a, b) : Tramos.restar(tramos, a, b);
      selP = null; sel = null;
      return registrar(`${j - i + 1} ${j > i ? "palabras" : "palabra"} ${restaurar ? "recuperadas" : "cortadas"}`);
    }
    const i = tramoActivo();
    if (i < 0) return decir("Elige un tramo o pon el cabezal sobre uno.");
    tramos = tramos.filter((_, k) => k !== i); sel = null;
    registrar(`Tramo ${i + 1} quitado`);
  }
  function hacerZoom(d) {
    const z = Math.min(ZOOMS.length - 1, Math.max(0, zoom + d));
    if (z === zoom) return;
    zoom = z; lienzo.style.width = `${ZOOMS[zoom] * 100}%`; q("zoom").textContent = `${ZOOMS[zoom]}×`;
    q("alejar").disabled = !zoom; q("acercar").disabled = zoom === ZOOMS.length - 1;
    pintarRegla(); sinPerderFoco();
    linea.scrollLeft = (actual() / dur) * lienzo.clientWidth - linea.clientWidth / 2;
  }
  async function cerrar(sinPreguntar = false) {
    if (!sinPreguntar && JSON.stringify(tramos) !== guardado &&
        !await confirmar("Salir sin guardar", "Los cambios de tiempos de este clip se perderán.", "Salir sin guardar", true)) return;
    video.pause(); video.removeAttribute("src"); video.load();            // suelta el archivo (en Windows no se borra un archivo abierto)
    const fin = () => {
      document.removeEventListener("keydown", teclas, true);
      raiz.remove(); $("#app").inert = false; document.body.style.overflow = ""; editorAbierto = false;
      (antes?.isConnected && antes !== document.body ? antes : $("#principal")).focus();
    };
    if (animar()) gsap.to(raiz, { opacity: 0, duration: 0.16, ease: "power1.in", onComplete: fin }); else fin();
  }

  q("play").onclick = alternar;
  q("dividir").onclick = dividir;
  q("quitar").onclick = quitar;
  q("completo").onclick = () => { tramos = [[0, dur]]; sel = null; selP = null; registrar("Clip completo"); };
  q("deshacer").onclick = () => historia(-1); q("rehacer").onclick = () => historia(1);
  q("acercar").onclick = () => hacerZoom(1); q("alejar").onclick = () => hacerZoom(-1);
  q("cerrar").onclick = () => cerrar(); q("cancelar").onclick = () => cerrar();
  q("guardar").onclick = intentar(async () => {
    q("guardar").disabled = true;
    try {
      await api(`/api/trabajos/${t.id}/edicion`, { method: "PUT", json: { tramos } });
    } catch (e) { pintarResultado(); throw e; }
    avisar(`Tiempos guardados: el clip durará ${rd(Tramos.total(tramos))}. Se renderiza de nuevo.`);
    antes = null;                 // el botón «Editar tiempos» desaparece mientras se renderiza
    cerrar(true); refrescar();
  });

  // --- arrastres (mouse y dedo): bordes de tramo, cabezal y regla, selección de palabras
  function arrastrar(e, el, mover, soltar) {
    e.preventDefault();
    el.setPointerCapture(e.pointerId);
    arrastre = true;
    el.onpointermove = (ev) => mover(ev);
    el.onpointerup = el.onpointercancel = () => { el.onpointermove = el.onpointerup = el.onpointercancel = null; arrastre = false; soltar?.(); pintarResultado(); };
    mover(e);
  }
  const bordes = palabras.flatMap((p) => [p.inicio, p.fin]);
  // Al arrastrar un borde se pega al inicio o al final de la palabra más cercana (8 px).
  const imantar = (tt) => {
    const b = bordes.reduce((m, x) => (Math.abs(x - tt) < Math.abs(m - tt) ? x : m), Infinity);
    return Math.abs(b - tt) <= (8 / lienzo.clientWidth) * dur ? b : tt;
  };
  function limites(i, lado) {
    return lado ? [tramos[i][0] + Tramos.MIN, i < tramos.length - 1 ? tramos[i + 1][0] : dur]
      : [i ? tramos[i - 1][1] : 0, tramos[i][1] - Tramos.MIN];
  }
  function moverBorde(i, lado, tt, el) {
    const [lo, hi] = limites(i, lado);
    tramos[i][lado] = redondo(Math.min(hi, Math.max(lo, tt)));
    const d = el.parentElement;
    d.style.left = pct(tramos[i][0], dur); d.style.width = pct(tramos[i][1] - tramos[i][0], dur);
    el.setAttribute("aria-label", `${lado ? "Final" : "Inicio"} del tramo ${i + 1}: ${rd(tramos[i][lado])}`);
    video.pause(); video.currentTime = tramos[i][lado]; pintarCabezal(tramos[i][lado]);  // el video muestra el cuadro del borde
    pintarCortes(); pintarResultado();
  }
  q("onda").addEventListener("pointerdown", (e) => {
    const a = e.target.closest(".et-asa");
    if (!a) return;
    const i = +a.dataset.i, lado = +a.dataset.lado;
    sel = i; raiz.querySelectorAll(".et-tramo").forEach((d) => d.classList.toggle("elegido", +d.dataset.i === i));
    a.focus({ preventScroll: true });
    arrastrar(e, a, (ev) => moverBorde(i, lado, imantar(tiempoEn(ev.clientX)), a), () => registrar(`${lado ? "Final" : "Inicio"} del tramo ${i + 1} en ${rd(tramos[i][lado])}`));
  });
  // Un toque en la onda (sin arrastrar: arrastrar desplaza la línea) lleva el cabezal y elige el tramo.
  q("onda").addEventListener("click", (e) => {
    if (e.target.closest(".et-asa")) return;
    const tt = tiempoEn(e.clientX), i = Tramos.dentro(tramos, tt);
    sel = i < 0 ? null : i; selP = null;
    ir(tt); pintarTramos(); pintarPalabras();
  });
  const arrastrarCabezal = (e) => { video.pause(); arrastrar(e, e.currentTarget, (ev) => { const tt = tiempoEn(ev.clientX); video.currentTime = tt; pintarCabezal(tt); }); };
  q("regla").addEventListener("pointerdown", arrastrarCabezal);
  q("asa").addEventListener("pointerdown", arrastrarCabezal);

  const indicePalabra = (tt) => {
    let k = 0;
    palabras.forEach((p, i) => { if (p.inicio <= tt) k = i; });
    return k;
  };
  function elegirPalabra(i, extender) {
    if (!palabras.length) return;
    i = Math.min(palabras.length - 1, Math.max(0, i));
    if (!extender || ancla === null) ancla = i;
    selP = [Math.min(ancla, i), Math.max(ancla, i)]; sel = null;
    palabrasEl[foco].tabIndex = -1; foco = i; palabrasEl[i].tabIndex = 0;
    if (document.activeElement !== palabrasEl[i]) palabrasEl[i].focus({ preventScroll: true });
    video.pause(); ir(palabras[i].inicio); pintarTramos(); pintarPalabras();
    const n = selP[1] - selP[0] + 1;
    decir(n > 1 ? `${n} palabras elegidas` : `${palabras[i].texto}, ${rd(palabras[i].inicio)}`);
  }
  q("palabras").addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".et-palabra");
    if (!b) return;
    let ultima = -1;      // arrastrar sobre las palabras extiende la selección
    arrastrar(e, e.currentTarget, (ev) => {
      const i = ev === e ? +b.dataset.i : indicePalabra(tiempoEn(ev.clientX));
      if (i !== ultima) elegirPalabra(i, ev === e ? e.shiftKey : true);
      ultima = i;
    });
  });

  // --- teclado: en todo el documento mientras el editor está abierto (el foco puede quedar en un botón que se desactiva)
  function teclas(e) {
    if (!$("#modal-fondo").hidden) return;
    const k = e.key, ctrl = e.ctrlKey || e.metaKey, enAsa = e.target.closest?.(".et-asa"), enPalabra = e.target.closest?.(".et-palabra");
    if (ctrl && (k.toLowerCase() === "z" || k.toLowerCase() === "y")) { e.preventDefault(); return historia(k.toLowerCase() === "z" && !e.shiftKey ? -1 : 1); }
    if (ctrl || e.altKey) return;
    const paso = e.shiftKey ? 1 : 0.1;
    if ((k === "ArrowLeft" || k === "ArrowRight") && enAsa) {
      e.preventDefault();
      const i = +enAsa.dataset.i, lado = +enAsa.dataset.lado;
      sel = i; moverBorde(i, lado, tramos[i][lado] + (k === "ArrowLeft" ? -paso : paso), enAsa);
      registrar(`${lado ? "Final" : "Inicio"} del tramo ${i + 1} en ${rd(tramos[i][lado])}`);
      return raiz.querySelector(`.et-asa[data-i="${i}"][data-lado="${lado}"]`).focus();     // los tramos se repintaron
    }
    if ((k === "ArrowLeft" || k === "ArrowRight") && enPalabra) { e.preventDefault(); return elegirPalabra(foco + (k === "ArrowLeft" ? -1 : 1), e.shiftKey); }
    if (k === "Enter" && enPalabra) { e.preventDefault(); return elegirPalabra(+enPalabra.dataset.i, e.shiftKey); }
    if (k === " " && !e.target.matches("input, textarea, select")) { e.preventDefault(); alternar(); }
    else if (k === "ArrowLeft" || k === "ArrowRight") { e.preventDefault(); video.pause(); ir(actual() + (k === "ArrowLeft" ? -paso : paso)); }
    else if (k === "Home" || k === "End") { e.preventDefault(); ir(k === "Home" ? 0 : dur); }
    else if (k.toLowerCase() === "s") { e.preventDefault(); dividir(); }
    else if (k === "Delete" || k === "Backspace") { e.preventDefault(); quitar(); }
    else if (k === "+" || k === "=") hacerZoom(1);
    else if (k === "-") hacerZoom(-1);
    else if (k === "Escape") {
      e.stopPropagation();
      if (selP || sel !== null) { selP = null; sel = null; pintarTramos(); pintarPalabras(); decir("Nada elegido"); } else cerrar();
    }
  }
  document.addEventListener("keydown", teclas, true);       // captura: antes que el Esc general de app.js
  linea.addEventListener("wheel", (e) => { if (e.ctrlKey) { e.preventDefault(); hacerZoom(e.deltaY < 0 ? 1 : -1); } }, { passive: false });
  new ResizeObserver(() => pintarRegla()).observe(linea);

  q("alejar").disabled = true;
  pintarTodo(); pintarRegla(); pintarCabezal(tramos[0]?.[0] || 0);
  requestAnimationFrame(cuadro);
  q("play").focus();
  // Entrada: la onda se dibuja de izquierda a derecha y el resto llega detrás.
  if (animar()) {
    gsap.from(raiz, { opacity: 0, duration: 0.18 });
    gsap.from(raiz.querySelectorAll(".et-escena, .et-mando, .et-herramientas, .et-pie"), { y: 10, opacity: 0, duration: 0.3, ease: "power3.out", stagger: 0.04, clearProps: "all" });
    gsap.fromTo(raiz.querySelector(".et-onda svg"), { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: 0.7, ease: "power2.inOut", delay: 0.1, clearProps: "clipPath" });
  }
}
