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
const ESTADOS = { pendiente: "En cola", procesando: "Procesando", propuestas: "Momentos listos", renderizado: "Renderizado", subiendo: "Subiendo", publicado: "Subido · privado", error: "Error" };
let S = { sesion: null, estado: null, vista: "cola", jid: null, detalle: null, sucio: false, pestana: "diseno", ajustes: null };

async function api(ruta, opciones = {}) {
  if (opciones.json !== undefined) {
    opciones.body = JSON.stringify(opciones.json);
    opciones.headers = { "Content-Type": "application/json" };
  }
  const r = await fetch(ruta, opciones);
  if (r.status === 401) { mostrarVinculacion(); throw new Error("Dispositivo no vinculado."); }
  const datos = r.headers.get("content-type")?.includes("json") ? await r.json() : null;
  if (!r.ok) throw new Error(datos?.error || `Error ${r.status}`);
  return datos;
}

function avisar(texto, mal = false) {
  const d = document.createElement("div");
  d.textContent = texto;
  if (mal) d.className = "mal";
  $("#avisos").append(d);
  setTimeout(() => d.remove(), mal ? 9000 : 4000);
}
const intentar = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { avisar(e.message, true); } };

// ---------------------------------------------------------------- arranque y navegación
function mostrarVinculacion() { $("#app").hidden = true; $("#vincular").hidden = false; }

$("#form-vincular").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/vincular", { method: "POST", json: { codigo: $("#v-codigo").value, nombre: $("#v-nombre").value } });
    location.reload();
  } catch (err) { $("#v-error").textContent = err.message; }
});

function navegar() {
  const [vista, jid] = location.hash.replace("#", "").split("/");
  S.vista = ["cola", "biblioteca", "ajustes", "trabajo"].includes(vista) ? vista : "cola";
  S.jid = S.vista === "trabajo" ? jid : null;
  S.detalle = null; S.sucio = false;
  document.querySelectorAll(".lateral a").forEach((a) => a.classList.toggle("activa", a.dataset.vista === S.vista));
  pintar(true);
}
window.addEventListener("hashchange", navegar);

async function refrescar() {
  try {
    S.estado = await api("/api/estado");
    if (S.jid) S.detalle = await api(`/api/trabajos/${S.jid}`).catch(() => null);
    pintar(false);
  } catch (e) { /* se reintenta en el siguiente ciclo */ }
}

(async function iniciar() {
  S.sesion = await (await fetch("/api/sesion")).json();
  if (!S.sesion.autorizado) return mostrarVinculacion();
  $("#app").hidden = false;
  await refrescar();
  navegar();
  setInterval(refrescar, 2000);
})();

// ---------------------------------------------------------------- vistas
function pintar(completo) {
  if (!S.estado) return;
  const yt = S.estado.youtube;
  $("#pie-canal").innerHTML = yt.canal_id ? h`Canal de destino<br><b>${yt.canal_nombre}</b><br>${yt.canal_id}` : "Sin canal de YouTube confirmado";
  const m = $("#principal");
  if (S.vista === "cola") pintarCola(m, completo);
  else if (S.vista === "biblioteca") m.innerHTML = vistaBiblioteca();
  else if (S.vista === "trabajo") pintarTrabajo(m, completo);
  else if (S.vista === "ajustes" && completo) pintarAjustes(m);
}

function filaTrabajo(t) {
  const mini = t.tiene_video ? h`<img class="mini" src="/media/${t.id}/miniatura.jpg?v=${t.actualizado}" alt="" loading="lazy">` : `<div class="mini"></div>`;
  const barras = etapasDe(t).map(([k]) => h`<i class="${t.etapas[k]?.estado || ""}"></i>`).join("");
  const linea = t.estado === "error" ? t.error.split("\n")[0] : t.progreso || t.textos.titulo || etiquetaOrigen(t);
  return h`<button class="trabajo" data-ir="${t.id}">${crudo(mini)}
    <span class="info"><span class="nombre">${t.nombre}</span><span class="etapas" aria-hidden="true">${crudo(barras)}</span>
    <span class="pequeno tenue nombre">${linea}</span></span>
    <span class="estado ${t.estado}">${ESTADOS[t.estado]}</span></button>`;
}
const etiquetaOrigen = (t) => ({ archivo: "Archivo importado", carpeta: "Carpeta 1_clips_crudos", enlace: "Enlace de Kick", momento: "Momento de un video largo" }[t.origen_tipo]) + (t.modo === "largo" ? " · video largo" : "");

function pintarCola(m, completo) {
  if (completo || !$("#cola-lista")) {
    m.innerHTML = h`<div class="cabecera"><h1>Cola</h1><span class="tenue pequeno" id="cola-resumen"></span></div>
    <div class="rejilla2" style="margin-bottom:22px">
      <div class="tarjeta pila">
        <h3>Importar archivo</h3>
        <div class="soltar" id="soltar">Arrastra un video aquí o
          <label class="boton" style="display:inline-flex;flex-direction:row;color:var(--texto)">elige un archivo<input type="file" id="archivo" accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.mkv,.webm,.m4v" multiple hidden></label>
        </div>
        <p class="pequeno tenue" id="subiendo"></p>
      </div>
      <form class="tarjeta pila" id="form-enlace">
        <h3>Importar enlace de Kick</h3>
        <label>Enlace público del clip<input id="enlace" type="url" placeholder="https://kick.com/…" required></label>
        <div class="fila separado"><span class="pequeno tenue">Si Kick exige iniciar sesión o bloquea la descarga, se indicará el motivo.</span><button>Añadir a la cola</button></div>
      </form>
    </div>
    <label style="margin-bottom:12px;max-width:520px">Tipo de video<select id="modo">
      <option value="clip">Clip ya seleccionado: se convierte completo en un Short</option>
      <option value="largo">Video largo: transcribir y proponer momentos para recortar</option></select></label>
    <label class="linea" style="margin-bottom:18px"><input type="checkbox" id="publicar" checked> Los clips importados se destinan a YouTube (siempre en privado y tras tu revisión, salvo que actives la subida automática en Ajustes)</label>
    <div id="cola-carpeta"></div><div class="lista" id="cola-lista"></div>`;
    const soltar = $("#soltar");
    ["dragover", "dragenter"].forEach((ev) => soltar.addEventListener(ev, (e) => { e.preventDefault(); soltar.classList.add("encima"); }));
    ["dragleave", "drop"].forEach((ev) => soltar.addEventListener(ev, () => soltar.classList.remove("encima")));
    soltar.addEventListener("drop", (e) => { e.preventDefault(); subirArchivos(e.dataTransfer.files); });
    $("#archivo").addEventListener("change", (e) => { subirArchivos(e.target.files); e.target.value = ""; });
    $("#form-enlace").addEventListener("submit", intentar(async (e) => {
      e.preventDefault();
      await api("/api/importar/enlace", { method: "POST", json: { url: $("#enlace").value, publicar: $("#publicar").checked, modo: $("#modo").value } });
      $("#enlace").value = ""; avisar("Enlace añadido a la cola."); refrescar();
    }));
  }
  const activos = S.estado.trabajos.filter((t) => t.estado !== "publicado");
  const c = S.estado.carpeta;
  $("#cola-resumen").textContent = `${activos.length} en curso · ${S.estado.trabajos.length - activos.length} subidos`;
  $("#cola-carpeta").innerHTML = c.pendientes.map((p) => h`<p class="nota" style="margin-bottom:8px"><b>${p.archivo}</b> (carpeta): ${p.motivo}</p>`).join("");
  $("#cola-lista").innerHTML = activos.length ? activos.map(filaTrabajo).join("")
    : h`<div class="vacio">No hay trabajos en curso. Importa un clip arriba${c.activa ? crudo(h` o cópialo en <code>${c.ruta}</code>`) : ""}.</div>`;
}

async function subirArchivos(archivos) {
  for (const f of archivos) {
    $("#subiendo").textContent = `Enviando ${f.name}…`;
    const datos = new FormData();
    datos.append("archivo", f); datos.append("publicar", $("#publicar").checked); datos.append("modo", $("#modo").value);
    try { await api("/api/importar/archivo", { method: "POST", body: datos }); avisar(`${f.name} añadido a la cola.`); }
    catch (e) { avisar(`${f.name}: ${e.message}`, true); }
  }
  $("#subiendo").textContent = ""; refrescar();
}

function vistaBiblioteca() {
  const listos = S.estado.trabajos.filter((t) => t.tiene_video);
  return h`<div class="cabecera"><h1>Biblioteca</h1><span class="tenue pequeno">${listos.length} Shorts renderizados</span></div>` +
    (listos.length ? `<div class="galeria">` + listos.map((t) => h`<button class="pieza" data-ir="${t.id}">
      <img src="/media/${t.id}/miniatura.jpg?v=${t.actualizado}" alt="" loading="lazy">
      <div><b>${t.textos.titulo || t.nombre}</b><span class="estado ${t.estado}">${ESTADOS[t.estado]}</span></div></button>`).join("") + `</div>`
      : `<div class="vacio">Aún no hay Shorts renderizados.</div>`);
}

document.addEventListener("click", (e) => {
  const ir = e.target.closest("[data-ir]");
  if (ir) location.hash = `trabajo/${ir.dataset.ir}`;
  const acc = e.target.closest("[data-accion]");
  if (acc) acciones[acc.dataset.accion]?.(acc);
});

// ---------------------------------------------------------------- detalle del trabajo
function pintarTrabajo(m, completo) {
  const t = S.detalle;
  if (!t) { m.innerHTML = `<div class="cabecera"><h1>Trabajo</h1></div><div class="vacio">Cargando… Si no aparece, el trabajo ya no existe. <a href="#cola">Volver a la cola</a></div>`; return; }
  if (t.modo === "largo") return pintarLargo(m, t, completo);
  if (completo || !$("#t-estado") || $("#t-estado").dataset.id !== t.id) {
    m.innerHTML = h`<div class="cabecera"><h1 id="t-nombre"></h1><a class="boton" href="#cola">← Volver</a></div>
      <div class="detalle"><div class="pila"><div id="t-video"></div></div>
      <div class="pila"><div class="pila" id="t-estado" data-id="${t.id}"></div><div class="pila" id="t-edicion"></div></div></div>`;
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
  if (t.estado === "error") botones += `<button class="primario" data-accion="reintentar">Reintentar</button>`;
  if (t.estado === "renderizado" && !t.subir_solicitado) {
    botones += yt.canal_id ? h`<button class="primario" data-accion="subir">Subir en privado a ${yt.canal_nombre}</button>` : `<a class="boton" href="#ajustes">Conectar YouTube para subir</a>`;
    botones += `<button data-accion="renderizar">Renderizar de nuevo</button>`;
  }
  if (t.tiene_video) botones += h`<a class="boton" href="/media/${t.id}/short.mp4" download="${t.nombre}.mp4">Descargar MP4</a>`;
  if (!["procesando", "subiendo"].includes(t.estado)) botones += `<button class="texto peligro" data-accion="eliminar">Eliminar</button>`;
  $("#t-estado").innerHTML = h`<div class="fila"><span class="estado ${t.estado}">${ESTADOS[t.estado]}</span>
      <span class="tenue pequeno">${t.progreso || (t.subir_solicitado ? "En cola para subir…" : etiquetaOrigen(t))}</span></div>
    ${t.error ? crudo(h`<p class="nota mal" role="alert">${t.error}</p>`) : ""}
    ${t.avisos.map((a) => crudo(h`<p class="nota">${a}</p>`))}
    ${t.youtube_id ? crudo(h`<p class="nota bien">Subido en privado. ID de YouTube: <code>${t.youtube_id}</code> ·
      <a href="https://studio.youtube.com/video/${t.youtube_id}/edit" target="_blank" rel="noopener">Abrir en YouTube Studio</a></p>`) : ""}
    <ul class="pasos tarjeta">${crudo(pasos)}</ul>
    ${t.salida ? crudo(h`<p class="pequeno tenue">Resultado: ${t.salida.ancho}×${t.salida.alto} · ${t.salida.duracion.toFixed(1)} s · ${t.salida.codec_video}/${t.salida.codec_audio || "sin audio"} · ${(t.salida.tamano_bytes / 1048576).toFixed(1)} MB · copia en 2_shorts_renderizados/${t.copia}</p>`) : ""}
    <div class="fila">${crudo(botones)}</div>`;

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
    m.innerHTML = h`<div class="cabecera"><h1 id="t-nombre"></h1><a class="boton" href="#cola">← Volver</a></div>
      <div class="pila"><div class="pila" id="l-estado" data-id="${t.id}"></div>
      ${t.entrada ? crudo(h`<video id="l-video" controls playsinline preload="metadata" src="/media/${t.id}/entrada" style="width:100%;max-width:640px;border-radius:10px;border:1px solid var(--borde);background:#000"></video>`) : crudo(`<p class="pequeno tenue">El formato del original no se puede reproducir en el navegador; guíate por el texto de cada momento.</p>`)}
      <div class="pila" id="l-momentos"></div></div>`;
    S.version = null; S.sucio = false;
  }
  $("#t-nombre").textContent = t.nombre;
  const pasos = ETAPAS_LARGO.map(([k, n]) => h`<li class="${t.etapas[k]?.estado || ""}"><span class="punto"></span><span>${n}</span><span>${t.etapas[k]?.detalle || ""}</span></li>`).join("");
  $("#l-estado").innerHTML = h`<div class="fila"><span class="estado ${t.estado}">${ESTADOS[t.estado]}</span><span class="tenue pequeno">${t.progreso || etiquetaOrigen(t)}</span></div>
    ${t.error ? crudo(h`<p class="nota mal" role="alert">${t.error}</p>`) : ""}
    ${t.avisos.map((a) => crudo(h`<p class="nota">${a}</p>`))}
    <ul class="pasos tarjeta">${crudo(pasos)}</ul>
    <div class="fila">${t.estado === "error" ? crudo(`<button class="primario" data-accion="reintentar">Reintentar</button>`) : ""}
      ${["propuestas", "error"].includes(t.estado) ? crudo(`<button data-accion="proponer-momentos">Proponer momentos de nuevo</button>`) : ""}
      ${t.estado !== "procesando" ? crudo(`<button class="texto peligro" data-accion="eliminar">Eliminar</button>`) : ""}</div>`;
  const mo = t.momentos;
  const version = `${t.actualizado}|${t.clips.map((c) => c.id + c.estado).join()}`;
  if (!mo || S.sucio || S.version === version || $("#l-momentos").contains(document.activeElement)) return;
  S.version = version;
  const clipDe = (p) => t.clips.find((c) => Math.abs(c.inicio - p.inicio) < 0.02 && Math.abs(c.fin - p.fin) < 0.02);
  const local = mo.origen === "local";
  $("#l-momentos").innerHTML = h`<div class="fila separado"><h2>Momentos propuestos</h2><span class="pequeno tenue">Origen: ${mo.origen}</span></div>
    ${local ? crudo(`<p class="nota">Propuestas de la heurística local: mide ritmo de habla, exclamaciones y preguntas, pero no entiende el contenido. Revisa cada tramo antes de crear el Short. Con una clave de Gemini las propuestas se basan en lo que se dice.</p>`) : ""}
    ${mo.propuestas.length ? "" : crudo(`<div class="vacio">No hay propuestas. Puedes crear un clip indicando los tiempos abajo.</div>`)}
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
    ${t.clips.length ? crudo(h`<div class="tarjeta pila"><h3>Clips creados</h3>${t.clips.map((c) => crudo(h`<a class="fila separado" href="#trabajo/${c.id}" style="text-decoration:none"><span>${reloj(c.inicio)} – ${reloj(c.fin)} · ${c.nombre}</span><span class="estado ${c.estado}">${ESTADOS[c.estado]}</span></a>`))}</div>`) : ""}`;
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
    if (!confirm(`Se subirá este Short en PRIVADO al canal «${yt.canal_nombre}» (${yt.canal_id}). ¿Continuar?`)) return;
    await api(`/api/trabajos/${S.jid}/subir`, { method: "POST" }); avisar("Subida en cola."); refrescar();
  }),
  eliminar: intentar(async () => {
    if (!confirm("Se eliminará el trabajo y sus archivos intermedios de este PC. No borra nada de YouTube. ¿Continuar?")) return;
    await api(`/api/trabajos/${S.jid}`, { method: "DELETE" }); location.hash = "cola";
  }),
  pestana: (b) => { S.pestana = b.dataset.p; pintarAjustes($("#principal")); },
  "codigo": intentar(async () => {
    const c = await api("/api/vincular/codigo", { method: "POST" });
    $("#zona-codigo").innerHTML = h`<p class="codigo">${c.codigo}</p><p class="pequeno tenue">Válido 10 minutos y para un solo dispositivo. En la tablet abre <code>${c.direccion || "http://IP-del-PC:8765"}</code> en el navegador, conectada al mismo wifi.</p>`;
  }),
  "quitar-dispositivo": intentar(async (b) => { await api(`/api/dispositivos/${b.dataset.id}`, { method: "DELETE" }); pintarAjustes($("#principal")); }),
  "yt-desconectar": intentar(async () => { if (confirm("¿Desconectar la cuenta de YouTube de Fábrica Studio?")) { await api("/api/youtube/desconectar", { method: "POST" }); await refrescar(); pintarAjustes($("#principal")); } }),
  "yt-confirmar": intentar(async (b) => {
    if (!confirm(`¿Confirmas «${b.dataset.titulo}» (${b.dataset.id}) como canal de destino de las subidas?`)) return;
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
  try { a = S.ajustes = await api("/api/ajustes"); } catch (e) { return avisar(e.message, true); }
  const v = a.valores, local = S.sesion.local, yt = S.estado.youtube, p = S.estado.proveedores;
  const soloPc = local ? "" : `<p class="nota">Por seguridad, esta sección solo se puede modificar desde el panel abierto en el PC.</p>`;
  const pestanas = [["diseno", "Diseño"], ["youtube", "YouTube"], ["proveedores", "Proveedores"], ["dispositivos", "Dispositivos"]];
  let cuerpo = "";
  if (S.pestana === "diseno") {
    cuerpo = h`<div class="diseno"><form class="pila" id="form-diseno">
      <div class="campos">${CAMPOS_DISENO.map(([k, n, tipo]) => crudo(h`<label>${n}<input name="${k}" type="${tipo || "number"}" value="${v[k]}"></label>`))}</div>
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
        ${c.id === yt.canal_id ? crudo(`<span class="estado publicado">Destino confirmado</span>`) : crudo(h`<button data-accion="yt-confirmar" data-id="${c.id}" data-titulo="${c.titulo}" ${local ? "" : "disabled"}>Confirmar como destino</button>`)}</div>`).join("")
        : `<p class="nota">La cuenta conectada no tiene ningún canal de YouTube.</p>`;
    } catch (e) { $("#yt-canales").innerHTML = h`<p class="nota mal">${e.message}</p>`; }
  }
}
