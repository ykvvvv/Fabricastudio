# Fábrica Studio

Convierte clips de streamers en YouTube Shorts verticales (1080×1920) desde un panel
local que se usa en el PC y, como control remoto, en la tablet.

El PC hace todo el trabajo (transcribir, renderizar, subir) y guarda la cola. La tablet
solo abre el panel en su navegador: puede apagarse sin que el PC se detenga.

**Estado:** versión 0.2, base funcional. Lo que está probado y lo que falta está en
[ESTADO.md](ESTADO.md). Léelo antes de dar algo por hecho.

## Qué hace

1. Importa un video (archivo, carpeta vigilada o enlace público de Kick).
2. Comprueba el archivo y lee sus propiedades reales con FFmpeg.
3. Transcribe el audio en español con Whisper, en tu PC y sin coste.
4. Genera banner, título y descripción (Gemini si configuras una clave; si no, un borrador local).
5. Crea subtítulos sincronizados.
6. Renderiza el Short: fondo negro, tarjeta blanca con banner rojo, video centrado,
   subtítulos, logo y nombre del creador.
7. Muestra la vista previa y permite corregir textos y subtítulos (opcional).
8. Sube a YouTube **siempre en privado**, al canal que tú confirmes.

## Instalación en Windows 11

Todo se hace en **PowerShell**. Ábrelo en la carpeta del proyecto (clic derecho en la
carpeta → «Abrir en Terminal»).

**1. Requisitos** (solo la primera vez). Si no tienes Python o FFmpeg:

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg
```

Cierra PowerShell y vuelve a abrirlo para que reconozca los programas nuevos.

**2. Instalar Fábrica Studio:**

```powershell
.\scripts\instalar.ps1
```

Debe terminar con «Instalación terminada». Si PowerShell dice que la ejecución de
scripts está deshabilitada, ejecuta esto una vez y repite:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**3. Abrir el panel:**

```powershell
.\scripts\iniciar.ps1
```

También puedes hacer doble clic en **`Abrir Fabrica Studio.cmd`**, en la carpeta del proyecto
(no en los `.ps1`: esos se abren en el Bloc de notas).

Aparecerán dos direcciones. Abre en el navegador del PC `http://127.0.0.1:8765`.
Deja la ventana de PowerShell abierta mientras trabajas.

La primera vez que proceses un clip se descarga el modelo de Whisper (unos 500 MB
para `small`); necesita internet solo esa vez.

**4. Comprobar que todo funciona en tu PC** (recomendado la primera vez):

```powershell
.\scripts\diagnostico.ps1
```

Muestra una lista con `[ OK ]`, `[FALLA]` o `[ -- ]` (opcional) e incluye un render de
prueba de 2 segundos. Si algo falla, copia la salida completa y pégala en el chat.

## Usar la tablet

1. PC y tablet deben estar en el mismo wifi.
2. La primera vez, Windows preguntará si permites a Python en la red: acepta para
   **redes privadas**.
3. En el PC: **Ajustes → Dispositivos → Generar código**.
4. En la tablet: abre en el navegador la dirección que muestra el PC
   (algo como `http://192.168.1.20:8765`) y escribe el código.

Conectar cuentas, guardar claves y elegir el canal solo se puede hacer desde el PC.

## Videos largos

Al importar, elige «Video largo». El programa transcribe todo el video y propone
momentos para recortar. Tú revisas cada tramo, ajustas los tiempos si quieres y pulsas
«Crear Short»: se genera un clip nuevo que sigue el flujo normal, sin transcribir otra vez.

Sin clave de Gemini las propuestas vienen de una heurística que mide ritmo de habla y
exclamaciones pero no entiende el contenido: tómalas como punto de partida.

## Contraseña del panel (opcional)

Puedes proteger el panel con usuario y contraseña. La cuenta solo se crea desde el PC. Si olvidas
la contraseña, en PowerShell dentro de la carpeta del proyecto:

```powershell
.\.venv\Scripts\python.exe -m fabrica_studio.cuentas --restablecer
```

Borra la contraseña y las sesiones; tus clips y ajustes no se tocan.

## Carpetas

Dentro de `datos/` (se crea sola, no se sube al repositorio):

| Carpeta | Uso |
| --- | --- |
| `1_clips_crudos/` | Copia aquí un video y entra solo a la cola cuando termina de copiarse. |
| `2_shorts_renderizados/` | Copia de cada Short terminado. |
| `3_procesados_ok/` | Los originales se mueven aquí solo tras confirmar la subida a YouTube. |
| `secretos/` | Clave de Gemini y credenciales de YouTube. No la compartas. |

## Conectar YouTube (opcional, para subir)

En el **navegador**, en [Google Cloud Console](https://console.cloud.google.com/):

1. Crea un proyecto y habilita **YouTube Data API v3**.
2. En «Pantalla de consentimiento de OAuth»: tipo Externo, y añade como usuario de
   prueba la cuenta de Google que administra el canal.
3. En «Credenciales»: crear **ID de cliente de OAuth → App de escritorio**. Descarga el JSON.

En el **panel del PC**: Ajustes → YouTube → carga ese JSON → «Conectar cuenta de
Google» → revisa que el canal mostrado (nombre **e ID**) sea el correcto → «Confirmar
como destino». Sin esa confirmación no se sube nada.

La API de YouTube tiene una cuota diaria gratuita que limita cuántos videos puedes
subir por día; revisa el valor vigente en tu consola de Google Cloud.

## Textos con Gemini (opcional)

Ajustes → Proveedores → pega la clave de API. El panel la valida, lista los modelos
que tu clave tiene disponibles y elige uno. Es consumo de API (con cuota gratuita o de
pago según tu cuenta de Google), distinto de las suscripciones de ChatGPT o Claude.
Sin clave, los textos son un borrador hecho con frases literales de la transcripción.

## Desarrollo

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

Estructura: ver [CLAUDE.md](CLAUDE.md). Fuente incluida: Inter (licencia OFL, en
`fabrica_studio/assets/fonts/`).
