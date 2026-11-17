# Estado de Fábrica Studio

Registro compartido entre Cristóbal, Claude Code y Codex. Última actualización: 2026-11-17.

## Resumen

Versión 0.3 en desarrollo. Funciona en el entorno de nube (Linux): clip seleccionado
→ Short vertical, modo video largo con propuesta de momentos, panel web, cola
persistente, carpeta vigilada, vinculación de tablet y diagnóstico del equipo.
La subida a YouTube está implementada y probada solo contra un YouTube simulado.

**En el PC Windows (2026-11-16):** instalación, 47 pruebas, diagnóstico, arranque del panel y
primer Short real renderizado y **primera subida real a YouTube en privado** (ver «Comprobado en el PC Windows»).
**Nada probado aún en la tablet ni con Gemini.**

## Repositorio y rama

- Repositorio: https://github.com/ykvvvv/Fabricastudio
- Rama con los últimos avances: `claude/fabrica-studio-shorts-x34of8` (es la única rama).
- Enviado a GitHub y verificado el 2026-11-16: el commit remoto coincide con el local.
  Los envíos anteriores fallaron con 403; se resolvió al corregir el acceso de Claude a GitHub.
- Todo el desarrollo hasta ahora se hizo en una sesión de Claude Code **en la nube (Linux)**.
  El PC de Cristóbal todavía no tiene una copia: hay que clonarla (ver «Pasos para continuar en Windows»).

## Login del panel: servidor, pantallas (fase 1) y animaciones con GSAP (fase 2) listos (2026-11-17)

`fabrica_studio/cuentas.py` + rutas en `server.py`. Una cuenta (el propietario), contraseña con scrypt,
sesiones en cookie HttpOnly (hash en SQLite), bloqueo por IP tras 5 fallos con espera creciente.
**Compatible con el panel actual:** mientras no se cree la cuenta, todo funciona como antes.

Contrato para la interfaz:

| Ruta | Uso |
| --- | --- |
| `GET /api/sesion` | `{autorizado, local, cuenta_creada, usuario, sesion_iniciada, version}`. No revela el usuario sin sesión. |
| `POST /api/cuenta/crear` `{nombre, contrasena, recordar}` | Primera configuración. **Solo desde el PC** y solo si no hay cuenta (409 si ya existe). Deja la sesión iniciada. |
| `POST /api/login` `{usuario, contrasena, recordar}` | 403 credenciales malas; 429 `{espera}` si está bloqueado, **ya en el fallo que activa el bloqueo** (el 5.º). `GET /api/sesion` incluye `espera_login` (segundos, 0 si no hay bloqueo) para mostrarlo al recargar. `recordar` = 30 días; si no, sesión del navegador (12 h máx.). |
| `POST /api/logout` | Cierra la sesión actual. |
| `PUT /api/cuenta/contrasena` `{actual, nueva}` | Solo PC. Cierra todas las sesiones y deja abierta la actual. |
| `GET /api/sesiones`, `DELETE /api/sesiones/<id>` | Sesiones abiertas (con `actual`); cerrar una solo desde el PC. |

Flujo de pantallas: `cuenta_creada=false` y `local=true` → ofrecer «Crear cuenta» (opcional, se puede seguir
sin contraseña). `cuenta_creada=true` y `autorizado=false` → pantalla de login. Los dispositivos vinculados
con código siguen funcionando. Si se olvida la contraseña: `python -m fabrica_studio.cuentas --restablecer` en el PC.

**Plan: `docs/diseno/plan-login.md`.** Decisiones de Cristóbal (2026-11-17): bienvenida una sola vez («Ahora no»
la oculta para siempre); cuenta regresiva con los datos del servidor; Three.js en la última fase y opcional
(el fondo es la cuadrícula CSS); licencia de GSAP aceptada (se incluirá en `web/vendor/` con su archivo de licencia).

**Fase 1 implementada (solo CSS, sin bibliotecas)** en `web/index.html`, `estilo.css`, `app.js`, `iconos.js`:

- Pantallas de acceso en `#acceso`: bienvenida + crear cuenta (PC, primera vez), login y vinculación por código
  (la de antes, ahora dentro del mismo contenedor, con paso de ida y vuelta al login).
- Login: error con el mensaje del servidor y sacudida; bloqueo 429 con cuenta regresiva calculada contra la hora
  de fin (`performance.now()`), que sigue al recargar gracias a `espera_login`. No se reenvía solo al terminar.
- Ajustes → pestaña **Cuenta**: cambiar contraseña (solo PC), sesiones abiertas (cerrar otras, solo PC), salir.
  Sin cuenta: tarjeta «Protege tu panel».
- Menú de usuario al pie de la barra lateral (también plegada): «Cuenta» y «Cerrar sesión». Si el dispositivo
  sigue vinculado por código, se queda en el panel con un aviso.
- Si la API responde 401 con el panel abierto, se muestra el login con «Tu sesión caducó».
- Tras crear la cuenta o iniciar sesión ya no se recarga la página: se entra con la transición de la fase 2.

Probado con Playwright (Chromium) contra un servidor temporal con datos vacíos, en 1440×900 y, entrando por la IP
de la red (`192.168.1.116`, que el servidor trata como dispositivo no local), en 1280×800 y 800×1280: crear cuenta,
login correcto e incorrecto, bloqueo (30 → 25 en 5,0 s; servidor y panel coinciden tras recargar), fin del bloqueo,
cerrar sesión, sesión + vinculación, cambio de contraseña, cierre de otra sesión, «Ahora no» y «reducir movimiento».
Capturas en `docs/diseno/capturas-login/`. **No probado en la tablet real ni en su navegador.**

**Fase 2 implementada: animaciones con GSAP 3.15.1 local** (`web/vendor/gsap.min.js`, 73 KB, sin CDN ni plugins;
versión, huella SHA-256 y licencia en `web/vendor/LICENCIAS.md`; `.gitattributes` impide que Git altere el archivo).

- Bienvenida: marca → texto → tarjeta → campos escalonados (≈ 1,2 s; se puede escribir desde el principio).
- Login y vinculación: la tarjeta sube 8 px con opacidad.
- Login o cuenta creada → panel **sin recargar**: check en el botón, la tarjeta se retira, el acceso se desvanece
  como velo mientras el panel carga debajo y entran la barra lateral y la superior. Medido: 808 ms a 60 cuadros/s.
- Cerrar sesión: el panel se desvanece (220 ms) y entra el login.
- La sacudida de error, el bloqueo y el anillo siguen en CSS (ya cumplían el plan; no se duplicaron en GSAP).
- Sin `gsap.min.js` o con «reducir movimiento» no se monta ninguna línea de tiempo y todo funciona igual
  (comprobado bloqueando el archivo). Al terminar cada animación no queda estilo en línea.

Probado con Playwright en 1440×900 y, por la IP de la red, en 1280×800, 800×1280 y 600×900: bienvenida, crear cuenta,
login mal y bien, dos entradas seguidas en la misma página, bloqueo + recarga, cerrar sesión; ninguna petición
fuera del PC y ningún error de JavaScript. Capturas `fase2-*.png`. **La fluidez en la tablet real está sin probar.**

Pendiente: fase 3 opcional (Three.js). Límite conocido: un
dispositivo ya vinculado por código entra directo al panel y no tiene forma de iniciar sesión con contraseña
desde la interfaz (solo importa para que aparezca en «Sesiones abiertas»).

## Estilo pantalla completa tipo OpusClip (2026-11-16)

Implementada la **fase 1** de `docs/ESTILO_OPUSCLIP.md`: el video llena el 9:16 y el encuadre
sigue los rostros (YuNet + cámara virtual), con subtítulos grandes en mayúsculas sobre la imagen.
Se elige en Ajustes → Diseño → «Estilo de encuadre», o por clip en su página. El estilo clásico sigue
siendo el predeterminado. Nueva dependencia: `opencv-python-headless` (hay rueda para Windows x64).

Probado aquí: video sintético con un rostro real que cruza la imagen; la cámara lo sigue y corta en
el salto. **Falta validarlo con clips reales en el PC** (después de `git pull`, volver a ejecutar
`scripts\instalar.ps1` para instalar OpenCV y luego `scripts\diagnostico.ps1`).

Siguientes fases (vista dividida, hablante activo, subtítulos animados): ver `docs/ESTILO_OPUSCLIP.md`.

## Diseño de referencia (2026-11-16)

Cristóbal comparó un Short generado aquí con uno anterior que considera correcto (canal
PaltitaClips, banner «PROTESTA POR ALZA COMBUSTIBLE»). Valores medidos sobre esa referencia
y aplicados como predeterminados en `config.py`:

| Elemento | Valor en 1080×1920 |
| --- | --- |
| Tarjeta del banner | 1044 px de ancho (≈18 px de margen), letra hasta 92 (Inter Black), rojo `#E3222A`, esquinas 22 |
| Video | Todo el ancho, pegado bajo la tarjeta (separación 10) |
| Subtítulos | 30 px bajo el video, letra 66, 3 palabras por bloque, **palabra activa en verde `#53FC18`** |
| Logo | 126 px de alto, inmediatamente bajo los subtítulos |
| Firma | `@jongottii`, gris claro `#D9D9D9`, 40 px |

Además: **recorte automático de franjas negras** del clip original (cropdetect). El primer clip
real de Cristóbal se vio pequeño y descentrado porque el original traía bordes negros incrustados.

Pendiente para igualar la referencia: **el logo oficial de Kick** (letras pixeladas). No se dibuja
desde el código; Cristóbal lo sube en Ajustes → Diseño → «Subir logo PNG».
Si en el panel ya se habían guardado ajustes de diseño, hay que pulsar «Restablecer valores
iniciales» para que se apliquen los nuevos.

## Trabajo anterior en Codex/ChatGPT y el APK

Cristóbal quiere que el panel y el diseño sean iguales a los de su versión anterior (hecha con
ChatGPT/Codex, incluida un APK). Estado real:

- La sesión de Claude Code en la nube **no puede leer** conversaciones de Codex ni de ChatGPT.
- Codex (CLI y extensión) guarda sus sesiones en el PC, en `%USERPROFILE%\.codex\sessions\` (archivos `.jsonl`).
  Un Claude Code ejecutándose **en el PC de Cristóbal** sí puede leerlos, si existen.
- Las conversaciones de chatgpt.com no se guardan en el PC: hay que exportarlas
  (chatgpt.com → Configuración → Controles de datos → Exportar datos).
- Los archivos anteriores (`Fabrica_Studio_Tablet_0_1.apk`, `Fabrica_Studio_Android_Fuentes_0_1.zip`,
  `Fabrica_Studio_Ember.html`) no están en el repositorio. Si Cristóbal los copia a `referencias/`
  (excluida de git), se pueden analizar para portar su diseño al panel.

**Tarea para el Claude Code local (PC de Cristóbal):**
1. Buscar sesiones en `%USERPROFILE%\.codex\sessions\` relacionadas con Fábrica Studio y resumir
   decisiones de diseño, valores de layout y requisitos que no estén ya en este archivo.
2. Si existe `referencias/Fabrica_Studio_Ember.html` o el ZIP de fuentes Android, extraer la paleta,
   tipografía, estructura de pantallas y componentes, y proponer cómo aplicarlos a `fabrica_studio/web/`.
3. Registrar los hallazgos aquí antes de cambiar código. No copiar claves ni tokens que aparezcan en esos chats.

**Resultado (2026-11-16, Claude Code en el PC, solo lectura):** no se encontró el diseño ni los requisitos
del trabajo anterior.

- Sesiones locales de Codex: **46 revisadas** (23-oct → 16-nov-2026), filtrando por APK, Fábrica, Shorts,
  clips, Whisper, subtítulos y YouTube. **Ninguna trata de Fábrica Studio**, salvo la revisión de solo
  lectura del 16-nov (ya registrada). El resto son temas ajenos al proyecto.
- `referencias/` no existe todavía en el PC: no hay APK, ZIP ni HTML Ember que analizar (puntos 2 y 3 sin hacer).
- Conclusión: ese trabajo se hizo **probablemente en ChatGPT web**. Para recuperarlo: exportar el historial
  de chatgpt.com o copiar los tres archivos a `referencias/`, revisando antes que no tengan claves.

## Panel nuevo según `docs/diseno/referencia-panel.html` (en curso)

Plan aprobado por Cristóbal el 2026-11-16, en 4 fases. El detalle del clip sigue siendo una página
(`#trabajo/<id>`), no un modal. No hay skill `design`: la revisión de accesibilidad se hace a mano con Playwright.

**Fase 1 hecha (2026-11-16): estructura, Resumen y Cola.**

- Barra lateral (riel de iconos en tablet vertical, menú desplegable por debajo de 680 px), barra superior con
  buscador (Ctrl K), avisos, ventanas accesibles que sustituyen a `confirm()`, pantalla de vinculación con el estilo nuevo.
- Resumen con datos reales: clips en cola, listos para revisar, canal confirmado, enlace rápido, actividad
  reciente, maqueta real del formato (`/api/diseno/vista`), estado de YouTube y dispositivos vinculados.
- Cola en tabla con filtros (Todos / En espera / Generando / Listos / Con error), búsqueda, eliminar con
  confirmación y progreso por etapas (un segmento por etapa; el motor no da porcentaje).
- Ventana «Nuevo clip»: varios enlaces o varios archivos, tipo clip / video largo, casilla de YouTube.
- API: el trabajo público incluye `duracion` (leída de `propiedades.json`; `null` hasta la etapa «comprobar»). Prueba nueva.
- Quitado de la referencia por no tener datos reales: curvas de las estadísticas, textos de demo, «Pausar»,
  «Probar el flujo», campo «Nombre», tipos de clip por color. Letra mínima 12 px y grises más claros (contraste AA).
- Biblioteca, detalle del clip, video largo y Ajustes **funcionan igual que antes** con la paleta nueva; se
  rediseñan en las fases 2 a 4. «Plantilla» y «Cómo funciona» aún no están en el menú (fases 3 y 4).

Probado aquí (PC, Chromium con Playwright, servidor de prueba con datos temporales y transcripción fija,
3 clips sintéticos): 62 pruebas de pytest; recorrido a 1280×800 y 800×1280 (enlace rechazado por el servidor,
subir 2 clips y 1 video largo, duplicado rechazado, etapas en vivo, filtros, búsqueda, eliminar, servidor caído);
sin desborde horizontal a 1280, 800 y 600 px; sin errores de JavaScript (solo los 400/409 provocados a propósito).
Accesibilidad medida: contraste ≥ 4,5:1 en todo el texto de Resumen, Cola y ventana; foco visible y atrapado en
la ventana; Esc cierra y devuelve el foco; el foco sobrevive al refresco de 2 s; objetivos táctiles ≥ 44 px
(la casilla mide 22 px pero toda su fila es pulsable); `prefers-reduced-motion` desactiva las animaciones.

**No probado:** la tablet real, la pantalla de vinculación vista desde otro dispositivo, un enlace real de Kick,
Gemini, y el panel con los datos reales de Cristóbal (canal confirmado, Shorts ya subidos).

**Fase 2 hecha (2026-11-16): Biblioteca en tarjetas y detalle del clip.** Solo `web/app.js` y `web/estilo.css`.

- Biblioteca: tarjetas 9:16 con miniatura real, estado, duración, fecha y «Sin subir / En YouTube (privado)»;
  orden (recientes / por nombre), búsqueda, botón «Importar un video». Ya no se repinta entera cada 2 s.
- Detalle: ficha con estado, Origen, Duración, Resultado, Copia y YouTube, etapas y acciones en una tarjeta.
  El enlace «←» y el menú recuerdan si se llegó desde la Biblioteca o desde la Cola; eliminar vuelve ahí.
  El estado ya no se reescribe cada 2 s (el selector de estilo y los botones conservan el foco).
- Video largo: misma cabecera y pastillas de estado; los formularios de momentos no cambian.
- Probado aquí (Chromium/Playwright, servidor de prueba con transcripción fija, 2 clips y 1 video largo sintéticos):
  abrir tarjeta, cambiar estilo y re-render, búsqueda sin resultados, eliminar desde el detalle, video largo desde la
  cola; sin desborde a 1280, 800 y 600 px; contraste mínimo 5,56:1; letra mínima 12 px; sin errores de JavaScript.
- pytest tras el cambio: 62 pasan (no se añadieron pruebas: el cambio es solo de interfaz).
- **No probado:** el orden «por nombre» con títulos distintos, un clip en
  `error` o ya subido en la ficha nueva, el centrado del video en tablet tras el último ajuste de CSS, la tablet real.

**Fase de movimiento hecha (2026-11-17): animaciones del panel.** Solo `web/` (`index.html`, `app.js`, `estilo.css`,
`iconos.js`). Sin librerías: CSS, `@keyframes` y Web Animations API. Se anima solo `transform` y `opacity`; la única
excepción es la barra lateral (`grid-template-columns`). Ninguna animación inventa progreso: todas salen de la API.

- **Barra lateral plegable:** botón en la barra superior y Ctrl+B; 224 px ↔ 72 px en 220 ms; plegada muestra iconos con
  el nombre al pasar el mouse o enfocar. Se recuerda en `localStorage` (`fabrica.lateral`); sin valor guardado, arranca
  plegada si la pantalla mide 900 px o menos. Bajo 680 px es un menú que entra deslizándose sobre un fondo oscurecido
  (Esc o tocar fuera lo cierra; el foco entra al menú y vuelve al botón). `aria-expanded` en el botón.
- **Vistas:** fundido + 6 px en 180 ms solo al cambiar de vista. Las listas (Cola, Biblioteca, actividad reciente) ahora
  se actualizan fila por fila (`ponerLista`): el refresco de 2 s no vuelve a animar nada.
- **Resumen:** las dos cifras cuentan desde 0 hasta el número real al abrir la vista (600 ms), no al refrescar.
- **Progreso:** brillo que recorre la etapa en curso; cuando la API marca una etapa como hecha, su segmento se rellena
  una vez; cuando un clip pasa a renderizado, subido o «momentos listos», aparece un check animado en su fila y un aviso.
- **Filas y tarjetas:** entrada escalonada (30 ms, máximo 8) solo para elementos nuevos; elevación de 2 px con sombra
  al pasar el mouse (solo en las que son enlaces: tarjetas de la Biblioteca y filas de la Cola).
- **Esqueleto de carga** al abrir el panel, el detalle de un clip y Ajustes. El detalle ya no espera al ciclo de 2 s.
- **Zona de soltar:** aro con brillo que late mientras se arrastra un archivo encima.
- **Ventanas y avisos:** entran con escala 0,98 → 1 y fundido; salen deslizándose 10 px (180 ms).
- **«Reducir movimiento»:** todo cambia al instante; el brillo de la etapa y el esqueleto quedan como indicadores fijos.
- Con la barra desplegada en tablet (≤ 900 px), el Resumen pasa a una columna para que no se apriete.

Probado aquí (PC, Chromium con Playwright, servidor de prueba con datos temporales y transcripción fija, 3 clips
sintéticos procesados de verdad): 63 pruebas de pytest tras integrar el cambio de la nube. A 1280×800, 800×1280 y 600×900: plegar y desplegar con el botón
y con Ctrl+B, estado recordado tras recargar, nombres al pasar el mouse, menú móvil con foco y Esc; sin desborde
horizontal con la barra plegada ni desplegada; sin errores de JavaScript. Medido con eventos `animationstart` durante el
proceso de los 3 clips: 3 entradas de fila (una por clip), 3 rellenos de etapa, 3 checks y 3 avisos «listo para
revisar»; tras dos refrescos sin cambios, 0 animaciones nuevas y el contador quieto. Plegar y desplegar 6 veces a
800×1280: 16,7 ms por cuadro de media, peor cuadro 17 ms, también con la CPU de Chromium frenada ×4.
Capturas en `.playwright-mcp/movimiento/` (carpeta local, no se sube al repositorio).

**No probado:** la tablet real (la fluidez se midió en el Chromium del PC, no en la MatePad); arrastrar un archivo real
con el mouse (se simuló el evento); el check de «subido» y el de «momentos listos» (solo se vio el de «renderizado»);
Firefox y Safari.

**Fase 3 hecha (2026-11-17): Plantilla con vista previa en vivo.** Solo `web/` (`index.html`, `app.js`, `estilo.css`, `iconos.js`).

- Entrada nueva «Plantilla» en el menú (`#plantilla`). Sustituye a la pestaña «Diseño» de Ajustes, que desaparece
  (Ajustes abre ahora en YouTube). El enlace «Personalizar» del Resumen lleva aquí.
- Formulario por secciones: Encuadre, Pantalla completa (solo visible con ese estilo), Banner superior, Subtítulos,
  Marca y nombre (con el logo). Los 31 campos son ajustes reales de `config.py`; no se añadió ninguno.
- Vista previa en vivo: la maqueta la dibuja el PC (`/api/diseno/vista`) con los valores del formulario, guardados o
  no, 250 ms después del último cambio (varios cambios seguidos = una sola petición). Acompaña al desplazarse.
  Si el servidor rechaza un valor, su mensaje se muestra bajo la maqueta. «Texto de ejemplo» solo afecta a la vista.
- Estado visible: «Cambios sin guardar» / «Guardado». «Restablecer» pide confirmación. Subir o quitar el logo no
  borra lo que se esté editando.
- Tokens y movimiento del login: `--t-rapida`, `--sombra-flota`, `--curva`; entrada escalonada de las secciones y
  pulso de la maqueta con GSAP (`animar()`); sin GSAP o con «reducir movimiento» no se anima.
- Tamaños: dos columnas hasta 680 px (230 px de maqueta en tablet vertical); en móvil, o en tablet con la barra
  lateral desplegada, la vista previa pasa arriba.

Probado aquí (Chromium/Playwright, servidor temporal con datos vacíos) en 1440×900 y, por la IP de la red como
dispositivo vinculado, en 1280×800, 800×1280 (barra plegada y desplegada) y 600×900: vista previa al cambiar texto
de ejemplo, color, tamaño y estilo; valor imposible (error 400 visible); guardar y recargar; restablecer (cancelar y
aceptar); subir, quitar y rechazar un logo; salir con cambios sin guardar; guardar desde la tablet; sin desborde
horizontal, letra mínima 12 px, sin errores de JavaScript. Capturas en `docs/diseno/capturas-plantilla/`.
Prueba nueva: cada campo de la plantilla existe en `AJUSTES_POR_DEFECTO`. 78 pruebas tras integrar el cambio de la nube.

**No probado:** la tablet real; un render real con la plantilla cambiada (la maqueta y el render usan el mismo código
de disposición, pero no se generó un Short aquí). **Límites:** al salir de la vista con cambios sin guardar se
descartan sin preguntar (solo avisa la pastilla); el servidor guarda valores imposibles (p. ej. tamaño negativo) sin
validarlos, igual que antes: la maqueta muestra el error pero «Guardar» no lo impide.

**Falta:** fase 4 (Ajustes y ayuda).

## Beta 0.1 encontrada (2026-11-16)

Cristóbal indicó la carpeta `C:\Users\notea\Downloads\FabricaStudio`: es el trabajo anterior (beta 0.1,
fechada el 15-nov-2026). Revisada **solo leyendo**; no se copió nada al repositorio ni se ejecutó nada.

**Qué contiene** (20 archivos, sin `.venv`, sin EXE, sin APK, sin datos en `%LOCALAPPDATA%\FabricaStudio`):

- `app/server.py`: FastAPI + SQLite, cola con un trabajador, acceso por código de sesión, rutas en inglés
  (`/api/state`, `/api/jobs`, `/api/queue/pause`, `/api/admin/*`).
- `app/engine/`: `fabrica_gemini.py` (descarga, textos, Pillow, FFmpeg), `subtitulos.py`, `youtube_auto.py`
  (bibliotecas de Google; este repositorio usa REST con httpx).
- `app/web/diseno.html`: el prototipo de diseño. **Es el mismo archivo** que `docs/diseno/referencia-panel.html`
  (solo cambian los saltos de línea). `index.html` se genera con `build_frontend.py`, que toma ese HTML,
  sustituye los textos de «demo» y le pega `app.js`.
- `tests/` (28 pruebas con unittest), `LEEME.md`, `VALIDACION.md` (solo validado en Linux, nunca en Windows).
- Lanzadores `Instalar_y_abrir.cmd`, `Abrir_Fabrica.cmd`, `Crear_EXE.cmd` y `studio.spec` (PyInstaller).

**Credenciales:** no se encontró ninguna clave, token ni `client_secret` en esos archivos (búsqueda por
patrones de Google, OpenAI y claves privadas; la única coincidencia es la expresión que oculta claves en
los registros). No hay nada que revocar por esta carpeta.

**Ideas útiles para el panel nuevo**

- Confirma el plan: la beta ya quitó las curvas decorativas y los textos de demo de la referencia.
- Descarga del registro del trabajo y de un ZIP con el resultado (aquí no existe; posible ampliación).
- Pausar la cola (no inicia clips nuevos; el activo termina). Aquí no existe: sin botón hasta que el motor lo tenga.
- Texto de ayuda de `LEEME.md` para la MatePad (misma wifi, firewall solo redes privadas, red de invitados).

**Lo que no se reutiliza:** nombres de modelos de Gemini escritos a mano (regla 7), categoría 20 fija,
código de acceso por sesión (aquí hay vinculación por dispositivo), la plantilla con colores bloqueados.

**Para el .exe futuro** (`Crear_EXE.cmd` + `studio.spec`, nunca compilados en Windows):

- Sirve el enfoque: PyInstaller en modo carpeta (`COLLECT`, no un único archivo), `console=True`, `upx=False`,
  `collect_all` para `faster_whisper`, `ctranslate2`, `onnxruntime`, `av`, `tokenizers`, `yt_dlp`, `curl_cffi`
  y `collect_submodules('uvicorn')`; FFmpeg se copia aparte a `dist\...\bin`.
- Hay que adaptarlo: punto de entrada `fabrica_studio`, incluir `web/` completa y las fuentes, añadir OpenCV
  y el modelo YuNet, quitar las bibliotecas de Google, y fijar la versión de PyInstaller en su momento.

## Implementado

| Área | Qué hay |
| --- | --- |
| Importación | Archivo desde el panel, carpeta `1_clips_crudos` (espera a que termine la copia), enlace de Kick con yt-dlp. Rechazo de duplicados por hash. |
| Comprobación | Propiedades reales con ffprobe (tamaño, duración, rotación, audio). |
| Transcripción | faster-whisper local con tiempos por palabra. Una vez descargado el modelo funciona sin internet. |
| Textos | Banner, título y descripción normalizados. Gemini (modelo elegido de la lista de la API) o borrador local. |
| Subtítulos | Bloques cortos sincronizados, editables desde el panel. |
| Render | 1080×1920, H.264 + AAC, tarjeta con banner, video centrado, subtítulos, logo y nombre. Ajustes con maqueta en vivo. |
| Video largo | Transcribe, propone momentos (Gemini o heurística local), permite ajustar tiempos y crea clips que reutilizan la transcripción. |
| YouTube | OAuth de escritorio, verificación de canal por ID, subida reanudable siempre privada, protección contra duplicados. |
| Panel | Cola por etapas, biblioteca, vista previa, edición, ajustes, proveedores, dispositivos. Escritorio y tablet. |
| Acceso | PC directo; otros dispositivos con código de un solo uso. Acciones sensibles solo desde el PC. |
| Fiabilidad | Cola en SQLite, un archivo por etapa, reanudación tras reinicio, errores con causa y reintento. |
| Diagnóstico | `scripts\diagnostico.ps1` y botón en Ajustes → Proveedores: revisa FFmpeg, Whisper, GPU y hace un render de prueba. |
| Windows | Scripts de instalación, arranque y diagnóstico; manejo de archivos abiertos; rutas con espacios y acentos. |

## Pruebas realizadas

Entorno: contenedor Linux (4 CPU, 16 GB, sin GPU), Python 3.13, FFmpeg 6.1.

**Automáticas** — `python -m pytest`: 50 pruebas, todas pasan. No usan red ni descargan modelos.

- Render: un MP4 horizontal produce 1080×1920 H.264/AAC con la misma duración.
- Diseño: sin choques entre banner, video, subtítulos, logo y nombre en 16:9, 4:3, 1:1 y 9:16.
- Logo: recorta márgenes transparentes antes de escalar.
- Textos: límites, descripción en una línea reorganizada, hashtags sin repetir, `#GTA6` filtrado.
- Gemini simulado: elección de modelo, reintento ante 503, formato con adornos, caída al borrador local ante 429.
- Duplicados: mismo archivo, mismo tramo de un video largo, Short ya subido.
- Fallos: se conservan los intermedios; reintentar no repite la transcripción; un clip con error no detiene al siguiente; un reinicio retoma lo pendiente.
- Carpeta vigilada: no importa archivos a medio copiar; el original solo se mueve tras confirmar la subida.
- YouTube simulado: privado, categoría Gaming solo si corresponde, canal no confirmado rechazado, reanudación tras cortes, sin duplicar si el corte llega tras el último bloque, recuperación de un video ya subido.
- Acceso: 401 sin vincular, código de un solo uso, bloqueo tras 5 fallos, revocación, acciones sensibles vetadas fuera del PC, orígenes ajenos rechazados, secretos fuera de las respuestas.
- Video largo: propuestas válidas sin solaparse, validación de la respuesta de la IA, recorte exacto y transcripción desplazada, error claro si el original se eliminó.
- Rutas con espacios, acentos y «ñ» en la carpeta de datos y en el nombre del archivo.

**Manuales en el contenedor**

- Flujo real con faster-whisper `small` en CPU sobre clips sintéticos (imagen de prueba y
  **voz sintética** en español): un clip de 15 s tarda unos 12 s con el modelo ya descargado.
  Transcripción buena pero no perfecta («Poye chat… cree» por «Oye chat… creer»).
- Video largo real de 63 s: transcripción, una propuesta de 38 s por heurística, creación
  del clip y render, todo desde el panel.
- Arranque con internet bloqueado: el modelo ya descargado se usa sin conexión.
- Panel con Playwright/Chromium a 1280×800 y 800×1280: importar, duplicados, enlace no
  compatible, edición, re-render, biblioteca, ajustes, diagnóstico, código de vinculación,
  video largo. Sin desbordes horizontales ni errores de JavaScript.

## Comprobado en el PC Windows

Entorno: Windows 11 Home, Python 3.13.15 en `.venv`, FFmpeg 9.0.2 full_build (Gyan), GTX 1650.
Proyecto en `OneDrive\Escritorio\Fabricastudio`; datos fuera de OneDrive con
`FABRICA_DATOS=C:\FabricaStudio_datos` (variable de usuario ya definida).

- `scripts\instalar.ps1` termina con «Instalación terminada» (ahora instala también pytest).
- `.\.venv\Scripts\python.exe -m pytest`: **48 pasan** (las 47 originales sin cambios + 1 nueva de fechas;
  antes del arreglo de YouTube fallaba 1; ver Registro).
- `scripts\diagnostico.ps1`: todo `[ OK ]`, incluido libass, H.264/AAC, autoprueba de render y
  «GPU para Whisper» detectada (GTX 1650, 4 GB). No se ha probado Whisper en GPU.
- Panel arrancado con `.\.venv\Scripts\python.exe -m fabrica_studio`: `http://127.0.0.1:8765` responde 200.
- **Primer Short real:** `Descargas\clip_01JTZ79TQ46787D3MCG4FAY56P.mp4` (Kick, 1920×1080, 18 s),
  importado por la API del panel (`/api/importar/archivo`, la misma que usa el botón).
  Trabajo `20261116-140757-1342e3` → `renderizado` en ~25 s con CPU (Whisper `small` ya descargado
  en ese primer uso). Salida 1080×1920 H.264/AAC, 18,0 s; copia en `2_shorts_renderizados`.
  Textos con el borrador local (sin Gemini). Revisado con dos fotogramas extraídos, no reproducido entero.
- YouTube real (en curso): cliente OAuth de escritorio creado por Cristóbal y cargado con la API del
  panel → `C:\FabricaStudio_datos\secretos\client_secret.json` (tipo `installed`, fuera del repositorio).
  El enlace `/api/youtube/conectar` redirige a Google con alcances `youtube.upload` y `youtube.readonly`
  y regreso a `http://127.0.0.1:8765/api/youtube/callback`.
- **Autorización real hecha** por Cristóbal en su navegador: Google entregó token de renovación
  (`secretos\youtube_token.json`, fuera del repositorio). La API real devolvió un canal:
  nombre «Paltita», `@paltitaclips`, ID `UCTxlp22T7KxKH6REgAJ9gHQ`. Cristóbal comparó el ID en
  YouTube Studio y se confirmó como canal de destino.
- **Subida real (Y3), 2026-11-16:** el trabajo `20261116-140757-1342e3` (sin `youtube_id` ni sesión previa)
  se subió una vez por `/api/trabajos/<id>/subir` con sus textos guardados. YouTube devolvió el ID
  `jEo0C6qTsLA` (https://youtu.be/jEo0C6qTsLA). Consultado con la API `videos`: canal
  `UCTxlp22T7KxKH6REgAJ9gHQ`, `privacyStatus: private`, `madeForKids: false`, categoría 24
  (Entretenimiento; no es Gaming), título con tildes correctas, `uploadStatus: uploaded`, procesándose.
  El trabajo quedó `publicado`.
- **Subida automática activada** (`subida_automatica = true`) tras la prueba: los trabajos nuevos con
  «publicar» se suben en privado al canal confirmado al terminar el render. El pie lateral del panel
  muestra «Subida automática: activa (privado)».
- **Falta:** Y4 (no se probó en real pulsar subir otra vez) e Y5.

Pendiente de valorar por Cristóbal en ese Short: transcripción («a la vía, hermano» puede ser un
error de Whisper), legibilidad de subtítulos, banner y logo. El clip trae bordes negros propios
(contenido 1614×918 arriba a la izquierda), por eso el video se ve descentrado en el Short.

## Comprobaciones que requieren a Cristóbal

Ninguna de estas se puede hacer desde la nube. Están ordenadas: cada una depende de la anterior.

### En el PC Windows 11

- [x] **W1. Instalación.** Comprobado por Claude Code en el PC (2026-11-16).
- [x] **W2. Diagnóstico.** Sin `[FALLA]` (2026-11-16).
- [x] **W3. Arranque.** El servidor responde en `http://127.0.0.1:8765`. Falta que Cristóbal
      lo abra en su navegador y lo arranque él con `scripts\iniciar.ps1`.
- [ ] **W4. Clip real.** Render hecho (18 s, ~25 s de proceso). **Falta la valoración de Cristóbal**:
      transcripción de modismos chilenos, legibilidad de subtítulos, banner y logo. Probar también un
      clip más largo y con música de fondo.
- [ ] **W5. Re-render con la vista previa abierta.** Cambiar el banner mientras el video se
      reproduce: en Windows el archivo queda bloqueado; debe reintentarse solo o avisar con claridad.
- [ ] **W6. Carpeta vigilada.** Copiar un video grande a `datos\1_clips_crudos` y comprobar
      que no entra a la cola hasta terminar la copia.
- [ ] **W7. Reinicio.** Cerrar PowerShell a mitad de un proceso y volver a iniciar: el trabajo debe retomarse.
- [ ] **W8. Enlace de Kick.** Pegar un enlace público real. Si Kick lo bloquea, el panel debe decirlo.
- [ ] **W9. Video largo real** (20 minutos o más): tiempo de transcripción y calidad de las propuestas.

### Con la GPU (GTX 1650)

- [x] **G1.** CUDA detecta la GTX 1650 (4096 MiB, controlador 610.91). Falta G2. En el diagnóstico, la línea «GPU para Whisper» indica si CUDA está disponible.
- [ ] **G2.** Si lo está: Ajustes → Proveedores → Dispositivo «GPU NVIDIA» y comparar tiempos con CPU.
      Si no: hace falta instalar las librerías cuDNN/cuBLAS de NVIDIA; se verá cuando toque.
      La GPU es opcional: todo funciona en CPU.

### Con la tablet (MatePad 11.5 S)

- [ ] **T1.** Aceptar el aviso del firewall de Windows para redes privadas.
- [ ] **T2.** Abrir `http://IP-del-PC:8765` en el navegador de la tablet, por wifi de casa.
- [ ] **T3.** Vincular con el código y comprobar: ver la cola, importar un archivo, reproducir la vista previa.

Desde datos móviles la tablet no alcanza el PC: el acceso fuera de casa es una ampliación futura.

### Con autorización de Google / YouTube

- [x] **Y1.** Cliente OAuth de escritorio creado y cargado (2026-11-16).
- [x] **Y2.** Cuenta conectada; canal confirmado por ID `UCTxlp22T7KxKH6REgAJ9gHQ` («Paltita», @paltitaclips) (2026-11-16).
- [x] **Y3.** Subida privada `jEo0C6qTsLA` verificada por la API (2026-11-16). Falta que Cristóbal la mire en YouTube Studio.
- [ ] **Y4.** Pulsar subir otra vez sobre el mismo trabajo: debe negarse.
- [ ] **Y5.** Cortar el wifi a mitad de una subida y reintentar: debe continuar, no duplicar.

### Con una clave de Gemini

- [ ] **A1.** Ajustes → Proveedores → guardar la clave y pulsar «Probar»: lista los modelos disponibles.
- [ ] **A2.** Regenerar los textos de un clip real y valorar banner, título y descripción.
- [ ] **A3.** Proponer momentos de un video largo con la IA y compararlos con la heurística.

## Pasos para continuar en Windows

1. **Obtener el código** (PowerShell, en la carpeta donde quieras guardarlo, por ejemplo `Documentos`):
   ```powershell
   git clone https://github.com/ykvvvv/Fabricastudio
   cd Fabricastudio
   git checkout claude/fabrica-studio-shorts-x34of8
   ```
   Si `git` no existe: `winget install Git.Git` y reabrir PowerShell. No uses el ZIP antiguo
   salvo que no haya otra opción: el repositorio es la fuente de verdad.
2. **PowerShell**, dentro de la carpeta del proyecto: `.\scripts\instalar.ps1`.
3. **PowerShell:** `.\scripts\diagnostico.ps1` y pegar la salida en el chat.
4. **PowerShell:** `.\scripts\iniciar.ps1`. **Navegador:** `http://127.0.0.1:8765`.
5. Importar un clip real y seguir la lista W4 en adelante.

Los detalles (requisitos, permisos de PowerShell, YouTube, Gemini) están en [README.md](README.md).

## Dependencias

- Para instalar en Windows: Git (`winget install Git.Git`), Python 3.12 (`winget install Python.Python.3.12`)
  y FFmpeg (`winget install Gyan.FFmpeg`). El resto lo instala `scripts\instalar.ps1` dentro de `.venv`.
- `requirements.txt`: FastAPI, uvicorn, python-multipart, httpx, Pillow, faster-whisper, yt-dlp (con curl-cffi).
- `requirements-dev.txt`: pytest.
- Externas: Python 3.10 o superior y FFmpeg con libass, libx264 y AAC.
- No se usan Google Play Services, Node ni compilación de interfaz.

## Qué no entra al repositorio

`.gitignore` excluye: `datos/` (cola, clips, modelos, credenciales), `.env` y `.env.*`,
`client_secret*.json`, `token*.json`, almacenes de claves de firma, y todo archivo de
video, audio o ZIP. Los clips de prueba se generan con FFmpeg durante las pruebas.

## Decisiones

| Decisión | Motivo |
| --- | --- |
| Python + FastAPI + SQLite + web sin compilación | Pocas piezas, fácil de instalar en Windows y de entender. |
| Tablet mediante navegador, no APK (por ahora) | Funciona en HarmonyOS sin Google Play Services y sin firmar nada. |
| Un archivo por etapa en la carpeta del trabajo | Reintentar o cambiar el diseño no repite transcripción ni consume API. |
| Whisper en CPU por defecto (`small`, int8) | Funciona en cualquier PC. La GPU requiere librerías extra y no se ha probado. |
| Gemini por REST, modelo elegido de la lista de la API | No depender de nombres de modelos que cambian. |
| Si Gemini falla, alternativa local con aviso | Un fallo del proveedor no detiene el clip; se puede regenerar después. |
| Subtítulos ASS quemados con fuente Inter incluida (OFL) | No depender de Arial ni de fuentes del sistema. |
| Logo: rótulo de texto «KICK» por defecto; el logo real lo sube el usuario | No se redistribuye una marca sin permiso. |
| OAuth de escritorio con redirección a 127.0.0.1 | Flujo correcto para una app local. |
| Privacidad fija en «private» | No publicar en público sin autorización explícita. |
| Acciones sensibles solo desde 127.0.0.1 | La tablet controla la cola pero no ve ni cambia credenciales. |
| Video largo: el clip se recorta recodificando | Corte exacto al fotograma; el copiado directo corta en fotogramas clave. |
| Los clips de un video largo heredan su transcripción | No transcribir dos veces el mismo audio. |

## Problemas conocidos y límites

- El borrador local de textos y la heurística de momentos son básicos; la calidad editorial depende de Gemini.
- Los subtítulos no resaltan palabra por palabra ni llevan emojis.
- La restricción de edad no se configura por API; «no creado para niños» sí se envía.
- El panel usa HTTP sin cifrar: adecuado solo para la red doméstica.
- Un video largo se transcribe entero antes de proponer: en CPU puede tardar bastante.
- Sin empaquetado EXE ni APK todavía.
- Los entregables anteriores (notebook de Colab, ZIP de Windows, APK, HTML Ember) no estaban
  en el repositorio; esta base es nueva.
- Clips con bordes negros propios (p. ej. capturas de Kick) quedan descentrados: el render centra el
  cuadro completo. Posible mejora: recorte automático con `cropdetect` (sin hacer).
- Codex CLI 0.169.0 instalado en el PC (2026-11-16); primera revisión de solo lectura hecha (ver Registro).
  Pendiente de esa revisión, sin aplicar: README (política de ejecución, `Unblock-File`) y
  comprobar en `instalar.ps1` la versión de Python de un `.venv` existente.

## Seguridad: acción pendiente de Cristóbal

Una clave de OpenAI se compartió antes en un chat. Considérala comprometida:
revócala en platform.openai.com → API keys si sigue activa. Este proyecto no usa OpenAI.

## Siguientes pasos de desarrollo

1. Corregir lo que aparezca en las comprobaciones W1–W9 (archivos según el fallo).
2. Subtítulos con resaltado por palabra y estilos (`subtitulos.py`, `render.py`, panel).
3. Aviso de progreso durante transcripciones largas (`transcribe.py`, `pipeline.py`).
4. Evaluar OpenShorts como motor alternativo (investigación; sin tocar código).
5. Empaquetado para Windows y decisión sobre el APK, cuando el flujo base esté verificado en el PC.
6. Acceso fuera de casa, solo si se justifica y con autorización.

## Registro

- **2026-11-16 · Claude Code** — Base 0.2 desde cero: flujo completo hasta render, panel, cola
  persistente, carpeta vigilada, vinculación, módulo de YouTube. 37 pruebas.
- **2026-11-16 · Claude Code** — 0.3: modo video largo, diagnóstico del equipo, Whisper sin
  conexión, endurecimiento para Windows (archivos abiertos, rutas con acentos, consola UTF-8),
  `.gitignore` ampliado. 47 pruebas; prueba real de video largo desde el panel. Envío a GitHub rechazado (403).
- **2026-11-16 · Claude Code** — Acceso a GitHub corregido: rama enviada y verificada. ESTADO.md
  actualizado para continuar en Windows. Siguiente: Cristóbal clona en su PC y ejecuta W1–W4.
- **2026-11-16 · Claude Code (nube)** — Diseño ajustado a la referencia de PaltitaClips (medido),
  palabra activa resaltada, firma `@jongottii`, recorte de franjas negras, fuente Inter Black.
  50 pruebas pasan. Pendiente: logo oficial, comprobación con clip real en el PC, revisión de chats de Codex.
- **2026-11-16 · Claude Code** — Proyecto clonado en el PC de Cristóbal (`OneDrive\Escritorio\Fabricastudio`).
  Scripts .ps1 pasados a UTF-8 con BOM (PowerShell 5.1 mostraba mal los acentos). W1, W2 y G1 verificados
  en Windows. Siguiente: W3–W4 (arrancar el panel y procesar un clip real), luego G2.
- **2026-11-16 · Claude Code (PC Windows)** — Rediseño visual del panel (solo `web/estilo.css` y
  `theme-color`): grafito azulado con acento ámbar, títulos en Inter, barra de etapas como cinta
  (la etapa en curso se anima; respeta «reducir movimiento»). `app.js` sin cambios. Revisado con
  capturas de Playwright a 1280 px y 800 px con trabajos de ejemplo inyectados; falta verlo en la tablet real.
  El `.venv` del PC no tiene pytest: instalar `requirements-dev.txt` para correr las pruebas.
- **2026-11-16 · Claude Code + Codex (PC Windows)** — Codex revisó en solo lectura instrucciones y scripts.
  Aplicado: `instalar.ps1` instala también `requirements-dev.txt`; `iniciar.ps1` y `diagnostico.ps1`
  devuelven el código de salida de Python; bloque de comandos para Windows en `CLAUDE.md`.
  Arreglado un error real en `youtube.py` (`_buscar_reciente`): convertía la hora UTC de YouTube con
  `mktime - timezone`, que en horario de verano de Chile desfasa 1 h e impedía reconocer un video ya
  subido (riesgo de duplicado tras un corte). Ahora usa `calendar.timegm`. Lo destapó
  `test_sesion_perdida_recupera_video_ya_subido`, que en la nube (UTC) pasaba. 47/47 pruebas.
  Primer Short real renderizado en el PC (ver «Comprobado en el PC Windows»). Siguiente: Cristóbal
  valora el Short (W4) y sigue con W5–W9; después Gemini (A1) y YouTube (Y1–Y5).
- **2026-11-16 · Claude Code (PC Windows)** — Fechas de YouTube revisadas: la documentación de la API
  solo dice «ISO 8601» (sin zona explícita; el perfil W3C que enlaza exige `Z` o `±hh:mm`). Nueva
  `_instante_iso()` en `youtube.py` respeta la zona escrita en el valor; sin zona lanza ValueError en vez
  de adivinar. Prueba nueva independiente de la zona del PC. 48/48. `.gitignore`: `token*.json` →
  `*token*.json` (cubre `youtube_token.json`). Panel reiniciado. Cliente OAuth cargado (Y1).
- **2026-11-16 · Claude Code (PC Windows)** — Prueba Y3: subida privada real `jEo0C6qTsLA` verificada por
  la API; subida automática activada y visible en el pie del panel (`app.js`). Revisadas en solo lectura
  las sesiones de Codex en busca del trabajo anterior (APK, Colab, ZIP, Ember): no contienen nada del
  proyecto y no hay carpeta `referencias` (ver «Trabajo anterior en Codex/ChatGPT y el APK»).
- **2026-11-16 · Claude Code (nube)** — Estilo pantalla completa con seguimiento de rostros (fase 1 de
  `docs/ESTILO_OPUSCLIP.md`), selector de estilo general y por clip, diagnóstico de OpenCV. 61 pruebas.
  Siguiente: Cristóbal reinstala dependencias y prueba 3–5 clips reales en ambos estilos.
- **2026-11-16 · Claude Code (PC Windows)** — Beta 0.1 de `Descargas\FabricaStudio` revisada en solo lectura (sin
  credenciales). Panel nuevo, fase 1: estructura, Resumen, Cola con filtros, ventana «Nuevo clip», campo
  `duracion` en la API. 62 pruebas. Siguiente: Cristóbal revisa en el navegador y pide la fase 2.
- **2026-11-17 · Claude Code (nube)** — `importar.py`: solo se aceptan enlaces de Kick a un clip
  (`/canal/clips/clip_…`, `?clip=clip_…`) o a un video (`/canal/videos/<id>`, `/video/<id>`). Antes se
  aceptaba la página de clips del canal y se intentaba descargarla. Límite de un solo video por enlace
  (`playlistend`). 63 pruebas. Falta probar con un enlace real de Kick en el PC.
- **2026-11-17 · Claude Code (PC Windows)** — Fase 2 del panel en su propio commit. Fase de movimiento: barra lateral
  plegable (botón y Ctrl+B), contadores, progreso en vivo con check y aviso, entrada escalonada solo de elementos nuevos,
  esqueletos de carga, zona de soltar, salida de ventanas y avisos; todo respeta «reducir movimiento». 63 pruebas (con la del enlace de Kick que llegó de la nube).
  Siguiente: Cristóbal lo revisa en el navegador y en la tablet; después, fase 3 (Plantilla).
- **2026-11-17 · Claude Code (nube)** — `Abrir Fabrica Studio.cmd`: abre el panel con doble clic
  (ejecuta `scripts\iniciar.ps1` sin cambiar la política de ejecución global). Sin probar en Windows.
- **2026-11-17 · Claude Code (nube)** — Login en el servidor (`cuentas.py`, tablas `cuenta` y `sesiones`,
  rutas de cuenta/login/logout/sesiones) con 8 pruebas nuevas; 71 pasan. Falta la pantalla de login y
  las animaciones (Claude Code del PC, con las skills GSAP, Three.js, Motion Design y Design DNA).
- **2026-11-17 · Claude Code (PC Windows)** — Plan de diseño del login en `docs/diseno/plan-login.md` (sin código):
  tokens, movimiento, bocetos y GSAP/Three.js locales. Instaladas skills de diseño en `.claude/skills/` (sin versionar).
  Siguiente: Cristóbal responde las decisiones del §6 y se implementa la fase A (pantallas solo con CSS).
- **2026-11-17 · Claude Code (nube)** — Login: el 429 llega en el 5.º fallo y `GET /api/sesion` expone
  `espera_login` (decisión 2 del plan de login). Prueba ampliada.
- **2026-11-17 · Claude Code (PC Windows)** — Login, fase 1: pantallas de bienvenida/crear cuenta, login con error y
  bloqueo con cuenta regresiva, pestaña Cuenta y menú de usuario, solo con CSS y contra la API real. Prueba nueva
  `tests/test_web.py` (sin recursos de internet; acciones e iconos enlazados). 73 pruebas. Playwright en escritorio
  y tamaño tablet; capturas en `docs/diseno/capturas-login/`. Siguiente: Cristóbal lo revisa en el navegador y en la tablet; después, fase 2 (GSAP).
- **2026-11-17 · Claude Code (PC Windows)** — Login, fase 2: GSAP 3.15.1 local en `web/vendor/` (con huella y licencia) y
  líneas de tiempo del acceso: bienvenida, entrada del login, transición al panel sin recargar y salida al cerrar sesión.
  Prueba nueva de la huella del archivo. 74 pruebas. Playwright en escritorio y tamaños de tablet y móvil.
  Siguiente: Cristóbal valora el movimiento en el PC y en la tablet; después decide si se hace la fase 3 (Three.js).
- **2026-11-17 · Claude Code (nube)** — VOD completo a Shorts sin intervención: ajustes `momentos_auto`
  (por defecto desactivado) y `momentos_auto_solo_ia` (por defecto activado: con la heurística local solo avisa).
  Gemini analiza VODs largos por tramos (antes fallaba con más de ~1 h y caía a la heurística). 77 pruebas.
  **Falta en el panel:** dos interruptores en Ajustes (Claude Code del PC, fase 4). Sin probar con un VOD real.
- **2026-11-17 · Claude Code (PC Windows)** — Panel, fase 3: vista «Plantilla» con vista previa en vivo (sustituye a
  Ajustes → Diseño), con los tokens y el movimiento GSAP del login. 78 pruebas (con las de la nube). Playwright en escritorio, tablet y móvil;
  capturas en `docs/diseno/capturas-plantilla/`. Siguiente: Cristóbal la revisa y prueba un render real; después, fase 4.
