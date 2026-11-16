"""Control de acceso al panel.

- Desde el propio PC (127.0.0.1) el acceso es directo.
- Cualquier otro dispositivo (la tablet) debe vincularse una vez con un código de
  6 dígitos que solo se muestra en el panel del PC. Recibe una credencial propia
  en una cookie; el servidor guarda solo su hash.
"""
from __future__ import annotations

import hashlib
import ipaddress
import secrets
import socket
import threading
import time

COOKIE = "fabrica_dispositivo"
DURACION_CODIGO = 600
INTENTOS_MAX = 5


def es_local(host: str | None) -> bool:
    try:
        return bool(host) and ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


def host_permitido(cabecera_host: str) -> bool:
    """Solo 'localhost' o direcciones IP: evita ataques de DNS rebinding."""
    host = cabecera_host.rsplit(":", 1)[0] if cabecera_host.count(":") == 1 else cabecera_host
    host = host.strip("[]").split("]")[0]
    if host == "localhost":
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ip_red_local() -> str:
    """IP del PC en la red doméstica (no envía ningún dato: solo consulta la ruta de salida)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


class Vinculacion:
    def __init__(self):
        self._lock = threading.Lock()
        self._codigo = ""
        self._caduca = 0.0
        self._intentos = 0

    def nuevo_codigo(self) -> dict:
        with self._lock:
            self._codigo = f"{secrets.randbelow(10**6):06d}"
            self._caduca = time.time() + DURACION_CODIGO
            self._intentos = 0
            return {"codigo": self._codigo, "segundos": DURACION_CODIGO}

    def canjear(self, codigo: str) -> str | None:
        """Devuelve un token nuevo si el código es correcto. El código sirve una sola vez."""
        with self._lock:
            if not self._codigo or time.time() > self._caduca:
                self._codigo = ""
                return None
            if not secrets.compare_digest(self._codigo, "".join(c for c in str(codigo) if c.isdigit())):
                self._intentos += 1
                if self._intentos >= INTENTOS_MAX:
                    self._codigo = ""
                return None
            self._codigo = ""
            return secrets.token_urlsafe(32)
