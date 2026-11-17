"""Cuenta del propietario e inicio de sesión del panel.

- Una sola cuenta (el propietario). Se crea desde el PC (127.0.0.1): nadie en la red
  puede apropiarse del panel creando la cuenta primero.
- La contraseña se guarda con scrypt (biblioteca estándar) y sal aleatoria; nunca en claro.
- Cada inicio de sesión crea una sesión con un token aleatorio en una cookie HttpOnly;
  la base de datos guarda solo su hash.
- Intentos fallidos limitados por dirección IP, con espera creciente.
- Si se olvida la contraseña, desde el PC:  python -m fabrica_studio.cuentas --restablecer
  (borra la cuenta y las sesiones; el panel vuelve al modo sin contraseña).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sys
import threading
import time

from .errores import ErrorEtapa

COOKIE_SESION = "fabrica_sesion"
LARGO_MINIMO = 8
DURACION_RECORDAR = 30 * 86400        # «Mantener la sesión iniciada»
DURACION_NORMAL = 12 * 3600
_N, _R, _P = 2 ** 14, 8, 1           # coste de scrypt: ~50 ms por intento


def hash_contrasena(contrasena: str, sal: bytes | None = None) -> str:
    sal = sal or secrets.token_bytes(16)
    h = hashlib.scrypt(contrasena.encode("utf-8"), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${h.hex()}"


def verificar_contrasena(contrasena: str, guardado: str) -> bool:
    try:
        _, n, r, p, sal, h = guardado.split("$")
        calc = hashlib.scrypt(contrasena.encode("utf-8"), salt=bytes.fromhex(sal), n=int(n), r=int(r),
                              p=int(p), dklen=len(bytes.fromhex(h)))
        return hmac.compare_digest(calc.hex(), h)
    except (ValueError, TypeError):
        return False


def validar_nueva(nombre: str, contrasena: str) -> tuple[str, str]:
    nombre = (nombre or "").strip()[:40]
    if not nombre:
        raise ErrorEtapa("Escribe un nombre de usuario.", "entrada")
    if len(contrasena or "") < LARGO_MINIMO:
        raise ErrorEtapa(f"La contraseña debe tener al menos {LARGO_MINIMO} caracteres.", "entrada")
    if contrasena.strip().lower() in (nombre.lower(), "12345678", "password", "contraseña", "fabrica123"):
        raise ErrorEtapa("Esa contraseña es demasiado fácil de adivinar.", "entrada")
    return nombre, contrasena


class Limitador:
    """Bloqueo temporal por IP tras varios intentos fallidos (en memoria)."""

    def __init__(self, gratis: int = 5, espera_base: float = 30.0, espera_max: float = 900.0):
        self.gratis, self.base, self.max = gratis, espera_base, espera_max
        self._lock = threading.Lock()
        self._fallos: dict[str, tuple[int, float]] = {}

    def espera(self, ip: str) -> float:
        """Segundos que faltan para poder volver a intentar (0 = puede intentar)."""
        with self._lock:
            n, hasta = self._fallos.get(ip, (0, 0.0))
            return max(0.0, hasta - time.time())

    def fallo(self, ip: str) -> None:
        with self._lock:
            n, _ = self._fallos.get(ip, (0, 0.0))
            n += 1
            espera = 0.0 if n < self.gratis else min(self.max, self.base * 2 ** (n - self.gratis))
            self._fallos[ip] = (n, time.time() + espera)

    def exito(self, ip: str) -> None:
        with self._lock:
            self._fallos.pop(ip, None)


def main() -> int:
    if "--restablecer" not in sys.argv:
        print("Uso: python -m fabrica_studio.cuentas --restablecer   (borra la contraseña del panel)")
        return 2
    from .config import Rutas
    from .db import DB
    rutas = Rutas()
    if not rutas.db.exists():
        print("No hay base de datos en", rutas.base)
        return 1
    DB(rutas.db).borrar_cuenta()
    print("Contraseña y sesiones borradas. Al abrir el panel en el PC podrás crear una nueva.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
