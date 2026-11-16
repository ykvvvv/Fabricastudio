"""Errores con un mensaje pensado para mostrarse en el panel."""
from __future__ import annotations

import re


class ErrorEtapa(Exception):
    """Fallo de una etapa. `tipo` permite explicar la causa y decidir si reintentar.

    Tipos: entrada, herramienta, autenticacion, cuota, modelo, temporal,
    configuracion, incierto, interno.
    """

    def __init__(self, mensaje: str, tipo: str = "interno"):
        super().__init__(mensaje)
        self.tipo = tipo


_SECRETOS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),                 # claves de API de Google
    re.compile(r"ya29\.[0-9A-Za-z_\-\.]+"),                 # tokens de acceso de Google
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),                  # claves estilo OpenAI
    re.compile(r"(?i)(key|token|secret|code)=([^&\s\"']+)"),
    re.compile(r"(?i)(bearer)\s+[A-Za-z0-9_\-\.]+"),
]


def sin_secretos(texto: str) -> str:
    """Quita claves y tokens de un texto antes de guardarlo o mostrarlo."""
    for patron in _SECRETOS:
        if patron.groups >= 2:
            texto = patron.sub(lambda m: f"{m.group(1)}=***", texto)
        elif patron.groups == 1:
            texto = patron.sub(lambda m: f"{m.group(1)} ***", texto)
        else:
            texto = patron.sub("***", texto)
    return texto
