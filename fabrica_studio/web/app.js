"use strict";
// Panel de Fábrica Studio. Sin dependencias: un único archivo que consulta la API cada 2 s.

const $ = (s, r = document) => r.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// Plantilla que escapa todo lo interpolado, salvo lo marcado con crudo().
const crudo = (s) => ({ __crudo: String(s) });
const h = (partes, ...vals) => partes.reduce((a, p, i) => a + p + (i < vals.length ? (vals[i]?.__crudo ?? (Array.isArray(vals[i]) ? vals[i].map((x) => x?.__crudo ?? esc(x)).join("") : esc(vals[i]))) : ""), "");

const ETAPAS = [["importar", "Importar"], ["comprobar", "Comprobar"], ["transcribir", "Transcribir"], ["textos", "Textos"], ["subtitulos", "Subtítulos"], ["render", "Render"], ["subir", "Subir"]];
const ETAPAS_LARGO = [["importar", "Importar"], ["comprobar", "Comprobar"], ["transcribir", "Transcribir"], ["momentos", "Momentos"]];
const etapasDe = (t) => (t.modo === "largo" ? ETAPAS_LARGO : ETAPAS);
const reloj = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const aSegundos = (txt) => { const p = String(txt).trim().split(":").map(Number); return p.some(isNaN) ? NaN : p.reduce((a, x) => a * 60 + x, 0); };
const ESTADOS = { pendiente: "En espera", procesando: "Procesando", propuestas: "Momentos listos", renderizado: "Renderizado", subiendo: "Subiendo", publicado: "Subido · privado", error: "Error" };
const dos = (n) => String(n).padStart(2, "0");
const calma = matchMedia("(prefers-reduced-motion: reduce)");   // con «reducir movimiento» nada se anima
let S = { cambios: {}, orden: "recientes", desde: "cola", busca: "", filtro: "todos", conectado: true, dispositivos: null, sesion: null, estado: null, vista: "resumen", jid: null, detalle: null, sucio: false, pestana: "diseno", ajustes: null };

async function api(ruta, opciones = {}) {
  if (opciones.json !== undefined) {
    opciones.body = JSON.stringify(opciones.json);
    opciones.headers = { "Content-Type": "application/json" };
  }
  const r = await fetch(ruta, opciones);
  if (r.status === 401) { sinAcceso(); throw new Error("Inicia sesión o vincula este dispositivo."); }
  const datos = r.headers.get("content-type")?.includes("json") ? await r.json() : null;
  if (!r.ok) throw new Error(datos?.error || `Error ${r.status}`);
  return datos;
}

function avisar(texto, mal = false) {
  const d = document.createElement("div");
  d.textContent = texto;
  if (mal) d.className = "mal";
  $("#avisos").append(d);
  setTimeout(() => salir(d, () => d.remove()), mal ? 9000 : 4000);
}
// Salida deslizándose (Web Animations API); al terminar llama a hecho().
function salir(el, hecho) {
  if (calma.matches) return void hecho();
  const a = el.animate({ opacity: [1, 0], transform: ["none", "translateY(10px)"] }, { duration: 180, easing: "ease-in" });
  a.onfinish = hecho;
  return a;
}
const intentar = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { avisar(e.message, true); } };

// ---------------------------------------------------------------- piezas comunes
const ic = (n) => crudo(icono(n));
const GERUNDIOS = { importar: "Importando", comprobar: "Comprobando", transcribir: "Transcribiendo", textos: "Creando textos", subtitulos: "Subtitulando", render: "Renderizando", subir: "Subiendo", momentos: "Buscando momentos" };
const CLASE_ESTADO = { pendiente: "", procesando: "proceso", subiendo: "proceso", propuestas: "listo", renderizado: "listo", publicado: "subido", error: "fallo" };
const FILTROS = [["todos", "Todos", () => true], ["espera", "En espera", (t) => t.estado === "pendiente"],
  ["generando", "Generando", (t) => ["procesando", "subiendo"].includes(t.estado)],
  ["listos", "Listos", (t) => ["renderizado", "propuestas", "publicado"].includes(t.estado)], ["error", "Con error", (t) => t.estado === "error"]];
const NOMBRES_VISTA = { resumen: "Resumen", cola: "Cola de clips", biblioteca: "Biblioteca", ajustes: "Ajustes", trabajo: "Clip" };
const enCola = (t) => ["pendiente", "procesando", "subiendo"].includes(t.estado);
const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;
const coincide = (t) => !S.busca || `${t.nombre} ${t.textos.titulo || ""}`.toLowerCase().includes(S.busca);
const etiquetaOrigen = (t) => ({ archivo: "Archivo importado", carpeta: "Carpeta 1_clips_crudos", enlace: "Enlace de Kick", momento: "Momento de un video largo" }[t.origen_tipo]) + (t.modo === "largo" ? " · video largo" : "");

// Cambia el contenido solo si es distinto (no reinicia animaciones) y conserva el foco del teclado.
function poner(el, html) {
  if (!el || el._html === html) return;
  const a = document.activeElement, clave = el.contains(a) && (a.getAttribute("href") ? `[href="${a.getAttribute("href")}"]` : a.dataset.foco ? `[data-foco="${a.dataset.foco}"]` : "");
  el.innerHTML = el._html = html;
  if (clave) el.querySelector(clave)?.focus();
}
// Lista con clave (id del trabajo): cada elemento se actualiza por separado y solo los nuevos
// llevan la animación de entrada (al abrir la vista o al llegar un trabajo), escalonada hasta 8.
function ponerLista(el, trabajos, etiqueta, html) {
  el._html = null;
  const viejos = new Map([...el.children].map((c) => [c.dataset.k, c]));
  let nuevos = 0;
  trabajos.forEach((t, i) => {
    let c = viejos.get(t.id);
    viejos.delete(t.id);
    if (!c) { c = document.createElement(etiqueta); c.dataset.k = t.id; c.className = "entra-fila"; c.style.setProperty("--i", Math.min(nuevos++, 8)); }
    poner(c, html(t));
    if (el.children[i] !== c) el.insertBefore(c, el.children[i] || null);
  });
  viejos.forEach((c) => c.remove());
}
// Esqueleto de carga mientras llegan los datos de la API.
function esqueleto(m) {
  if (!S.conectado) m.innerHTML = `<div class="panel sin-nada" role="status">Sin conexión con el PC. Se reintenta cada 2 s.</div>`;
  else if (!$(".esqueleto", m)) m.innerHTML = `<div class="esqueleto" role="status"><span class="solo-lector">Cargando…</span><i style="width:38%;height:34px"></i><i style="width:24%"></i><div><i></i><i></i><i></i></div><i style="height:220px"></i></div>`;
}
// Cuenta desde cero hasta el número real que ya entregó la API (solo al abrir el Resumen).
function contar(raiz) {
  if (calma.matches) return;
  raiz.querySelectorAll("[data-cuenta]").forEach((el) => {
    const fin = +el.dataset.cuenta, t0 = performance.now();
    const paso = (t) => {
      const p = Math.min((t - t0) / 600, 1);
      el.textContent = dos(Math.round(fin * (1 - (1 - p) ** 3)));
      if (p < 1 && el.isConnected) requestAnimationFrame(paso);
    };
    if (fin) paso(t0);
  });
}
function hidratar(raiz = document) { raiz.querySelectorAll("i[data-icono]").forEach((i) => { i.outerHTML = icono(i.dataset.icono); }); }

function pastilla(t) {
  const texto = t.estado === "procesando" ? GERUNDIOS[t.etapa] || ESTADOS.procesando : t.estado === "renderizado" ? "Listo para revisar" : ESTADOS[t.estado];
  const terminado = ["renderizado", "publicado", "propuestas"].includes(t.estado);
  return h`<span class="pastilla ${CLASE_ESTADO[t.estado]} ${S.cambios[t.id]?.logro ? "recien" : ""}">${terminado ? ic("check") : ""}${texto}</span>`;
}
function clipHtml(t) {
  const mini = t.tiene_video ? h`<img src="/media/${t.id}/miniatura.jpg?v=${t.actualizado}" alt="" loading="lazy">` : icono("pelicula");
  const mal = t.estado === "error";
  const linea = mal ? t.error.split("\n")[0] : t.progreso || t.textos.titulo || etiquetaOrigen(t);
  const etapas = enCola(t) || mal ? h`<span class="segmentos" role="img" aria-label="Etapas: ${etapasDe(t).filter(([k]) => t.etapas[k]?.estado === "hecho").length} de ${etapasDe(t).length} completadas">${etapasDe(t).map(([k]) => crudo(h`<i class="${t.etapas[k]?.estado || ""} ${S.cambios[t.id]?.etapas.includes(k) ? "recien" : ""}"></i>`))}</span>` : "";
  return h`<a class="clip" href="#trabajo/${t.id}"><span class="miniatura">${crudo(mini)}</span>
    <span class="clip-texto"><span class="clip-nombre">${t.nombre}</span><span class="clip-meta ${mal ? "mal" : ""}">${linea}</span>${crudo(etapas)}</span></a>`;
}

// ---------------------------------------------------------------- ventanas
let modalAntes = null, modalResuelve = null, modalSalida = null;
function abrirModal(titulo, cuerpo, pie = "") {
  modalAntes = modalAntes || document.activeElement;
  $("#modal-fondo").getAnimations({ subtree: true }).forEach((a) => a.cancel()); modalSalida = null;   // corta una salida a medias
  $("#modal-titulo").textContent = titulo;
  $("#modal-cuerpo").innerHTML = cuerpo; $("#modal-pie").innerHTML = pie;
  $("#modal-fondo").hidden = false; document.body.style.overflow = "hidden";
  ($("#modal-cuerpo").querySelector("input:not([type=file]), textarea, select") || $("#modal-pie button:last-child") || $("#modal button")).focus();
}
function cerrarModal(valor = false) {
  const fondo = $("#modal-fondo");
  if (fondo.hidden || modalSalida) return;
  document.body.style.overflow = "";
  if (modalAntes && document.contains(modalAntes)) modalAntes.focus();
  modalAntes = null;
  const velo = calma.matches ? null : fondo.animate({ opacity: [1, 0] }, { duration: 180, fill: "forwards" });
  modalSalida = salir($("#modal"), () => { fondo.hidden = true; velo?.cancel(); modalSalida = null; });
  const r = modalResuelve; modalResuelve = null; r?.(valor);
}
// Sustituye a confirm(): devuelve una promesa con true si se acepta.
function confirmar(titulo, texto, etiqueta, peligro = false) {
  return new Promise((resolver) => {
    abrirModal(titulo, h`<p>${texto}</p>`, h`<button data-accion="cerrar-modal">Cancelar</button><button class="primario ${peligro ? "peligro" : ""}" id="modal-si">${etiqueta}</button>`);
    modalResuelve = resolver;
    $("#modal-si").onclick = () => cerrarModal(true);
  });
}
$("#modal-fondo").addEventListener("mousedown", (e) => { if (e.target.id === "modal-fondo") cerrarModal(); });
document.addEventListener("keydown", (e) => {
  const abierto = !$("#modal-fondo").hidden;
  if (e.key === "Escape") { cerrarModal(); cerrarMenu(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k" && !abierto) { e.preventDefault(); $("#buscar").focus(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b" && !abierto) { e.preventDefault(); alternarLateral(); }
  if (e.key === "Tab" && abierto) {      // el foco no sale de la ventana
    const f = [...$("#modal").querySelectorAll("button, input, textarea, select, a[href]")].filter((x) => !x.disabled && x.offsetParent !== null);
    if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
    else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
  }
});

function nuevoClip(pestana = "enlace") {
  let modo = pestana, archivos = [];
  abrirModal("Añadir un clip", h`<div class="modal-pestanas" role="tablist">
      <button role="tab" id="np-enlace" aria-controls="nc-enlace" data-p="enlace">Enlace de Kick</button><button role="tab" id="np-archivo" aria-controls="nc-archivo" data-p="archivo">Archivo de video</button></div>
    <div id="nc-enlace" role="tabpanel" aria-labelledby="np-enlace"><label>Enlace público del clip<textarea id="nc-urls" rows="3" placeholder="https://kick.com/…"></textarea>
      <span>Puedes pegar varios, uno por línea. Si Kick bloquea la descarga, se indicará el motivo.</span></label></div>
    <div id="nc-archivo" role="tabpanel" aria-labelledby="np-archivo"><label class="soltar" id="nc-soltar">${ic("subir")}<span id="nc-elegidos">Arrastra videos aquí o pulsa para elegirlos</span><small>MP4, MOV, MKV o WebM</small>
      <input type="file" id="nc-archivos" class="solo-lector" accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.mkv,.webm,.m4v" multiple></label></div>
    <label>Tipo de video<select id="nc-modo"><option value="clip">Clip ya seleccionado: se convierte completo en un Short</option>
      <option value="largo">Video largo: transcribir y proponer momentos para recortar</option></select></label>
    <label class="linea"><input type="checkbox" id="nc-publicar" checked> Destinar a YouTube (siempre en privado)</label>
    <p class="error" id="nc-error" role="alert" hidden></p>`,
  h`<span class="pequeno tenue" id="nc-progreso" style="margin-right:auto"></span><button data-accion="cerrar-modal">Cancelar</button><button class="primario" id="nc-anadir">${ic("mas")}Añadir a la cola</button>`);
  const pestanas = () => ["enlace", "archivo"].forEach((p) => { $(`#np-${p}`).setAttribute("aria-selected", p === modo); $(`#nc-${p}`).hidden = p !== modo; });
  pestanas();
  $("#modal .modal-pestanas").addEventListener("click", (e) => { const b = e.target.closest("[data-p]"); if (b) { modo = b.dataset.p; pestanas(); } });
  const elegir = (lista) => { archivos = [...lista]; $("#nc-elegidos").textContent = archivos.length ? archivos.map((f) => f.name).join(", ") : "Arrastra videos aquí o pulsa para elegirlos"; };
  const soltar = $("#nc-soltar");
  ["dragover", "dragenter"].forEach((ev) => soltar.addEventListener(ev, (e) => { e.preventDefault(); soltar.classList.add("encima"); }));
  ["dragleave", "drop"].forEach((ev) => soltar.addEventListener(ev, (e) => { if (ev === "drop" || !soltar.contains(e.relatedTarget)) soltar.classList.remove("encima"); }));
  soltar.addEventListener("drop", (e) => { e.preventDefault(); elegir(e.dataTransfer.files); });
  $("#nc-archivos").addEventListener("change", (e) => elegir(e.target.files));
  if (pestana === "archivo") $("#nc-archivos").focus();
  $("#nc-anadir").onclick = async () => {
    const urls = [...new Set($("#nc-urls").value.split(/[\s,]+/).filter(Boolean))];
    const cosas = modo === "enlace" ? urls : archivos, fallos = [];
    const error = $("#nc-error"); error.hidden = true;
    if (!cosas.length) { error.textContent = modo === "enlace" ? "Pega al menos un enlace." : "Elige al menos un archivo de video."; error.hidden = false; return; }
    const publicar = $("#nc-publicar").checked, tipo = $("#nc-modo").value, boton = $("#nc-anadir");
    boton.disabled = true;
    let bien = 0;
    for (const [i, c] of cosas.entries()) {
      $("#nc-progreso").textContent = `Enviando ${i + 1} de ${cosas.length}…`;
      try {
        if (modo === "enlace") await api("/api/importar/enlace", { method: "POST", json: { url: c, publicar, modo: tipo } });
        else { const d = new FormData(); d.append("archivo", c); d.append("publicar", publicar); d.append("modo", tipo); await api("/api/importar/archivo", { method: "POST", body: d }); }
        bien++;
      } catch (e) { fallos.push(`${c.name || c}: ${e.message}`); }
    }
    if (bien) avisar(`${plural(bien, "clip añadido", "clips añadidos")} a la cola.`);
    refrescar();
    if (!fallos.length) return cerrarModal();
    if (!$("#nc-anadir")) return avisar(fallos.join("\n"), true);     // la ventana se cerró mientras se enviaba
    boton.disabled = false; $("#nc-progreso").textContent = "";
    error.textContent = fallos.join("\n"); error.style.whiteSpace = "pre-wrap"; error.hidden = false;
  };
}

// ---------------------------------------------------------------- arranque y navegación
// Pantallas de acceso: "bienvenida" (crear cuenta, solo en el PC), "login" o "vincular" (código de 6 dígitos).
const leerSesion = async () => { S.sesion = await (await fetch("/api/sesion")).json(); return S.sesion; };
function mostrarAcceso(modo, nota = "") {
  cerrarModal();
  $("#app").hidden = true; $("#acceso").hidden = false;
  for (const m of ["bienvenida", "form-login", "vincular"]) $(`#${m}`).hidden = !m.endsWith(modo);
  $("#l-nota").textContent = nota || "Tu estudio te espera.";
  $("#l-codigo").hidden = S.sesion.local; $("#v-login").hidden = !S.sesion.cuenta_creada;
  document.title = `${{ bienvenida: "Bienvenida", login: "Iniciar sesión", vincular: "Vincular" }[modo]} · Fábrica Studio`;
  if (modo === "login" && S.sesion.espera_login > 0) bloquear(S.sesion.espera_login);    // sigue bloqueado tras recargar
  $(`#acceso > :not([hidden]) input:not(:disabled)`)?.focus();
}
// La API respondió 401 con el panel abierto: la sesión caducó o se cerró desde el PC.
async function sinAcceso() {
  if (!$("#acceso").hidden || (await leerSesion()).autorizado) return;
  mostrarAcceso(S.sesion.cuenta_creada ? "login" : "vincular", S.sesion.cuenta_creada ? "Tu sesión caducó. Vuelve a entrar." : "");
}
const enviar = async (ruta, json) => {
  const r = await fetch(ruta, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(json) });
  return [r, await r.json().catch(() => ({}))];
};
// Error visible en la tarjeta: mensaje del servidor tal cual y una sacudida (sin movimiento si está reducido).
function errorAcceso(f, texto) {
  const p = $(".error", f);
  p.className = "error"; p.textContent = texto;
  f.classList.remove("sacude"); void f.offsetWidth; f.classList.add("sacude");
}

// Bloqueo por intentos (429). La cuenta regresiva sale de los segundos que da el servidor y se calcula
// contra la hora de fin con el reloj monótono: no se atrasa aunque la pestaña quede en segundo plano.
let finBloqueo = 0, relojBloqueo = 0;
const faltaTexto = (s) => (s < 60 ? `${s} s` : reloj(s));
function bloquear(segundos) {
  finBloqueo = performance.now() + segundos * 1000;
  $("#l-bloqueo").style.setProperty("--espera", `${segundos}s`);
  const p = $("#form-login .error");
  p.className = "error solo-lector"; p.textContent = `Demasiados intentos. Espera ${segundos} segundos.`;   // se anuncia una sola vez
  clearInterval(relojBloqueo); relojBloqueo = setInterval(pintarBloqueo, 250);
  pintarBloqueo();
}
function pintarBloqueo() {
  const f = $("#form-login"), falta = Math.ceil((finBloqueo - performance.now()) / 1000), activo = falta > 0;
  f.classList.toggle("bloqueado", activo); $("#l-bloqueo").hidden = !activo;
  f.querySelectorAll("label input, .primario").forEach((x) => { x.disabled = activo; });
  $(".primario span", f).textContent = activo ? `Espera ${faltaTexto(falta)}…` : "Entrar";
  if (activo) {
    $("#l-falta").textContent = falta < 60 ? falta : reloj(falta);
    $("#l-falta-texto").textContent = `Podrás volver a intentarlo en ${faltaTexto(falta)}.`;
    return;
  }
  clearInterval(relojBloqueo);
  const p = $(".error", f);
  p.className = "error tenue"; p.textContent = "Ya puedes volver a intentarlo.";
  if (!f.hidden) f.contrasena.focus();
}

$("#form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  if (finBloqueo > performance.now()) return;
  f.classList.add("enviando"); $(".primario", f).disabled = true;
  try {
    const [r, d] = await enviar("/api/login", { usuario: f.usuario.value, contrasena: f.contrasena.value, recordar: f.recordar.checked });
    if (r.ok) return location.reload();
    f.contrasena.value = "";
    errorAcceso(f, r.status === 429 && d.espera ? "" : d.error || `Error ${r.status}`);
    if (r.status === 429 && d.espera) bloquear(d.espera); else f.contrasena.focus();
  } catch (err) { errorAcceso(f, "No se pudo conectar con el PC."); }
  f.classList.remove("enviando"); $(".primario", f).disabled = finBloqueo > performance.now();
});

$("#form-crear").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  if (f.contrasena.value !== f.repetir.value) { errorAcceso(f, "Las dos contraseñas no coinciden."); return f.repetir.focus(); }
  $(".primario", f).disabled = true;
  try {
    const [r, d] = await enviar("/api/cuenta/crear", { nombre: f.nombre.value, contrasena: f.contrasena.value, recordar: f.recordar.checked });
    if (r.ok) return location.reload();
    if (r.status === 409) { await leerSesion(); mostrarAcceso("login", "Ya existe una cuenta. Inicia sesión."); }
    else errorAcceso(f, d.error || `Error ${r.status}`);
  } catch (err) { errorAcceso(f, "No se pudo conectar con el PC."); }
  $(".primario", f).disabled = false;
});
$("#form-crear").contrasena.addEventListener("input", (e) => $("#c-regla").classList.toggle("cumple", e.target.value.length >= 8));

$("#vincular").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/vincular", { method: "POST", json: { codigo: $("#v-codigo").value, nombre: $("#v-nombre").value } });
    location.reload();
  } catch (err) { $("#v-error").textContent = err.message; }
});
// El menú de usuario se cierra al pulsar fuera de él o al elegir una opción.
document.addEventListener("click", (e) => { if (!e.target.closest("#perfil")) $("#menu-usuario").open = false; });

// Barra lateral: plegada (72 px, solo iconos) o desplegada (224 px). Bajo 680 px es un menú que se desliza.
const movil = matchMedia("(max-width: 680px)");
let plegada = innerWidth <= 900;      // en tablet arranca plegada, salvo que se haya elegido otra cosa
try { const g = localStorage.getItem("fabrica.lateral"); if (g) plegada = g === "plegada"; } catch (e) { /* sin almacenamiento: vale el valor inicial */ }
function ponerLateral(menu = false) {
  $("#app").classList.toggle("plegada", plegada);
  if (!menu && $("#lateral.abierto")?.contains(document.activeElement)) $("#boton-menu").focus();   // el foco no se queda en el menú oculto
  $("#lateral").classList.toggle("abierto", menu); $("#velo").classList.toggle("abierto", menu);
  $("#boton-menu").setAttribute("aria-expanded", movil.matches ? menu : !plegada);
}
function alternarLateral() {
  if (movil.matches) {
    const abrir = !$("#lateral").classList.contains("abierto");
    ponerLateral(abrir);
    if (abrir) $(".nav a").focus();
    return;
  }
  plegada = !plegada;
  try { localStorage.setItem("fabrica.lateral", plegada ? "plegada" : "abierta"); } catch (e) { /* no se recuerda entre visitas */ }
  ponerLateral();
}
const cerrarMenu = () => ponerLateral();
movil.addEventListener("change", cerrarMenu);
ponerLateral();
$("#boton-menu").addEventListener("click", alternarLateral);
$("#velo").addEventListener("click", cerrarMenu);
$("#buscar").addEventListener("input", (e) => { S.busca = e.target.value.trim().toLowerCase(); pintar(false); });

function navegar() {
  const [vista, jid] = location.hash.replace("#", "").split("/");
  S.vista = vista in NOMBRES_VISTA ? vista : "resumen";
  S.jid = S.vista === "trabajo" ? jid : null;
  S.detalle = null; S.sucio = false;
  if (S.vista !== "trabajo") S.desde = S.vista === "biblioteca" ? "biblioteca" : "cola";   // a dónde vuelve el detalle
  const activa = S.vista === "trabajo" ? S.desde : S.vista;
  document.querySelectorAll(".nav a").forEach((a) => { const si = a.dataset.vista === activa; a.classList.toggle("activa", si); si ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"); });
  $("#miga").textContent = NOMBRES_VISTA[S.vista];
  document.title = `${NOMBRES_VISTA[S.vista]} · Fábrica Studio`;
  cerrarMenu(); cerrarModal();
  const m = $("#principal");
  m._html = null; m.classList.remove("entra"); void m.offsetWidth; m.classList.add("entra");   // transición solo al cambiar de vista
  pintar(true); window.scrollTo(0, 0);
  if (S.jid && S.estado) refrescar();     // el detalle se pide ya, sin esperar al ciclo de 2 s
}
window.addEventListener("hashchange", navegar);

// Cambios reales entre dos lecturas de la API: etapas recién completadas y clips que terminan.
const LOGROS = { renderizado: "está listo para revisar", publicado: "se subió en privado a YouTube", propuestas: "tiene momentos propuestos" };
function anunciar(antes) {
  S.cambios = {};
  if (!antes) return;
  const previo = new Map(antes.trabajos.map((t) => [t.id, t]));
  for (const t of S.estado.trabajos) {
    const p = previo.get(t.id);
    if (!p) continue;
    const logro = p.estado !== t.estado && t.estado in LOGROS;
    S.cambios[t.id] = { logro, etapas: Object.keys(t.etapas).filter((k) => t.etapas[k]?.estado === "hecho" && p.etapas[k]?.estado !== "hecho") };
    if (logro) avisar(`«${t.nombre}» ${LOGROS[t.estado]}.`);
  }
}

async function refrescar() {
  if ($("#app").hidden) return;           // en una pantalla de acceso no se consulta el estado
  const primera = !S.estado;
  try {
    const nuevo = await api("/api/estado"), antes = S.estado;
    S.estado = nuevo;
    S.conectado = true;
    anunciar(antes);
    if (S.jid) S.detalle = await api(`/api/trabajos/${S.jid}`).catch(() => false);
  } catch (e) { S.conectado = false; /* se reintenta en el siguiente ciclo */ }
  pintar(primera);
}

let dentro = false;
async function entrar() {
  $("#acceso").hidden = true; $("#app").hidden = false;
  if (dentro) return navegar();
  dentro = true;
  navegar();                                   // esqueleto mientras llegan los datos
  S.ajustes = await api("/api/ajustes").catch(() => null);
  await refrescar();
  setInterval(refrescar, 2000);
}
const BIENVENIDA = "fabrica.bienvenida";       // «Ahora no» la oculta para siempre en este navegador
const bienvenidaVista = () => { try { return !!localStorage.getItem(BIENVENIDA); } catch (e) { return false; } };

(async function iniciar() {
  hidratar();
  await leerSesion();
  if (!S.sesion.autorizado) return mostrarAcceso(S.sesion.cuenta_creada ? "login" : "vincular");
  if (S.sesion.local && !S.sesion.cuenta_creada && !bienvenidaVista()) return mostrarAcceso("bienvenida");
  entrar();
})();

// ---------------------------------------------------------------- vistas
function pintar(completo) {
  const m = $("#principal");
  if (!S.estado) return esqueleto(m);
  document.documentElement.style.setProperty("--fase", `-${Date.now() % 1400}ms`);   // el brillo de la etapa no salta al repintar
  pintarLateral();
  if (S.vista === "resumen") pintarResumen(m, completo);
  else if (S.vista === "cola") pintarCola(m, completo);
  else if (S.vista === "biblioteca") pintarBiblioteca(m, completo);
  else if (S.vista === "trabajo") pintarTrabajo(m, completo);
  else if (S.vista === "ajustes" && completo) { esqueleto(m); pintarAjustes(m); }
}

function pintarLateral() {
  const e = S.estado, yt = e.youtube, p = e.proveedores, n = e.trabajos.filter(enCola).length;
  $("#nav-cuenta").hidden = !n; $("#nav-cuenta").textContent = n;
  $("#nav-cuenta").setAttribute("aria-label", plural(n, "clip en cola", "clips en cola"));
  const creador = S.ajustes?.valores.creador || "Fábrica Studio";
  poner($("#espacio"), h`<div class="avatar" aria-hidden="true">${creador.slice(0, 2).toUpperCase()}</div><div><strong>${creador}</strong><small>${yt.canal_id ? `Canal: ${yt.canal_nombre}` : "Sin canal de YouTube confirmado"}</small></div>`);
  poner($("#tarjeta-pc"), h`<b>${ic("monitor")}PC anfitrión<span class="punto ${S.conectado ? "bien" : "mal"}"></span></b>
    ${S.conectado ? crudo(h`${p.ffmpeg && p.ffprobe ? "FFmpeg disponible" : "FFmpeg no encontrado"}<br>Whisper ${p.whisper.modelo}<br>Carpeta vigilada ${e.carpeta.activa ? "activa" : "desactivada"}`) : "Sin conexión con el PC. Se reintenta cada 2 s."}`);
  const s = S.sesion, donde = s.local ? "Este PC" : s.sesion_iniciada ? "Sesión iniciada" : "Dispositivo vinculado";
  poner($("#perfil"), h`<div class="avatar" aria-hidden="true">${ic(s.local ? "monitor" : "dispositivos")}</div><div><strong>${s.usuario || donde}</strong><small>${s.usuario ? `${donde} · v` : "Versión "}${s.version}</small></div>`);
  poner($("#menu-lista"), h`<a href="#ajustes" data-accion="ir-ajustes" data-p="cuenta">${ic("ajustes")}Cuenta</a>${s.sesion_iniciada ? crudo(h`<button data-accion="cerrar-sesion">${ic("salir")}Cerrar sesión</button>`) : ""}`);
}

function pintarResumen(m, completo) {
  const e = S.estado, yt = e.youtube, ts = e.trabajos;
  const abrir = completo || !$("#r-cifras");
  if (abrir) {
    m.innerHTML = h`<div class="cabecera"><div><div class="antetitulo">Tu espacio creativo</div><h1>Tu estudio</h1><p>De un buen momento a tu próximo Short.</p></div>
        <button class="primario" data-accion="nuevo">${ic("mas")}Nuevo clip</button></div>
      <div class="cifras" id="r-cifras"></div>
      <div class="dos-columnas"><div class="panel">
          <div class="panel-titulo"><div><h2>Un enlace. Un nuevo clip.</h2><p>Añade un momento de tu stream a la cola.</p></div></div>
          <form class="entrada" id="r-form"><div class="entrada-caja">${ic("enlace")}<input id="r-url" type="url" aria-label="Enlace del clip de Kick" placeholder="Pega un enlace de Kick…" autocomplete="off" required>
            <button class="primario">Añadir${ic("flecha")}</button></div>
            <div class="entrada-pie"><span>Se procesa en tu PC y se destina a YouTube en privado.</span><button type="button" class="enlace-fino" data-accion="nuevo" data-p="archivo">${ic("subir")}O elige un archivo</button></div>
            <p class="error" id="r-error" role="alert" hidden></p></form>
          <div class="franja"><h3>Actividad reciente</h3><a class="enlace-fino" href="#cola">Ver la cola${ic("flecha")}</a></div>
          <div class="recientes" id="r-recientes"></div>
          <div class="panel-pie" id="r-pie"></div></div>
        <div class="panel formato"><div class="panel-titulo"><div><h2>Tu formato</h2><p id="r-estilo"></p></div><span class="pequeno tenue">9:16</span></div>
          <div class="formato-escena"><img src="/api/diseno/vista?t=${Date.now()}" alt="Maqueta del diseño actual de tus Shorts" width="176" height="313"></div>
          <div class="panel-pie"><span>1080 × 1920</span><a class="enlace-fino" href="#ajustes" data-accion="ir-ajustes" data-p="diseno">Personalizar${ic("flecha")}</a></div></div></div>
      <div class="dos-columnas"><div class="panel conexion" id="r-youtube"></div><div class="panel conexion" id="r-tablet"></div></div>`;
    $("#r-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const error = $("#r-error"); error.hidden = true;
      try {
        await api("/api/importar/enlace", { method: "POST", json: { url: $("#r-url").value, publicar: true, modo: "clip" } });
        $("#r-url").value = ""; avisar("1 clip añadido a la cola."); refrescar();
      } catch (err) { error.textContent = err.message; error.hidden = false; }
    });
    S.dispositivos = null;
    api("/api/dispositivos").then((d) => { S.dispositivos = d; pintar(false); }).catch(() => {});
  }
  const cola = ts.filter(enCola).length, fallos = ts.filter((t) => t.estado === "error").length;
  const listos = ts.filter((t) => t.estado === "renderizado").length, subidos = ts.filter((t) => t.estado === "publicado").length;
  poner($("#r-cifras"), h`<div class="cifra"><div class="cifra-titulo">Clips en la cola${ic("capas")}</div><div class="cifra-valor"><span data-cuenta="${cola}">${dos(cola)}</span> <small>${cola === 1 ? "clip" : "clips"}</small></div>
      <div class="cifra-nota">${fallos ? `${plural(fallos, "clip con error", "clips con error")}: revísalos en la cola` : "En espera o generándose"}</div></div>
    <div class="cifra"><div class="cifra-titulo">Listos para revisar${ic("check-circulo")}</div><div class="cifra-valor"><span data-cuenta="${listos}">${dos(listos)}</span> <small>${listos === 1 ? "Short" : "Shorts"}</small></div>
      <div class="cifra-nota">${plural(subidos, "subido", "subidos")} en privado a YouTube</div></div>
    <div class="cifra"><div class="cifra-titulo">Canal de YouTube${ic("youtube")}</div><div class="cifra-valor texto">${yt.canal_id ? yt.canal_nombre : "Sin confirmar"}</div>
      <div class="cifra-nota">${yt.canal_id ? `${yt.canal_id} · subidas siempre en privado` : "No se puede subir hasta confirmar el canal"}</div></div>`);
  if (abrir) contar($("#r-cifras"));
  const recientes = [...ts].filter(coincide).sort((a, b) => b.creado - a.creado).slice(0, 3);
  if (recientes.length) ponerLista($("#r-recientes"), recientes, "div", (t) => h`<div class="reciente">${crudo(clipHtml(t))}${crudo(pastilla(t))}</div>`);
  else poner($("#r-recientes"), `<div class="sin-nada">${icono("capas")}${S.busca ? "Ningún clip coincide con la búsqueda." : "Aún no hay clips. Pega un enlace arriba para empezar."}</div>`);
  poner($("#r-pie"), h`<span>${cola ? `${plural(cola, "clip", "clips")} en cola` : "No hay clips en cola"}</span><span>${e.carpeta.activa ? "Carpeta vigilada activa" : ""}</span>`);
  $("#r-estilo").textContent = e.estilo === "completo" ? "Pantalla completa con seguimiento" : "Clásico: video completo con tarjeta";
  poner($("#r-youtube"), h`<div class="conexion-icono">${ic("youtube")}</div><div><h3>${yt.canal_id ? `Canal de destino: ${yt.canal_nombre}` : "Tu canal, en el mismo lugar"}</h3>
      <p>${yt.canal_id ? `Subida automática ${e.subida_automatica ? "activa" : "desactivada"}. Todo se sube en privado.` : yt.conectado ? "Cuenta conectada. Falta confirmar el canal de destino." : "Conecta YouTube para recibir tus Shorts en privado."}</p></div>
    <a class="boton" href="#ajustes" data-accion="ir-ajustes" data-p="youtube">${yt.canal_id ? "Ver" : "Conectar"}</a>`);
  const d = S.dispositivos;
  poner($("#r-tablet"), h`<div class="conexion-icono">${ic("dispositivos")}</div><div><h3>PC + tablet</h3>
      <p>${d === null ? "Un estudio. La misma cola." : d.length ? `${plural(d.length, "dispositivo vinculado", "dispositivos vinculados")}: ${d.map((x) => x.nombre).join(", ")}` : "Ningún dispositivo vinculado todavía."}</p></div>
    ${S.sesion.local ? crudo(h`<a class="boton" href="#ajustes" data-accion="ir-ajustes" data-p="dispositivos">Vincular</a>`) : ""}`);
}

function pintarCola(m, completo) {
  const e = S.estado, ts = e.trabajos.filter(coincide);
  if (completo || !$("#cola-cuerpo")) {
    m.innerHTML = h`<div class="cabecera"><div><div class="antetitulo">En producción</div><h1>Cola de clips</h1><p>Cada momento, en su lugar.</p></div>
        <button class="primario" data-accion="nuevo">${ic("mas")}Nuevo clip</button></div>
      <div class="herramientas"><div class="filtros" id="cola-filtros" role="group" aria-label="Filtrar por estado"></div></div>
      <div class="pila" id="cola-carpeta" style="margin-bottom:14px"></div>
      <div class="panel"><div class="tabla-desliza"><table class="tabla-cola"><thead><tr><th scope="col">Clip</th><th scope="col">Estado</th><th scope="col">Origen</th><th scope="col">Duración</th><th scope="col"><span class="solo-lector">Acciones</span></th></tr></thead>
        <tbody id="cola-cuerpo"></tbody></table></div><div id="cola-vacia" class="sin-nada" hidden></div></div>`;
  }
  poner($("#cola-filtros"), FILTROS.map(([k, n, f]) => h`<button data-accion="filtro" data-foco="f-${k}" data-f="${k}" aria-pressed="${S.filtro === k}">${n} <span>${ts.filter(f).length}</span></button>`).join(""));
  poner($("#cola-carpeta"), e.carpeta.pendientes.map((p) => h`<p class="nota"><b>${p.archivo}</b> (carpeta vigilada): ${p.motivo}</p>`).join(""));
  const visibles = ts.filter(FILTROS.find(([k]) => k === S.filtro)[2]);
  const origen = { archivo: "Archivo", carpeta: "Carpeta", enlace: "Kick", momento: "Video largo" };
  ponerLista($("#cola-cuerpo"), visibles, "tr", (t) => h`<td>${crudo(clipHtml(t))}</td><td>${crudo(pastilla(t))}</td><td>${origen[t.origen_tipo]}${t.modo === "largo" ? " · largo" : ""}</td>
    <td>${t.duracion ? reloj(t.duracion) : "—"}</td>
    <td>${["procesando", "subiendo"].includes(t.estado) ? "" : crudo(h`<button class="icono-boton" data-accion="quitar" data-foco="q-${t.id}" data-id="${t.id}" data-nombre="${t.nombre}" aria-label="Eliminar ${t.nombre}">${ic("papelera")}</button>`)}</td>`);
  $("#cola-vacia").hidden = visibles.length > 0;
  poner($("#cola-vacia"), `${icono("capas")}` + (S.busca ? "Ningún clip coincide con la búsqueda."
    : S.filtro !== "todos" ? "No hay clips en este estado."
    : h`Aún no hay clips. Pulsa «Nuevo clip»${e.carpeta.activa ? crudo(h` o copia un video en <code>${e.carpeta.ruta}</code>`) : ""}.`));
}

function pintarBiblioteca(m, completo) {
  if (completo || !$("#bib-rejilla")) {
    m.innerHTML = h`<div class="cabecera"><div><div class="antetitulo">Tus resultados</div><h1>Biblioteca</h1><p>Una colección de buenos momentos.</p></div>
        <button data-accion="nuevo" data-p="archivo">${ic("subir")}Importar un video</button></div>
      <div class="herramientas"><span class="pequeno tenue" id="bib-cuenta"></span>
        <select id="bib-orden" aria-label="Ordenar la biblioteca" style="width:auto"><option value="recientes">Más recientes primero</option><option value="nombre">Por nombre</option></select></div>
      <div class="galeria" id="bib-rejilla"></div><div id="bib-vacia" class="panel sin-nada" hidden></div>`;
    $("#bib-orden").value = S.orden;
    $("#bib-orden").addEventListener("change", (e) => { S.orden = e.target.value; pintar(false); });
  }
  const titulo = (t) => t.textos.titulo || t.nombre;
  const listos = S.estado.trabajos.filter((t) => t.tiene_video && coincide(t))
    .sort(S.orden === "nombre" ? (a, b) => titulo(a).localeCompare(titulo(b), "es") : (a, b) => b.creado - a.creado);
  $("#bib-cuenta").textContent = plural(listos.length, "Short renderizado", "Shorts renderizados");
  ponerLista($("#bib-rejilla"), listos, "div", (t) => h`<a class="pieza" href="#trabajo/${t.id}"><span class="pieza-arte">
      <img src="/media/${t.id}/miniatura.jpg?v=${t.actualizado}" alt="" loading="lazy">${crudo(pastilla(t))}${t.duracion ? crudo(h`<span class="duracion">${reloj(t.duracion)}</span>`) : ""}</span>
    <b>${titulo(t)}</b><small>${new Date(t.creado * 1000).toLocaleDateString("es-CL")} · ${t.youtube_id ? "En YouTube (privado)" : "Sin subir"}</small></a>`);
  $("#bib-vacia").hidden = listos.length > 0;
  poner($("#bib-vacia"), icono("pelicula") + (S.busca ? "Ningún Short coincide con la búsqueda." : "Aún no hay Shorts renderizados. Aparecerán aquí cuando termine el primer render."));
}

document.addEventListener("change", intentar(async (e) => {
  const sel = e.target.closest("[data-estilo-trabajo]");
  if (!sel) return;
  await api(`/api/trabajos/${S.jid}/estilo`, { method: "PUT", json: { estilo: sel.value } });
  avisar("Estilo cambiado: se renderiza de nuevo (no se repite la transcripción)."); refrescar();
}));

document.addEventListener("click", (e) => {
  const acc = e.target.closest("[data-accion]");
  if (acc) acciones[acc.dataset.accion]?.(acc);
});

// ---------------------------------------------------------------- detalle del trabajo
function pintarTrabajo(m, completo) {
  const t = S.detalle;
  if (t === null) return esqueleto(m);
  if (!t) { m.innerHTML = `<div class="cabecera"><h1>Clip</h1></div><div class="panel sin-nada">No se pudo cargar el clip: puede que ya no exista. <a href="#cola">Volver a la cola</a></div>`; return; }
  if (t.modo === "largo") return pintarLargo(m, t, completo);
  if (completo || !$("#t-estado") || $("#t-estado").dataset.id !== t.id) {
    m.innerHTML = h`<div class="cabecera"><div><a class="enlace-fino" href="#${S.desde}">← ${S.desde === "biblioteca" ? "Biblioteca" : "Cola de clips"}</a><h1 id="t-nombre" style="margin-top:8px"></h1></div></div>
      <div class="detalle"><div id="t-video"></div>
      <div class="pila"><div class="tarjeta pila" id="t-estado" data-id="${t.id}"></div><div class="pila" id="t-edicion"></div></div></div>`;
    S.sucio = false; S.version = null;
  }
  $("#t-nombre").textContent = t.nombre;
  // Video: solo se reemplaza cuando cambia el render, para no cortar la reproducción.
  const clave = t.tiene_video ? `v${t.salida ? t.etapas.render?.t : 0}` : "sin";
  const v = $("#t-video");
  if (v.dataset.clave !== clave) {
    v.dataset.clave = clave;
    v.innerHTML = t.tiene_video ? h`<video controls playsinline preload="metadata" src="/media/${t.id}/short.mp4?v=${clave}" poster="/media/${t.id}/miniatura.jpg?v=${clave}"></video>`
      : `<div class="hueco">La vista previa aparecerá cuando termine el render.</div>`;
  }
  const yt = S.estado.youtube;
  const ocupado = ["procesando", "subiendo"].includes(t.estado) || t.subir_solicitado || t.estado === "pendiente";
  const pasos = ETAPAS.map(([k, n]) => h`<li class="${t.etapas[k]?.estado || ""}"><span class="punto"></span><span>${n}</span><span>${t.etapas[k]?.detalle || ""}</span></li>`).join("");
  let botones = "";
  if (t.estado === "error") botones += `<button class="primario" data-accion="reintentar" data-foco="b-reintentar">Reintentar</button>`;
  if (t.estado === "renderizado" && !t.subir_solicitado) {
    botones += yt.canal_id ? h`<button class="primario" data-accion="subir" data-foco="b-subir">Subir en privado a ${yt.canal_nombre}</button>` : `<a class="boton" href="#ajustes" data-accion="ir-ajustes" data-p="youtube">Conectar YouTube para subir</a>`;
    botones += `<button data-accion="renderizar" data-foco="b-render">Renderizar de nuevo</button>`;
  }
  if (["renderizado", "error"].includes(t.estado) && !t.subir_solicitado && !t.youtube_id) {
    const general = S.estado.estilo === "completo" ? "pantalla completa" : "clásico";
    botones += h`<label class="estilo-trabajo">Estilo<select data-estilo-trabajo data-foco="b-estilo">
      <option value="" ${t.estilo === "" ? "selected" : ""}>General de Ajustes (${general})</option>
      <option value="clasico" ${t.estilo === "clasico" ? "selected" : ""}>Clásico: video completo con tarjeta</option>
      <option value="completo" ${t.estilo === "completo" ? "selected" : ""}>Pantalla completa con seguimiento</option></select></label>`;
  }
  if (t.tiene_video) botones += h`<a class="boton" href="/media/${t.id}/short.mp4" download="${t.nombre}.mp4">Descargar MP4</a>`;
  if (!["procesando", "subiendo"].includes(t.estado)) botones += `<button class="texto peligro" data-accion="eliminar" data-foco="b-eliminar">Eliminar</button>`;
  const sal = t.salida;
  const destino = t.youtube_id ? "Subido en privado" : t.subir_solicitado || t.estado === "subiendo" ? "En cola para subir en privado" : t.publicar ? "Sin subir" : "No destinado a YouTube";
  poner($("#t-estado"), h`<div class="fila">${crudo(pastilla(t))}<span class="tenue pequeno">${t.progreso || (t.subir_solicitado ? "En cola para subir…" : "")}</span></div>
    ${t.error ? crudo(h`<p class="nota mal" role="alert">${t.error}</p>`) : ""}
    ${t.avisos.map((a) => crudo(h`<p class="nota">${a}</p>`))}
    ${t.youtube_id ? crudo(h`<p class="nota bien">Subido en privado. ID de YouTube: <code>${t.youtube_id}</code> ·
      <a href="https://studio.youtube.com/video/${t.youtube_id}/edit" target="_blank" rel="noopener">Abrir en YouTube Studio</a></p>`) : ""}
    <dl class="ficha"><dt>Origen</dt><dd>${etiquetaOrigen(t)}</dd>
      <dt>Duración</dt><dd>${t.duracion ? reloj(t.duracion) : "—"}</dd>
      <dt>Resultado</dt><dd>${sal ? `${sal.ancho} × ${sal.alto} · ${sal.codec_video}/${sal.codec_audio || "sin audio"} · ${(sal.tamano_bytes / 1048576).toFixed(1)} MB` : "Aún sin renderizar"}</dd>
      ${sal && t.copia ? crudo(h`<dt>Copia</dt><dd>2_shorts_renderizados/${t.copia}</dd>`) : ""}
      <dt>YouTube</dt><dd>${destino}</dd></dl>
    <ul class="pasos">${crudo(pasos)}</ul>
    <div class="fila">${crudo(botones)}</div>`);

  // Formularios: se repintan solo si el trabajo cambió y no hay cambios sin guardar.
  const version = `${t.actualizado}|${ocupado}`;
  if (S.sucio || S.version === version || $("#t-edicion").contains(document.activeElement)) return;
  S.version = version;
  const bloqueado = ocupado || !!t.youtube_id;
  const x = t.textos;
  const [desc, etiquetas] = (x.descripcion || "\n").split("\n");
  $("#t-edicion").innerHTML = !x.titulo ? "" : h`<form class="tarjeta pila" id="form-textos">
      <div class="fila separado"><h3>Textos</h3><span class="pequeno tenue">Origen: ${x.origen || ""}</span></div>
      <label>Banner (máx. 6 palabras)<input name="banner" value="${x.banner}" ${bloqueado ? "disabled" : ""}></label>
      <label>Título<input name="titulo" value="${x.titulo}" ${bloqueado ? "disabled" : ""}><span class="contador" id="c-titulo"></span></label>
      <label>Descripción<textarea name="desc" rows="2" ${bloqueado ? "disabled" : ""}>${desc}</textarea></label>
      <label>Hashtags<input name="etiquetas" value="${etiquetas || ""}" ${bloqueado ? "disabled" : ""}></label>
      <label class="linea"><input type="checkbox" name="es_gaming" ${x.es_gaming ? "checked" : ""} ${bloqueado ? "disabled" : ""}> Es contenido de videojuegos (categoría Gaming)</label>
      <div class="fila"><button class="primario" ${bloqueado ? "disabled" : ""}>Guardar textos</button>
      <button type="button" data-accion="regenerar-textos" ${bloqueado ? "disabled" : ""}>Regenerar automáticamente</button></div>
      <p class="pequeno tenue">Editar es opcional. Cambiar el banner vuelve a renderizar; no repite la transcripción.</p>
    </form>
    ${t.bloques.length ? crudo(h`<details class="tarjeta"><summary>Subtítulos (${t.bloques.length} bloques${t.subtitulos_editados ? ", editados" : ""})</summary>
      <form class="pila" id="form-subs" style="margin-top:10px"><div class="subs">
      ${t.bloques.map((b, i) => crudo(h`<div><span>${b.inicio.toFixed(1)}–${b.fin.toFixed(1)}</span><input data-i="${i}" value="${b.texto}" aria-label="Subtítulo ${i + 1}" ${bloqueado ? "disabled" : ""}></div>`))}
      </div><div class="fila"><button ${bloqueado ? "disabled" : ""}>Guardar y renderizar</button>
      ${t.subtitulos_editados ? crudo(`<button type="button" data-accion="restaurar-subtitulos" ${bloqueado ? "disabled" : ""}>Restaurar originales</button>`) : ""}</div></form></details>`) : ""}
    ${t.transcripcion ? crudo(h`<details class="tarjeta"><summary>Transcripción literal</summary><p class="transcripcion">${t.transcripcion}</p></details>`) : ""}`;
  const ft = $("#form-textos");
  if (ft) {
    const contar = () => { const n = ft.titulo.value.length; $("#c-titulo").textContent = `${n}/80`; $("#c-titulo").classList.toggle("pasado", n > 80); };
    contar();
    ft.addEventListener("input", () => { S.sucio = true; contar(); });
    ft.addEventListener("submit", intentar(async (e) => {
      e.preventDefault();
      await api(`/api/trabajos/${t.id}/textos`, { method: "PUT", json: { banner: ft.banner.value, titulo: ft.titulo.value, descripcion: `${ft.desc.value}\n${ft.etiquetas.value}`, es_gaming: ft.es_gaming.checked } });
      S.sucio = false; avisar("Textos guardados."); document.activeElement.blur(); refrescar();
    }));
  }
  const fs = $("#form-subs");
  if (fs) {
    fs.addEventListener("input", () => { S.sucio = true; });
    fs.addEventListener("submit", intentar(async (e) => {
      e.preventDefault();
      const bloques = [...fs.querySelectorAll("input[data-i]")].map((i) => ({ ...t.bloques[+i.dataset.i], texto: i.value }));
      await api(`/api/trabajos/${t.id}/subtitulos`, { method: "PUT", json: { bloques } });
      S.sucio = false; avisar("Subtítulos guardados; se renderiza de nuevo."); document.activeElement.blur(); refrescar();
    }));
  }
}

// ---------------------------------------------------------------- video largo
function pintarLargo(m, t, completo) {
  if (completo || !$("#l-estado") || $("#l-estado").dataset.id !== t.id) {
    m.innerHTML = h`<div class="cabecera"><div><a class="enlace-fino" href="#${S.desde}">← ${S.desde === "biblioteca" ? "Biblioteca" : "Cola de clips"}</a><h1 id="t-nombre" style="margin-top:8px"></h1></div></div>
      <div class="pila"><div class="tarjeta pila" id="l-estado" data-id="${t.id}"></div>
      ${t.entrada ? crudo(h`<video id="l-video" controls playsinline preload="metadata" src="/media/${t.id}/entrada" style="width:100%;max-width:640px;border-radius:10px;border:1px solid var(--borde);background:#000"></video>`) : crudo(`<p class="pequeno tenue">El formato del original no se puede reproducir en el navegador; guíate por el texto de cada momento.</p>`)}
      <div class="pila" id="l-momentos"></div></div>`;
    S.version = null; S.sucio = false;
  }
  $("#t-nombre").textContent = t.nombre;
  const pasos = ETAPAS_LARGO.map(([k, n]) => h`<li class="${t.etapas[k]?.estado || ""}"><span class="punto"></span><span>${n}</span><span>${t.etapas[k]?.detalle || ""}</span></li>`).join("");
  poner($("#l-estado"), h`<div class="fila">${crudo(pastilla(t))}<span class="tenue pequeno">${t.progreso || etiquetaOrigen(t)}</span></div>
    ${t.error ? crudo(h`<p class="nota mal" role="alert">${t.error}</p>`) : ""}
    ${t.avisos.map((a) => crudo(h`<p class="nota">${a}</p>`))}
    <ul class="pasos">${crudo(pasos)}</ul>
    <div class="fila">${t.estado === "error" ? crudo(`<button class="primario" data-accion="reintentar" data-foco="b-reintentar">Reintentar</button>`) : ""}
      ${["propuestas", "error"].includes(t.estado) ? crudo(`<button data-accion="proponer-momentos" data-foco="b-proponer">Proponer momentos de nuevo</button>`) : ""}
      ${t.estado !== "procesando" ? crudo(`<button class="texto peligro" data-accion="eliminar" data-foco="b-eliminar">Eliminar</button>`) : ""}</div>`);
  const mo = t.momentos;
  const version = `${t.actualizado}|${t.clips.map((c) => c.id + c.estado).join()}`;
  if (!mo || S.sucio || S.version === version || $("#l-momentos").contains(document.activeElement)) return;
  S.version = version;
  const clipDe = (p) => t.clips.find((c) => Math.abs(c.inicio - p.inicio) < 0.02 && Math.abs(c.fin - p.fin) < 0.02);
  const local = mo.origen === "local";
  $("#l-momentos").innerHTML = h`<div class="fila separado"><h2>Momentos propuestos</h2><span class="pequeno tenue">Origen: ${mo.origen}</span></div>
    ${local ? crudo(`<p class="nota">Propuestas de la heurística local: mide ritmo de habla, exclamaciones y preguntas, pero no entiende el contenido. Revisa cada tramo antes de crear el Short. Con una clave de Gemini las propuestas se basan en lo que se dice.</p>`) : ""}
    ${mo.propuestas.length ? "" : crudo(`<div class="panel sin-nada">No hay propuestas. Puedes crear un clip indicando los tiempos abajo.</div>`)}
    ${mo.propuestas.map((p) => { const c = clipDe(p); return crudo(h`<form class="tarjeta pila momento" data-ini="${p.inicio}" data-fin="${p.fin}">
      <div class="fila separado"><b>${reloj(p.inicio)} – ${reloj(p.fin)} · ${Math.round(p.fin - p.inicio)} s</b><span class="pequeno tenue">${p.motivo}</span></div>
      <p class="transcripcion">${p.texto}</p>
      <div class="fila"><label style="width:110px">Inicio (m:ss)<input name="ini" value="${reloj(p.inicio)}" inputmode="numeric"></label>
        <label style="width:110px">Fin (m:ss)<input name="fin" value="${reloj(p.fin)}" inputmode="numeric"></label>
        ${t.entrada ? crudo(`<button type="button" data-accion="ver-momento">Ver tramo</button>`) : ""}
        ${c ? crudo(h`<a class="boton" href="#trabajo/${c.id}">Abrir clip (${ESTADOS[c.estado]})</a>`) : crudo(`<button class="primario">Crear Short</button>`)}</div></form>`); })}
    <form class="tarjeta pila momento"><h3>Tramo manual</h3><div class="fila">
      <label style="width:110px">Inicio (m:ss)<input name="ini" placeholder="0:00" required></label>
      <label style="width:110px">Fin (m:ss)<input name="fin" placeholder="0:40" required></label>
      ${t.entrada ? crudo(`<button type="button" data-accion="ver-momento">Ver tramo</button>`) : ""}<button>Crear Short</button></div></form>
    ${t.clips.length ? crudo(h`<div class="tarjeta pila"><h3>Clips creados</h3>${t.clips.map((c) => crudo(h`<a class="fila separado" href="#trabajo/${c.id}" style="text-decoration:none"><span>${reloj(c.inicio)} – ${reloj(c.fin)} · ${c.nombre}</span>${crudo(pastilla(c))}</a>`))}</div>`) : ""}`;
  document.querySelectorAll("form.momento").forEach((f) => {
    f.addEventListener("input", () => { S.sucio = true; });
    f.addEventListener("submit", intentar(async (e) => {
      e.preventDefault();
      // Si no se tocaron los tiempos se usan los exactos de la propuesta (con decimales).
      const intacto = f.dataset.ini && f.ini.value === reloj(+f.dataset.ini) && f.fin.value === reloj(+f.dataset.fin);
      const inicio = intacto ? +f.dataset.ini : aSegundos(f.ini.value), fin = intacto ? +f.dataset.fin : aSegundos(f.fin.value);
      if (isNaN(inicio) || isNaN(fin)) throw new Error("Escribe los tiempos como minutos:segundos, por ejemplo 1:25.");
      await api(`/api/trabajos/${t.id}/clips`, { method: "POST", json: { inicio, fin } });
      S.sucio = false; avisar("Clip añadido a la cola."); document.activeElement.blur(); refrescar();
    }));
  });
}

const accionTrabajo = (nombre, mensaje) => intentar(async () => {
  await api(`/api/trabajos/${S.jid}/${nombre}`, { method: "POST" });
  S.sucio = false; if (mensaje) avisar(mensaje); refrescar();
});
const acciones = {
  nuevo: (b) => nuevoClip(b.dataset.p),
  "cerrar-modal": () => cerrarModal(false),
  "ir-ajustes": (b) => { S.pestana = b.dataset.p; if (S.vista === "ajustes") pintarAjustes($("#principal")); },
  acceso: (b) => mostrarAcceso(b.dataset.modo),
  "ver-clave": (b) => {
    const i = b.previousElementSibling, ver = i.type === "password";
    i.type = ver ? "text" : "password"; b.setAttribute("aria-pressed", ver); i.focus();
  },
  "ahora-no": () => { try { localStorage.setItem(BIENVENIDA, "omitida"); } catch (e) { /* volverá a mostrarse */ } entrar(); },
  "crear-cuenta": () => mostrarAcceso("bienvenida"),
  "cerrar-sesion": intentar(async () => {
    await api("/api/logout", { method: "POST" });
    if (!(await leerSesion()).autorizado) return mostrarAcceso("login");
    // Un dispositivo vinculado por código sigue autorizado aunque cierre su sesión.
    avisar("Sesión cerrada. Este dispositivo sigue vinculado por código; para quitarlo, usa Ajustes → Dispositivos en el PC.");
    pintar(true);
  }),
  "cerrar-otra": intentar(async (b) => {
    await api(`/api/sesiones/${b.dataset.id}`, { method: "DELETE" });
    salir(b.closest(".sesion"), () => pintarAjustes($("#principal")));
  }),
  filtro: (b) => { S.filtro = b.dataset.f; pintar(false); },
  quitar: intentar(async (b) => {
    if (!await confirmar("Eliminar el clip", `Se eliminará «${b.dataset.nombre}» y sus archivos intermedios de este PC. No borra nada de YouTube.`, "Eliminar", true)) return;
    await api(`/api/trabajos/${b.dataset.id}`, { method: "DELETE" }); avisar("Clip eliminado."); refrescar();
  }),
  reintentar: accionTrabajo("reintentar", "Reintentando desde la etapa que falló."),
  renderizar: accionTrabajo("renderizar", "En cola para renderizar con los ajustes actuales."),
  "proponer-momentos": accionTrabajo("proponer-momentos", "Buscando momentos de nuevo."),
  "ver-momento": (b) => {
    const f = b.closest("form"), v = $("#l-video"), ini = aSegundos(f.ini.value), fin = aSegundos(f.fin.value);
    if (!v || isNaN(ini)) return;
    v.currentTime = ini; v.play();
    clearInterval(v._tope); v._tope = setInterval(() => { if (!isNaN(fin) && v.currentTime >= fin) { v.pause(); clearInterval(v._tope); } }, 200);
    v.scrollIntoView({ behavior: "smooth", block: "center" });
  },
  diagnostico: intentar(async (b) => {
    b.disabled = true; $("#diag").innerHTML = `<p class="pequeno tenue">Comprobando (incluye un render de prueba de 2 s)…</p>`;
    try {
      const r = await api("/api/diagnostico?autoprueba=true");
      $("#diag").innerHTML = r.map((x) => h`<div class="dato"><span>${x.ok === true ? "✓" : x.ok === false ? "✗ Falla" : "– Opcional"} · ${x.nombre}</span><span class="${x.ok === false ? "error" : ""}">${x.detalle}</span></div>`).join("");
    } finally { b.disabled = false; }
  }),
  "regenerar-textos": accionTrabajo("regenerar-textos", "Regenerando textos."),
  "restaurar-subtitulos": accionTrabajo("restaurar-subtitulos", "Subtítulos restaurados."),
  subir: intentar(async () => {
    const yt = S.estado.youtube;
    if (!await confirmar("Subir a YouTube", `Se subirá este Short en PRIVADO al canal «${yt.canal_nombre}» (${yt.canal_id}).`, "Subir en privado")) return;
    await api(`/api/trabajos/${S.jid}/subir`, { method: "POST" }); avisar("Subida en cola."); refrescar();
  }),
  eliminar: intentar(async () => {
    if (!await confirmar("Eliminar el trabajo", "Se eliminará el trabajo y sus archivos intermedios de este PC. No borra nada de YouTube.", "Eliminar", true)) return;
    await api(`/api/trabajos/${S.jid}`, { method: "DELETE" }); location.hash = S.desde;
  }),
  pestana: (b) => { S.pestana = b.dataset.p; pintarAjustes($("#principal")); },
  "codigo": intentar(async () => {
    const c = await api("/api/vincular/codigo", { method: "POST" });
    $("#zona-codigo").innerHTML = h`<p class="codigo">${c.codigo}</p><p class="pequeno tenue">Válido 10 minutos y para un solo dispositivo. En la tablet abre <code>${c.direccion || "http://IP-del-PC:8765"}</code> en el navegador, conectada al mismo wifi.</p>`;
  }),
  "quitar-dispositivo": intentar(async (b) => { await api(`/api/dispositivos/${b.dataset.id}`, { method: "DELETE" }); pintarAjustes($("#principal")); }),
  "yt-desconectar": intentar(async () => { if (await confirmar("Desconectar YouTube", "Se desconectará la cuenta de YouTube de Fábrica Studio y habrá que confirmar el canal de nuevo.", "Desconectar", true)) { await api("/api/youtube/desconectar", { method: "POST" }); await refrescar(); pintarAjustes($("#principal")); } }),
  "yt-confirmar": intentar(async (b) => {
    if (!await confirmar("Confirmar canal de destino", `Las subidas irán, siempre en privado, al canal «${b.dataset.titulo}» (${b.dataset.id}).`, "Confirmar canal")) return;
    await api("/api/youtube/canal", { method: "POST", json: { id: b.dataset.id } }); await refrescar(); pintarAjustes($("#principal"));
  }),
  "gemini-borrar": intentar(async () => { await api("/api/secretos/gemini", { method: "DELETE" }); await refrescar(); pintarAjustes($("#principal")); }),
  "gemini-probar": intentar(async () => {
    const r = await api("/api/proveedores/gemini");
    $("#gemini-info").textContent = r.clave ? `Clave válida. Modelo que se usará: ${r.elegido}. Disponibles: ${r.modelos.join(", ")}` : "No hay clave configurada.";
  }),
  "logo-quitar": intentar(async () => { await api("/api/logo", { method: "DELETE" }); pintarAjustes($("#principal")); }),
  "restablecer": intentar(async () => {
    const { defecto } = S.ajustes; const cambios = {};
    document.querySelectorAll("#form-diseno [name]").forEach((i) => { cambios[i.name] = defecto[i.name]; });
    await api("/api/ajustes", { method: "PUT", json: cambios }); avisar("Diseño restablecido."); pintarAjustes($("#principal"));
  }),
};

// ---------------------------------------------------------------- ajustes
// Nombre legible a partir del agente de usuario; si no se reconoce, no se inventa.
const primero = (lista, ag) => lista.find(([r]) => r.test(ag))?.[1];
const dispositivoDe = (ag) => [primero([[/Windows/, "Windows"], [/HarmonyOS|OpenHarmony/, "HarmonyOS"], [/Android/, "Android"], [/iPad|iPhone/, "iOS"], [/Mac OS X/, "macOS"], [/Linux|X11/, "Linux"]], ag),
  primero([[/Edg\//, "Edge"], [/HuaweiBrowser/, "Navegador Huawei"], [/Firefox\//, "Firefox"], [/Chrome\//, "Chrome"], [/Safari\//, "Safari"]], ag)].filter(Boolean).join(" · ") || `Navegador desconocido${ag ? ` (${ag.slice(0, 40)})` : ""}`;
const lapso = (s) => (s < 3600 ? `${Math.max(1, Math.round(s / 60))} min` : s < 172800 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} días`);
const CAMPOS_COMPLETO = [
  ["completo_zoom", "Zoom (%; 100 = sin zoom extra)"], ["completo_banner_y", "Banner: posición vertical"],
  ["completo_sub_y", "Subtítulos: posición vertical"], ["completo_sub_tamano", "Subtítulos: tamaño"],
  ["completo_logo_y", "Logo: posición vertical"], ["completo_logo_alto", "Logo: alto (px)"],
];
const CAMPOS_DISENO = [
  ["creador", "Nombre del creador (títulos)", "text"], ["firma", "Firma bajo el logo", "text"],
  ["banner_color", "Color del banner", "color"], ["sub_color_resalte", "Color de la palabra activa", "color"],
  ["nombre_color", "Color de la firma", "color"],
  ["video_desplazamiento_y", "Video: desplazamiento vertical (px)"], ["video_alto_max", "Video: alto máximo (px)"],
  ["banner_tamano", "Banner: tamaño de letra"], ["banner_ancho", "Banner: ancho de tarjeta"],
  ["banner_separacion", "Banner: separación del video"], ["banner_radio", "Banner: redondeo de esquinas"],
  ["sub_tamano", "Subtítulos: tamaño"], ["sub_desplazamiento", "Subtítulos: distancia bajo el video"],
  ["sub_palabras_max", "Subtítulos: palabras por bloque"], ["sub_caracteres_max", "Subtítulos: caracteres por bloque"],
  ["logo_alto", "Logo: alto (px)"], ["logo_separacion", "Logo: separación"], ["nombre_tamano", "Firma: tamaño"],
];

async function pintarAjustes(m) {
  let a;
  try { a = S.ajustes = await api("/api/ajustes"); } catch (e) {
    if ($(".esqueleto", m)) m.innerHTML = `<div class="panel sin-nada" role="alert">No se pudieron cargar los ajustes. Vuelve a entrar en Ajustes para reintentar.</div>`;
    return avisar(e.message, true);
  }
  if (S.vista !== "ajustes") return;     // se cambió de vista mientras llegaban los datos
  const v = a.valores, local = S.sesion.local, yt = S.estado.youtube, p = S.estado.proveedores;
  const soloPc = local ? "" : `<p class="nota">Por seguridad, esta sección solo se puede modificar desde el panel abierto en el PC.</p>`;
  const pestanas = [["diseno", "Diseño"], ["youtube", "YouTube"], ["proveedores", "Proveedores"], ["dispositivos", "Dispositivos"], ["cuenta", "Cuenta"]];
  let cuerpo = "";
  if (S.pestana === "diseno") {
    cuerpo = h`<div class="diseno"><form class="pila" id="form-diseno">
      <label>Estilo de encuadre<select name="estilo">
        <option value="clasico" ${v.estilo === "clasico" ? "selected" : ""}>Clásico: video completo centrado con tarjeta</option>
        <option value="completo" ${v.estilo === "completo" ? "selected" : ""}>Pantalla completa: recorte 9:16 que sigue los rostros</option></select></label>
      <div class="campos">${CAMPOS_DISENO.map(([k, n, tipo]) => crudo(h`<label>${n}<input name="${k}" type="${tipo || "number"}" value="${v[k]}"></label>`))}</div>
      <details class="tarjeta"${v.estilo === "completo" ? " open" : ""}><summary>Ajustes de pantalla completa</summary><div class="campos" style="margin-top:12px">
        ${CAMPOS_COMPLETO.map(([k, n]) => crudo(h`<label>${n}<input name="${k}" type="number" value="${v[k]}"></label>`))}</div>
        <label class="linea" style="margin-top:10px"><input type="checkbox" name="completo_banner" ${v.completo_banner ? "checked" : ""}> Mostrar tarjeta del banner arriba</label>
        <label class="linea"><input type="checkbox" name="completo_mayusculas" ${v.completo_mayusculas ? "checked" : ""}> Subtítulos en mayúsculas</label></details>
      <label class="linea"><input type="checkbox" name="mostrar_logo" ${v.mostrar_logo ? "checked" : ""}> Mostrar logo</label>
      <label class="linea"><input type="checkbox" name="mostrar_nombre" ${v.mostrar_nombre ? "checked" : ""}> Mostrar firma bajo el logo</label>
      <label class="linea"><input type="checkbox" name="sub_resaltar" ${v.sub_resaltar ? "checked" : ""}> Resaltar en color la palabra que se está diciendo</label>
      <label class="linea"><input type="checkbox" name="recortar_bordes" ${v.recortar_bordes ? "checked" : ""}> Quitar franjas negras del clip original</label>
      <div class="tarjeta pila"><h3>Logo</h3>
        <p class="pequeno tenue">${a.logo_propio ? "Usando tu logo. Los márgenes transparentes se recortan automáticamente." : "Sin logo propio: se muestra el rótulo de texto «KICK». Sube el logo oficial en PNG transparente si tienes permiso para usarlo."}</p>
        <div class="fila"><label class="boton" style="flex-direction:row;color:var(--texto)">Subir logo PNG<input type="file" id="logo" accept="image/png,image/webp,image/jpeg" hidden></label>
        ${a.logo_propio ? crudo(`<button type="button" data-accion="logo-quitar">Quitar logo</button>`) : ""}</div></div>
      <div class="fila"><button class="primario">Guardar diseño</button><button type="button" data-accion="restablecer">Restablecer valores iniciales</button></div>
      <p class="pequeno tenue" id="diseno-aviso">Los cambios se aplican a los próximos renders. En un Short ya renderizado, pulsa «Renderizar de nuevo».</p>
    </form><img id="vista-diseno" alt="Maqueta del diseño con los ajustes actuales"></div>`;
  } else if (S.pestana === "youtube") {
    cuerpo = h`${crudo(soloPc)}<div class="tarjeta">
      <div class="dato"><span>Credenciales OAuth</span><span>${yt.credenciales ? `Cargadas (tipo ${yt.tipo_cliente === "installed" ? "escritorio" : yt.tipo_cliente})` : "Falta client_secret.json"}</span></div>
      <div class="dato"><span>Cuenta</span><span>${yt.conectado ? "Conectada" : "Sin conectar"}</span></div>
      <div class="dato"><span>Canal de destino</span><span>${yt.canal_id ? crudo(h`<b>${yt.canal_nombre}</b> · <code>${yt.canal_id}</code>`) : "Sin confirmar: no se puede subir"}</span></div>
      <div class="dato"><span>Privacidad</span><span>Privado (fijo en esta versión)</span></div>
      <div class="dato"><span>Audiencia</span><span>${v.contenido_para_ninos ? "Creado para niños" : "No creado para niños"} · sin restricción de edad (se configura aparte en YouTube Studio)</span></div>
    </div>
    ${yt.tipo_cliente === "web" ? `<p class="nota">El archivo es de tipo «aplicación web». Funciona solo si en Google Cloud añadiste el URI de redirección <code>http://127.0.0.1:8765/api/youtube/callback</code>. Lo recomendado es crear un cliente de tipo «App de escritorio».</p>` : ""}
    <div class="tarjeta pila"><h3>Conexión</h3>
      <div class="fila"><label class="boton" style="flex-direction:row;color:var(--texto)">${yt.credenciales ? "Reemplazar" : "Cargar"} client_secret.json<input type="file" id="yt-cred" accept=".json,application/json" hidden ${local ? "" : "disabled"}></label>
      ${yt.credenciales && local ? crudo(`<a class="boton" href="/api/youtube/conectar">${yt.conectado ? "Conectar otra cuenta" : "Conectar cuenta de Google"}</a>`) : ""}
      ${yt.conectado && local ? crudo(`<button data-accion="yt-desconectar">Desconectar</button>`) : ""}</div>
      <div id="yt-canales" class="pila"></div></div>
    <form class="tarjeta pila" id="form-pub"><h3>Publicación</h3>
      <label class="linea"><input type="checkbox" name="subida_automatica" ${v.subida_automatica ? "checked" : ""}> Subir en privado automáticamente al terminar el render (sin revisión previa)</label>
      <label class="linea"><input type="checkbox" name="contenido_para_ninos" ${v.contenido_para_ninos ? "checked" : ""}> Declarar el contenido como «creado para niños»</label>
      <div><button>Guardar</button></div></form>`;
  } else if (S.pestana === "proveedores") {
    cuerpo = h`<div class="tarjeta">
      <div class="dato"><span>FFmpeg</span><span>${p.ffmpeg && p.ffprobe ? "Disponible" : "No encontrado: instala FFmpeg"}</span></div>
      <div class="dato"><span>Transcripción</span><span>faster-whisper (local, sin coste) · modelo ${p.whisper.modelo} · ${p.whisper.descargado ? "descargado" : "se descargará en el primer uso"}</span></div>
      <div class="dato"><span>Textos</span><span>${p.gemini.clave ? "Gemini (API de pago por uso o cuota gratuita, según tu cuenta de Google)" : "Borrador local (sin IA): no hay clave de Gemini"}</span></div>
    </div>
    <div class="tarjeta pila"><div class="fila separado"><h3>Diagnóstico de este PC</h3><button data-accion="diagnostico">Comprobar ahora</button></div>
      <div id="diag"><p class="pequeno tenue">Verifica FFmpeg, Whisper, GPU y hace un render de prueba. También se puede ejecutar con <code>scripts\\diagnostico.ps1</code>.</p></div></div>
    <form class="tarjeta pila" id="form-prov"><h3>Transcripción</h3><div class="campos">
      <label>Modelo de Whisper<select name="whisper_modelo">${["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"].map((x) => crudo(h`<option ${x === v.whisper_modelo ? "selected" : ""}>${x}</option>`))}</select></label>
      <label>Dispositivo<select name="whisper_dispositivo">${[["auto", "Automático (GPU si funciona)"], ["cpu", "CPU"], ["cuda", "GPU NVIDIA"]].map(([k, n]) => crudo(h`<option value="${k}" ${k === v.whisper_dispositivo ? "selected" : ""}>${n}</option>`))}</select></label>
      <label>Textos<select name="proveedor_textos">${[["auto", "Gemini si hay clave; si no, local"], ["gemini", "Gemini"], ["local", "Solo borrador local"]].map(([k, n]) => crudo(h`<option value="${k}" ${k === v.proveedor_textos ? "selected" : ""}>${n}</option>`))}</select></label>
      <label>Modelo de Gemini (vacío = automático)<input name="gemini_modelo" value="${v.gemini_modelo}"></label>
      <label>Momentos a proponer por video largo<input name="momentos_cantidad" type="number" min="1" max="20" value="${v.momentos_cantidad}"></label></div>
      <p class="pequeno tenue">Modelos más grandes transcriben mejor pero tardan más. «small» es un punto de partida razonable en CPU.</p>
      <div><button class="primario">Guardar</button></div></form>
    <div class="tarjeta pila"><h3>Clave de Gemini</h3>${crudo(soloPc)}
      <form class="fila" id="form-gemini"><input type="password" id="gemini-clave" placeholder="${p.gemini.clave ? "Hay una clave guardada" : "Pega aquí la clave de API"}" autocomplete="off" style="flex:1;min-width:200px" ${local ? "" : "disabled"}>
      <button ${local ? "" : "disabled"}>Guardar clave</button>
      <button type="button" data-accion="gemini-probar">Probar</button>
      ${p.gemini.clave && local ? crudo(`<button type="button" class="texto peligro" data-accion="gemini-borrar">Borrar</button>`) : ""}</form>
      <p class="pequeno tenue" id="gemini-info">La clave se guarda solo en este PC y nunca se muestra en el panel.</p></div>`;
  } else if (S.pestana === "cuenta") {
    const s = await leerSesion();
    if (!s.cuenta_creada) {
      cuerpo = h`<div class="tarjeta pila"><h3>Protege tu panel</h3>
        <p class="pequeno tenue">Ahora el panel se abre sin contraseña desde este PC. Con una cuenta, también el PC pedirá iniciar sesión.</p>
        ${local ? crudo(`<div><button class="primario" data-accion="crear-cuenta">Crear cuenta</button></div>`) : crudo(`<p class="nota">La cuenta se crea desde el panel abierto en el PC.</p>`)}</div>`;
    } else {
      const ss = await api("/api/sesiones").catch(() => []), ahora = Date.now() / 1000;
      cuerpo = h`<form class="tarjeta pila" id="form-clave"><h3>Contraseña</h3>${crudo(soloPc)}
        <p class="pequeno tenue">Al cambiarla se cierran las demás sesiones abiertas.</p>
        <div class="campos">${[["actual", "Contraseña actual", "current-password", 1], ["nueva", "Nueva (8 caracteres o más)", "new-password", 8], ["repetir", "Repite la nueva", "new-password", 8]].map(([k, n, ac, min]) =>
          crudo(h`<label>${n}<input name="${k}" type="password" autocomplete="${ac}" minlength="${min}" required ${local ? "" : "disabled"}></label>`))}</div>
        <p class="error" role="alert"></p>
        <div><button class="primario" ${local ? "" : "disabled"}>Cambiar contraseña</button></div></form>
      <div class="tarjeta pila"><h3>Sesiones abiertas</h3>
        <div>${ss.length ? ss.map((x) => crudo(h`<div class="sesion"><div class="avatar" aria-hidden="true">${ic(/Windows|Mac OS X|X11/.test(x.agente) ? "monitor" : "dispositivos")}</div>
          <div><b>${dispositivoDe(x.agente)}</b> ${x.actual ? crudo(`<span class="pastilla subido">Esta sesión</span>`) : ""}
            <small>${x.ip} · ${ahora - x.visto < 90 ? "activa ahora" : `vista hace ${lapso(ahora - x.visto)}`} · caduca en ${lapso(x.expira - ahora)}</small></div>
          ${local && !x.actual ? crudo(h`<button class="texto peligro" data-accion="cerrar-otra" data-id="${x.id}">Cerrar</button>`) : ""}</div>`))
          : crudo(`<p class="tenue pequeno">No hay sesiones abiertas.</p>`)}</div>
        ${local ? "" : crudo(`<p class="pequeno tenue">Las sesiones de otros dispositivos se cierran desde el panel abierto en el PC.</p>`)}</div>
      <div class="tarjeta fila separado"><div><h3>Salir</h3><p class="pequeno tenue">${s.sesion_iniciada ? "Cierra la sesión en este dispositivo." : "Este dispositivo entra por vinculación con código, sin sesión iniciada."}</p></div>
        ${s.sesion_iniciada ? crudo(h`<button data-accion="cerrar-sesion">${ic("salir")}Cerrar sesión</button>`) : ""}</div>`;
    }
  } else {
    const ds = await api("/api/dispositivos").catch(() => []);
    cuerpo = h`${crudo(soloPc)}<div class="tarjeta pila"><h3>Vincular un dispositivo</h3>
      <div id="zona-codigo"><p class="pequeno tenue">Genera un código aquí y escríbelo en el navegador de la tablet.</p></div>
      <div><button class="primario" data-accion="codigo" ${local ? "" : "disabled"}>Generar código</button></div></div>
    <div class="tarjeta pila"><h3>Dispositivos vinculados</h3>
      ${ds.length ? ds.map((d) => crudo(h`<div class="fila separado"><span>${d.nombre} <span class="tenue pequeno">· visto ${new Date(d.visto * 1000).toLocaleString("es-CL")}</span></span>
        <button class="texto peligro" data-accion="quitar-dispositivo" data-id="${d.id}" ${local ? "" : "disabled"}>Revocar</button></div>`)) : crudo(`<p class="tenue pequeno">Ninguno todavía.</p>`)}</div>`;
  }
  m.innerHTML = h`<div class="cabecera"><h1>Ajustes</h1></div><div class="pestanas" role="tablist">${pestanas.map(([k, n]) => crudo(h`<button role="tab" aria-selected="${k === S.pestana}" class="${k === S.pestana ? "activa" : ""}" data-accion="pestana" data-p="${k}">${n}</button>`))}</div><div class="pila">${crudo(cuerpo)}</div>`;

  const guardarForm = (sel, mensaje) => $(sel)?.addEventListener("submit", intentar(async (e) => {
    e.preventDefault();
    const cambios = {};
    e.target.querySelectorAll("[name]").forEach((i) => { cambios[i.name] = i.type === "checkbox" ? i.checked : i.value; });
    await api("/api/ajustes", { method: "PUT", json: cambios }); avisar(mensaje); refrescar();
  }));
  guardarForm("#form-diseno", "Diseño guardado."); guardarForm("#form-pub", "Publicación guardada."); guardarForm("#form-prov", "Proveedores guardados.");

  $("#form-clave")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target, error = $(".error", f);
    if (f.nueva.value !== f.repetir.value) { error.textContent = "Las dos contraseñas nuevas no coinciden."; return f.repetir.focus(); }
    try {
      await api("/api/cuenta/contrasena", { method: "PUT", json: { actual: f.actual.value, nueva: f.nueva.value } });
      avisar("Contraseña cambiada. Se cerraron las demás sesiones."); pintarAjustes(m);
    } catch (err) { error.textContent = err.message; }
  });

  const fd = $("#form-diseno");
  if (fd) {
    let espera;
    const vista = () => {
      const q = new URLSearchParams();
      fd.querySelectorAll("[name]").forEach((i) => q.set(i.name, i.type === "checkbox" ? i.checked : i.value));
      $("#vista-diseno").src = `/api/diseno/vista?${q}&t=${Date.now()}`;
    };
    fd.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(vista, 350); });
    vista();
    $("#logo").addEventListener("change", intentar(async (e) => {
      const datos = new FormData(); datos.append("archivo", e.target.files[0]);
      await api("/api/logo", { method: "POST", body: datos }); avisar("Logo actualizado."); pintarAjustes(m);
    }));
  }
  $("#yt-cred")?.addEventListener("change", intentar(async (e) => {
    const datos = new FormData(); datos.append("archivo", e.target.files[0]);
    await api("/api/youtube/credenciales", { method: "POST", body: datos }); avisar("Credenciales cargadas."); await refrescar(); pintarAjustes(m);
  }));
  $("#form-gemini")?.addEventListener("submit", intentar(async (e) => {
    e.preventDefault();
    const r = await api("/api/secretos/gemini", { method: "PUT", json: { clave: $("#gemini-clave").value } });
    avisar(`Clave válida y guardada (${r.modelos.length} modelos disponibles).`); await refrescar(); pintarAjustes(m);
  }));
  if (S.pestana === "youtube" && yt.conectado) {
    try {
      const canales = await api("/api/youtube/canales");
      $("#yt-canales").innerHTML = canales.length ? canales.map((c) => h`<div class="fila separado"><span><b>${c.titulo}</b> ${c.identificador} · <code>${c.id}</code></span>
        ${c.id === yt.canal_id ? crudo(`<span class="pastilla subido">Destino confirmado</span>`) : crudo(h`<button data-accion="yt-confirmar" data-id="${c.id}" data-titulo="${c.titulo}" ${local ? "" : "disabled"}>Confirmar como destino</button>`)}</div>`).join("")
        : `<p class="nota">La cuenta conectada no tiene ningún canal de YouTube.</p>`;
    } catch (e) { $("#yt-canales").innerHTML = h`<p class="nota mal">${e.message}</p>`; }
  }
}
