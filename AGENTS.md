# Fábrica Studio — guía para agentes (Codex)

Las reglas, la arquitectura y los comandos del proyecto están en [CLAUDE.md](CLAUDE.md)
y valen igual para Codex. Este archivo solo añade cómo colaborar.

## Antes de empezar

1. Lee `CLAUDE.md` (reglas que no se rompen) y `ESTADO.md` (qué está hecho y qué sigue).
2. Ejecuta `python -m pytest`: debe pasar antes y después de tu cambio.

## Reparto

- **Claude Code** coordina, mantiene el contexto, define tareas e integra.
- **Codex** implementa tareas delimitadas, investiga errores y revisa cambios.
- Claude Code y Codex **no comparten conversaciones ni memoria**: lo que no esté
  escrito en el repositorio, el otro no lo sabe.

## Cómo tomar una tarea

- Las tareas abiertas están en la sección «Siguientes pasos» de `ESTADO.md`. Cada una
  indica los archivos que toca.
- Trabaja en una rama propia (`codex/<tarea>`) y no edites archivos que otra tarea
  en curso tenga asignados.
- Al terminar, añade una entrada en «Registro» de `ESTADO.md`: qué cambiaste, qué
  pruebas ejecutaste y con qué resultado, y qué queda pendiente. Distingue
  «probado con pytest», «probado a mano» y «sin probar».

## Revisiones

Al revisar un cambio, comprueba sobre todo: privacidad de subida, verificación de
canal, duplicados, secretos en registros o respuestas de la API, y que los errores
de proveedores dejen el trabajo reanudable.
