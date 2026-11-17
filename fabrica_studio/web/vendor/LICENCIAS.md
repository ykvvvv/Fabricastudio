# Bibliotecas incluidas en `web/vendor/`

Archivos de terceros copiados tal cual (sin modificar) para que el panel funcione sin internet.
Para actualizar uno: descargar el paquete de npm, copiar el archivo y anotar aquí versión y huella.

## GSAP — `gsap.min.js`

| Dato | Valor |
| --- | --- |
| Versión | 3.15.1 |
| Origen | paquete `gsap@3.15.1` del registro de npm, archivo `dist/gsap.min.js` |
| Descargado | 2026-11-17, con `npm pack gsap@3.15.1` |
| SHA-1 del paquete (`.tgz`) | `593af220d8bec874b30c4f4b2f459057bf6fe5a1` (coincide con el publicado por npm) |
| SHA-256 de `gsap.min.js` | `3d1bea374ab1b703cc5c4105358eec63c4465efdc573931dc116e34a0a190c1b` |
| Tamaño | 73 357 bytes |

Comprobar la huella en PowerShell: `Get-FileHash fabrica_studio\web\vendor\gsap.min.js -Algorithm SHA256`

### Licencia

Copyright (c) 2008-2026, GreenSock. All rights reserved.

GSAP se distribuye bajo la licencia estándar «no charge» de GreenSock. **No es MIT.**
El paquete de npm no incluye el texto de la licencia: solo remite a esta dirección, que es la fuente válida:

https://gsap.com/standard-license

El aviso de licencia que el propio archivo lleva en su cabecera se conserva intacto. Cristóbal aceptó la
licencia el 2026-11-17 (ver `docs/diseno/plan-login.md`, decisión 4). Solo se usa el núcleo, sin plugins.
