# Plan de diseño: login del panel

Fecha: 2026-11-17 · Estado: **fases A (pantallas con CSS) y B (GSAP) implementadas; falta la C (Three.js, opcional)** — ver `ESTADO.md`. Fuentes: `docs/diseno/referencia-panel.html`,
`fabrica_studio/web/estilo.css` (lo ya implementado), el contrato de `ESTADO.md` → «Login del panel»
y el código real de `server.py` / `cuentas.py`. Método: skills `design-dna` (tokens, estilo, efectos)
y `motion-design` (personalidad, duraciones, coreografía).

Los colores se leyeron del CSS de la referencia, no se estimaron a ojo: son exactos.

---

## 1. Tokens del diseño de referencia

### 1.1 Paleta

| Rol | Referencia | Ya en `estilo.css` | Uso en el login |
| --- | --- | --- | --- |
| Fondo | `#111112` | `--fondo` | Lienzo de la pantalla de acceso |
| Barra lateral | `#0c0c0d` | `--lateral` | Tono más profundo: niebla del fondo 3D |
| Panel / tarjeta | `#161617` (variantes `#141415`, `#181819`) | `--panel` | Tarjeta de acceso |
| Hover | `#1d1d1f` | `--panel2` | Hover de filas (sesiones) |
| Borde | `#28282b` | `--borde` | Borde de tarjeta y filas |
| Borde suave | `#202022` | `--borde-suave` | Separadores |
| Borde de campo | `#333336` – `#39393d` | `--borde-fuerte` `#3d3d42` | Campos y ventanas |
| Texto | `#e9e9eb` | `--texto` | Títulos y valores |
| Texto secundario | `#9b9b9f` | `--tenue` `#a6a6ab` (aclarado) | Descripciones |
| Texto apagado | `#76767d` | `--apagado` `#8e8e95` (aclarado) | Notas, etiquetas |
| Acento arena | `#d8aa91` | `--acento` | Foco, cuenta regresiva, 1 de cada ~8 piezas del fondo |
| Primario claro | `#e5e4e2` sobre tinta `#222224`, hover `#fff` | `--claro`, `--acento-tinta` | Botón «Entrar» / «Crear cuenta» |
| Foco de campo | contorno `#806859`, borde `#887260` | igual | Campos |
| Correcto | `#a3c9ad` (pastilla `#aac9b3` / `#19241d` / `#2b3b30`) | `--ok` | Check de éxito, «Esta sesión» |
| Aviso | `#d8bfa2` (nota `#c1af97` / `#1d1a16` / `#383129`) | `--alerta` | Bloqueo 429 (es espera, no error) |
| Error | `#df9690` (fondo `#251515` en lo implementado) | `--mal` | Credenciales malas |
| Velo de ventana | `#000a` + desenfoque 5 px | igual | Confirmaciones |

Regla de la referencia: **un solo acento cálido** y muy poca superficie de color; el estado se dice con
pastillas pequeñas, no con fondos grandes. El login la mantiene.

Diferencia a respetar: la referencia usa letra de 10–11 px y el gris `#76767d` sobre `#111112`
(≈ 4,2:1, bajo el mínimo AA). El panel real ya lo corrigió (mínimo 12 px, grises más claros).
**El login usa los tokens de `estilo.css`, no los valores crudos de la referencia.** No hace falta
ningún color nuevo.

### 1.2 Tipografía

| Elemento | Referencia | En el login |
| --- | --- | --- |
| Familia | `Inter, ui-sans-serif, "Segoe UI"…` | `--letra` (Segoe UI Variable / HarmonyOS Sans); Inter local solo en pesos 600–900 |
| Base | 14 px, suavizado, cifras tabulares | igual |
| Título de página | 29 px · 500 · tracking −1,2 px · 1,2 | Título de bienvenida |
| Título de ventana | 16 px · 500 · −0,3 px | Título de la tarjeta de login |
| Marca | 17 px · 620 · −0,6 px + «STUDIO» pequeño | Encabezado de la tarjeta |
| Sobretítulo | 10 px · mayúsculas · tracking 1,35–1,5 px | 12 px · tracking 0,1em |
| Cuerpo / ayuda | 12 px / 10–11 px, interlineado 1,6–1,7 | 14 px / 13 px (mínimo 12) |
| Campo en táctil | 16 px (evita el zoom del navegador) | igual |
| Cifra grande | 30 px · 450 · −1,1 px · tabular | Cuenta regresiva del bloqueo |

Carácter: pesos medios (450–620), nunca negritas fuertes en la interfaz; títulos con tracking negativo;
etiquetas en mayúsculas espaciadas.

### 1.3 Espaciado

La referencia no usa una escala estricta: son valores ópticos (5, 7, 9, 11, 13, 17, 20–21, 24, 27, 35–37).
Para el login se redondea a la escala que ya usa `estilo.css`:

| Paso | px | Uso |
| --- | --- | --- |
| xs | 4 | Icono ↔ texto en pastillas |
| s | 8 | Entre etiqueta y campo |
| m | 14–16 | Entre campos |
| l | 24–28 | Relleno de tarjeta (`.vincular .tarjeta` ya usa 28) |
| xl | 36 | Márgenes de página, separación marca ↔ tarjeta |

Medidas fijas heredadas: tarjeta de acceso 400 px de ancho máximo; botones 35 px de alto (44 en táctil);
barra lateral 224 px; barra superior 68 px; contenido máximo 1500 px.

### 1.4 Radios

| Radio | Dónde |
| --- | --- |
| 3–5 px | Pastillas, contadores, teclas |
| 6–7 px (`--radio-c`) | Botones, campos, navegación |
| 8–9 px | Notas, avisos, cajas de entrada |
| 12 px (`--radio`) | Paneles y tarjetas |
| 15 px | Ventanas y **tarjeta de acceso** |
| 50 % / 20 px | Puntos de estado / interruptores |

### 1.5 Sombras y profundidad

La referencia separa planos con **bordes de 1 px y cambios de tono**, casi sin sombras:

| Sombra | Dónde |
| --- | --- |
| `inset 0 1px 0 #ffffff08` | Brillo superior del elemento activo |
| `0 1px 3px #0003` | Botón primario |
| `0 12px 30px #0004` | Marco del Short |
| `0 8px 30px #0007` | Avisos |
| `0 30px 100px #0007` | Ventanas → **tarjeta de acceso** (flota sobre el fondo 3D) |

Texturas: degradados lineales de 120–145° entre dos carbones cercanos y una cuadrícula de 24 px con
líneas `#ffffff02`. Esa cuadrícula es el **fondo de reserva** del login cuando no hay WebGL.

### 1.6 Estilo y efectos (las otras dos dimensiones de design-dna)

- **Estilo:** estudio editorial oscuro; sereno, preciso, sin adornos. Voz breve y cercana en segunda
  persona («Tu estudio», «De un buen momento a tu próximo Short»). Mucho aire, jerarquía por tamaño y tono.
- **Efectos en la referencia:** ninguno (sin canvas ni WebGL; solo dos transiciones CSS de 0,2 y 0,45 s
  y `prefers-reduced-motion`). Todo lo que añada el login es nuevo, así que debe ser **ambiental y
  sobrio**: intensidad baja, nivel de rendimiento «ligero».

---

## 2. Sistema de movimiento

### 2.1 Intención y personalidad

- **Qué debe sentirse:** calma y confianza al llegar; firmeza ante un error; paciencia (no castigo)
  durante el bloqueo; una pequeña recompensa al entrar.
- **Personalidad:** *Premium contenido* — entre «Corporate» y «Premium» de motion-design. Sin rebotes.
  El único exceso permitido es el check de éxito, que ya existe en el panel (`marca`).
- **Micro-historia:** *clips sueltos → se ordenan → tu estudio*. El fondo muestra marcos 9:16 a la
  deriva; al iniciar sesión se alinean y la cámara los atraviesa hasta el panel.

### 2.2 Las tres constantes

| Constante | Valor | Equivalente GSAP |
| --- | --- | --- |
| Curva firma (entradas, 80 % de los casos) | `--curva: cubic-bezier(.3, .7, .2, 1)` (ya existe) | `power3.out` |
| Curva de salida | `cubic-bezier(.3, 0, 1, 1)` | `power2.in` |
| Curva en pantalla (mover, redimensionar) | `cubic-bezier(.2, 0, 0, 1)` | `power2.inOut` |
| Ambiental (bucles) | seno | `sine.inOut` |
| Entrada tipo | subir 6–12 px + opacidad (igual que `@keyframes entra`) | — |

Los nombres de GSAP son aproximaciones de las curvas CSS, no idénticos. Se evita el plugin
`CustomEase` para no añadir otro archivo.

### 2.3 Duraciones

| Nombre | ms | Para |
| --- | --- | --- |
| Instantánea | 80–120 | Hover, pulsar, mostrar/ocultar contraseña |
| Rápida | 160–220 | Foco, mensajes de error, filas, salidas |
| Estándar | 300–360 | Tarjeta que entra, sacudida de error, cambio login ↔ código |
| Lenta | 450–600 | Cambio de pantalla |
| Teatral | 900–1100 | **Solo dos veces:** bienvenida la primera vez y login → panel |

Reglas: la salida dura un 30–40 % menos que la entrada; escalonado de 50–60 ms con un total ≤ 400 ms
(en tablet, 30 % menos); nunca `linear` salvo el anillo de la cuenta regresiva y el giro de carga.

### 2.4 Tres capas

| Capa | Qué | Herramienta |
| --- | --- | --- |
| Primaria | Tarjeta, campos, botón, mensajes | CSS para estados; GSAP para secuencias |
| Secundaria | Sombra de la tarjeta, signo de la marca, borde de foco | GSAP / CSS |
| Ambiental | Marcos 9:16 a la deriva en profundidad | Three.js (reserva: cuadrícula CSS fija) |

Reparto: **CSS** para todo lo que es un estado (hover, foco, pulsado, error visible). **GSAP** solo para
líneas de tiempo con varios elementos (bienvenida, sacudida, transición al panel). **Three.js** solo el
fondo de las pantallas de acceso.

### 2.5 Coreografía por momento

| Momento | Secuencia | Total |
| --- | --- | --- |
| Bienvenida (primera vez) | fondo aparece 600 → signo de la marca: dos barras caen y se inclinan −28° (350) → título (300) → texto → tarjeta sube 12 px (360) → campos escalonados 50 ms | ≈ 1,1 s; se puede escribir desde los 500 ms |
| Login (visitas siguientes) | tarjeta sube 8 px + opacidad (300); foco directo en la contraseña | 300 ms |
| Enviar | botón baja a 0,98 (100) → texto cambia a giro de carga | — |
| Error 403 | tarjeta: 3 oscilaciones ±8 px, `power2.inOut`, sin rebote (360) · borde del campo a `--mal` (160) · mensaje baja 4 px + opacidad (200) | 360 ms |
| Bloqueo 429 | el formulario se atenúa a 45 % (220) → el bloque de espera crece desde 0,98 (300) → anillo se vacía de forma lineal · el fondo 3D baja a ¼ de velocidad | 300 ms + espera |
| Fin del bloqueo | bloque sale (200) → formulario vuelve a 100 % (220) → foco en la contraseña · fondo recupera velocidad en 600 | 420 ms |
| Éxito → panel | ver §3.4 | ≈ 1,0 s |
| Cerrar sesión | panel se desvanece (220, salida) → tarjeta de login entra (300) | 520 ms |
| Fila de sesión cerrada | opacidad + deslizar 8 px (200) → la lista cierra el hueco (220) | 420 ms |

Regla de 1/3: nunca más de un tercio de los elementos en movimiento a la vez; el fondo ambiental no
cuenta porque se mueve a menos del 5 % de la pantalla por segundo.

### 2.6 Accesibilidad y rendimiento

- `prefers-reduced-motion`: el CSS actual ya anula animaciones y transiciones. Además: GSAP no monta
  líneas de tiempo (los estados se aplican de golpe), **no se carga Three.js** (queda la cuadrícula fija),
  la sacudida se sustituye por el borde rojo y el mensaje, y la cuenta regresiva muestra solo el número.
- Solo se animan `transform` y `opacity`.
- El fondo 3D se detiene con la pestaña oculta y se destruye al entrar al panel.
- Nada bloquea la entrada: se puede escribir y enviar durante cualquier animación.

---

## 3. Bocetos en texto

Estados que decide `GET /api/sesion`:

| `cuenta_creada` | `local` | `autorizado` | Pantalla |
| --- | --- | --- | --- |
| no | sí | sí | Panel. La **primera vez**, antes: bienvenida con «Crear cuenta» (opcional) |
| no | no | no | Vinculación por código (la de hoy, sin cambios) |
| sí | — | no | **Login** (con enlace a «usar un código» en dispositivos que no son el PC) |
| sí | — | sí | Panel directo, sin animación de acceso |

### 3.1 Bienvenida y crear cuenta (primera vez, en el PC)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  (fondo: marcos 9:16 a la deriva, muy tenues)                            │
│                                                                          │
│     //  Fábrica STUDIO                                                   │
│                                                                          │
│     TU ESPACIO CREATIVO                 ┌─────────────────────────────┐  │
│     Bienvenido a tu estudio.            │ Protege tu panel            │  │
│                                         │ Crea una cuenta para que    │  │
│     De un buen momento a tu             │ solo tú puedas abrirlo.     │  │
│     próximo Short. Todo ocurre          │                             │  │
│     en este PC.                         │ Nombre de usuario           │  │
│                                         │ [ Cristóbal              ]  │  │
│     ● Este PC procesa los clips         │ Contraseña            (ojo) │  │
│     ● La tablet se conecta por Wi-Fi    │ [ ••••••••••             ]  │  │
│     ● YouTube siempre en privado        │ ✓ 8 caracteres o más        │  │
│                                         │ Repite la contraseña        │  │
│                                         │ [ ••••••••••             ]  │  │
│                                         │ [x] Mantener la sesión      │  │
│                                         │     iniciada en este PC     │  │
│                                         │                             │  │
│                                         │ [      Crear cuenta      ]  │  │
│                                         │ Ahora no, seguir sin clave  │  │
│                                         └─────────────────────────────┘  │
│  Si la olvidas: python -m fabrica_studio.cuentas --restablecer           │
└──────────────────────────────────────────────────────────────────────────┘
```

- En pantallas de menos de 900 px el texto de bienvenida queda arriba y la tarjeta debajo.
- Validación en el navegador solo para lo evidente (8 caracteres, las dos contraseñas iguales). Los
  demás mensajes son **los del servidor, tal cual**: «Escribe un nombre de usuario.», «Esa contraseña
  es demasiado fácil de adivinar.». Un 409 («Ya existe una cuenta») cambia a la pantalla de login.
- «Mantener la sesión iniciada» marcado por defecto (así lo trata el servidor al crear la cuenta).
- «Ahora no» entra al panel y guarda la elección en `localStorage`; la bienvenida no vuelve a salir
  y la opción queda en Ajustes → Cuenta. *(Decisión a confirmar por Cristóbal.)*
- Al crear la cuenta la sesión ya queda iniciada → misma transición que login → panel (§3.4).
- Desde otro dispositivo no se puede crear la cuenta (el servidor responde 403): allí nunca se muestra.

### 3.2 Login

```
              //  Fábrica STUDIO

        ┌──────────────────────────────────┐
        │ Inicia sesión                    │
        │ Tu estudio te espera.            │
        │                                  │
        │ Usuario                          │
        │ [ Cristóbal                    ] │
        │ Contraseña                 (ojo) │
        │ [ ••••••••                     ] │
        │ [ ] Mantener la sesión iniciada  │
        │     30 días en este dispositivo  │
        │                                  │
        │ [           Entrar →           ] │
        │                                  │
        │ Usar un código de vinculación    │   ← solo si no es el PC
        └──────────────────────────────────┘
        ¿Olvidaste la contraseña? Se restablece
        desde el PC.                    v0.3
```

- Sin marcar «mantener»: la sesión dura hasta cerrar el navegador (12 h como máximo). Marcada: 30 días.
- «Usar un código de vinculación» cambia el contenido de la tarjeta por el formulario actual de
  vinculación (cruce de 300 ms); los dispositivos vinculados siguen funcionando igual.
- Si una sesión caduca con el panel abierto (la API responde 401), se muestra este login con la nota
  «Tu sesión caducó. Vuelve a entrar.» y sin animación de entrada.

**Con error (403):**

```
        │ Contraseña                 (ojo) │
        │ [                              ] │  ← borde rojo, vacío y con el foco
        │ ⚠ Usuario o contraseña           │  ← role="alert"
        │   incorrectos.                   │
        │ [           Entrar →           ] │
```

La tarjeta se sacude una vez (360 ms). **No se muestra «te quedan N intentos»**: el servidor no envía
ese dato y no se inventa.

**Con bloqueo (429) y cuenta regresiva real:**

```
        ┌──────────────────────────────────┐
        │ Inicia sesión                    │
        │                                  │
        │   ╭────╮  Demasiados intentos    │
        │   │ 28 │  Podrás volver a        │
        │   ╰────╯  intentarlo en 28 s.    │
        │    (anillo arena que se vacía)   │
        │                                  │
        │ [ Usuario      ] (atenuado)      │
        │ [ Contraseña   ] (atenuado)      │
        │ [    Espera 28 s…   ] (inactivo) │
        └──────────────────────────────────┘
```

Cómo se garantiza que la cuenta es real:

1. El número sale de `espera` en la respuesta 429 (segundos, ya redondeados hacia arriba por el
   servidor, así que el panel nunca desbloquea antes que él).
2. Al recibirla se guarda la hora de fin con el reloj monótono (`performance.now() + espera × 1000`).
   Cada repintado calcula lo que **falta** hasta esa hora; no se restan segundos con un temporizador,
   que se atrasa en pestañas en segundo plano. Al volver a la pestaña se recalcula.
3. Al llegar a cero se reactiva el formulario y el foco va a la contraseña. **No se reenvía solo.**
4. Si aun así el servidor responde otro 429, se toma su nuevo `espera` y se reinicia.
5. Formato: menos de un minuto «28 s»; más, «14:32» (el bloqueo crece 30 s → 60 s → … → 15 min).
6. Lectores de pantalla: se anuncia al empezar y al terminar, no cada segundo.
7. Color de aviso (`--alerta`), no de error: es una espera.

Límites del servidor actual que el diseño debe conocer (no se cambian en este plan):

- El quinto fallo responde **403 normal**; el bloqueo solo se ve en el intento siguiente (429). La
  cuenta regresiva empieza ahí. Tampoco aparece al recargar la página hasta volver a intentarlo.
- Mejora opcional y pequeña para más adelante: que el 403 que activa el bloqueo incluya `espera` y que
  `GET /api/sesion` informe la espera vigente. Requiere tocar `server.py` y sus pruebas.
- El bloqueo vive en memoria: reiniciar el panel lo borra.

### 3.3 Estados del botón principal

| Estado | Aspecto |
| --- | --- |
| Reposo | Claro `#e5e4e2`, texto tinta, flecha |
| Hover / foco | `#fff` / contorno arena de 2 px |
| Enviando | Giro de carga, inactivo, mismo ancho (sin saltos) |
| Éxito | Check dibujado en `--ok` |
| Bloqueado | Inactivo, «Espera 28 s…» |

### 3.4 Transición login → panel

```
 t = 0      200       420        700        1000 ms
 ├──────────┼─────────┼──────────┼──────────┤
 check en el botón
            la tarjeta se encoge a 0,98 y se desvanece (curva de salida)
            los marcos del fondo se alinean en rejilla; la cámara avanza
                      velo al color de fondo
                      barra lateral entra (−12 px) → barra superior
                                 contenido: `entra` + tarjetas escalonadas 60 ms
                                            se destruye la escena 3D
```

- Los datos del panel se piden **en cuanto llega el 200**, en paralelo con la animación; si tardan,
  se ven los esqueletos de carga que ya existen.
- El panel responde a clics desde ≈ 600 ms. El foco pasa al contenido principal.
- Con «reducir movimiento» o sin WebGL: cruce simple de 200 ms o cambio directo.
- Si ya había sesión al abrir el panel, **no hay transición**: se entra directo.

### 3.5 Ajustes → pestaña nueva «Cuenta»

Se añade a las pestañas actuales (Diseño · YouTube · Proveedores · Dispositivos · **Cuenta**).
Si no hay cuenta, la pestaña muestra solo la tarjeta «Protege tu panel» con el formulario de §3.1
(en el PC) o una nota «Se crea desde el PC» (en otros dispositivos).

**Cambiar contraseña** (solo desde el PC):

```
┌ Contraseña ────────────────────────────────────────────┐
│ Al cambiarla se cierran las demás sesiones.            │
│ Contraseña actual   [ ••••••••            ] (ojo)      │
│ Nueva contraseña    [ ••••••••••          ] (ojo)      │
│                     ✓ 8 caracteres o más               │
│ Repite la nueva     [ ••••••••••          ]            │
│                                 [ Cambiar contraseña ] │
└────────────────────────────────────────────────────────┘
```

- Error «La contraseña actual no es correcta.» bajo el primer campo (mensaje del servidor).
- Éxito: nota verde «Contraseña cambiada. Se cerraron las demás sesiones.»; la lista de sesiones se
  recarga y las otras filas salen animadas. La sesión actual sigue abierta (30 días).
- En la tablet: la tarjeta aparece inactiva con «Por seguridad, solo desde el panel abierto en el PC.»

**Sesiones abiertas:**

```
┌ Sesiones abiertas ─────────────────────────────────────┐
│ (pc)  Windows · Chrome            [Esta sesión]        │
│       127.0.0.1 · activa ahora · caduca en 30 días     │
│ ────────────────────────────────────────────────────── │
│ (tab) HarmonyOS · Navegador                 [ Cerrar ] │
│       192.168.1.34 · vista hace 2 h · caduca en 11 h   │
└────────────────────────────────────────────────────────┘
```

- Datos reales de `GET /api/sesiones`: `agente`, `ip`, `creado`, `visto`, `expira`, `actual`.
- El nombre del dispositivo se deduce del agente de usuario con reglas simples; si no se reconoce,
  se muestra «Navegador desconocido» y el texto del agente recortado. No se inventa nada.
- «Vista hace…» puede ir hasta un minuto atrasado (el servidor lo actualiza cada 60 s).
- «Cerrar» solo aparece en el PC (el servidor lo exige). Cerrar la sesión actual equivale a salir.
- Los dispositivos vinculados por código **no** salen aquí: siguen en la pestaña Dispositivos.
- Lista vacía (panel abierto en el PC sin haber iniciado sesión): «No hay sesiones abiertas.»

**Cerrar sesión:**

```
┌ Salir ─────────────────────────────────────────────────┐
│ Cierra la sesión en este dispositivo.  [ Cerrar sesión ]│
└────────────────────────────────────────────────────────┘
```

- También desde el perfil, al pie de la barra lateral (icono de salida junto a «Este PC»).
- Sin ventana de confirmación: es un clic y se deshace volviendo a entrar.
- Después de `POST /api/logout` se vuelve a consultar `/api/sesion`:
  - sin autorización → pantalla de login (transición corta de §2.5);
  - **sigue autorizado** (dispositivo vinculado por código) → se queda en el panel con el aviso
    «Sesión cerrada. Este dispositivo sigue vinculado; para quitarlo, usa Dispositivos en el PC.»

---

## 4. GSAP y Three.js como archivos locales (sin CDN)

### 4.1 Por qué se añaden (regla de dependencias)

Hasta hoy el panel no tiene dependencias. Estas dos son **archivos estáticos**, no paquetes de Python:
no cambian `requirements.txt`, no necesitan compilación y funcionan igual en Windows.

| Biblioteca | Versión vista hoy en npm | Licencia | Archivos | Tamaño |
| --- | --- | --- | --- | --- |
| GSAP | 3.15.1 | «Standard no-charge» de GreenSock (gratuita, **no es MIT**) | `dist/gsap.min.js` | 73 KB |
| Three.js | 0.187.0 | MIT | `build/three.module.js` + `build/three.core.js` | 659 KB + 1,47 MB |

- GSAP se justifica por las líneas de tiempo (bienvenida, sacudida, transición). Sin plugins.
- Three.js se justifica solo por el fondo ambiental. Es lo más prescindible del plan: **va en la última
  fase**, y todo debe verse bien antes sin él.
- La versión 0.187.0 no publica compilados minificados en `build/`; se copian los dos módulos tal
  cual. `three.module.js` importa `./three.core.js`, así que deben estar juntos y con esos nombres.
- La licencia de GSAP permite el uso gratuito; conviene que Cristóbal lea
  https://gsap.com/standard-license antes de publicarlo en el repositorio. Se conserva la cabecera
  de licencia de cada archivo.

### 4.2 Estructura

```
fabrica_studio/web/vendor/
├── gsap.min.js          (script clásico: crea la variable global `gsap`)
├── three.module.js      (módulo ES)
├── three.core.js        (módulo ES, lo importa el anterior)
└── VERSIONES.md         (versión, origen, fecha, SHA-256 y licencia de cada archivo)
```

`server.py` ya sirve toda la carpeta `web/` como archivos estáticos: **no hace falta ninguna ruta nueva**.

### 4.3 Cómo se obtienen (una sola vez, en PowerShell, desde la carpeta del proyecto)

```powershell
$tmp = Join-Path $env:TEMP "fabrica-vendor"
New-Item -ItemType Directory -Force $tmp | Out-Null
Push-Location $tmp
npm pack gsap@3.15.1 three@0.187.0        # descarga dos .tgz del registro de npm
tar -xf gsap-3.15.1.tgz;  Rename-Item package gsap
tar -xf three-0.187.0.tgz; Rename-Item package three
Pop-Location
New-Item -ItemType Directory -Force fabrica_studio\web\vendor | Out-Null
Copy-Item "$tmp\gsap\dist\gsap.min.js" fabrica_studio\web\vendor\
Copy-Item "$tmp\three\build\three.module.js","$tmp\three\build\three.core.js" fabrica_studio\web\vendor\
Get-FileHash fabrica_studio\web\vendor\*.js -Algorithm SHA256     # copiar a VERSIONES.md
```

Resultado esperado: tres archivos `.js` en `vendor\` y sus tres huellas en pantalla. La descarga ocurre
una vez al preparar el proyecto; **el panel en marcha nunca sale a internet a buscarlas**.

### 4.4 Cómo se cargan

- **GSAP:** `<script src="vendor/gsap.min.js" defer></script>` en `index.html`, antes de `app.js`.
  Si `window.gsap` no existe, el código aplica los estados finales sin animar (el login sigue funcionando).
- **Three.js:** no va en `index.html`. Se carga con `import("./vendor/three.module.js")` **solo** cuando
  se va a mostrar la bienvenida o el login, hay WebGL y no está activo «reducir movimiento». Quien ya
  tiene sesión nunca descarga esos 2 MB. Si la carga falla, queda la cuadrícula CSS.
- Sin `importmap`, sin empaquetador, sin `node_modules` en el repositorio.

### 4.5 Escena 3D: límites

- Unos 40–60 marcos 9:16 como una sola malla instanciada (una llamada de dibujo), material sin luces,
  niebla hacia `#0c0c0d`, 1 de cada 8 en arena. Sin sombras, sin posprocesado, sin texturas.
- `powerPreference: "low-power"`, densidad de píxeles limitada a 1,5, pausa con la pestaña oculta.
- Al entrar al panel: liberar geometría y material, `renderer.dispose()` y quitar el `<canvas>`.

### 4.6 Riesgos a comprobar al implementarlo

1. **Tipo MIME en Windows.** Los módulos ES exigen `text/javascript`. En algunos Windows el registro
   asocia `.js` a `text/plain` y el navegador rechaza el módulo. Si ocurre, una línea en `server.py`
   (`mimetypes.add_type("text/javascript", ".js")`) lo resuelve; se cubre con una prueba.
2. **Finales de línea.** Añadir `fabrica_studio/web/vendor/* -text` a `.gitattributes` para que Git no
   altere los archivos y las huellas SHA-256 sigan coincidiendo.
3. **Tablet (HarmonyOS):** WebGL y rendimiento sin comprobar. La reserva en CSS es obligatoria.
4. **Prueba automática:** que `index.html`, `app.js` y `estilo.css` no contengan ninguna URL
   `http(s)://` de scripts u hojas de estilo, y que los archivos de `vendor/` existan.

---

## 5. Orden de implementación propuesto (cuando Cristóbal lo apruebe)

| Fase | Contenido | Archivos |
| --- | --- | --- |
| A | Pantallas funcionando solo con CSS: bienvenida, login, error, bloqueo con cuenta regresiva, pestaña Cuenta | `index.html`, `estilo.css`, `app.js`, pruebas |
| B | GSAP local y las líneas de tiempo de §2.5 | `vendor/gsap.min.js`, `app.js` |
| C | Fondo Three.js con reserva | `vendor/three.*`, `app.js`, `.gitattributes` |

Cada fase deja el panel utilizable y con sus pruebas. La fase A no depende de ninguna biblioteca.

## 6. Decisiones que necesita Cristóbal

1. ¿La bienvenida se muestra una sola vez y «Ahora no» la oculta para siempre (propuesto), o cada vez
   que se abre el panel sin cuenta?
2. ¿Se acepta ampliar el servidor para que la cuenta regresiva aparezca ya en el quinto fallo y al
   recargar (§3.2), o basta con que empiece en el intento siguiente?
3. ¿Three.js entra (fase C) o el fondo se queda en la cuadrícula CSS? Son 2 MB para un efecto ambiental.
4. Revisar la licencia de GSAP antes de subir `gsap.min.js` al repositorio.
