# Estado de Fábrica Studio

Registro compartido entre Cristóbal, Claude Code y Codex. Última actualización: 2026-11-16.

## Resumen

Versión 0.2: flujo de clip seleccionado completo hasta el render, con panel web,
cola persistente, carpeta vigilada, vinculación de tablet y subida privada a YouTube
implementada pero **sin probar contra YouTube real** (faltan credenciales).

## Punto de partida

- El repositorio estaba vacío: ninguno de los entregables anteriores
  (`Fabrica_Shorts_Gemini.ipynb`, `Fabrica_Studio_Windows_Beta_0_1.zip`,
  `Fabrica_Studio_Tablet_0_1.apk`, `Fabrica_Studio_Ember.html`…) estaba disponible.
  Esta base es nueva. Si Cristóbal los conserva, se pueden revisar para rescatar ideas.
- Codex Plugin CC, Replica, OpenShorts, Ponytail y las demás skills mencionadas **no
  están instaladas** en el entorno de desarrollo usado. Nada fue revisado por Codex.

## Decisiones

| Decisión | Motivo |
| --- | --- |
| Python + FastAPI + SQLite + web sin compilación | Pocas piezas, fácil de instalar en Windows y de entender. |
| Tablet mediante navegador, no APK (por ahora) | Funciona en HarmonyOS sin Google Play Services y sin firmar nada. |
| Un archivo por etapa en la carpeta del trabajo | Reintentar o cambiar el diseño no repite transcripción ni consume API. |
| Whisper en CPU por defecto (`small`, int8) | Funciona en cualquier PC. La GPU (GTX 1650) requiere cuDNN y no se ha probado. |
| Gemini por REST, modelo elegido de la lista que devuelve la API | No depender de nombres de modelos que cambian. |
| Si Gemini falla, borrador local y aviso | Un fallo del proveedor no detiene el clip; se puede regenerar después. |
| Subtítulos ASS quemados por FFmpeg con fuente Inter incluida (OFL) | No depender de Arial ni de fuentes del sistema. |
| Logo: rótulo de texto «KICK» por defecto; logo real lo sube el usuario | No se redistribuye una marca sin permiso. |
| OAuth de escritorio con redirección a 127.0.0.1 | Flujo correcto para una app local; evita la confusión escritorio/web. |
| Privacidad fija en «private» | No publicar en público sin autorización explícita. |
| Acciones sensibles solo desde 127.0.0.1 | La tablet controla la cola pero no ve ni cambia credenciales. |

## Pruebas realizadas

Entorno: contenedor Linux (4 CPU, 16 GB, sin GPU), Python 3.13, FFmpeg 6.1. **No Windows.**

Automáticas (`python -m pytest`, 37 pruebas, todas pasan):

- Un MP4 horizontal produce 1080×1920, H.264 + AAC, misma duración.
- Disposición sin choques para 16:9, 4:3, 1:1 y 9:16: banner sobre el video, subtítulos
  bajo el video, logo bajo los subtítulos, nombre bajo el logo, todo dentro del lienzo.
- El logo recorta márgenes transparentes antes de escalar.
- Textos: límites de banner y título, descripción en una línea reorganizada, hashtags
  deduplicados, `#GTA6` filtrado si la transcripción no lo menciona.
- Gemini simulado: elección de modelo, reintento ante 503, JSON con cercas de código,
  caída a borrador local con explicación ante 429.
- Duplicados: el mismo archivo no crea dos trabajos; un trabajo subido no vuelve a subir.
- Un fallo conserva resultados intermedios; reintentar no repite la transcripción.
- Un clip con error no detiene al siguiente; un reinicio retoma lo que estaba a medias.
- Carpeta vigilada: no importa archivos que aún se están copiando; el original solo
  se mueve a `3_procesados_ok` tras confirmar la subida.
- YouTube simulado: subida privada, categoría Gaming solo si corresponde, rechazo de
  canal no confirmado, reanudación tras cortes, corte tras el último bloque sin
  duplicar, recuperación de un video ya subido cuando la sesión se pierde.
- Acceso: tablet sin vincular recibe 401; código de un solo uso; bloqueo tras 5
  fallos; revocación; acciones sensibles vetadas fuera del PC; rechazo de orígenes ajenos.

Manuales en el contenedor:

- Flujo real con faster-whisper `small` en CPU sobre un clip sintético 1280×720 de
  15 s con **voz sintética** en español: Short correcto en unos 30 s. La transcripción
  fue buena pero no perfecta («Poye chat… cree» por «Oye chat… creer»).
- Panel con Playwright/Chromium a 1280×800 y 800×1280: importar, rechazo de duplicado
  y de enlace no compatible, editar textos, re-render, biblioteca, ajustes, generación
  de código. Sin desbordes horizontales ni errores de JavaScript.

## Pendiente de probar (no dar por hecho)

- [ ] **Un clip real de Jongottii** (voz real, modismos chilenos, música de fondo).
- [ ] Instalación y arranque en Windows 11 (`scripts\instalar.ps1`, `iniciar.ps1`).
- [ ] Panel desde la MatePad real por wifi (navegador de HarmonyOS, firewall de Windows).
- [ ] Importación por enlace de Kick: implementada con yt-dlp, **nunca ejecutada contra
      Kick** (el entorno de desarrollo no tiene acceso). Kick usa Cloudflare y puede bloquearla.
- [ ] Gemini real (hace falta una clave de API).
- [ ] OAuth y subida privada reales a YouTube; verificación del ID de PaltitaClips.
- [ ] Whisper en GPU (GTX 1650): requiere librerías cuDNN/cuBLAS.
- [ ] Videos largos (más de 10 minutos) y archivos de varios GB.

## Problemas conocidos y límites

- El borrador local de textos es básico (frases literales). La calidad editorial depende de Gemini.
- Los subtítulos no resaltan palabra por palabra ni llevan emojis.
- La restricción de edad no se configura por API en esta versión; «no creado para
  niños» sí se envía.
- El panel usa HTTP sin cifrar: adecuado solo para la red doméstica.
- Sin empaquetado EXE ni APK todavía.

## Seguridad: acción pendiente de Cristóbal

Una clave de OpenAI se compartió antes en un chat. Considérala comprometida:
revócala en platform.openai.com → API keys si sigue activa. Este proyecto no usa OpenAI.

## Siguientes pasos

1. **Cristóbal:** instalar en Windows y procesar un clip real. Reportar el resultado.
2. **Cristóbal:** crear credenciales OAuth (README) y probar una subida privada.
3. Modo video largo: detectar y proponer momentos (`pipeline.py`, nuevo `momentos.py`, panel).
4. Subtítulos con resaltado por palabra y estilos (`subtitulos.py`, `render.py`).
5. Evaluar OpenShorts como motor alternativo (investigación; no tocar código).
6. Empaquetado Windows (PyInstaller) y decidir si hace falta APK o basta el navegador.
7. Acceso remoto fuera de casa (túnel o nube), solo si se justifica.

## Registro

- **2026-11-16 · Claude Code** — Base 0.2 creada desde cero: flujo completo hasta render,
  panel, cola persistente, carpeta vigilada, vinculación, módulo de YouTube. 37 pruebas
  automáticas pasan; prueba real de transcripción y render en Linux; panel probado con
  Playwright. Sin probar: Windows, tablet real, Kick, Gemini y YouTube reales.
