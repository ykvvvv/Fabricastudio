# Estado de Fábrica Studio

Registro compartido entre Cristóbal, Claude Code y Codex. Última actualización: 2026-11-16.

## Resumen

Versión 0.3 en desarrollo. Funciona en el entorno de nube (Linux): clip seleccionado
→ Short vertical, modo video largo con propuesta de momentos, panel web, cola
persistente, carpeta vigilada, vinculación de tablet y diagnóstico del equipo.
La subida a YouTube está implementada y probada solo contra un YouTube simulado.

En el PC Windows ya funcionan la instalación y el diagnóstico (W1, W2, G1). Falta procesar un clip real. La tablet no se ha probado.

## Repositorio y rama

- Repositorio: https://github.com/ykvvvv/Fabricastudio
- Rama con los últimos avances: `claude/fabrica-studio-shorts-x34of8` (es la única rama).
- Enviado a GitHub y verificado el 2026-11-16: el commit remoto coincide con el local.
  Los envíos anteriores fallaron con 403; se resolvió al corregir el acceso de Claude a GitHub.
- Todo el desarrollo hasta ahora se hizo en una sesión de Claude Code **en la nube (Linux)**.
  El PC de Cristóbal todavía no tiene una copia: hay que clonarla (ver «Pasos para continuar en Windows»).

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

## Comprobaciones que requieren a Cristóbal

Ninguna de estas se puede hacer desde la nube. Están ordenadas: cada una depende de la anterior.

### En el PC Windows 11

- [x] **W1. Instalación.** Hecho el 2026-11-16. `scripts\instalar.ps1` termina con «Instalación terminada».
- [x] **W2. Diagnóstico.** Hecho el 2026-11-16: todo OK (Windows 11, Python 3.13.15, FFmpeg 9.0.2 de Gyan con libass, autoprueba 1080×1920). Datos en `C:\FabricaStudio_datos` (fuera de OneDrive, variable `FABRICA_DATOS`). `scripts\diagnostico.ps1` sin líneas `[FALLA]`. Pegar la salida en el chat.
      Riesgo principal: que el FFmpeg instalado no traiga el filtro `ass` (el de Gyan sí lo trae).
- [ ] **W3. Arranque.** `scripts\iniciar.ps1` y abrir `http://127.0.0.1:8765`.
- [ ] **W4. Clip real.** Procesar un clip de Jongottii y valorar: transcripción de modismos
      chilenos con música de fondo, legibilidad de subtítulos, posición del banner y del logo.
      Anotar cuánto tarda.
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

- [ ] **Y1.** Crear el cliente OAuth de escritorio en Google Cloud (pasos en el README).
- [ ] **Y2.** Conectar la cuenta y comprobar que el canal mostrado es PaltitaClips, **por su ID**.
- [ ] **Y3.** Subir un Short en privado y verificarlo en YouTube Studio: privado, «no creado para niños», categoría correcta.
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
- Codex, Replica, OpenShorts y Ponytail no están instalados en el entorno usado. Nada fue revisado por Codex.

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
