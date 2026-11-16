# Estilo tipo OpusClip: especificación y hoja de ruta

Objetivo de Cristóbal: que los clips puedan verse como los de OpusClip, con el video a
pantalla completa, un encuadre que sigue a las personas como un zoom y subtítulos grandes
sobre la imagen, y más adelante la vista dividida (dos encuadres apilados).

Esta es una implementación propia. No se reproducen los modelos internos de OpusClip ni se
promete el mismo resultado: cada fase se valida con clips reales de Jongottii.

El estilo **clásico** (video completo centrado con tarjeta) se mantiene siempre disponible
(regla 9 de CLAUDE.md).

## Cómo hace OpusClip ese efecto

| Efecto | Qué es técnicamente |
| --- | --- |
| «Zoom» que llena la pantalla | Recorte 9:16 de un video 16:9 (se usa ~32 % del ancho) escalado a 1080×1920 |
| El encuadre sigue a la persona | Detección de rostros por fotograma y una cámara virtual suavizada |
| Cambia entre personas | Detección de **quién habla** (hablante activo) y corte al cambiar |
| Vista dividida | Dos recortes apilados (p. ej. facecam arriba y juego abajo, o dos personas) |
| Subtítulos grandes animados | Texto en mayúsculas con contorno, palabra activa resaltada y animación al aparecer |
| Indicador «baja resolución» | Solo es la vista previa del editor; el render final sale en alta calidad |

## Fase 1 — Pantalla completa con seguimiento ✅ implementada (2026-11-16)

- Ajuste general `estilo`: `clasico` | `completo`. Cada clip puede usar otro estilo desde su página.
- `reencuadre.py`: detección de rostros con **YuNet** (OpenCV, modelo de 230 KB con licencia MIT
  incluido en `assets/modelos/`), 5 fotogramas por segundo a 640 px.
- Cámara virtual: sigue al rostro más grande; encuadra al grupo si caben dos o más; no reacciona a
  temblores (zona muerta del 6 %); se desplaza suave en movimientos medianos; **corta** en saltos
  grandes (cambio de plano); en huecos sin rostro mantiene la última posición; sin rostros, centrado.
- Render: el filtro `sendcmd` mueve el `crop` de FFmpeg fotograma a fotograma.
- Subtítulos de pantalla completa: Inter Black, mayúsculas, contorno grueso, palabra activa en verde.
- El análisis se guarda en `encuadre.json`: cambiar diseño o estilo no repite el análisis.
- Ajustes: zoom, posición del banner, subtítulos y logo, tamaño de subtítulos, mayúsculas, mostrar banner.
- Si falta OpenCV o el modelo, el encuadre queda centrado con un aviso; el trabajo no se detiene.

**Pendiente de validar con clips reales (Cristóbal, PC):** IRL caminando, dos personas, poca luz,
streamer con facecam pequeña. Medir tiempo de análisis en la GTX 1650/CPU.

## Fase 2 — Vista dividida (arriba y abajo)

Dos variantes, porque resuelven casos distintos:

**2a. Facecam + contenido (streams de juego o reacción)**
- El streamer suele tener la cámara en una esquina fija. Se define una vez por creador:
  en el panel, sobre un fotograma del clip, se marca el rectángulo de la facecam.
- Render: facecam ampliada arriba (≈40 % del alto) y el contenido recortado abajo (≈60 %).
- Archivos: `config.py` (preset por creador), `render.py` (dos `crop` + `vstack`), panel (selector de zona).
- Detección automática de la facecam: opcional después (rostro que se mantiene fijo en una esquina).

**2b. Dos personas (IRL, conversación)**
- Si hay dos rostros que no caben juntos en 9:16 durante más de ~2 s, apilar un recorte por persona.
- Reutiliza `encuadre.json` (ya contiene todos los rostros por muestra).
- Archivos: `reencuadre.py` (seguimiento de dos pistas), `render.py` (`vstack` con dos `sendcmd`).

## Fase 3 — Hablante activo

- Elegir a quién encuadrar según **quién habla**, no solo el rostro más grande.
- Opción local y gratuita: combinar los tiempos de voz de Whisper con el movimiento de la boca
  (puntos faciales que YuNet ya entrega) para estimar quién habla en cada tramo.
- Requiere pruebas con clips reales; es el punto más difícil y no se promete precisión.

## Fase 4 — Subtítulos animados y extras

- Animación al aparecer cada palabra (escala o rebote) con etiquetas ASS (`\t`, `\fscx`).
- Plantillas de subtítulos seleccionables (colores, fuente, posición).
- Emojis contextuales opcionales, con un set de emojis de licencia libre (p. ej. Twemoji, CC-BY).
- Sin promesas de gráficos idénticos a los de iPhone.

## Fase 5 — Selección de momentos mejorada (modo video largo)

- Ya existe la propuesta de momentos (Gemini o heurística). Se puede sumar la energía del audio
  (risas, gritos) y los cambios de escena como señales.
- No se mostrarán «puntuaciones de viralidad» inventadas: solo señales medibles y su explicación.

## Orden recomendado

1. Validar la fase 1 con 3–5 clips reales y ajustar valores por defecto.
2. Fase 2a (facecam) si los clips de Jongottii incluyen streams con cámara; si son IRL, fase 2b.
3. Fase 4 (animación de subtítulos): mejora visible con poco riesgo.
4. Fase 3 (hablante activo): solo si la fase 2 muestra que hace falta.
