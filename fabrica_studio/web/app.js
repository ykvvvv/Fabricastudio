"use strict";
// Panel de Fábrica Studio: un único archivo que consulta la API cada 2 s. Única biblioteca: GSAP local (opcional, solo anima el acceso).

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
let S = { cambios: {}, orden: "recientes", desde: "cola", busca: "", filtro: "todos", conectado: true, dispositivos: null, sesion: null, estado: null, vista: "resumen", jid: null, detalle: null, sucio: false, pestana: "youtube", ajustes: null,
  seleccion: new Set() };      // clips elegidos en la cola (para «Regenerar textos»)

async function api(ruta, opciones = {}) {
  if (opciones.json !== undefined) {
    opciones.body = JSON.stringify(opciones.json);
    opciones.headers = { "Content-Type": "application/json" };
  }
  const r = await fetch(ruta, opciones);
  if (r.status === 401) { sinAcceso(); throw new Error("Inicia sesión o vincula este dispositivo."); }
  const datos = r.headers.get("content-type")?.includes("json") ? await r.json() : null;
  if (!r.ok) throw Object.assign(new Error(datos?.error || `Error ${r.status}`), { status: r.status });   // status: el servidor respondió
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
const NOMBRES_VISTA = { resumen: "Resumen", cola: "Cola de clips", biblioteca: "Biblioteca", perfiles: "Perfiles", plantilla: "Plantilla",ajustes: "Ajustes", trabajo: "Clip" };
const enCola = (t) => ["pendiente", "procesando", "subiendo"].includes(t.estado);
const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;
const coincide = (t) => !S.busca || `${t.nombre} ${t.textos.titulo || ""}`.toLowerCase().includes(S.busca);
const etiquetaOrigen = (t) => ({ archivo: "Archivo importado", carpeta: "Carpeta 1_clips_crudos", enlace: "Enlace de Kick", momento: "Momento de un video largo" }[t.origen_tipo]) + (t.modo === "largo" ? " · video largo" : "");
// Perfiles de creador: /api/estado trae la lista corta (id, nombre, firma, tema, estilo, logo, v) y el activo.
const perfilPorId = (id) => S.estado?.perfiles.find((p) => p.id === id);
const perfilActivo = () => perfilPorId(S.estado?.perfil_activo);
const TEMAS = { "": "Detectar en cada clip", gta6: "GTA 6" };
const iniciales = (n) => (String(n || "?").replace(/^@/, "").trim().slice(0, 2) || "?").toUpperCase();
const avatarPerfil = (p, clase = "") => (p?.logo ? h`<span class="avatar ${clase}" aria-hidden="true"><img src="/api/perfiles/${p.id}/logo?v=${p.v}" alt=""></span>`
  : h`<span class="avatar ${clase}" aria-hidden="true">${iniciales(p?.nombre)}</span>`);
const opcionesPerfil = (elegido) => S.estado.perfiles.map((p) => h`<option value="${p.id}" ${p.id === elegido ? "selected" : ""}>${p.nombre}${p.tema === "gta6" ? " · GTA 6" : ""}</option>`).join("");
// Subidas. YouTube pone sus propios topes y el programa no los controla: este texto se muestra donde se decide subir.
const LIMITES_YOUTUBE = "YouTube tiene sus propios límites diarios (la cuota de la API de tu proyecto de Google y los videos por día de tu canal) que Fábrica Studio no controla: si se alcanzan, las subidas se pausan solas hasta el día siguiente y siguen sin duplicar nada.";
// Renderizados que aún no están en YouTube, del más antiguo al más reciente.
const esperanSubir = () => S.estado.trabajos.filter((t) => t.estado === "renderizado" && !t.youtube_id).sort((a, b) => a.creado - b.creado);
function estadoSubida(t) {
  if (!t.subir_solicitado) return "";
  const pausa = S.estado.subidas_pausadas_hasta;
  if (pausa) return `YouTube pausó las subidas por su límite diario: este Short sube cuando termine la pausa (${horaSubida(pausa)}).`;
  if (t.subir_ya) return "Subida prioritaria: empieza en cuanto termine lo que se está procesando.";
  return S.estado.proxima_subida ? `En cola para subir: con el ritmo de publicación, la próxima subida es ${horaSubida(S.estado.proxima_subida)}.` : "En cola para subir…";
}
// Nombre del perfil de un clip; si se eliminó, el que tenía (el clip conserva una copia de sus valores).
const nombrePerfil = (t) => perfilPorId(t.perfil)?.nombre || (t.perfil_copia ? `${t.perfil_copia} (perfil eliminado)` : "—");

// Cambia el contenido solo si es distinto (no reinicia animaciones) y conserva el foco del teclado.
function poner(el, html) {
  if (!el || el._html === html) return;
  const a = document.activeElement, clave = el.contains(a) && (a.getAttribute("href") ? `[href="${a.getAttribute("href")}"]` : a.dataset.foco ? `[data-foco="${a.dataset.foco}"]` : "");
  el.innerHTML = el._html = html;
  if (clave) el.querySelector(clave)?.focus();
}
// Lista con clave (id del trabajo): cada elemento se actualiza por separado y solo los nuevos
// llevan la animación de entrada (al abrir la vista o al llegar un trabajo), escalonada hasta 8.
// Si cambia qué se ve o en qué orden (filtro, orden, búsqueda, cambio de estado), los que siguen y están en pantalla
// se deslizan a su lugar nuevo (técnica FLIP: se mide antes y después y se anima solo transform con Web Animations,
// que corre en el compositor; GSAP Flip costaba ~15 ms más por clic en la tablet emulada). Los que salen desaparecen
// y los nuevos entran con la animación de entrada.
function ponerLista(el, trabajos, etiqueta, html) {
  el._html = null;
  const viejos = new Map([...el.children].map((c) => [c.dataset.k, c]));
  const ids = new Set(trabajos.map((t) => t.id));
  const antes = new Map(), fuera = [], visible = (r) => r.bottom > 0 && r.top < innerHeight;
  if (mover() && viejos.size && [...viejos.keys()].join() !== trabajos.map((t) => t.id).join()) {
    for (const c of viejos.values()) {
      const r = c.getBoundingClientRect();      // dónde se ve ahora, aunque otro vuelo esté a medias
      if (ids.has(c.dataset.k)) visible(r) ? antes.set(c, r) : fuera.push(c);
      c.classList.remove("entra-fila");         // moverlo no debe repetir la entrada (todos a la vez: un solo recálculo)
    }
    el._vuelos?.forEach((a) => a.cancel()); el.classList.remove("volando");   // sin reordenar, un vuelo sigue hasta el final
  }
  let nuevos = 0;
  trabajos.forEach((t, i) => {
    let c = viejos.get(t.id);
    viejos.delete(t.id);
    if (!c) {
      c = document.createElement(etiqueta); c.dataset.k = t.id; c.className = "entra-fila"; c.style.setProperty("--i", Math.min(nuevos++, 8));
    }
    poner(c, html(t));
    c.classList.toggle("logro", !!S.cambios[t.id]?.logro);    // brillo: la API dice que acaba de terminar
    if (el.children[i] !== c) el.insertBefore(c, el.children[i] || null);
  });
  viejos.forEach((c) => c.remove());
  if (!antes.size && !fuera.length) return;
  el.classList.add("volando");                               // sin transiciones CSS de transform mientras vuela
  el._vuelos = [];
  antes.forEach((r, c) => {
    const n = c.getBoundingClientRect(), dx = r.left - n.left, dy = r.top - n.top;
    if (dx || dy) el._vuelos.push(c.animate({ transform: [`translate(${dx}px, ${dy}px)`, "none"] }, { duration: 280, easing: "cubic-bezier(.2, 0, 0, 1)" }));   // curva «en pantalla» del plan
  });
  // Los que no se veían y ahora sí (p. ej. al filtrar) entran como uno nuevo, en vez de aparecer de golpe.
  for (const c of fuera) if (visible(c.getBoundingClientRect())) el._vuelos.push(c.animate({ opacity: [0, 1], transform: ["translateY(8px)", "none"] }, { duration: 220, easing: "cubic-bezier(.3, .7, .2, 1)" }));
  Promise.all(el._vuelos.map((a) => a.finished)).then(() => el.classList.remove("volando"), () => {});   // cancelado: lo limpia el vuelo siguiente
}
// Esqueleto de carga mientras llegan los datos de la API.
function esqueleto(m) {
  if (!S.conectado) m.innerHTML = `<div class="panel sin-nada" role="status">Sin conexión con el PC. Se reintenta cada 2 s.</div>`;
  else if (!$(".esqueleto", m)) m.innerHTML = `<div class="esqueleto" role="status"><span class="solo-lector">Cargando…</span><i style="width:38%;height:34px"></i><i style="width:24%"></i><div><i></i><i></i><i></i></div><i style="height:220px"></i></div>`;
}
// Cuenta hasta el número real que ya entregó la API: desde cero al abrir el Resumen y, cuando una cifra cambia,
// desde la que se veía (desde[i]). Solo se escribe texto; el número final siempre es el de la API.
function contar(raiz, desde = null) {
  if (calma.matches) return;
  raiz.querySelectorAll("[data-cuenta]").forEach((el, i) => {
    const fin = +el.dataset.cuenta, ini = desde ? desde[i] ?? fin : 0, t0 = performance.now();
    if (ini === fin) return;
    const paso = (t) => {
      const p = Math.min((t - t0) / 600, 1);
      el.textContent = dos(Math.round(ini + (fin - ini) * (1 - (1 - p) ** 3)));
      if (p < 1 && el.isConnected) requestAnimationFrame(paso);
    };
    paso(t0);
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
  if (e.key === "Escape") { cerrarModal(); cerrarMenu(); cerrarMenuPerfiles(); }
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
    <div id="nc-enlace" role="tabpanel" aria-labelledby="np-enlace"><label>Enlaces públicos de clips o videos<textarea id="nc-urls" rows="4" placeholder="https://kick.com/…"></textarea>
      <span>Sin límite: pega todos los que quieras, uno por línea. Si Kick bloquea alguna descarga, se indica el motivo de esa.</span></label></div>
    <div id="nc-archivo" class="pila" role="tabpanel" aria-labelledby="np-archivo"><label class="soltar" id="nc-soltar">${ic("subir")}<span id="nc-elegidos">Arrastra videos aquí o pulsa para elegirlos</span><small>MP4, MOV, MKV, WebM o M4V · sin límite de cantidad</small>
      <input type="file" id="nc-archivos" class="solo-lector" accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.mkv,.webm,.m4v" multiple></label>
      <div class="fila" id="nc-carpeta-fila"><label class="boton">${ic("subir")}Elegir una carpeta completa<input type="file" id="nc-carpeta" class="solo-lector" webkitdirectory multiple></label>
        <span class="pequeno tenue">Se añaden todos sus videos (también los de sus subcarpetas).</span></div></div>
    <div class="campos"><label>Perfil de creador<select id="nc-perfil" aria-describedby="nc-perfil-ayuda">${crudo(opcionesPerfil(S.estado.perfil_activo))}</select></label>
      <label>Tipo de video<select id="nc-modo"><option value="clip">Clip ya seleccionado: se convierte completo en un Short</option>
      <option value="largo">Video largo: transcribir y proponer momentos para recortar</option></select></label></div>
    <p class="pequeno tenue" id="nc-perfil-ayuda">El perfil decide el nombre, la firma, el contexto de transcripción y el tema de estos clips.</p>
    <label class="linea"><input type="checkbox" id="nc-publicar" checked> Destinar a YouTube (siempre en privado)</label>
    <p class="error" id="nc-error" role="alert" hidden></p>`,
  h`<span class="pequeno tenue" id="nc-progreso" style="margin-right:auto"></span><button data-accion="cerrar-modal">Cancelar</button><button class="primario" id="nc-anadir">${ic("mas")}Añadir a la cola</button>`);
  const pestanas = () => ["enlace", "archivo"].forEach((p) => { $(`#np-${p}`).setAttribute("aria-selected", p === modo); $(`#nc-${p}`).hidden = p !== modo; });
  pestanas();
  $("#modal .modal-pestanas").addEventListener("click", (e) => { const b = e.target.closest("[data-p]"); if (b) { modo = b.dataset.p; pestanas(); } });
  // Solo los formatos que acepta el servidor (media.EXTENSIONES); el resto se cuenta y se dice.
  const elegir = (lista, carpeta = "") => {
    const todos = [...lista]; archivos = todos.filter((f) => /\.(mp4|mov|mkv|webm|m4v)$/i.test(f.name));
    const omitidos = todos.length - archivos.length;
    const que = carpeta ? `${plural(archivos.length, "video", "videos")} de la carpeta «${carpeta}»`
      : archivos.length > 3 ? `${plural(archivos.length, "video elegido", "videos elegidos")}` : archivos.map((f) => f.name).join(", ");
    $("#nc-elegidos").textContent = !todos.length ? "Arrastra videos aquí o pulsa para elegirlos"
      : !archivos.length ? "Ninguno es un video MP4, MOV, MKV, WebM o M4V."
        : que + (omitidos ? ` (se ${omitidos === 1 ? "omite" : "omiten"} ${plural(omitidos, "archivo que no es video", "archivos que no son video")})` : "");
  };
  $("#nc-carpeta").addEventListener("change", (e) => elegir(e.target.files, e.target.files[0]?.webkitRelativePath.split("/")[0] || ""));
  if (!("webkitdirectory" in document.createElement("input"))) $("#nc-carpeta-fila").hidden = true;   // navegadores sin selector de carpetas
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
    const publicar = $("#nc-publicar").checked, tipo = $("#nc-modo").value, perfil = $("#nc-perfil").value, boton = $("#nc-anadir");
    boton.disabled = true;
    let bien = 0;
    for (const [i, c] of cosas.entries()) {
      $("#nc-progreso").textContent = `Enviando ${i + 1} de ${cosas.length}…`;
      try {
        if (modo === "enlace") await api("/api/importar/enlace", { method: "POST", json: { url: c, publicar, modo: tipo, perfil } });
        else { const d = new FormData(); d.append("archivo", c); d.append("publicar", publicar); d.append("modo", tipo); d.append("perfil", perfil); await api("/api/importar/archivo", { method: "POST", body: d }); }
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
  entradaAcceso(modo);
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
  f.addEventListener("animationend", () => f.classList.remove("sacude"), { once: true });    // no se repite al volver a mostrar la tarjeta
}

// ---------------------------------------------------------------- movimiento del acceso (GSAP local, fase 2 del plan)
// Sin GSAP o con «reducir movimiento» no se monta ninguna línea de tiempo: los estados se aplican de golpe.
const animar = () => !!window.gsap && !calma.matches;
const mover = () => !calma.matches && !!Element.prototype.animate;     // listas que se reordenan (ponerLista); sin GSAP
if (animar()) $("#acceso").classList.add("con-gsap");       // apaga las entradas CSS equivalentes
let entrada = null;
function entradaAcceso(modo) {
  if (!animar()) return;
  entrada?.progress(1).kill();          // una entrada cortada a medias dejaría valores intermedios como estado final
  const t = entrada = gsap.timeline({ defaults: { ease: "power3.out", duration: 0.3, clearProps: "all" } });   // al terminar no queda estilo en línea
  if (modo !== "bienvenida") return void t.from("#acceso > form:not([hidden])", { y: 8, opacity: 0 });
  // Bienvenida: marca → texto → tarjeta → campos. Se puede escribir desde el primer momento.
  t.from("#acceso .marca-signo", { y: -14, rotation: 28, opacity: 0, duration: 0.35 })
    .from("#acceso .marca span", { x: -6, opacity: 0 }, "-=0.15")
    .from(".acceso-texto > *", { y: 10, opacity: 0, stagger: 0.06 }, "-=0.15")
    .from("#form-crear", { y: 12, opacity: 0, duration: 0.36 }, "-=0.3")
    .from("#form-crear > *", { y: 6, opacity: 0, duration: 0.25, stagger: 0.04 }, "-=0.2");
}
// Login o cuenta creada → panel: check en el botón, la tarjeta se retira y el acceso se desvanece como un velo
// mientras el panel ya carga debajo y entran la barra lateral y la superior (≈ 0,9 s).
async function alPanel(f) {
  const b = $(".primario", f), antes = b.innerHTML, a = $("#acceso");
  const limpiar = () => { f.classList.remove("enviando", "sacude"); b.classList.remove("hecho"); b.disabled = false; b.innerHTML = antes; $("#c-regla").classList.remove("cumple"); };
  f.reset(); $(".error", f).textContent = "";        // ni la contraseña ni un error anterior se quedan en la página
  await leerSesion();
  if (!animar()) { limpiar(); return entrar(); }
  entrada?.progress(1).kill();
  f.classList.remove("enviando"); b.classList.add("hecho"); b.innerHTML = icono("check");
  a.classList.add("saliendo");
  entrar(false);
  $("#principal").focus({ preventScroll: true });
  const t = gsap.timeline({ onComplete: () => { a.hidden = true; a.classList.remove("saliendo"); gsap.set([a, f, "#lateral", ".barra"], { clearProps: "all" }); limpiar(); } })
    .from(b.firstChild, { scale: 0.2, rotation: -25, opacity: 0, duration: 0.2, ease: "back.out(2)" })
    .to(f, { scale: 0.98, opacity: 0, duration: 0.22, ease: "power2.in" }, "+=0.12")
    .to(a, { opacity: 0, duration: 0.3, ease: "power2.in" }, "-=0.1")
    .from(".barra", { y: -8, opacity: 0, duration: 0.3, ease: "power3.out" }, "<0.06");
  if (!movil.matches) t.from("#lateral", { x: -12, opacity: 0, duration: 0.3, ease: "power3.out" }, "<");     // en móvil es un menú oculto
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
    if (r.ok) return alPanel(f);
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
    if (r.ok) return alPanel(f);
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

// Selector de perfil de la barra superior: un clic abre la lista y otro activa el perfil (menú con flechas y Esc).
function abrirMenuPerfiles() {
  const menu = $("#menu-perfiles"), activo = S.estado.perfil_activo;
  menu.innerHTML = S.estado.perfiles.map((p) => h`<button type="button" role="menuitemradio" aria-checked="${p.id === activo}" data-accion="activar-perfil" data-id="${p.id}">
      ${crudo(avatarPerfil(p, "mini"))}<span><b>${p.nombre}</b><small>${p.firma || "Sin firma"} · ${TEMAS[p.tema] || p.tema}</small></span>${p.id === activo ? ic("check") : ""}</button>`).join("")
    + h`<a href="#perfiles" role="menuitem" data-accion="cerrar-perfiles">${ic("ajustes")}Gestionar perfiles</a>`;
  menu.hidden = false;
  $("#boton-perfil").setAttribute("aria-expanded", "true");
  (menu.querySelector('[aria-checked="true"]') || menu.firstElementChild).focus();
}
function cerrarMenuPerfiles(devolverFoco = false) {
  if ($("#menu-perfiles").hidden) return;
  $("#menu-perfiles").hidden = true;
  $("#boton-perfil").setAttribute("aria-expanded", "false");
  if (devolverFoco) $("#boton-perfil").focus();
}
$("#boton-perfil").addEventListener("click", () => ($("#menu-perfiles").hidden ? abrirMenuPerfiles() : cerrarMenuPerfiles()));
$("#menu-perfiles").addEventListener("keydown", (e) => {
  const opciones = [...$("#menu-perfiles").querySelectorAll('[role^="menuitem"]')], i = opciones.indexOf(document.activeElement);
  const ir = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: opciones.length - 1 }[e.key];
  if (ir !== undefined) { e.preventDefault(); opciones[(ir + opciones.length) % opciones.length].focus(); }
  else if (e.key === "Escape") { e.stopPropagation(); cerrarMenuPerfiles(true); }
  else if (e.key === "Tab") cerrarMenuPerfiles();
});
document.addEventListener("click", (e) => { if (!e.target.closest("#selector-perfil")) cerrarMenuPerfiles(); });

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
  const antes = $("#lateral").offsetWidth;
  ponerLateral();
  animarLateral(antes);
}
// Plegar/desplegar: la rejilla cambia una sola vez (un cálculo de maquetación) y lo que se ve se desliza con
// transform y clip-path, que no recalculan la maquetación en cada cuadro (antes se animaba grid-template-columns).
function animarLateral(antes) {
  const lat = $("#lateral"), despues = lat.offsetWidth, ancho = Math.max(antes, despues);
  if (calma.matches || antes === despues) return;
  lat.getAnimations().forEach((a) => a.cancel()); $(".cuerpo").getAnimations().forEach((a) => a.cancel());
  const tiempo = { duration: 220, easing: "cubic-bezier(.3, .7, .2, 1)" };        // --t-rapida y --curva
  lat.style.width = `${ancho}px`;                 // al plegar, la barra sigue ancha (sobre el contenido) mientras se recorta
  lat.animate({ clipPath: [`inset(0 ${ancho - antes}px 0 0)`, `inset(0 ${ancho - despues}px 0 0)`] }, tiempo)
    .finished.catch(() => {}).finally(() => { lat.style.width = ""; });
  $(".cuerpo").animate({ transform: [`translateX(${antes - despues}px)`, "none"] }, tiempo);
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
  cerrarMenu(); cerrarModal(); pararPrevia();
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
    // En un «Regenerar textos» masivo no se avisa clip por clip (serían decenas): se avisa una vez al terminar.
    if (logro && !S.estado.lote_textos?.ids.includes(t.id)) avisar(`«${t.nombre}» ${LOGROS[t.estado]}.`);
  }
  const l = S.estado.lote_textos;
  if (l?.terminado && antes.lote_textos && !antes.lote_textos.terminado) {
    avisar(`Textos regenerados: ${l.listos} de ${l.total} listos${l.errores ? `, ${l.errores} con error` : ""}.`);
  }
}

// Sondeo: una consulta a la vez; cada 2 s mientras algo avanza (o sin conexión), cada 15 s en reposo
// (carpeta vigilada, otro dispositivo, sesión) y nada con la pestaña oculta.
const SONDEO_ACTIVO = 2000, SONDEO_REPOSO = 15000;
let detalleLeido = 0;
// Una subida pedida no cuenta mientras la cuota de YouTube tenga las subidas en pausa (pueden ser horas);
// un archivo que aún se copia a la carpeta vigilada sí (carpeta.pendientes[].copiando).
const algoAvanza = () => !S.conectado || S.estado.carpeta.pendientes.some((p) => p.copiando)
  || S.estado.trabajos.some((t) => enCola(t) || (t.subir_solicitado && !S.estado.subidas_pausadas_hasta));
// Huella de lo que muestra el panel: si una consulta trae lo mismo, no se reconstruye nada (antes se repintaba en cada ciclo).
let huellaPintada = "";
const huellaDatos = () => JSON.stringify([S.estado, S.detalle, S.conectado, S.jid]);
const sondeo = crearSondeo({        // web/sondeo.js
  consultar,
  // Lo recién completado se compara con lo último que se mostró, aunque se encadenen consultas; el primer pintado es completo.
  alEmpezar: () => ({ antes: S.estado, primera: !S.estado }),
  alTerminar: ({ antes, primera }) => {
    const huella = huellaDatos();
    if (!primera && huella === huellaPintada) { S.cambios = {}; return; }   // sin «recién completado» que repetir
    anunciar(antes); pintar(primera); huellaPintada = huella;
  },
  intervalo: () => (algoAvanza() ? SONDEO_ACTIVO : SONDEO_REPOSO),
  puede: () => !document.hidden && !$("#app").hidden && dentro,
});
// En una pantalla de acceso no se consulta el estado.
const refrescar = () => ($("#app").hidden ? Promise.resolve() : sondeo.refrescar());
document.addEventListener("visibilitychange", () => (document.hidden ? sondeo.detener() : refrescar()));

// Una respuesta que nunca llega no bloquea el sondeo: a los 15 s cuenta como «sin conexión» y se reintenta.
const plazo = () => { const c = new AbortController(); setTimeout(() => c.abort(), 15000); return { signal: c.signal }; };
async function consultar() {
  try {
    const nuevo = await api("/api/estado", plazo());
    S.estado = nuevo;
    S.conectado = true;
    const jid = S.jid;                         // se lee ahora: pudo abrirse un clip mientras llegaba el estado
    if (jid) {
      // La ficha completa solo se pide si el clip cambió (o cada 60 s); el progreso en vivo llega con /api/estado.
      const resumen = nuevo.trabajos.find((t) => t.id === jid), d = S.detalle;
      const vigente = d && resumen && d.id === jid && d.actualizado === resumen.actualizado && d.modo !== "largo" && Date.now() - detalleLeido < 60000;
      // Si el servidor responde con error, el clip ya no está (false); si no responde (plazo, red), se conserva la
      // ficha que se ve —con lo que se esté editando— con el estado actual del resumen pero la versión con la que se
      // descargó (así la próxima consulta la pide de nuevo y el formulario no se da por actualizado).
      const ficha = vigente ? { ...d, ...resumen } : await api(`/api/trabajos/${jid}`, plazo())
        .then((f) => { detalleLeido = Date.now(); return f; })
        .catch((e) => (e.status ? false : d?.id === jid ? { ...d, ...resumen, actualizado: d.actualizado } : null));
      if (S.jid === jid) S.detalle = ficha;     // se navegó a otro clip mientras llegaba: se descarta
    }
  } catch (e) { S.conectado = false; /* se reintenta en el siguiente ciclo */ }
}

let dentro = false;
async function entrar(ocultar = true) {        // ocultar = false: el acceso sigue encima mientras se desvanece (alPanel)
  $("#acceso").hidden = ocultar; $("#app").hidden = false;
  navegar();                                   // esqueleto mientras llegan los datos
  if (dentro) return refrescar();              // ya se había entrado antes en esta página (cerrar sesión y volver)
  dentro = true;
  S.ajustes = await api("/api/ajustes").catch(() => null);
  await refrescar();
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
  else if (S.vista === "perfiles") pintarPerfiles(m, completo);
  else if (S.vista === "trabajo") pintarTrabajo(m, completo);
  else if (S.vista === "plantilla" && completo) { esqueleto(m); pintarPlantilla(m); }
  else if (S.vista === "ajustes" && completo) { esqueleto(m); pintarAjustes(m); }
}

function pintarLateral() {
  const e = S.estado, yt = e.youtube, p = e.proveedores, n = e.trabajos.filter(enCola).length;
  $("#nav-cuenta").hidden = !n; $("#nav-cuenta").textContent = n;
  $("#nav-cuenta").setAttribute("aria-label", plural(n, "clip en cola", "clips en cola"));
  const activo = perfilActivo();
  poner($("#espacio"), h`${crudo(avatarPerfil(activo))}<div><strong>${activo?.nombre || "Fábrica Studio"}</strong><small>${yt.canal_id ? `Canal: ${yt.canal_nombre}` : "Sin canal de YouTube confirmado"}</small></div>`);
  poner($("#boton-perfil"), h`${crudo(avatarPerfil(activo, "mini"))}<span class="perfil-etiqueta"><span class="tenue">Creador:</span> <b>${activo?.nombre || "—"}</b></span>${ic("abajo")}`);
  poner($("#tarjeta-pc"), h`<b>${ic("monitor")}PC anfitrión<span class="punto ${S.conectado ? "bien" : "mal"}"></span></b>
    ${S.conectado ? crudo(h`${p.ffmpeg && p.ffprobe ? "FFmpeg disponible" : "FFmpeg no encontrado"}<br>Whisper ${p.whisper.modelo}<br>Carpeta vigilada ${e.carpeta.activa ? "activa" : "desactivada"}`) : "Sin conexión con el PC. Se reintenta cada 2 s."}`);
  const s = S.sesion, donde = s.local ? "Este PC" : s.sesion_iniciada ? "Sesión iniciada" : "Dispositivo vinculado";
  poner($("#perfil"), h`<div class="avatar" aria-hidden="true">${ic(s.local ? "monitor" : "dispositivos")}</div><div><strong>${s.usuario || donde}</strong><small>${s.usuario ? `${donde} · v` : "Versión "}${s.version}</small></div>`);
  poner($("#menu-lista"), h`<a href="#ajustes" data-accion="ir-ajustes" data-p="cuenta">${ic("ajustes")}Cuenta</a>${s.sesion_iniciada ? crudo(h`<button data-accion="cerrar-sesion">${ic("salir")}Cerrar sesión</button>`) : ""}`);
}

// Resumen: los Shorts renderizados sin subir, con «Subir ahora» para el más antiguo, «Elegir otro…» y «Subir todos».
function pintarSubidas(yt) {
  const caja = $("#r-subir"), lista = esperanSubir(), destinados = lista.filter((t) => t.publicar);
  caja.hidden = !yt.canal_id || !lista.length;
  if (caja.hidden) return poner(caja, "");
  const primero = destinados.find((t) => !t.subir_ya), pausa = S.estado.subidas_pausadas_hasta;
  const prioritarios = lista.filter((t) => t.subir_ya).length, conRitmo = lista.filter((t) => t.subir_solicitado && !t.subir_ya).length;
  const situacion = pausa ? `YouTube pausó las subidas por su límite diario hasta ${horaSubida(pausa)}.`
    : [prioritarios && `${plural(prioritarios, "va", "van")} primero en la cola`, conRitmo && `${conRitmo} con el ritmo de publicación (próxima: ${S.estado.proxima_subida ? horaSubida(S.estado.proxima_subida) : "ahora"})`]
      .filter(Boolean).join(" · ") || "Ninguno está en la cola de subida todavía.";
  poner(caja, h`<div class="subir-cabeza"><div class="conexion-icono">${ic("youtube")}</div>
      <div><h2>${plural(lista.length, "Short renderizado", "Shorts renderizados")} sin subir</h2><p>${situacion}</p></div></div>
    ${primero ? crudo(h`<div class="subir-primero"><span class="miniatura"><img src="/media/${primero.id}/miniatura.jpg?v=${primero.actualizado}" alt="" loading="lazy"></span>
      <span class="fila-subir-texto"><small>El más antiguo que espera</small><b>${primero.nombre}</b><small>${primero.textos.titulo || etiquetaOrigen(primero)}</small></span>
      <button class="primario" data-accion="subir-ahora" data-id="${primero.id}" data-foco="r-subir-ahora">${ic("subir")}Subir ahora</button></div>`)
      : crudo(`<p class="pequeno tenue">${destinados.length ? "Todos los que esperan ya van primero en la cola." : "Los que quedan se importaron sin destinar a YouTube: puedes subirlos uno a uno con «Elegir»."}</p>`)}
    <div class="fila"><button data-accion="elegir-subida" data-foco="r-elegir">Elegir otro…</button>
      ${destinados.length ? crudo(h`<button data-accion="subir-todos" data-foco="r-todos">Subir todos ahora (${destinados.length})</button>`) : ""}</div>
    <p class="pequeno tenue">Siempre en privado, al canal «${yt.canal_nombre}». «Subir ahora» se salta el ritmo de publicación del programa, no el límite diario de YouTube.</p>`);
}

// Hora de la próxima subida (la API da segundos desde 1970; 0 = se puede subir ya). Como mucho es al día siguiente.
function horaSubida(s) {
  const d = new Date(s * 1000), hora = d.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  return d.toDateString() === new Date().toDateString() ? hora : `mañana a las ${hora}`;
}
function pintarResumen(m, completo) {
  const e = S.estado, yt = e.youtube, ts = e.trabajos;
  const abrir = completo || !$("#r-cifras");
  if (abrir) {
    m.innerHTML = h`<div class="cabecera"><div><div class="antetitulo">Tu espacio creativo</div><h1>Tu estudio</h1><p>De un buen momento a tu próximo Short.</p></div>
        <button class="primario" data-accion="nuevo">${ic("mas")}Nuevo clip</button></div>
      <div class="cifras" id="r-cifras"></div>
      <section class="panel subir-panel" id="r-subir" aria-label="Subir a YouTube" hidden></section>
      <div class="dos-columnas"><div class="panel">
          <div class="panel-titulo"><div><h2>Un enlace. Un nuevo clip.</h2><p>Añade un momento de tu stream a la cola.</p></div></div>
          <form class="entrada" id="r-form"><div class="entrada-caja">${ic("enlace")}<input id="r-url" type="url" aria-label="Enlace del clip de Kick" placeholder="Pega un enlace de Kick…" autocomplete="off" required>
            <button class="primario">Añadir${ic("flecha")}</button></div>
            <div class="entrada-pie"><label class="perfil-rapido">Perfil<select id="r-perfil" aria-label="Perfil de creador para este enlace"></select></label>
              <span>Se procesa en tu PC y se destina a YouTube en privado.</span><button type="button" class="enlace-fino" data-accion="nuevo" data-p="archivo">${ic("subir")}O elige un archivo</button></div>
            <p class="error" id="r-error" role="alert" hidden></p></form>
          <div class="franja"><h3>Actividad reciente</h3><a class="enlace-fino" href="#cola">Ver la cola${ic("flecha")}</a></div>
          <div class="recientes" id="r-recientes"></div>
          <div class="panel-pie" id="r-pie"></div></div>
        <div class="panel formato"><div class="panel-titulo"><div><h2>Tu formato</h2><p id="r-estilo"></p></div><span class="pequeno tenue">9:16</span></div>
          <div class="formato-escena"><img src="/api/diseno/vista?ancho=352&t=${Date.now()}" alt="Maqueta del diseño actual de tus Shorts" width="176" height="313"></div>
          <div class="panel-pie"><span>1080 × 1920</span><a class="enlace-fino" href="#plantilla">Personalizar${ic("flecha")}</a></div></div></div>
      <div class="dos-columnas"><div class="panel conexion" id="r-youtube"></div><div class="panel conexion" id="r-tablet"></div></div>`;
    $("#r-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const error = $("#r-error"); error.hidden = true;
      try {
        await api("/api/importar/enlace", { method: "POST", json: { url: $("#r-url").value, publicar: true, modo: "clip", perfil: $("#r-perfil").value } });
        $("#r-url").value = ""; avisar("1 clip añadido a la cola."); refrescar();
      } catch (err) { error.textContent = err.message; error.hidden = false; }
    });
    S.dispositivos = null;
    api("/api/dispositivos").then((d) => { S.dispositivos = d; pintar(false); }).catch(() => {});
  }
  const cola = ts.filter(enCola).length, fallos = ts.filter((t) => t.estado === "error").length;
  const listos = ts.filter((t) => t.estado === "renderizado").length, subidos = ts.filter((t) => t.estado === "publicado").length;
  const cifras = $("#r-cifras"), vistas = [...cifras.querySelectorAll("[data-cuenta]")].map((el) => +el.textContent), previo = cifras._html;
  poner(cifras, h`<div class="cifra"><div class="cifra-titulo">Clips en la cola${ic("capas")}</div><div class="cifra-valor"><span data-cuenta="${cola}">${dos(cola)}</span> <small>${cola === 1 ? "clip" : "clips"}</small></div>
      <div class="cifra-nota">${fallos ? `${plural(fallos, "clip con error", "clips con error")}: revísalos en la cola` : "En espera o generándose"}</div></div>
    <div class="cifra"><div class="cifra-titulo">Listos para revisar${ic("check-circulo")}</div><div class="cifra-valor"><span data-cuenta="${listos}">${dos(listos)}</span> <small>${listos === 1 ? "Short" : "Shorts"}</small></div>
      <div class="cifra-nota">${plural(subidos, "subido", "subidos")} en privado a YouTube</div></div>
    <div class="cifra"><div class="cifra-titulo">Canal de YouTube${ic("youtube")}</div><div class="cifra-valor texto">${yt.canal_id ? yt.canal_nombre : "Sin confirmar"}</div>
      <div class="cifra-nota">${yt.canal_id ? `${yt.canal_id} · subidas siempre en privado` : "No se puede subir hasta confirmar el canal"}</div></div>`);
  if (abrir) contar(cifras);
  else if (cifras._html !== previo) contar(cifras, vistas);      // solo si la API trajo otras cifras
  const recientes = [...ts].filter(coincide).sort((a, b) => b.creado - a.creado).slice(0, 3);
  if (recientes.length) ponerLista($("#r-recientes"), recientes, "div", (t) => h`<div class="reciente">${crudo(clipHtml(t))}${crudo(pastilla(t))}</div>`);
  else poner($("#r-recientes"), `<div class="sin-nada">${icono("capas")}${S.busca ? "Ningún clip coincide con la búsqueda." : "Aún no hay clips. Pega un enlace arriba para empezar."}</div>`);
  poner($("#r-pie"), h`<span>${cola ? `${plural(cola, "clip", "clips")} en cola` : "No hay clips en cola"}</span><span>${e.carpeta.activa ? "Carpeta vigilada activa" : ""}</span>`);
  poner($("#r-perfil"), opcionesPerfil(e.perfil_activo));      // se rehace solo si cambian los perfiles o el activo
  pintarSubidas(yt);
  $("#r-estilo").textContent = NOMBRE_ESTILO[e.estilo] || NOMBRE_ESTILO.clasico;
  poner($("#r-youtube"), h`<div class="conexion-icono">${ic("youtube")}</div><div><h3>${yt.canal_id ? `Canal de destino: ${yt.canal_nombre}` : "Tu canal, en el mismo lugar"}</h3>
      <p>${yt.canal_id ? `Subida automática ${e.subida_automatica ? "activa" : "desactivada"}. Todo se sube en privado.` : yt.conectado ? "Cuenta conectada. Falta confirmar el canal de destino." : "Conecta YouTube para recibir tus Shorts en privado."}${e.proxima_subida > 0 ? ` Próxima subida: ${horaSubida(e.proxima_subida)}.` : ""}</p></div>
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
      <div class="herramientas"><div class="filtros" id="cola-filtros" role="group" aria-label="Filtrar por estado"></div>
        <div class="fila acciones-lote" id="cola-lote"></div></div>
      <div class="pila" id="cola-carpeta" style="margin-bottom:14px"></div>
      <div id="cola-progreso"></div>
      <div class="panel"><div class="tabla-desliza"><table class="tabla-cola"><thead><tr><th scope="col" class="sel"><input type="checkbox" id="sel-todos" aria-label="Elegir todos los clips que se ven"></th>
        <th scope="col">Clip</th><th scope="col">Estado</th><th scope="col">Origen</th><th scope="col">Duración</th><th scope="col"><span class="solo-lector">Acciones</span></th></tr></thead>
        <tbody id="cola-cuerpo"></tbody></table></div><div id="cola-vacia" class="sin-nada" hidden></div></div>`;
  }
  poner($("#cola-filtros"), FILTROS.map(([k, n, f]) => h`<button data-accion="filtro" data-foco="f-${k}" data-f="${k}" aria-pressed="${S.filtro === k}">${n} <span>${ts.filter(f).length}</span></button>`).join(""));
  poner($("#cola-carpeta"), e.carpeta.pendientes.map((p) => h`<p class="nota"><b>${p.archivo}</b> (carpeta vigilada): ${p.motivo}</p>`).join(""));
  const visibles = ts.filter(FILTROS.find(([k]) => k === S.filtro)[2]);
  const origen = { archivo: "Archivo", carpeta: "Carpeta", enlace: "Kick", momento: "Video largo" };
  for (const id of S.seleccion) if (!e.trabajos.some((t) => t.id === id)) S.seleccion.delete(id);   // eliminados
  ponerLista($("#cola-cuerpo"), visibles, "tr", (t) => h`<td class="sel"><input type="checkbox" data-sel="${t.id}" data-foco="s-${t.id}" aria-label="Elegir «${t.nombre}»" ${S.seleccion.has(t.id) ? "checked" : ""}></td>
    <td>${crudo(clipHtml(t))}</td><td>${crudo(pastilla(t))}</td><td>${origen[t.origen_tipo]}${t.modo === "largo" ? " · largo" : ""}</td>
    <td>${t.duracion ? reloj(t.duracion) : "—"}</td>
    <td>${["procesando", "subiendo"].includes(t.estado) ? "" : crudo(h`<button class="icono-boton" data-accion="quitar" data-foco="q-${t.id}" data-id="${t.id}" data-nombre="${t.nombre}" aria-label="Eliminar ${t.nombre}">${ic("papelera")}</button>`)}</td>`);
  $("#cola-vacia").hidden = visibles.length > 0;
  poner($("#cola-vacia"), `${icono("capas")}` + (S.busca ? "Ningún clip coincide con la búsqueda."
    : S.filtro !== "todos" ? "No hay clips en este estado."
    : h`Aún no hay clips. Pulsa «Nuevo clip»${e.carpeta.activa ? crudo(h` o copia un video en <code>${e.carpeta.ruta}</code>`) : ""}.`));
  const ids = visibles.map((t) => t.id), marcados = ids.filter((id) => S.seleccion.has(id)).length, todos = $("#sel-todos");
  todos.checked = marcados > 0 && marcados === ids.length; todos.indeterminate = marcados > 0 && marcados < ids.length;
  const sinSubir = e.trabajos.filter(regenerable).length;
  poner($("#cola-lote"), (S.seleccion.size ? h`<span class="pequeno">${plural(S.seleccion.size, "elegido", "elegidos")}</span>
      <button data-accion="regenerar-elegidos" data-foco="l-elegidos">Regenerar textos (${S.seleccion.size})</button>
      <button class="texto" data-accion="quitar-seleccion" data-foco="l-quitar">Quitar selección</button>` : "")
    + (sinSubir ? h`<button data-accion="regenerar-todos" data-foco="l-todos">Regenerar textos de todos los sin subir (${sinSubir})</button>` : ""));
  pintarLoteTextos();
}
// Lo que el servidor sí regenera (el resto lo omite y lo cuenta): sin subir, clip, terminado, fuera de la cola de subida
// y con la transcripción hecha (los textos salen de ella).
const regenerable = (t) => !t.youtube_id && t.modo !== "largo" && ["renderizado", "error"].includes(t.estado) && !t.subir_solicitado
  && t.etapas.transcribir?.estado === "hecho";
// Progreso del último «Regenerar textos» masivo, contado por el servidor con el estado real de cada clip.
function pintarLoteTextos() {
  const l = S.estado.lote_textos, caja = $("#cola-progreso");
  if (!caja) return;
  if (!l) return poner(caja, "");
  // La estructura se crea una vez; después solo cambian el texto y el transform de la barra (que así se llena suave).
  if (!$("#lp-barra", caja)) poner(caja, `<div class="panel lote-progreso" role="status"><div class="fila separado"><b id="lp-texto"></b><span id="lp-cerrar"></span></div>
    <div class="barra-progreso" aria-hidden="true"><i id="lp-barra" style="transform:scaleX(0)"></i></div><p class="pequeno tenue" id="lp-nota" hidden></p></div>`);
  $(".lote-progreso", caja).classList.toggle("terminado", l.terminado);
  $("#lp-texto").textContent = `${l.terminado ? "Textos regenerados" : "Regenerando textos"}: ${l.listos} de ${l.total} listos${l.errores ? ` · ${l.errores} con error` : ""}`;
  $("#lp-barra").style.transform = `scaleX(${(l.total ? (l.listos + l.errores) / l.total : 1).toFixed(3)})`;
  if (!!$("#lp-cerrar").firstChild !== l.terminado) $("#lp-cerrar").innerHTML = l.terminado ? `<button class="texto" data-accion="cerrar-lote">Cerrar</button>` : "";
  const nota = $("#lp-nota");
  nota.hidden = !l.con_borrador_local;
  nota.textContent = l.con_borrador_local ? `${plural(l.con_borrador_local, "clip quedó", "clips quedaron")} con el borrador local porque Gemini falló o no hay clave: su aviso dice el motivo.` : "";
}
const OMITIDOS = { subidos: "ya subidos", editados: "editados a mano", en_proceso: "en proceso", en_cola_de_subida: "en la cola de subida",
  sin_transcripcion: "aún sin transcripción", videos_largos: "videos largos", no_existen: "que ya no existen" };
// «Regenerar textos» de los elegidos (ids) o de todos los que no se han subido (null). Explica qué pasa y con qué.
async function regenerarVarios(ids) {
  const ts = S.estado.trabajos, elegidos = ids ? ts.filter((t) => ids.includes(t.id)) : ts.filter((t) => !t.youtube_id);
  const posibles = elegidos.filter(regenerable), editados = posibles.filter((t) => t.textos.origen === "editado").length;
  // Con «todos los sin subir» también se dice: así queda claro que lo publicado no cambia.
  const subidos = (ids ? elegidos : ts).filter((t) => t.youtube_id).length, base = posibles.length - editados;
  if (!posibles.length) return avisar("Ninguno de esos clips se puede regenerar ahora: están subidos, en proceso o en la cola de subida.", true);
  const p = S.estado.proveedores, gemini = p.gemini.clave && p.textos !== "local";
  const ok = await new Promise((resolver) => {
    abrirModal("Regenerar textos", h`<p>Se volverán a generar el banner, el título y la descripción de ${plural(base, "clip", "clips")} con ${gemini ? "Gemini (una llamada por clip, con tu cuota)" : "el borrador local (sin IA)"} y se renderizarán de nuevo. No se transcriben otra vez.</p>
      ${editados ? crudo(h`<label class="linea"><input type="checkbox" id="rv-editados" ${base ? "" : "checked"}> Incluir también ${plural(editados, "clip editado", "clips editados")} a mano (se pierden esos cambios)</label>`) : ""}
      ${subidos ? crudo(h`<p class="pequeno tenue">${subidos === 1 ? "1 clip ya subido no se toca" : `${subidos} clips ya subidos no se tocan`}: sus textos ya están en YouTube.</p>`) : ""}
      <p class="pequeno tenue">Los que estén en proceso o en la cola de subida se omiten. El avance se ve en la cola.</p>`,
    h`<button data-accion="cerrar-modal">Cancelar</button><button class="primario" id="modal-si">Regenerar textos</button>`);
    modalResuelve = resolver;
    $("#modal-si").onclick = () => cerrarModal({ editados: !!$("#rv-editados")?.checked });
  });
  if (!ok) return;
  const r = await api("/api/textos/regenerar", { method: "POST", json: { ids, incluir_editados: ok.editados } });
  const omitidos = Object.entries(r.omitidos).map(([k, n]) => `${n} ${OMITIDOS[k] || k}`).join(", ");
  avisar(`Regenerando los textos de ${plural(r.regenerando, "clip", "clips")}.${omitidos ? ` Omitidos: ${omitidos}.` : ""}`);
  S.seleccion.clear(); refrescar();
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

// Biblioteca: al pasar el mouse (o mantener pulsado en la tablet) la tarjeta reproduce su Short en silencio. El video
// se crea al empezar (preload="none": nada se descarga antes) y se destruye al salir; queda la miniatura.
let previa = null;
function verPrevia(pieza) {
  if (previa?.pieza === pieza) return;
  pararPrevia();
  if (!pieza || calma.matches) return;
  const v = document.createElement("video");
  v.muted = v.defaultMuted = v.loop = v.playsInline = true;
  v.preload = "none"; v.className = "previa"; v.setAttribute("aria-hidden", "true");
  v.src = `/media/${pieza.getAttribute("href").split("/")[1]}/short.mp4`;
  v.addEventListener("playing", () => v.classList.add("lista"), { once: true });   // aparece cuando de verdad reproduce
  $("img", pieza).after(v);
  previa = { pieza, v };
  v.play().catch(() => {});        // si el navegador no lo permite, se queda la miniatura
}
function pararPrevia() {
  if (!previa) return;
  const { v } = previa; previa = null;
  v.pause(); v.classList.remove("lista");
  setTimeout(() => { v.removeAttribute("src"); v.load(); v.remove(); }, calma.matches ? 0 : 160);   // corta la descarga
}
const piezaDe = (e) => e.target.closest?.("#bib-rejilla .pieza") || null;
document.addEventListener("pointerover", (e) => { if (e.pointerType === "mouse") verPrevia(piezaDe(e)); });
document.addEventListener("pointerout", (e) => { if (e.pointerType === "mouse" && previa && !previa.pieza.contains(e.relatedTarget)) pararPrevia(); });
// Tablet: mantener pulsado 350 ms. Un toque corto abre el clip como siempre; tras mantener pulsado, soltar no lo abre.
let pulsando = 0, tocando = false, mantenida = false;
document.addEventListener("pointerdown", (e) => {
  const p = e.pointerType !== "mouse" && piezaDe(e);
  if (!p) return;
  tocando = true; mantenida = false; clearTimeout(pulsando);
  pulsando = setTimeout(() => { mantenida = true; verPrevia(p); }, 350);
});
const soltarPieza = (e) => { if (e.pointerType === "mouse") return; tocando = false; clearTimeout(pulsando); if (mantenida) pararPrevia(); };
document.addEventListener("pointerup", soltarPieza);
document.addEventListener("pointercancel", soltarPieza);     // al desplazar la página el navegador cancela la pulsación
// Solo con el dedo: el menú del enlace taparía la vista previa. Con el mouse, el clic derecho sigue igual.
document.addEventListener("contextmenu", (e) => { if (tocando && piezaDe(e)) e.preventDefault(); });
document.addEventListener("click", (e) => { if (mantenida && piezaDe(e)) { e.preventDefault(); e.stopPropagation(); } mantenida = false; }, true);

// ---------------------------------------------------------------- perfiles de creador
// La lista completa (contexto, correcciones, hashtags) se pide a /api/perfiles al abrir la vista y cuando /api/estado
// avisa de un cambio (otro perfil, otra versión); el activo y cuántos clips usan cada uno salen siempre de /api/estado.
let perfilesPedidos = null;
const cargarPerfiles = () => (perfilesPedidos ||= api("/api/perfiles")
  .then((r) => { S.perfiles = r.perfiles; return r.perfiles; }).finally(() => { perfilesPedidos = null; }));
const huellaPerfiles = (lista, v) => lista.map((p) => p.id + p[v]).join();
const ESTILO_CORTO = { "": "El de la Plantilla", auto: "Automático", clasico: "Clásico", completo: "Pantalla completa", dividido: "Vista dividida" };

async function pintarPerfiles(m, completo) {
  if (completo || !$("#pf-rejilla")) {
    m.innerHTML = h`<div class="cabecera"><div><div class="antetitulo">Tus creadores</div><h1>Perfiles</h1>
        <p>Cada streamer con su nombre, firma, contexto de transcripción, tema y logo. Los clips nuevos usan el perfil activo.</p></div>
        <button class="primario" data-accion="nuevo-perfil">${ic("mas")}Nuevo perfil</button></div>
      <div class="perfiles" id="pf-rejilla"></div>`;
  }
  if (completo || !S.perfiles || huellaPerfiles(S.perfiles, "actualizado") !== huellaPerfiles(S.estado.perfiles, "v")) {
    try { await cargarPerfiles(); } catch (e) {
      if (!S.perfiles) $("#pf-rejilla").innerHTML = `<div class="panel sin-nada" role="alert">No se pudieron cargar los perfiles. Vuelve a entrar en Perfiles para reintentar.</div>`;
      return avisar(e.message, true);
    }
  }
  if (S.vista !== "perfiles" || !$("#pf-rejilla")) return;   // se cambió de vista mientras llegaban los datos
  ponerLista($("#pf-rejilla"), S.perfiles, "div", tarjetaPerfil);
}
function tarjetaPerfil(p) {
  const activo = p.id === S.estado.perfil_activo, clips = S.estado.trabajos.filter((t) => t.perfil === p.id).length;
  const corto = { ...p, v: p.actualizado };
  return h`<article class="tarjeta perfil-tarjeta ${activo ? "activo" : ""}" aria-labelledby="pf-n-${p.id}">
    <div class="perfil-cabeza">${crudo(avatarPerfil(corto, "grande"))}<div><h2 id="pf-n-${p.id}">${p.nombre}</h2><p>${p.firma || "Sin firma: se usa el nombre"}</p></div>
      ${activo ? crudo(`<span class="pastilla subido">${icono("check")}Activo</span>`) : ""}</div>
    <dl class="ficha"><dt>Tema</dt><dd>${TEMAS[p.tema] || p.tema}</dd>
      ${p.tema === "gta6" ? crudo(h`<dt>Hashtags</dt><dd>${p.hashtags_fijos || "—"}</dd>`) : ""}
      <dt>Estilo</dt><dd>${ESTILO_CORTO[p.estilo] || p.estilo}</dd>
      <dt>Logo</dt><dd>${p.logo ? "Propio" : "El general de la Plantilla"}</dd>
      <dt>Clips</dt><dd>${clips}</dd></dl>
    <div class="fila">${activo ? "" : crudo(h`<button class="primario" data-accion="activar-perfil" data-id="${p.id}" data-foco="pa-${p.id}">Usar este perfil</button>`)}
      <button data-accion="editar-perfil" data-id="${p.id}" data-foco="pe-${p.id}">Editar</button>
      <button data-accion="duplicar-perfil" data-id="${p.id}" data-foco="pd-${p.id}">Duplicar</button>
      <button class="texto peligro" data-accion="eliminar-perfil" data-id="${p.id}" data-foco="px-${p.id}" ${crudo(activo ? `disabled aria-describedby="pf-motivo-${p.id}"` : "")}>Eliminar</button></div>
    ${activo ? crudo(h`<p class="pequeno tenue" id="pf-motivo-${p.id}">Es el perfil activo: para eliminarlo, activa otro.</p>`) : ""}</article>`;
}

// Editor de un perfil (nuevo si p es null). El logo se sube después de guardar, porque necesita el id del perfil.
function editarPerfil(p) {
  const nuevo = !p;
  p = p || { nombre: "", firma: "", contexto_transcripcion: "", correcciones: "", tema: "", hashtags_fijos: "#GTA6 #GTAVI #GTA #Gaming", estilo: "", logo: false };
  let archivoLogo = null, quitarLogo = false, url = null;
  const general = ESTILO_CORTO[S.estado.estilo] || S.estado.estilo;
  abrirModal(nuevo ? "Nuevo perfil" : `Editar «${p.nombre}»`, h`<form id="form-perfil" class="pila" novalidate>
      <div class="campos"><label>Nombre del creador<input name="nombre" maxlength="40" required value="${p.nombre}" autocomplete="off"></label>
        <label>Firma bajo el logo<input name="firma" maxlength="40" value="${p.firma}" placeholder="@usuario" autocomplete="off"></label></div>
      <p class="pequeno tenue">El nombre aparece en títulos y descripciones; la firma, bajo el logo (vacía = el nombre).</p>
      <label>Contexto de transcripción<textarea name="contexto_transcripcion" rows="3" maxlength="600" aria-describedby="pf-ayuda-contexto">${p.contexto_transcripcion}</textarea></label>
      <p class="pequeno tenue" id="pf-ayuda-contexto">Escríbelo como se habla, con puntuación: «Stream de Chetalonso en Kick. ¿Cachai? Ya po, altiro.» Una lista de palabras sueltas empeora la transcripción. Solo orienta a Whisper; no agrega nada al texto.</p>
      <label>Correcciones de escritura<textarea name="correcciones" rows="3" maxlength="4000" placeholder="cachay => cachai" aria-describedby="pf-ayuda-correcciones">${p.correcciones}</textarea></label>
      <p class="pequeno tenue" id="pf-ayuda-correcciones">Una por línea: como sale => como debe verse. Corrigen subtítulos y títulos; la transcripción literal no cambia.</p>
      <div class="campos"><label>Tema<select name="tema">${Object.entries(TEMAS).map(([k, n]) => crudo(h`<option value="${k}" ${k === p.tema ? "selected" : ""}>${k === "gta6" ? "GTA 6: todo es de GTA 6" : n}</option>`))}</select></label>
        <label>Estilo preferido<select name="estilo">${Object.entries(ESTILO_CORTO).map(([k, n]) => crudo(h`<option value="${k}" ${k === p.estilo ? "selected" : ""}>${k ? n : `${n} (ahora: ${general})`}</option>`))}</select></label></div>
      <div class="pila" id="pf-hashtags" ${p.tema === "gta6" ? "" : crudo("hidden")}><label>Hashtags fijos<input name="hashtags_fijos" maxlength="200" value="${p.hashtags_fijos}" placeholder="#GTA6 #GTAVI #GTA #Gaming"></label>
        <p class="pequeno tenue">Con GTA 6 cada título menciona «GTA 6», la categoría es Gaming y estos hashtags van en la descripción.</p></div>
      <div class="logo-perfil"><span id="pf-logo-vista">${crudo(avatarPerfil({ ...p, v: p.actualizado }, "grande"))}</span>
        <div class="pila" style="gap:8px"><b>Logo propio (opcional)</b><p class="pequeno tenue" id="pf-logo-texto">${p.logo ? "Este perfil tiene su propio logo." : "Sin logo propio: se usa el logo general de la Plantilla."}</p>
          <div class="fila"><label class="boton">${ic("subir")}Elegir imagen<input type="file" id="pf-logo" class="solo-lector" accept="image/png,image/webp,image/jpeg"></label>
          <button type="button" id="pf-logo-quitar" ${p.logo ? "" : crudo("hidden")}>Quitar logo</button></div></div></div>
      <p class="error" id="pf-error" role="alert" hidden></p></form>`,
  h`<button data-accion="cerrar-modal">Cancelar</button><button class="primario" id="pf-guardar">${nuevo ? "Crear perfil" : "Guardar cambios"}</button>`);
  const f = $("#form-perfil"), error = $("#pf-error");
  const soltarUrl = () => { if (url) URL.revokeObjectURL(url); url = null; };
  modalResuelve = soltarUrl;                  // al cerrar la ventana de cualquier forma, se libera la vista previa del logo
  f.tema.addEventListener("change", () => { $("#pf-hashtags").hidden = f.tema.value !== "gta6"; });
  $("#pf-logo").addEventListener("change", (e) => {
    archivoLogo = e.target.files[0] || null; quitarLogo = false; soltarUrl();
    if (!archivoLogo) return;
    url = URL.createObjectURL(archivoLogo);
    $("#pf-logo-vista").innerHTML = h`<span class="avatar grande" aria-hidden="true"><img src="${url}" alt=""></span>`;
    $("#pf-logo-texto").textContent = `Se usará ${archivoLogo.name} al guardar.`; $("#pf-logo-quitar").hidden = false;
  });
  $("#pf-logo-quitar").addEventListener("click", () => {
    archivoLogo = null; quitarLogo = p.logo; soltarUrl(); $("#pf-logo").value = "";
    $("#pf-logo-vista").innerHTML = avatarPerfil({ nombre: f.nombre.value || p.nombre }, "grande");
    $("#pf-logo-texto").textContent = "Sin logo propio: se usará el logo general de la Plantilla."; $("#pf-logo-quitar").hidden = true;
  });
  f.addEventListener("submit", (e) => { e.preventDefault(); $("#pf-guardar").click(); });
  $("#pf-guardar").onclick = async () => {
    const campos = Object.fromEntries([...f.querySelectorAll("[name]")].map((i) => [i.name, i.value]));
    if (!campos.nombre.trim()) { error.textContent = "Escribe el nombre del creador."; error.hidden = false; return f.nombre.focus(); }
    const boton = $("#pf-guardar"); boton.disabled = true; error.hidden = true;
    try {
      const r = await api(nuevo ? "/api/perfiles" : `/api/perfiles/${p.id}`, { method: nuevo ? "POST" : "PUT", json: campos });
      if (archivoLogo) { const d = new FormData(); d.append("archivo", archivoLogo); await api(`/api/perfiles/${r.id}/logo`, { method: "POST", body: d }); }
      else if (quitarLogo) await api(`/api/perfiles/${r.id}/logo`, { method: "DELETE" });
      soltarUrl(); cerrarModal();
      avisar(nuevo ? `Perfil «${r.nombre}» creado.` : `Perfil «${r.nombre}» guardado. Se aplica a sus clips cuando se procesen o se rendericen de nuevo.`);
      await recargarPerfiles();
    } catch (err) {
      if (!$("#form-perfil")) return avisar(err.message, true);       // la ventana se cerró mientras se guardaba
      error.textContent = err.message; error.hidden = false; boton.disabled = false;
    }
  };
}
async function recargarPerfiles() {
  S.perfiles = null;
  await refrescar();
  if (S.vista === "perfiles") await pintarPerfiles($("#principal"), false);
}

document.addEventListener("change", intentar(async (e) => {
  if (e.target.closest("[data-perfil-trabajo]")) return cambiarPerfilClip(e.target);
  const sel = e.target.closest("[data-estilo-trabajo]");
  if (!sel) return;
  await api(`/api/trabajos/${S.jid}/estilo`, { method: "PUT", json: { estilo: sel.value } });
  avisar("Estilo cambiado: se renderiza de nuevo (no se repite la transcripción)."); refrescar();
}));

// Elegir clips en la cola (casillas): no se envía nada hasta pulsar una acción. La del encabezado elige los que se ven.
document.addEventListener("change", (e) => {
  const c = e.target.closest?.("[data-sel], #sel-todos");
  if (!c) return;
  const ids = c.id === "sel-todos" ? [...document.querySelectorAll("[data-sel]")].map((x) => x.dataset.sel) : [c.dataset.sel];
  ids.forEach((id) => (c.checked ? S.seleccion.add(id) : S.seleccion.delete(id)));
  pintar(false);
});

// Cambiar el perfil de un clip rehace textos y render. Si el contexto que recibiría Whisper es otro, la misma ventana
// ofrece volver a transcribir (si no, se conserva la transcripción actual).
async function cambiarPerfilClip(sel) {
  const t = S.detalle, nuevo = perfilPorId(sel.value);
  const volver = () => { sel.value = perfilPorId(t.perfil) ? t.perfil : ""; };
  let lista;
  try { lista = await cargarPerfiles(); } catch (err) { volver(); throw err; }
  const contexto = (id) => lista.find((p) => p.id === id)?.contexto_efectivo;
  const cambia = contexto(t.perfil) !== contexto(sel.value);
  const motivo = t.editado ? "tiene una edición de tiempos (quítala antes con «Volver al clip completo»)"
    : t.origen_tipo === "momento" ? "usa la transcripción de su video largo" : "";
  const ok = await new Promise((resolver) => {
    abrirModal("Cambiar el perfil del clip", h`<p>«${t.nombre}» pasará a usar el perfil «${nuevo.nombre}»: se vuelven a generar el banner, el título y la descripción (se pierden los cambios hechos a mano) y se renderiza de nuevo.</p>
      ${!cambia ? "" : motivo ? crudo(h`<p class="nota">El contexto de transcripción de «${nuevo.nombre}» es distinto, pero este clip no se puede volver a transcribir porque ${motivo}. Se conserva la transcripción actual.</p>`)
        : crudo(h`<label class="linea"><input type="checkbox" id="cp-retranscribir"> Volver a transcribir con el contexto de «${nuevo.nombre}»</label>
          <p class="pequeno tenue">El contexto de transcripción de este perfil es distinto. Volver a transcribir tarda unos minutos y rehace los subtítulos; si no, se conserva la transcripción actual.</p>`)}`,
    h`<button data-accion="cerrar-modal">Cancelar</button><button class="primario" id="modal-si">Cambiar perfil</button>`);
    modalResuelve = resolver;
    $("#modal-si").onclick = () => cerrarModal({ retranscribir: !!$("#cp-retranscribir")?.checked });
  });
  if (!ok) return volver();
  try {
    await api(`/api/trabajos/${t.id}/perfil`, { method: "PUT", json: { perfil: nuevo.id, retranscribir: ok.retranscribir } });
  } catch (err) { volver(); throw err; }
  avisar(ok.retranscribir ? `Perfil «${nuevo.nombre}»: se vuelve a transcribir y a renderizar.` : `Perfil «${nuevo.nombre}»: se regeneran los textos y el render.`);
  S.sucio = false; refrescar();
}

document.addEventListener("click", (e) => {
  const acc = e.target.closest("[data-accion]");
  if (acc) acciones[acc.dataset.accion]?.(acc);
});

// ---------------------------------------------------------------- detalle del trabajo
// El servidor deja en el detalle de la etapa Render «… · automático: <motivo> · <encuadre usado> · …».
function encuadreAuto(t) {
  const det = t.etapas.render?.estado === "hecho" ? t.etapas.render.detalle || "" : "";
  const motivo = /automático: ([^·]+)/.exec(det)?.[1].trim();
  if (!motivo) return "";
  const usado = ["vista dividida", "pantalla completa con seguimiento", "clásico"].find((x) => det.includes(` · ${x}`));
  return h`<p class="nota encuadre"><b>Encuadre automático${usado ? `: ${usado}` : ""}.</b> Motivo: ${motivo}.</p>`;
}
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
  if (t.estado === "renderizado" && !t.youtube_id) {
    if (!yt.canal_id) botones += t.subir_solicitado ? "" : `<a class="boton" href="#ajustes" data-accion="ir-ajustes" data-p="youtube">Conectar YouTube para subir</a>`;
    else {
      if (!t.subir_ya) botones += h`<button class="primario" data-accion="subir-ahora" data-foco="b-subir-ahora">${ic("subir")}Subir ahora</button>`;
      // Con un ritmo de publicación que haría esperar, también se puede dejar en la cola normal.
      if (!t.subir_solicitado && S.estado.proxima_subida && !S.estado.subidas_pausadas_hasta) botones += `<button data-accion="subir" data-foco="b-subir">Añadir a la cola (con el ritmo)</button>`;
      if (t.subir_solicitado) botones += `<button data-accion="cancelar-subida" data-foco="b-cancelar-subida">Quitar de la cola de subida</button>`;
    }
  }
  if (t.estado === "renderizado" && !t.subir_solicitado) {
    botones += `<button data-accion="renderizar" data-foco="b-render">Renderizar de nuevo</button>`;
    if (!t.youtube_id) botones += h`<button data-accion="editar-tiempos" data-foco="b-tiempos">${ic("tijera")}Editar tiempos</button>`;
  }
  if (["renderizado", "error"].includes(t.estado) && !t.subir_solicitado && !t.youtube_id) {
    botones += h`<label class="estilo-trabajo">Perfil<select data-perfil-trabajo data-foco="b-perfil">${crudo(opcionesPerfil(t.perfil))}
      ${perfilPorId(t.perfil) ? "" : crudo(h`<option value="" selected disabled>${nombrePerfil(t)}</option>`)}</select></label>`;
    const general = { auto: "automático", completo: "pantalla completa", dividido: "vista dividida" }[S.estado.estilo] || "clásico";
    botones += h`<label class="estilo-trabajo">Estilo<select data-estilo-trabajo data-foco="b-estilo">
      <option value="auto" ${t.estilo === "auto" ? "selected" : ""}>Automático (recomendado): elige el mejor encuadre</option>
      <option value="" ${t.estilo === "" ? "selected" : ""}>General de Ajustes (${general})</option>
      <option value="clasico" ${t.estilo === "clasico" ? "selected" : ""}>Clásico: video completo con tarjeta</option>
      <option value="completo" ${t.estilo === "completo" ? "selected" : ""}>Pantalla completa con seguimiento</option>
      <option value="dividido" ${t.estilo === "dividido" ? "selected" : ""}>Vista dividida: cámara arriba, contenido abajo</option></select></label>`;
  }
  let motivo = "";
  if (["renderizado", "error"].includes(t.estado) && !t.subir_solicitado && !t.youtube_id) {
    motivo = t.editado ? "Para volver a transcribir, primero quita la edición de tiempos («Editar tiempos» → «Volver al clip completo»)."
      : t.origen_tipo === "momento" ? "Este clip usa la transcripción de su video largo; no se transcribe por separado." : "";
    botones += h`<button data-accion="retranscribir" data-foco="b-retranscribir" ${crudo(motivo ? 'disabled aria-describedby="t-motivo"' : "")}>Volver a transcribir</button>`;
  }
  if (t.tiene_video && ["renderizado", "subiendo", "publicado"].includes(t.estado)) botones += h`<button data-accion="exportar" data-foco="b-exportar">${ic("subir")}Exportar</button>`;
  if (t.tiene_video) botones += h`<a class="boton" href="/media/${t.id}/short.mp4" download="${t.nombre}.mp4">Descargar MP4</a>`;
  if (!["procesando", "subiendo"].includes(t.estado)) botones += `<button class="texto peligro" data-accion="eliminar" data-foco="b-eliminar">Eliminar</button>`;
  const sal = t.salida;
  const destino = t.youtube_id ? "Subido en privado" : t.subir_solicitado || t.estado === "subiendo" ? "En cola para subir en privado" : t.publicar ? "Sin subir" : "No destinado a YouTube";
  poner($("#t-estado"), h`<div class="fila">${crudo(pastilla(t))}<span class="tenue pequeno">${t.progreso || estadoSubida(t)}</span></div>
    ${t.error ? crudo(h`<p class="nota mal" role="alert">${t.error}</p>`) : ""}
    ${crudo(encuadreAuto(t))}
    ${t.avisos.map((a) => crudo(h`<p class="nota">${a}</p>`))}
    ${t.youtube_id ? crudo(h`<p class="nota bien">Subido en privado. ID de YouTube: <code>${t.youtube_id}</code> ·
      <a href="https://studio.youtube.com/video/${t.youtube_id}/edit" target="_blank" rel="noopener">Abrir en YouTube Studio</a></p>`) : ""}
    <dl class="ficha"><dt>Origen</dt><dd>${etiquetaOrigen(t)}</dd>
      <dt>Perfil</dt><dd>${nombrePerfil(t)}</dd>
      <dt>Duración</dt><dd>${t.duracion ? reloj(t.duracion) : "—"}</dd>
      <dt>Resultado</dt><dd>${sal ? `${sal.ancho} × ${sal.alto} · ${sal.codec_video}/${sal.codec_audio || "sin audio"} · ${(sal.tamano_bytes / 1048576).toFixed(1)} MB` : "Aún sin renderizar"}</dd>
      ${sal && t.copia ? crudo(h`<dt>Copia</dt><dd>2_shorts_renderizados/${t.copia}</dd>`) : ""}
      <dt>YouTube</dt><dd>${destino}</dd></dl>
    <ul class="pasos">${crudo(pasos)}</ul>
    <div class="fila">${crudo(botones)}</div>${motivo ? crudo(h`<p class="pequeno tenue" id="t-motivo">${motivo}</p>`) : ""}`);

  // Formularios: se repintan solo si el trabajo cambió, no hay cambios sin guardar y no se está escribiendo ni leyendo
  // ahí. Un botón de acción con el foco (p. ej. «Regenerar automáticamente») no impide ver el resultado: el foco vuelve a él.
  const version = `${t.actualizado}|${ocupado}`, a = document.activeElement;
  const accion = $("#t-edicion").contains(a) && a.matches("button[data-accion]") ? a.dataset.accion : "";
  if (S.sucio || S.version === version || ($("#t-edicion").contains(a) && !accion)) return;
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
      <div class="pila" style="gap:8px"><h3>Así se verá</h3>${crudo(previasPublicacion(t))}
        <p class="pequeno tenue">Vista previa aproximada (cada app cambia su diseño); el texto es el real. Los emojis se ven con el estilo de cada teléfono.</p></div>
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
  if (accion) $(`#t-edicion [data-accion="${accion}"]`)?.focus();
  const ft = $("#form-textos");
  if (ft) {
    // Largo en caracteres como lo cuenta el servidor (un emoji de 4 bytes es 1, no 2 como en .length) y emojis completos.
    const contar = () => {
      const n = [...ft.titulo.value].length, e = (ft.titulo.value.match(EMOJIS) || []).length;
      $("#c-titulo").textContent = `${n}/80 · ${e === 1 ? "1 emoji" : `${e} emojis`}`; $("#c-titulo").classList.toggle("pasado", n > 80);
      ponerPrevias(ft.titulo.value, `${ft.desc.value}\n${ft.etiquetas.value}`);
    };
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

// ---------------------------------------------------------------- exportar a otras plataformas
const PLATAFORMAS = [["tiktok", "TikTok"], ["reels", "Instagram Reels"], ["shorts", "YouTube Shorts"]];
// Igual que exportar.texto_publicacion (Python; una prueba compara las dos): título sin #Shorts + descripción + hashtags.
function textoPublicacion(textos, plataforma) {
  const titulo = (textos.titulo || "").replace(/\s*#Shorts\b/gi, "").trim();
  const [descripcion = "", etiquetas = ""] = (textos.descripcion || "").split("\n");
  let hashtags = etiquetas.split(/\s+/).filter(Boolean);
  if (plataforma !== "shorts") hashtags = hashtags.filter((x) => x.toLowerCase() !== "#shorts");
  const partes = [titulo], d = descripcion.trim();
  if (d && !titulo.toLowerCase().includes(d.toLowerCase())) partes.push(d);
  partes.push(hashtags.join(" "));
  return partes.filter(Boolean).join("\n\n") + "\n";
}
// Un emoji completo (con tono de piel, selector de variación y lo que se le une con ZWJ), como textos.contar_emojis.
const EMOJIS = /\p{Extended_Pictographic}(?:\p{Emoji_Modifier}|\u{FE0F})*(?:\u{200D}\p{Extended_Pictographic}(?:\p{Emoji_Modifier}|\u{FE0F})*)*/gu;
// Vista previa del título en YouTube Shorts (el título) y en TikTok (el texto que deja «Exportar»), sobre la miniatura.
function previasPublicacion(t) {
  const fondo = t.tiene_video ? h`<img src="/media/${t.id}/miniatura.jpg?v=${t.actualizado}" alt="">` : "";
  const movil = (clase, cuenta, nombre) => h`<figure class="previa-movil ${clase}"><div class="previa-pantalla">${crudo(fondo)}
      <div class="previa-pie"><b>${cuenta}</b><p class="previa-titulo"></p></div></div><figcaption>${nombre}</figcaption></figure>`;
  return `<div class="previas" id="t-previas">${movil("yt", `@${S.estado.youtube.canal_nombre || "tu_canal"}`, "YouTube Shorts")}${movil("tt", "@tu_cuenta", "TikTok")}</div>`;
}
function ponerPrevias(titulo, descripcion) {
  const p = $("#t-previas");
  if (!p) return;
  $(".yt .previa-titulo", p).textContent = titulo;
  $(".tt .previa-titulo", p).textContent = textoPublicacion({ titulo, descripcion }, "tiktok").trim();
}
// Se muestra la ruta dentro de la carpeta de datos (4_exportados/<plataforma>/<archivo>), no la ruta completa del PC.
const rutaCorta = (r) => String(r).split(/[\\/]/).slice(-3).join("/");
// Desde la tablet el panel va por http en la red de casa y el portapapeles moderno no está disponible:
// se usa el método antiguo y, si tampoco funciona, el texto queda seleccionado para copiarlo a mano.
async function copiarTexto(area) {
  try { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(area.value); return true; } } catch (e) { /* se intenta el método antiguo */ }
  area.focus(); area.select();
  try { return document.execCommand("copy"); } catch (e) { return false; }
}
function exportarClip(t) {
  abrirModal("Exportar el Short", h`<p>Copia el video y el texto de la publicación a la carpeta <b>4_exportados</b> del PC para subirlos a mano. No se publica nada.</p>
    <div class="fila" role="group" aria-label="Plataforma">${PLATAFORMAS.map(([k, n]) => crudo(h`<button type="button" data-plataforma="${k}" aria-pressed="false">${n}</button>`))}</div>
    <div id="ex-resultado" class="pila" aria-live="polite"></div>`, `<button data-accion="cerrar-modal">Cerrar</button>`);
  const cuerpo = $("#modal-cuerpo"), resultado = $("#ex-resultado");
  cuerpo.addEventListener("click", intentar(async (e) => {
    if (e.target.closest("#ex-copiar")) {
      const bien = await copiarTexto($("#ex-texto"));
      $("#ex-copiado").textContent = bien ? "Copiado." : "Texto seleccionado: cópialo con Ctrl+C o manteniéndolo pulsado.";
      return;
    }
    const b = e.target.closest("[data-plataforma]");
    if (!b) return;
    const botones = [...cuerpo.querySelectorAll("[data-plataforma]")];
    botones.forEach((x) => { x.disabled = true; x.setAttribute("aria-pressed", x === b); });
    resultado.innerHTML = `<p class="pequeno tenue" role="status">Exportando…</p>`;
    let r;
    try { r = await api(`/api/trabajos/${t.id}/exportar`, { method: "POST", json: { plataforma: b.dataset.plataforma } }); }
    catch (err) { resultado.innerHTML = h`<p class="nota mal" role="alert">${err.message}</p>`; throw err; }
    finally { botones.forEach((x) => { x.disabled = false; }); }
    resultado.innerHTML = h`<p class="nota bien">Exportado para ${r.plataforma}. En el PC: <code>${rutaCorta(r.video)}</code> y <code>${rutaCorta(r.texto_archivo)}</code>.</p>
      <label>Texto de la publicación<textarea id="ex-texto" rows="5" readonly>${r.texto}</textarea></label>
      <div class="fila"><button type="button" id="ex-copiar">Copiar texto</button><span class="pequeno tenue" id="ex-copiado" role="status"></span></div>
      ${r.avisos.length ? crudo(h`<p class="pequeno"><b>Zona segura de ${r.plataforma}</b></p>${r.avisos.map((a) => crudo(h`<p class="nota">${a}</p>`))}`)
        : crudo(h`<p class="pequeno tenue">Nada queda bajo los botones ni los textos de ${r.plataforma}.</p>`)}
      <p class="pequeno tenue">Las zonas seguras son aproximadas: cada app cambia su diseño de vez en cuando.</p>`;
  }));
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
// El editor de tiempos (web/editor.js, 24 KB) se descarga la primera vez que se abre, no al cargar el panel.
let editorCargando = null;
function cargarEditor() {
  if (window.abrirEditorTiempos) return Promise.resolve();
  return (editorCargando ||= new Promise((ok, mal) => {
    const s = document.createElement("script");
    s.src = "editor.js"; s.onload = ok;
    s.onerror = () => { editorCargando = null; s.remove(); mal(new Error("No se pudo cargar el editor de tiempos. Revisa la conexión con el PC y vuelve a intentarlo.")); };
    document.head.append(s);
  }));
}
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
    if (!(await leerSesion()).autorizado) {
      if (animar()) await new Promise((hecho) => gsap.to("#app", { opacity: 0, duration: 0.22, ease: "power2.in", onComplete: hecho }));
      mostrarAcceso("login");
      return void window.gsap?.set("#app", { clearProps: "opacity" });
    }
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
    // Al salir de la vista el video se desconecta: el temporizador se detiene en vez de seguir despertando.
    clearInterval(v._tope); v._tope = setInterval(() => { if (!v.isConnected || (!isNaN(fin) && v.currentTime >= fin)) { v.pause(); clearInterval(v._tope); } }, 200);
    v.scrollIntoView({ behavior: "smooth", block: "center" });
  },
  diagnostico: intentar(async (b) => {
    b.disabled = true; $("#diag").innerHTML = `<p class="pequeno tenue">Comprobando (incluye un render de prueba de 2 s)…</p>`;
    try {
      const r = await api("/api/diagnostico?autoprueba=true");
      $("#diag").innerHTML = r.map((x) => h`<div class="dato"><span>${x.ok === true ? "✓" : x.ok === false ? "✗ Falla" : "– Opcional"} · ${x.nombre}</span><span class="${x.ok === false ? "error" : ""}">${x.detalle}</span></div>`).join("");
    } finally { b.disabled = false; }
  }),
  "editar-tiempos": intentar(async (b) => {          // web/editor.js
    b.disabled = true; b.lastChild.textContent = "Preparando…";
    try { await cargarEditor(); await abrirEditorTiempos(S.detalle); } finally { b.disabled = false; b.lastChild.textContent = "Editar tiempos"; }
  }),
  exportar: () => exportarClip(S.detalle),
  "regenerar-textos": accionTrabajo("regenerar-textos", "Regenerando textos."),
  retranscribir: intentar(async () => {
    if (!await confirmar("Volver a transcribir", `Whisper transcribirá de nuevo el audio con el contexto de transcripción del perfil «${nombrePerfil(S.detalle)}». Los subtítulos se rehacen (se pierden los cambios hechos a mano); el banner, el título y la descripción se conservan. Puede tardar unos minutos.`, "Volver a transcribir")) return;
    await accionTrabajo("retranscribir", "En cola para transcribir de nuevo.")();
  }),
  "restaurar-subtitulos": accionTrabajo("restaurar-subtitulos", "Subtítulos restaurados."),
  subir: intentar(async () => {
    const yt = S.estado.youtube;
    if (!await confirmar("Añadir a la cola de subida", `Se subirá en PRIVADO al canal «${yt.canal_nombre}» (${yt.canal_id}) cuando le toque según el ritmo de publicación: la próxima subida es ${horaSubida(S.estado.proxima_subida)}. Para no esperar, usa «Subir ahora».`, "Añadir a la cola")) return;
    await api(`/api/trabajos/${S.jid}/subir`, { method: "POST" }); avisar("En la cola de subida."); refrescar();
  }),
  // «Subir ahora»: primero en la cola y sin el ritmo del programa; la pausa por el límite de YouTube se respeta.
  "subir-ahora": intentar(async (b) => {
    const t = S.estado.trabajos.find((x) => x.id === (b.dataset.id || S.jid)), yt = S.estado.youtube, pausa = S.estado.subidas_pausadas_hasta;
    if (!t) return;
    const cuando = pausa ? `cuando termine la pausa de YouTube por su límite diario (${horaSubida(pausa)})` : "en cuanto termine lo que se está procesando";
    if (!await confirmar("Subir ahora", `«${t.nombre}» se subirá en PRIVADO al canal «${yt.canal_nombre}» (${yt.canal_id}) ${cuando}, sin esperar el ritmo de publicación.`, "Subir ahora en privado")) return;
    await api(`/api/trabajos/${t.id}/subir-ahora`, { method: "POST" });
    avisar(`«${t.nombre}» va primero en la cola de subida: sube ${cuando}.`); refrescar();
  }),
  "cancelar-subida": intentar(async (b) => {
    await api(`/api/trabajos/${b.dataset.id || S.jid}/cancelar-subida`, { method: "POST" });
    avisar("Quitado de la cola de subida: puedes editarlo o subirlo cuando quieras."); refrescar();
  }),
  "subir-todos": intentar(async () => {
    const yt = S.estado.youtube, todos = esperanSubir(), destinados = todos.filter((t) => t.publicar), pausa = S.estado.subidas_pausadas_hasta;
    if (!destinados.length) return avisar("No hay Shorts renderizados esperando subida.", true);
    const omitidos = todos.length - destinados.length;
    if (!await confirmar("Subir todos ahora", `Se subirán en PRIVADO al canal «${yt.canal_nombre}» (${yt.canal_id}) ${plural(destinados.length, "Short renderizado", "Shorts renderizados")}, del más antiguo al más reciente, sin esperar el ritmo de publicación.`
      + (omitidos ? ` Se ${omitidos === 1 ? "omite" : "omiten"} ${plural(omitidos, "clip importado", "clips importados")} como «no destinar a YouTube».` : "")
      + (pausa ? ` Ahora mismo YouTube tiene las subidas en pausa hasta ${horaSubida(pausa)}.` : "") + ` ${LIMITES_YOUTUBE}`, "Subir todos en privado")) return;
    const r = await api("/api/subir-todos", { method: "POST" });
    avisar(`${plural(r.encolados, "Short en cola", "Shorts en cola")} para subir en privado${r.pausa_hasta ? `, cuando termine la pausa de YouTube (${horaSubida(r.pausa_hasta)})` : ""}.`); refrescar();
  }),
  // Lista para elegir qué subir ahora (el Resumen propone el más antiguo).
  "elegir-subida": () => {
    const lista = esperanSubir(), yt = S.estado.youtube;
    abrirModal("Elegir qué subir ahora", h`<p>Shorts renderizados que aún no están en YouTube, del más antiguo al más reciente. Se suben en privado al canal «${yt.canal_nombre}».</p>
      <div class="lista-subir">${lista.map((t) => crudo(h`<div class="fila-subir"><span class="miniatura"><img src="/media/${t.id}/miniatura.jpg?v=${t.actualizado}" alt="" loading="lazy"></span>
        <span class="fila-subir-texto"><b>${t.nombre}</b><small>${t.textos.titulo || etiquetaOrigen(t)}</small>${t.publicar ? "" : crudo(`<small>Importado sin destinar a YouTube</small>`)}${t.subir_solicitado ? crudo(h`<small>${estadoSubida(t)}</small>`) : ""}</span>
        ${t.subir_ya ? crudo(`<span class="pastilla proceso">Primero en la cola</span>`) : crudo(h`<button class="primario" data-accion="subir-ahora" data-id="${t.id}">Subir ahora</button>`)}</div>`))}</div>`,
    `<button data-accion="cerrar-modal">Cerrar</button>`);
  },
  eliminar: intentar(async () => {
    if (!await confirmar("Eliminar el trabajo", "Se eliminará el trabajo y sus archivos intermedios de este PC. No borra nada de YouTube.", "Eliminar", true)) return;
    await api(`/api/trabajos/${S.jid}`, { method: "DELETE" }); location.hash = S.desde;
  }),
  pestana: (b) => { S.pestana = b.dataset.p; pintarAjustes($("#principal")); },
  "activar-perfil": intentar(async (b) => {
    cerrarMenuPerfiles(b.closest("#menu-perfiles") !== null);
    if (b.dataset.id === S.estado.perfil_activo) return;
    await api(`/api/perfiles/${b.dataset.id}/activar`, { method: "POST" });
    avisar(`Perfil activo: «${perfilPorId(b.dataset.id)?.nombre}». Los clips que importes desde ahora lo usarán; los ya importados conservan el suyo.`);
    await refrescar();
    // La maqueta muestra la firma y el logo del perfil activo; los cambios sin guardar de la plantilla se conservan.
    if (S.vista === "plantilla") $("#form-plantilla")?._perfil?.();
  }),
  "cerrar-perfiles": () => cerrarMenuPerfiles(),
  "regenerar-elegidos": intentar(() => regenerarVarios([...S.seleccion])),
  "regenerar-todos": intentar(() => regenerarVarios(null)),
  "quitar-seleccion": () => { S.seleccion.clear(); pintar(false); },
  "cerrar-lote": intentar(async () => { await api("/api/textos/lote", { method: "DELETE" }); refrescar(); }),
  "nuevo-perfil": () => editarPerfil(null),
  "editar-perfil": (b) => editarPerfil(S.perfiles.find((p) => p.id === b.dataset.id)),
  "duplicar-perfil": intentar(async (b) => {
    const r = await api(`/api/perfiles/${b.dataset.id}/duplicar`, { method: "POST" });
    avisar(`Creado «${r.nombre}». Edítalo para cambiar el nombre, la firma o el tema.`); await recargarPerfiles();
  }),
  "eliminar-perfil": intentar(async (b) => {
    const p = S.perfiles.find((x) => x.id === b.dataset.id), suyos = S.estado.trabajos.filter((t) => t.perfil === p.id), clips = suyos.length;
    const enProceso = suyos.filter((t) => ["procesando", "subiendo"].includes(t.estado)).length;
    if (enProceso) return avisar(`Hay ${plural(enProceso, "clip", "clips")} de «${p.nombre}» en proceso: espera a que terminen para eliminar el perfil.`, true);
    const texto = clips ? `Lo usan ${plural(clips, "clip", "clips")}. Esos clips guardan una copia de su nombre, firma, contexto y tema, así que no cambian; su logo propio se borra (si se renderizan de nuevo, usarán el logo general).`
      : "Ningún clip usa este perfil.";
    if (!await confirmar(`Eliminar «${p.nombre}»`, texto, "Eliminar perfil", true)) return;
    await api(`/api/perfiles/${p.id}${clips ? "?confirmar=true" : ""}`, { method: "DELETE" });
    avisar(`Perfil «${p.nombre}» eliminado.`); await recargarPerfiles();
  }),
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
  "logo-quitar": intentar(async () => { await api("/api/logo", { method: "DELETE" }); avisar("Logo general quitado."); const f = $("#form-plantilla"); f._logos(false); f._vista(); }),
  "logo-perfil-quitar": intentar(async () => {
    const p = perfilActivo();
    await api(`/api/perfiles/${p.id}/logo`, { method: "DELETE" }); await refrescar();
    avisar(`Logo de «${p.nombre}» quitado: usará el logo general.`); const f = $("#form-plantilla"); f._logos(); f._vista();
  }),
  "atajos-plantilla": () => abrirModal("Atajos de la plantilla", `<dl class="atajos">
      <dt><kbd>Ctrl</kbd> + <kbd>S</kbd></dt><dd>Guardar el diseño</dd>
      <dt><kbd>Ctrl</kbd> + <kbd>Z</kbd> / <kbd>Ctrl</kbd> + <kbd>Y</kbd></dt><dd>Deshacer / rehacer</dd>
      <dt><kbd>Alt</kbd> + <kbd>1</kbd> … <kbd>7</kbd></dt><dd>Ir a una sección (Encuadre … Perfiles)</dd>
      <dt>Flechas</dt><dd>Mover el elemento elegido en la maqueta (con <kbd>Mayús</kbd>, de 10 en 10)</dd>
      <dt><kbd>+</kbd> / <kbd>−</kbd></dt><dd>Agrandar o achicar el elemento elegido</dd>
      <dt><kbd>Esc</kbd></dt><dd>Soltar el elemento</dd></dl>`, `<button class="primario" data-accion="cerrar-modal">Entendido</button>`),
  "restablecer": intentar(async () => {
    if (!await confirmar("Restablecer la plantilla", "Todos los valores de la plantilla volverán a los iniciales y se guardarán. Tu logo no se toca.", "Restablecer", true)) return;
    const { defecto } = S.ajustes; const cambios = {};
    document.querySelectorAll("#form-plantilla [name]").forEach((i) => { cambios[i.name] = defecto[i.name]; });
    await api("/api/ajustes", { method: "PUT", json: cambios }); avisar("Plantilla restablecida."); pintarPlantilla($("#principal")); refrescar();
  }),
};

// ---------------------------------------------------------------- plantilla: secciones, vista previa y propiedades
// Cada campo es un ajuste real de config.py; la vista previa la dibuja el PC (/api/diseno/vista) con los valores del
// formulario, guardados o no. Sección: [id, nombre, icono, campos]; un texto entre los campos abre un grupo y
// {nota} añade una explicación.
// Campo: [clave, etiqueta, tipo = "number"].
const SECCIONES_PLANTILLA = [
  ["encuadre", "Encuadre", "recorte", [["estilo", "Estilo de encuadre", "estilo"],
    "Video", ["video_desplazamiento_y", "Desplazamiento vertical (px)"], ["video_alto_max", "Alto máximo (px)"],
    "Clip original", ["recortar_bordes", "Quitar franjas negras del clip original", "check"]]],
  ["banner", "Banner", "texto", ["Texto", ["banner_tamano", "Tamaño de letra"], ["banner_color", "Color del texto", "color"],
    "Tarjeta", ["banner_ancho", "Ancho"], ["banner_radio", "Redondeo de esquinas"], ["banner_separacion", "Separación del video"],
    "Gancho", { nota: "En la vista dividida (y en pantalla completa sin tarjeta) el banner aparece pequeño al inicio y se desvanece. La maqueta no lo anima: míralo en «Comparar en video»." },
    ["gancho", "Mostrar el banner de gancho", "check"], ["gancho_segundos", "Segundos en pantalla"], ["gancho_tamano", "Tamaño de letra"]]],
  ["subtitulos", "Subtítulos", "subtitulos", ["Texto", ["sub_tamano", "Tamaño"], ["sub_desplazamiento", "Distancia bajo el video"],
    "Bloques", ["sub_palabras_max", "Palabras por bloque"], ["sub_caracteres_max", "Caracteres por bloque"],
    "Palabra activa", ["sub_resaltar", "Resaltar en color la palabra que se está diciendo", "check"], ["sub_color_resalte", "Color", "color"]]],
  ["marca", "Logo y marca", "marca", ["Logo", ["mostrar_logo", "Mostrar logo", "check"], ["logo_alto", "Alto (px)"], ["logo_separacion", "Separación"],
    "Firma", ["mostrar_nombre", "Mostrar firma bajo el logo", "check"], ["nombre_tamano", "Tamaño"], ["nombre_color", "Color", "color"]]],
  ["completo", "Pantalla completa", "completo", ["Imagen", ["completo_zoom", "Zoom (%; 100 = sin zoom extra)"],
    "Banner", ["completo_banner", "Mostrar tarjeta del banner arriba", "check"], ["completo_banner_y", "Posición vertical"],
    "Subtítulos", ["completo_sub_y", "Posición vertical"], ["completo_sub_tamano", "Tamaño"], ["completo_mayusculas", "En mayúsculas (también en vista dividida)", "check"],
    "Logo", ["completo_logo_y", "Posición vertical"], ["completo_logo_alto", "Alto (px)"]]],
  ["dividido", "Vista dividida", "dividido", ["Cámara", ["dividido_proporcion", "Alto (% del video)"],
    "Banner", ["dividido_banner", "Mostrar tarjeta del banner", "check"],
    "Subtítulos", ["dividido_sub_y", "Posición vertical"], ["dividido_sub_tamano", "Tamaño"],
    "Logo", ["dividido_logo_y", "Posición vertical"], ["dividido_logo_alto", "Alto (px)"], ["dividido_firma", "Mostrar firma bajo el logo", "check"]]],
  ["perfiles", "Perfiles", "perfil", []],
];
// Nombre de cada ajuste con su grupo («Banner: posición vertical»): lo dicen el editor visual y el lector de pantalla.
const NOMBRE_AJUSTE = Object.fromEntries(SECCIONES_PLANTILLA.flatMap(([, , , campos]) => {
  let grupo = "";
  return campos.flatMap((c) => (typeof c === "string" ? ((grupo = c), []) : c.nota ? [] : [[c[0], grupo ? `${grupo}: ${c[1][0].toLowerCase()}${c[1].slice(1)}` : c[1]]]));
}));
const NOMBRE_ESTILO = { auto: "Automático: el mejor encuadre para cada clip", clasico: "Clásico: video completo con tarjeta", completo: "Pantalla completa con seguimiento",
  dividido: "Vista dividida: cámara arriba, contenido abajo" };
const ESTILOS_PLANTILLA = [["auto", "Automático", "El mejor encuadre para cada clip"], ["clasico", "Clásico", "Video completo con tarjeta"],
  ["completo", "Pantalla completa", "Recorte 9:16 que sigue los rostros"], ["dividido", "Vista dividida", "Cámara arriba, contenido abajo"]];
const NOMBRE_CORTO = Object.fromEntries(ESTILOS_PLANTILLA);
const COLORES_PLANTILLA = [["#E3222A", "Rojo"], ["#53FC18", "Verde Kick"], ["#FFD400", "Amarillo"], ["#FF7A00", "Naranjo"],
  ["#2F9BFF", "Azul"], ["#B04BFF", "Morado"], ["#FFFFFF", "Blanco"], ["#111111", "Negro"]];
const MUESTRAS_CMP = ["clasico", "completo", "dividido", "auto"];        // tarjetas de «Comparar en video»

// Un número con límites lleva deslizador (para el dedo o el ratón) y su valor editable (el teclado usa el número).
const campoPlantilla = ([k, n, tipo = "number"], v, lim) => {
  if (tipo === "check") return h`<label class="linea"><input type="checkbox" role="switch" name="${k}" ${v[k] ? "checked" : ""}> ${n}</label>`;
  if (tipo === "estilo") return h`<fieldset class="estilos"><legend>${n}</legend>${ESTILOS_PLANTILLA.map(([x, t, d]) => crudo(h`<label class="estilo-op">
      <input type="radio" name="${k}" value="${x}" ${x === v[k] ? "checked" : ""}><span><b>${t}</b><small>${d}</small></span></label>`))}</fieldset>`;
  if (tipo === "color") {
    const actual = String(v[k]).toLowerCase();
    return h`<fieldset class="color-campo"><legend>${n}</legend><div class="muestras-color">${COLORES_PLANTILLA.map(([c, nombre]) => crudo(h`<button type="button"
        class="muestra-color" style="--c:${c}" data-color="${c.toLowerCase()}" data-para="${k}" aria-pressed="${c.toLowerCase() === actual}" title="${nombre}" aria-label="${nombre}"></button>`))}
      <input type="color" name="${k}" value="${actual}" aria-label="${n}: otro color"><input class="hex" data-hex="${k}" value="${actual.toUpperCase()}" maxlength="7" spellcheck="false" autocomplete="off" aria-label="${n}: código del color"></div></fieldset>`;
  }
  const r = lim?.[k];
  if (!r) return h`<label>${n}<input name="${k}" type="number" value="${v[k]}"></label>`;
  return h`<div class="deslizador"><label for="pl-${k}">${n}</label><div class="fila-deslizador">
      <input type="range" data-par="${k}" min="${r[0]}" max="${r[1]}" value="${v[k]}" tabindex="-1" aria-hidden="true">
      <input id="pl-${k}" name="${k}" type="number" min="${r[0]}" max="${r[1]}" value="${v[k]}"></div></div>`;
};

async function pintarPlantilla(m) {
  let a;
  try { a = S.ajustes = await api("/api/ajustes"); } catch (e) {
    if ($(".esqueleto", m)) m.innerHTML = `<div class="panel sin-nada" role="alert">No se pudo cargar la plantilla. Vuelve a entrar en Plantilla para reintentar.</div>`;
    return avisar(e.message, true);
  }
  if (S.vista !== "plantilla") return;     // se cambió de vista mientras llegaban los datos
  const v = a.valores;
  let activa = "encuadre";
  try { const g = localStorage.getItem("fabrica.plantilla.seccion"); if (SECCIONES_PLANTILLA.some(([id]) => id === g)) activa = g; } catch (e) { /* sin almacenamiento: la primera */ }
  const extra = {
    encuadre: `<p class="pequeno tenue" id="pl-auto-nota"></p>`,
    banner: `<label>Texto de ejemplo (solo para esta vista previa; no se guarda)<input id="pl-banner" maxlength="64" value="ASÍ SE VERÁ TU BANNER"></label>`,
    marca: `<p class="pequeno tenue" id="pl-firma-nota"></p><div class="logos" id="pl-logos"></div>`,
    completo: `<p class="nota pl-uso" id="pl-uso-completo"></p>`, dividido: `<p class="nota pl-uso" id="pl-uso-dividido"></p>`,
    perfiles: `<div class="pila" id="pl-perfiles"></div>`,
  };
  const pieza = (c) => (typeof c === "string" ? h`<h3 class="pl-grupo">${c}</h3>` : c.nota ? h`<p class="pequeno tenue">${c.nota}</p>` : campoPlantilla(c, v, a.limites));
  const seccion = ([id, nombre, , campos]) => h`<section class="pl-seccion" data-seccion="${id}" aria-labelledby="pl-t-${id}" ${id === activa ? "" : crudo("hidden")}>
      <h2 id="pl-t-${id}" tabindex="-1">${nombre}</h2>${crudo(extra[id] || "")}${campos.map((c) => crudo(pieza(c)))}</section>`;
  const reproducir = calma.matches ? "controls" : "autoplay";      // con «reducir movimiento», las muestras no arrancan solas
  m.innerHTML = h`<form id="form-plantilla"><div class="cabecera"><div><div class="antetitulo">Identidad del canal</div><h1>Tu plantilla</h1><p>Un formato reconocible en todos tus clips.</p></div>
      <div class="fila"><span class="pastilla" id="pl-estado" role="status"></span><button type="button" class="texto" data-accion="atajos-plantilla">Atajos</button>
        <button type="button" class="texto" data-accion="restablecer">Restablecer</button><button class="primario" aria-keyshortcuts="Control+S">${ic("check")}Guardar diseño</button></div></div>
    <div class="pl-marco">
      <nav class="pl-nav" aria-label="Secciones de la plantilla">${SECCIONES_PLANTILLA.map(([id, nombre, icono], i) => crudo(h`<button type="button" data-seccion="${id}" aria-keyshortcuts="Alt+${i + 1}">${ic(icono)}<span>${nombre}</span></button>`))}</nav>
      <div class="panel pl-centro">
        <div class="pl-modos"><div class="segmentado" role="tablist" aria-label="Vista previa">
            <button type="button" role="tab" id="pl-m-diseno" aria-controls="pl-diseno" aria-selected="true">Diseño</button><button type="button" role="tab" id="pl-m-comparar" aria-controls="pl-comparar" aria-selected="false" tabindex="-1">Comparar en video</button></div>
          <div class="fila pl-historial"><button type="button" class="icono-boton" id="pl-deshacer" aria-label="Deshacer" title="Deshacer (Ctrl+Z)" disabled>${ic("deshacer")}</button><button type="button" class="icono-boton" id="pl-rehacer" aria-label="Rehacer" title="Rehacer (Ctrl+Y)" disabled>${ic("rehacer")}</button></div></div>
        <div id="pl-diseno" class="pl-vista" role="tabpanel" aria-labelledby="pl-m-diseno"><p class="pl-vista-de" id="pl-vista-de"></p>
          <div class="formato-escena"><div class="pl-lienzo"><img id="pl-img" alt="Maqueta del Short con los valores del formulario" width="540" height="960">
            <div class="pl-capa" id="pl-capa" role="group" aria-label="Elementos de la plantilla"><i class="pl-guia h" hidden></i><i class="pl-guia v" hidden></i><i class="pl-guia v" hidden></i></div></div></div>
          <p class="error" id="pl-error" role="alert"></p><p class="pl-avisos" id="pl-avisos"></p><p class="solo-lector" id="pl-lector" role="status"></p>
          <div class="panel-pie"><span>Toca un elemento y arrástralo. Con teclado: flechas para mover (con Mayús, de 10 en 10), + y − para el tamaño, Esc para soltar.</span></div></div>
        <div id="pl-comparar" class="pl-comparar" role="tabpanel" aria-labelledby="pl-m-comparar" hidden>
          <div class="cmp-cabeza"><label>Clip de ejemplo<select id="cmp-clip" disabled><option>Cargando tus clips…</option></select></label>
            <div class="cmp-avance" role="status"><span id="cmp-texto"></span><span class="barra-progreso" id="cmp-barra" hidden><i style="transform:scaleX(0)"></i></span></div></div>
          <div class="cmp-rejilla" id="cmp-rejilla">${MUESTRAS_CMP.map((e) => crudo(h`<div class="cmp-tarjeta" data-estilo="${e}" data-fase="en_espera" role="group" aria-label="${NOMBRE_CORTO[e]}">
              <p class="cmp-titulo"><b>${NOMBRE_CORTO[e]}</b><small></small></p>
              <div class="cmp-video"><video muted loop playsinline preload="auto" ${crudo(reproducir)} aria-label="Muestra en video: ${NOMBRE_CORTO[e]}"></video><span class="cmp-fase"></span>
                <button type="button" class="cmp-usar" data-usar="${e}">Usar este estilo</button></div></div>`))}</div>
          <ul class="cmp-notas" id="cmp-notas"></ul>
          <p class="pequeno tenue">Muestras de 6 s en baja calidad (540×960) hechas en este PC con los valores de la plantilla, guardados o no. El Short de verdad no cambia.</p></div>
      </div>
      <aside class="panel pl-props" aria-label="Propiedades de la sección">${SECCIONES_PLANTILLA.map((s) => crudo(seccion(s)))}</aside>
    </div></form>`;

  const f = $("#form-plantilla"), img = $("#pl-img"), panel = $("#pl-diseno"), estado = $("#pl-estado"), error = $("#pl-error"), capa = $("#pl-capa");
  const valores = () => {
    const c = {};
    f.querySelectorAll("[name]").forEach((i) => { if (i.type !== "radio" || i.checked) c[i.name] = i.type === "checkbox" ? i.checked : i.value; });
    return c;
  };
  // Al cambiar un valor por código (deshacer, editor visual, muestras de color) se ponen al día su deslizador y su código.
  const alDia = (k) => {
    const x = String(f.elements[k].value), r = f.querySelector(`[data-par="${k}"]`), hx = f.querySelector(`[data-hex="${k}"]`);
    if (r) r.value = x;
    if (hx && document.activeElement !== hx) hx.value = x.toUpperCase();
    f.querySelectorAll(`[data-para="${k}"]`).forEach((b) => b.setAttribute("aria-pressed", b.dataset.color === x.toLowerCase()));
  };
  const escribir = (cambios) => Object.entries(cambios).forEach(([k, x]) => {
    const i = f.elements[k];
    if (i.type === "checkbox") i.checked = x; else i.value = x;
    alDia(k);
  });
  const decir = (texto) => { $("#pl-lector").textContent = texto; };            // para lectores de pantalla
  let guardado = JSON.stringify(valores());
  const marcar = (recien = false) => {
    const sucio = S.sucio = JSON.stringify(valores()) !== guardado;             // deshacer hasta lo guardado quita el aviso
    estado.className = `pastilla ${sucio ? "listo" : "subido"} ${recien ? "recien" : ""}`;
    estado.innerHTML = sucio ? "Cambios sin guardar" : recien ? `${icono("check")}Guardado` : "";
  };

  // ---- Secciones. La maqueta enseña el encuadre de la sección que se edita (pantalla completa o dividida).
  const estiloVista = () => ({ completo: "completo", dividido: "dividido" })[activa] || f.elements.estilo.value;
  const notasEstilo = () => {
    const e = f.elements.estilo.value, ev = estiloVista();
    $("#pl-auto-nota").textContent = e === "auto" ? "Cada clip elige al renderizar entre cámara arriba y contenido abajo, dos personas en pantalla dividida, pantalla completa siguiendo al protagonista o el clásico. En «Comparar en video» ves qué elige con un clip tuyo." : "";
    for (const s of ["completo", "dividido"]) {
      const nota = $(`#pl-uso-${s}`);
      nota.hidden = [s, "auto"].includes(e);
      nota.textContent = `Se usa con «${NOMBRE_CORTO[s]}» y con «Automático»; ahora el estilo es «${NOMBRE_CORTO[e]}». La maqueta muestra este encuadre mientras editas esta sección.`;
    }
    $("#pl-vista-de").textContent = `Maqueta: ${NOMBRE_CORTO[ev === "auto" ? "clasico" : ev]}${ev !== e ? " (el encuadre de esta sección)" : e === "auto" ? " (Automático cambia según el clip)" : ""}`;
    f.querySelectorAll(".cmp-tarjeta").forEach((t) => {
      const si = t.dataset.estilo === e, b = $(".cmp-usar", t);
      t.classList.toggle("en-uso", si); b.disabled = si; b.textContent = si ? "Estilo elegido" : "Usar este estilo";
    });
  };
  function irSeccion(id, enfocar = false) {
    const antes = estiloVista();
    activa = id;
    f.querySelectorAll(".pl-nav [data-seccion]").forEach((b) => {
      const si = b.dataset.seccion === id;
      b.classList.toggle("activa", si);
      if (si) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current");
    });
    f.querySelectorAll(".pl-seccion").forEach((s) => { s.hidden = s.dataset.seccion !== id; });
    try { localStorage.setItem("fabrica.plantilla.seccion", id); } catch (e) { /* no se recuerda entre visitas */ }
    if (id === "perfiles") pintarPerfilesPl();
    if (enfocar) $(`#pl-t-${id}`).focus({ preventScroll: true });
    notasEstilo();
    if (estiloVista() !== antes) vista();
    const sec = $(`.pl-seccion[data-seccion="${id}"]`);
    if (animar()) gsap.from(sec, { y: 6, opacity: 0, duration: 0.2, ease: "power2.out", clearProps: "transform,opacity" });
  }

  // ---- Logos (general y del perfil activo) y perfiles.
  let logoGeneral = a.logo_propio, version = Date.now();
  function pintarLogos(recorte = null) {
    const p = perfilActivo();
    $("#pl-firma-nota").innerHTML = h`Nombre y firma: del perfil activo «${p?.nombre}» (${p?.firma || "sin firma: se usa el nombre"}). Se cambian en <a href="#perfiles">Perfiles</a>.`;
    const caja = (titulo, texto, src, entrada, quitar) => h`<div class="logo-caja"><span class="logo-muestra">${src ? crudo(h`<img src="${src}" alt="">`) : crudo(`<small>Sin logo</small>`)}</span>
      <div class="pila"><div><b>${titulo}</b><small>${texto}</small></div><div class="fila"><label class="boton">${ic("subir")}Subir…<input type="file" id="${entrada}" accept="image/png,image/webp,image/jpeg" hidden></label>
        ${src ? crudo(h`<button type="button" data-accion="${quitar}">Quitar</button>`) : ""}</div></div></div>`;
    $("#pl-logos").innerHTML = caja("Logo general", logoGeneral ? "Lo usan los perfiles sin logo propio." : "Sin logo general: los perfiles sin logo propio muestran el rótulo «KICK». Sube el logo oficial en PNG transparente si tienes permiso para usarlo.",
      logoGeneral ? `/api/logo?v=${version}` : "", "logo", "logo-quitar")
      + (p ? caja(`Logo de «${p.nombre}»`, p.logo ? "Solo para los clips de este perfil; es el que muestra la maqueta." : "Este perfil usa el logo general.",
        p.logo ? `/api/perfiles/${p.id}/logo?v=${p.v}` : "", "logo-perfil", "logo-perfil-quitar") : "")
      + (recorte ? h`<p class="pequeno tenue" role="status">${recorte.antes.join("×") === recorte.despues.join("×") ? `La imagen no tenía márgenes que quitar (${recorte.despues.join("×")} px).`
        : `Márgenes quitados: ${recorte.antes.join("×")} → ${recorte.despues.join("×")} px.`}</p>` : "");
  }
  function pintarPerfilesPl() {
    const activo = S.estado.perfil_activo;
    $("#pl-perfiles").innerHTML = h`<p class="pequeno tenue">La maqueta usa el nombre, la firma y el logo del perfil activo. Cada clip conserva el perfil con el que se importó; las muestras en video usan el del clip.</p>
      <ul class="pl-lista-perfiles">${S.estado.perfiles.map((p) => crudo(h`<li>${crudo(avatarPerfil(p))}<div><b>${p.nombre}</b><small>${p.firma || "Sin firma"} · ${p.logo ? "logo propio" : "logo general"}</small>
          ${p.estilo ? crudo(h`<small class="alerta">Sus clips usan siempre «${NOMBRE_CORTO[p.estilo] || p.estilo}»: el estilo de la plantilla no se les aplica.</small>`) : ""}</div>
        ${p.id === activo ? crudo(`<span class="pastilla subido">Activo</span>`) : crudo(h`<button type="button" data-accion="activar-perfil" data-id="${p.id}">Activar</button>`)}</li>`))}</ul>
      <a class="boton" href="#perfiles">${ic("perfil")}Editar perfiles</a>`;
  }

  // ---- Historial de la sesión: cada entrada guarda solo los campos que cambiaron (formulario o editor visual).
  let ultimo = valores(), hist = [], pos = 0, espera;
  const botones = () => { $("#pl-deshacer").disabled = !pos; $("#pl-rehacer").disabled = pos === hist.length; };
  const registrar = () => {
    const ahora = valores(), antes = {}, despues = {};
    for (const k in ahora) if (ahora[k] !== ultimo[k]) { antes[k] = ultimo[k]; despues[k] = ahora[k]; }
    if (Object.keys(antes).length) { hist.length = pos; hist.push({ antes, despues }); pos++; }
    ultimo = ahora; botones();
  };
  // Tras cualquier cambio: aviso de «sin guardar» y, después de una pausa, historial, maqueta y muestras nuevas.
  const cambio = (pausa = 250) => {
    marcar(); notasEstilo();
    clearTimeout(espera); espera = setTimeout(() => { registrar(); vista(); pedirMuestras(); }, pausa);
  };
  const historia = (atras) => {
    clearTimeout(espera); registrar();                    // un cambio aún sin anotar entra antes al historial
    if (atras ? !pos : pos === hist.length) return;
    const e = atras ? hist[--pos] : hist[pos++];
    escribir(atras ? e.antes : e.despues); ultimo = valores(); botones();
    decir(atras ? "Cambio deshecho." : "Cambio rehecho.");
    marcar(); notasEstilo(); vista(); pedirMuestras();
  };
  $("#pl-deshacer").onclick = () => historia(true); $("#pl-rehacer").onclick = () => historia(false);

  // ---- Maqueta y disposición: se piden juntas y solo se muestra la respuesta de la última petición.
  let turno = 0, elementos = [], lienzo = { w: 1080, h: 1920 }, sel = null, arr = null;
  const pedir = async (ruta, q) => {
    const r = await fetch(`/api/diseno/${ruta}?${q}`);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `Error ${r.status}`);
    return r;
  };
  const vista = async () => {
    const n = ++turno, q = new URLSearchParams({ ...valores(), estilo: estiloVista(), banner: $("#pl-banner").value });
    panel.classList.add("cargando");
    try {
      const [imagen, d] = await Promise.all([pedir("vista", q).then((r) => r.blob()), pedir("disposicion", q).then((r) => r.json())]);
      if (n !== turno || !img.isConnected) return;
      img.onload = () => URL.revokeObjectURL(img.src);
      img.src = URL.createObjectURL(imagen);
      await img.decode().catch(() => {});                  // imagen y marcos cambian en el mismo cuadro
      if (n !== turno) return;
      error.textContent = ""; $("#pl-avisos").textContent = (d.avisos || []).join(" ");
      lienzo = d.lienzo; pintarCapa(d.elementos);
    } catch (e) { if (n === turno) error.textContent = e.message; }
    if (n === turno) panel.classList.remove("cargando");
  };

  // ---- Capa interactiva. Reglas del servidor por elemento: mover, tamano y ancho = {ajuste, signo, valor, min, max}.
  const pct = (v, total) => `${(v / total) * 100}%`;
  const escala = () => capa.clientWidth / lienzo.w;        // px de pantalla por px del lienzo
  const deId = (id) => elementos.find((x) => x.id === id);
  const marcos = () => [...capa.querySelectorAll(".pl-el")];
  const limitar = (r, v) => Math.min(r.max ?? Infinity, Math.max(r.min ?? -Infinity, Math.round(v)));
  const caja = (b, c) => Object.assign(b.style, { left: pct(c.x, lienzo.w), top: pct(c.y, lienzo.h), width: pct(c.w, lienzo.w), height: pct(c.h, lienzo.h), transform: "" });
  const [guiaH, ...guiasV] = capa.querySelectorAll(".pl-guia");
  const guias = (y, xs = []) => {
    guiaH.hidden = y == null; if (y != null) guiaH.style.top = pct(y, lienzo.h);
    guiasV.forEach((g, i) => { g.hidden = xs[i] == null; if (xs[i] != null) g.style.left = pct(xs[i], lienzo.w); });
  };
  const seleccionar = (id, foco = false) => {
    sel = id;
    marcos().forEach((b) => { const si = b.dataset.id === id; b.classList.toggle("sel", si); b.setAttribute("aria-pressed", si); if (si && foco) b.focus({ preventScroll: true }); });
  };
  function pintarCapa(nuevos) {
    const antes = new Map(marcos().map((b) => [b.dataset.id, b.getBoundingClientRect()])), conFoco = capa.contains(document.activeElement);
    elementos = nuevos; arr = null; guias(null);
    marcos().forEach((b) => b.remove());
    // Los más grandes primero: los pequeños quedan encima y se pueden tocar.
    [...nuevos].sort((a, b) => b.caja.w * b.caja.h - a.caja.w * a.caja.h).forEach((el) => {
      const b = document.createElement("button");
      b.type = "button"; b.className = "pl-el"; b.dataset.id = el.id; caja(b, el.caja);
      b.setAttribute("aria-label", `${el.nombre}. ${["mover", "tamano", "ancho"].filter((r) => el[r]).map((r) => `${NOMBRE_AJUSTE[el[r].ajuste]}: ${el[r].valor}`).join(". ")}`);
      b.innerHTML = h`<span class="pl-etiqueta">${el.nombre}</span>${el.tamano ? crudo(`<i class="pl-tirador esquina" data-modo="tamano"></i>`) : ""}${el.ancho ? crudo(`<i class="pl-tirador lado" data-modo="ancho"></i>`) : ""}`;
      capa.append(b);
    });
    seleccionar(deId(sel) ? sel : null, conFoco);
    // Cada marco viaja desde donde estaba (donde se soltó, o su sitio anterior al deshacer) hasta donde lo dejó el motor.
    if (animar()) marcos().forEach((b) => {
      const o = antes.get(b.dataset.id), r = b.getBoundingClientRect();
      if (o && (Math.abs(o.top - r.top) > 0.5 || Math.abs(o.height - r.height) > 0.5 || Math.abs(o.width - r.width) > 0.5)) {
        gsap.from(b, { x: o.left - r.left, y: o.top - r.top, scaleX: o.width / r.width, scaleY: o.height / r.height, transformOrigin: "0 0", duration: 0.28, ease: "power3.out", clearProps: "transform,transformOrigin" });
      }
    });
  }
  // Mueve solo los marcos (nada se pide al servidor hasta soltar). dx y dy en px del lienzo.
  function arrastrar(dx, dy) {
    const { b, el, modo, grupo } = arr, r = el[modo], c = el.caja, iman = 6 / escala();
    let nuevo, linea = null;
    if (modo === "mover") {
      // Imán: centro del lienzo y bordes de los demás elementos.
      const lineas = [lienzo.h / 2, ...elementos.filter((o) => o.mover?.ajuste !== r.ajuste).flatMap((o) => [o.caja.y, o.caja.y + o.caja.h])];
      const bordes = [c.y, c.y + c.h / 2, c.y + c.h];
      let mejor = iman + 1;
      for (const bo of bordes) for (const l of lineas) if (Math.abs(l - bo - dy) < Math.abs(mejor)) { mejor = l - bo - dy; linea = l; }
      if (Math.abs(mejor) <= iman) dy += mejor;
      nuevo = limitar(r, r.valor + r.signo * dy);
      dy = (nuevo - r.valor) * r.signo;                    // lo que de verdad permite el rango del ajuste
      grupo.forEach((o) => { o.style.transform = `translateY(${dy * escala()}px)`; });
      guias(bordes.some((bo) => Math.abs(bo + dy - linea) < 1) ? linea : null);
    } else if (modo === "tamano") {
      // El alto máximo del video es su propio alto; los demás tamaños crecen en proporción a la caja.
      nuevo = limitar(r, el.id === "video" ? c.h + dy : r.valor * (c.h + dy) / c.h);
      // El banner (su ancho es otro ajuste) y el video (ya ocupa el ancho) solo crecen en alto; el resto, en proporción.
      const factor = el.id === "video" ? nuevo / c.h : nuevo / r.valor, w = el.ancho || el.id === "video" ? c.w : c.w * factor;
      caja(b, { x: c.x + (c.w - w) / 2, y: c.y, w, h: c.h * factor });
    } else {
      let w = c.w + 2 * dx;                                // centrado: crece hacia los dos lados
      const ancla = [lienzo.w, ...elementos.filter((o) => o !== el).map((o) => o.caja.w)].find((a) => Math.abs(a - w) <= iman);
      if (ancla) w = ancla;
      nuevo = limitar(r, r.valor + w - c.w); w = c.w + nuevo - r.valor;
      caja(b, { ...c, x: c.x + (c.w - w) / 2, w });
      guias(null, ancla === w ? [(lienzo.w - w) / 2, (lienzo.w + w) / 2] : []);
    }
    arr.nuevo = nuevo;
    $(".pl-etiqueta", b).textContent = `${el.nombre} · ${NOMBRE_AJUSTE[r.ajuste].toLowerCase()} ${nuevo}`;
  }
  function soltar(aplicar) {
    if (!arr) return;
    const { b, el, modo, nuevo, grupo } = arr, r = el[modo];
    arr = null; b.classList.remove("arrastra"); guias(null);
    $(".pl-etiqueta", b).textContent = el.nombre;
    if (aplicar && nuevo !== r.valor) {                    // el marco se queda donde se soltó hasta que llega la disposición real
      escribir({ [r.ajuste]: nuevo }); decir(`${el.nombre}. ${NOMBRE_AJUSTE[r.ajuste]}: ${nuevo}`);
      return cambio(0);
    }
    grupo.forEach((o) => caja(o, deId(o.dataset.id).caja));
  }
  capa.addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".pl-el");
    if (!b) return seleccionar(null);
    const el = deId(b.dataset.id), modo = e.target.dataset.modo || "mover", yaElegido = sel === el.id;
    seleccionar(el.id, true);
    // Con el dedo, el primer toque solo selecciona (así se puede seguir desplazando la página sobre la maqueta).
    if (e.button || !el[modo] || (e.pointerType === "touch" && !yaElegido)) return;
    e.preventDefault(); b.setPointerCapture(e.pointerId); b.classList.add("arrastra");
    arr = { b, el, modo, x: e.clientX, y: e.clientY, nuevo: el[modo].valor, grupo: modo === "mover" ? marcos().filter((o) => deId(o.dataset.id).mover?.ajuste === el.mover.ajuste) : [b] };
  });
  capa.addEventListener("pointermove", (e) => { if (arr) arrastrar((e.clientX - arr.x) / escala(), (e.clientY - arr.y) / escala()); });
  capa.addEventListener("pointerup", () => soltar(true));
  capa.addEventListener("pointercancel", () => soltar(false));
  capa.addEventListener("focusin", (e) => { const b = e.target.closest(".pl-el"); if (b && sel !== b.dataset.id) seleccionar(b.dataset.id); });
  capa.addEventListener("keydown", (e) => {
    const el = deId(sel);
    if (!el) return;
    if (e.key === "Escape") { if (arr) soltar(false); else { seleccionar(null); document.activeElement.blur(); } return; }
    const paso = e.shiftKey ? 10 : 1;
    const [modo, d] = { ArrowUp: ["mover", -paso], ArrowDown: ["mover", paso], ArrowLeft: ["ancho", -paso], ArrowRight: ["ancho", paso], "+": ["tamano", 2], "=": ["tamano", 2], "-": ["tamano", -2] }[e.key] || [];
    if (!modo || !el[modo] || arr || e.ctrlKey || e.metaKey) return;
    e.preventDefault();
    // Se acumula sobre el valor del formulario: varias pulsaciones seguidas valen aunque la maqueta aún no haya vuelto.
    const r = el[modo], actual = +f[r.ajuste].value, nuevo = limitar(r, actual + (modo === "mover" ? r.signo * d : d));
    if (nuevo === actual) return decir(`${NOMBRE_AJUSTE[r.ajuste]}: ${actual}. No admite más.`);
    escribir({ [r.ajuste]: nuevo }); decir(`${NOMBRE_AJUSTE[r.ajuste]}: ${nuevo}`);
    if (modo === "mover") marcos().filter((o) => deId(o.dataset.id).mover?.ajuste === r.ajuste).forEach((o) => { o.style.transform = `translateY(${(nuevo - r.valor) * r.signo * escala()}px)`; });
    cambio();
  });

  // ---- Comparar en video (muestras.py): 6 s de un clip real por estilo, con los valores del formulario sin guardar.
  // El PC las hace de a una en segundo plano y las guarda por huella: un cambio solo rehace la muestra afectada.
  const cmp = { abierta: false, n: 0, firma: "", reloj: 0, clips: null }, rejilla = $("#cmp-rejilla");
  const enCurso = (e) => ["preparando", "analizando", "generando"].includes(e.fase);
  async function abrirComparar() {
    if (!cmp.clips) {
      try {
        const e = await api("/api/diseno/muestras?clips=1");
        if (!f.isConnected) return;
        cmp.clips = e.clips;
        const elegir = $("#cmp-clip"), hecho = (c) => ["renderizado", "subiendo", "publicado"].includes(c.estado);
        if (!e.clips.length) {
          elegir.innerHTML = `<option>Sin clips todavía</option>`;
          $("#cmp-texto").textContent = "Aún no hay clips para usar de ejemplo: importa uno y, cuando esté listo, vuelve aquí.";
          return;
        }
        elegir.innerHTML = e.clips.map((c, i) => h`<option value="${c.id}">${c.nombre}${c.titulo ? ` · ${c.titulo}` : ""}${i === 0 && hecho(c) ? " (el último renderizado)" : ""}</option>`).join("");
        elegir.value = e.clips.some((c) => c.id === e.clip?.id) ? e.clip.id : e.clips[0].id;
        elegir.disabled = false;
      } catch (err) { $("#cmp-texto").textContent = err.message; return; }
    }
    cmp.firma = ""; pedirMuestras();
  }
  async function pedirMuestras() {
    if (!cmp.abierta || !cmp.clips?.length) return;
    const val = valores(), clip = $("#cmp-clip").value, firma = JSON.stringify([clip, val]);
    if (firma === cmp.firma) return;
    cmp.firma = firma;
    try { pintarMuestras(await api("/api/diseno/muestras", { method: "POST", json: { clip, valores: val } })); }
    catch (err) { cmp.firma = ""; $("#cmp-texto").textContent = err.message; return; }
    seguirMuestras();
  }
  function seguirMuestras() {
    clearTimeout(cmp.reloj);
    cmp.reloj = setTimeout(async () => {
      if (!cmp.abierta || !f.isConnected) return;
      try { const e = await api("/api/diseno/muestras"); pintarMuestras(e); if (enCurso(e)) seguirMuestras(); } catch (err) { seguirMuestras(); }
    }, 800);
  }
  function pintarMuestras(e) {
    if (e.n < cmp.n || !f.isConnected) return;
    cmp.n = e.n;
    const ms = e.muestras || {}, todas = Object.values(ms), listas = todas.filter((x) => x.estado === "lista").length;
    // «Automático» y una «Vista dividida» imposible con este clip muestran el video del estilo en que terminan.
    const de = { clasico: "clasico", completo: "completo", dividido: e.dividido?.estilo || "dividido", auto: e.auto?.estilo || "" };
    $("#cmp-texto").textContent = e.fase === "error" ? e.error : e.fase === "generando" ? `Generando muestras: ${listas} de ${todas.length} listas…`
      : e.fase === "lista" ? `Muestras listas de «${e.clip.nombre}», desde el segundo ${Math.floor(e.inicio)}.` : e.texto || "";
    $("#cmp-texto").classList.toggle("error", e.fase === "error");
    $("#cmp-barra").hidden = !enCurso(e);
    $("#cmp-barra i").style.transform = `scaleX(${todas.length ? listas / todas.length : 0})`;
    rejilla.querySelectorAll(".cmp-tarjeta").forEach((t) => {
      const s = ms[de[t.dataset.estilo]] || {}, video = $("video", t);
      if (s.url && video.dataset.url !== s.url) { video.dataset.url = s.url; video.src = s.url; }
      t.dataset.fase = s.estado || "en_espera";
      $(".cmp-fase", t).textContent = { en_espera: "En cola", generando: "Generando…", error: "No se pudo hacer" }[s.estado] || (s.estado ? "" : "En cola");
      if (s.estado === "error") $(".cmp-fase", t).title = s.error;
      $(".cmp-titulo small", t).textContent = t.dataset.estilo === "auto" && e.auto ? `elige ${NOMBRE_CORTO[e.auto.estilo]}`
        : t.dataset.estilo === "dividido" && e.dividido?.estilo === "completo" ? "sale en pantalla completa" : "";
    });
    $("#cmp-notas").innerHTML = [e.auto && h`<li><b>Automático</b> elige «${NOMBRE_CORTO[e.auto.estilo]}» para este clip: ${e.auto.motivo}.</li>`,
      e.dividido?.motivo && h`<li><b>Vista dividida</b>: ${e.dividido.motivo}.</li>`, e.aviso && h`<li>${e.aviso}</li>`,
      ...todas.filter((x) => x.estado === "error").map((x) => h`<li class="error">${x.error}</li>`)].filter(Boolean).join("");
  }
  // Las muestras se ven a la vez: cuando llega una nueva, todas vuelven al principio.
  rejilla.addEventListener("loadeddata", () => {
    if (calma.matches) return;
    rejilla.querySelectorAll("video").forEach((x) => { if (x.readyState >= 2) { x.currentTime = 0; x.play().catch(() => {}); } });
  }, true);
  const ponerModo = (comparar) => {
    cmp.abierta = comparar;
    [["#pl-m-diseno", !comparar], ["#pl-m-comparar", comparar]].forEach(([s, si]) => { $(s).setAttribute("aria-selected", si); $(s).tabIndex = si ? 0 : -1; });
    $("#pl-diseno").hidden = comparar; $("#pl-comparar").hidden = !comparar;
    rejilla.querySelectorAll("video").forEach((x) => { if (comparar && x.src && !calma.matches) x.play().catch(() => {}); else x.pause(); });
    if (!comparar) return clearTimeout(cmp.reloj);
    abrirComparar();
    $("#pl-comparar").scrollIntoView({ block: "nearest", behavior: calma.matches ? "auto" : "smooth" });   // las cuatro a la vista
  };
  $(".pl-modos [role=tablist]").addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const otro = cmp.abierta ? "#pl-m-diseno" : "#pl-m-comparar";
    ponerModo(!cmp.abierta); $(otro).focus();
  });

  // ---- Eventos del formulario.
  f.addEventListener("click", (e) => {
    const t = e.target;
    const s = t.closest(".pl-nav [data-seccion]"); if (s) return irSeccion(s.dataset.seccion);
    // Muestras de color, estilos y casillas son cambios de un toque: cada uno es un paso propio de «deshacer».
    const muestra = t.closest("[data-color]");
    if (muestra) { escribir({ [muestra.dataset.para]: muestra.dataset.color }); return cambio(0); }
    const usar = t.closest("[data-usar]");
    if (usar) { escribir({ estilo: usar.dataset.usar }); decir(`Estilo elegido: ${NOMBRE_CORTO[usar.dataset.usar]}. Guarda el diseño para usarlo.`); return cambio(0); }
    if (t.closest("#pl-m-diseno")) ponerModo(false);
    else if (t.closest("#pl-m-comparar")) ponerModo(true);
  });
  f.addEventListener("input", (e) => {
    const t = e.target;
    if (t.dataset.par) { f.elements[t.dataset.par].value = t.value; return cambio(); }
    if (t.dataset.hex) {
      const x = t.value.trim();
      if (/^#[0-9a-f]{6}$/i.test(x)) { f.elements[t.dataset.hex].value = x.toLowerCase(); alDia(t.dataset.hex); cambio(); }
      return;
    }
    if (t.name) { alDia(t.name); cambio(["checkbox", "radio"].includes(t.type) ? 0 : 250); } else if (t.id === "pl-banner") cambio();
  });
  f.addEventListener("change", intentar(async (e) => {
    const t = e.target;
    if (t.id === "cmp-clip") { cmp.firma = ""; return pedirMuestras(); }
    if (!["logo", "logo-perfil"].includes(t.id) || !t.files[0]) return;
    const datos = new FormData(), p = perfilActivo(), general = t.id === "logo";
    datos.append("archivo", t.files[0]);
    const r = await api(general ? "/api/logo" : `/api/perfiles/${p.id}/logo`, { method: "POST", body: datos });
    if (general) logoGeneral = true; else await refrescar();
    version = Date.now(); pintarLogos(r.recorte); vista();
    avisar(general ? "Logo general actualizado." : `Logo de «${p.nombre}» actualizado.`);
  }));
  f.addEventListener("submit", intentar(async (e) => {
    e.preventDefault();
    clearTimeout(espera); registrar();
    S.ajustes.valores = (await api("/api/ajustes", { method: "PUT", json: valores() })).valores;
    guardado = JSON.stringify(valores()); marcar(true); avisar("Diseño guardado. Se aplica a los próximos renders."); vista(); refrescar();
  }));
  f._vista = vista; f._historia = historia; f._seccion = irSeccion;      // para las acciones y los atajos de teclado
  f._logos = (general) => { if (general !== undefined) logoGeneral = general; version = Date.now(); pintarLogos(); };
  f._perfil = () => { pintarLogos(); if (activa === "perfiles") pintarPerfilesPl(); vista(); };   // se activó otro perfil
  pintarLogos(); irSeccion(activa); marcar(); vista();
  if (animar()) gsap.from(".pl-nav, .pl-centro, .pl-props", { y: 10, opacity: 0, duration: 0.3, ease: "power3.out", stagger: 0.05, clearProps: "transform,opacity" });
}
// Atajos de la Plantilla: Ctrl+S guarda; Ctrl+Z y Ctrl+Y (o Ctrl+Mayús+Z) deshacen y rehacen; Alt+1…7 cambian de sección.
// Dentro de un campo de texto, deshacer es el del navegador.
document.addEventListener("keydown", (e) => {
  const f = $("#form-plantilla"), tecla = e.key.toLowerCase(), ctrl = e.ctrlKey || e.metaKey;
  if (!f || !$("#modal-fondo").hidden) return;
  if (ctrl && tecla === "s") { e.preventDefault(); f.requestSubmit(); return; }
  const n = e.altKey && !ctrl && /^Digit([1-7])$/.exec(e.code);
  if (n) { e.preventDefault(); f._seccion(SECCIONES_PLANTILLA[n[1] - 1][0], true); return; }
  if (!ctrl || (tecla !== "z" && tecla !== "y")) return;
  if (e.target.matches?.("input:not([type=checkbox]):not([type=color]):not([type=radio]):not([type=range]), textarea")) return;
  e.preventDefault(); f._historia(tecla === "z" && !e.shiftKey);
});

// ---------------------------------------------------------------- ajustes
// Nombre legible a partir del agente de usuario; si no se reconoce, no se inventa.
const primero = (lista, ag) => lista.find(([r]) => r.test(ag))?.[1];
const dispositivoDe = (ag) => [primero([[/Windows/, "Windows"], [/HarmonyOS|OpenHarmony/, "HarmonyOS"], [/Android/, "Android"], [/iPad|iPhone/, "iOS"], [/Mac OS X/, "macOS"], [/Linux|X11/, "Linux"]], ag),
  primero([[/Edg\//, "Edge"], [/HuaweiBrowser/, "Navegador Huawei"], [/Firefox\//, "Firefox"], [/Chrome\//, "Chrome"], [/Safari\//, "Safari"]], ag)].filter(Boolean).join(" · ") || `Navegador desconocido${ag ? ` (${ag.slice(0, 40)})` : ""}`;
const lapso = (s) => (s < 3600 ? `${Math.max(1, Math.round(s / 60))} min` : s < 172800 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} días`);

async function pintarAjustes(m) {
  let a;
  try { a = S.ajustes = await api("/api/ajustes"); } catch (e) {
    if ($(".esqueleto", m)) m.innerHTML = `<div class="panel sin-nada" role="alert">No se pudieron cargar los ajustes. Vuelve a entrar en Ajustes para reintentar.</div>`;
    return avisar(e.message, true);
  }
  if (S.vista !== "ajustes") return;     // se cambió de vista mientras llegaban los datos
  const v = a.valores, local = S.sesion.local, yt = S.estado.youtube, p = S.estado.proveedores;
  const soloPc = local ? "" : `<p class="nota">Por seguridad, esta sección solo se puede modificar desde el panel abierto en el PC.</p>`;
  const pestanas = [["youtube", "YouTube"], ["proveedores", "Proveedores"], ["dispositivos", "Dispositivos"], ["cuenta", "Cuenta"]];
  let cuerpo = "";
  if (S.pestana === "youtube") {
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
      <label class="linea"><input type="checkbox" role="switch" name="subida_automatica" ${v.subida_automatica ? "checked" : ""}> Subir en privado automáticamente al terminar el render (sin revisión previa)</label>
      <label class="linea"><input type="checkbox" role="switch" name="contenido_para_ninos" ${v.contenido_para_ninos ? "checked" : ""}> Declarar el contenido como «creado para niños»</label>
      <div class="campos">
        <label>Máximo de subidas por día<input type="number" name="subidas_max_dia" min="0" max="100" step="1" value="${v.subidas_max_dia}" aria-describedby="ayuda-ritmo"></label>
        <label>Minutos entre subidas<input type="number" name="subidas_intervalo_min" min="0" max="1440" step="1" value="${v.subidas_intervalo_min}" aria-describedby="ayuda-ritmo"></label>
        <label>Recortar clips más largos de (s)<select name="recorte_auto_segundos" aria-describedby="ayuda-recorte">${[...new Set([0, 60, 180, v.recorte_auto_segundos])].map((x) => crudo(h`<option value="${x}" ${x === v.recorte_auto_segundos ? "selected" : ""}>${x ? `${x} s` : "Nunca"}</option>`))}</select></label>
      </div>
      <p class="pequeno tenue" id="ayuda-ritmo">Ritmo de publicación de Fábrica Studio: 0 en «Máximo de subidas por día» = sin máximo; 0 en «Minutos entre subidas» = sin espera. Con los dos en 0, cada Short sube en cuanto está listo. Mientras una subida espera su turno, el resto de la cola sigue procesándose, y «Subir ahora» (en el Resumen y en cada clip) se salta este ritmo.</p>
      <p class="pequeno" id="ritmo-ahora" role="status"></p>
      <p class="nota" id="limites-youtube">${LIMITES_YOUTUBE}</p>
      <p class="pequeno tenue" id="ayuda-recorte">Si un clip dura más, se conserva su mejor tramo (puedes cambiarlo en «Editar tiempos»). 180 s es el máximo de un Short.</p>
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
      <p class="nota">El contexto de transcripción, las correcciones de escritura, el tema (GTA 6) y los hashtags fijos ahora son de cada creador: se editan en <a href="#perfiles">Perfiles</a>.</p>
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
  guardarForm("#form-pub", "Publicación guardada."); guardarForm("#form-prov", "Proveedores guardados.");
  // El ritmo en palabras, mientras se escribe (0 = sin límite).
  const ritmo = () => {
    const f = $("#form-pub"), max = +f.subidas_max_dia.value, min = +f.subidas_intervalo_min.value;
    $("#ritmo-ahora").textContent = !max && !min ? "Ahora: sin límite del programa. Cada Short sube en cuanto está listo."
      : `Ahora: ${max ? `hasta ${plural(max, "subida", "subidas")} cada 24 h` : "sin máximo por día"}, ${min ? `con ${min} min entre una y otra` : "sin espera entre una y otra"}.`;
  };
  if ($("#form-pub")) { ritmo(); $("#form-pub").addEventListener("input", ritmo); }

  $("#form-clave")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target, error = $(".error", f);
    if (f.nueva.value !== f.repetir.value) { error.textContent = "Las dos contraseñas nuevas no coinciden."; return f.repetir.focus(); }
    try {
      await api("/api/cuenta/contrasena", { method: "PUT", json: { actual: f.actual.value, nueva: f.nueva.value } });
      avisar("Contraseña cambiada. Se cerraron las demás sesiones."); pintarAjustes(m);
    } catch (err) { error.textContent = err.message; }
  });

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
