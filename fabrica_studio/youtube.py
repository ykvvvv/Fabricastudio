"""YouTube: autorización OAuth, verificación del canal y subida reanudable en privado.

Reglas de seguridad de este módulo:
- La privacidad de subida es siempre "private". No hay opción para publicar en público.
- Solo se sube al canal cuyo ID confirmó el usuario en el panel.
- Antes de iniciar una subida nueva se comprueba si ya existe una sesión o un
  video reciente con el mismo título, para no duplicar.
- Tokens y sesiones de subida no se registran ni se envían al panel.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import httpx

from .errores import ErrorEtapa, sin_secretos

log = logging.getLogger("fabrica.youtube")

ALCANCES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
API = "https://www.googleapis.com/youtube/v3"
SUBIDA = "https://www.googleapis.com/upload/youtube/v3/videos"
BLOQUE = 8 * 1024 * 1024      # múltiplo de 256 KB, como exige la API
CATEGORIA_GAMING = "20"
CATEGORIA_ENTRETENIMIENTO = "24"


def _instante_iso(texto: str) -> float:
    """Segundos desde 1970 (UTC) de un datetime ISO 8601 de la API, respetando su zona ('Z' o ±hh:mm).

    No depende de la zona horaria ni del horario de verano del PC. Sin zona, la hora es ambigua: ValueError.
    """
    # Python 3.10 no acepta 'Z' ni fracciones de longitud libre en fromisoformat.
    d = datetime.fromisoformat(re.sub(r"\.\d+", "", texto.strip()).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("fecha sin zona horaria")
    return d.timestamp()


def _error_api(r: httpx.Response, contexto: str) -> ErrorEtapa:
    razon, mensaje = "", r.text[:300]
    try:
        err = r.json()["error"]
        if isinstance(err, dict):
            mensaje = err.get("message", mensaje)
            razon = (err.get("errors") or [{}])[0].get("reason", "")
        else:  # errores de OAuth: {"error": "invalid_grant", "error_description": "..."}
            razon, mensaje = str(err), r.json().get("error_description", str(err))
    except Exception:
        pass
    mensaje = sin_secretos(f"{contexto}: {mensaje} ({r.status_code}{', ' + razon if razon else ''})")
    if razon in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "uploadLimitExceeded") or r.status_code == 429:
        return ErrorEtapa(mensaje + ". Límite de la API o de subidas diarias; reintenta más tarde.", "cuota")
    if r.status_code == 401 or razon in ("invalid_grant", "authError"):
        return ErrorEtapa(mensaje + ". Vuelve a conectar la cuenta de YouTube en Ajustes.", "autenticacion")
    if r.status_code == 403:
        return ErrorEtapa(mensaje + ". La cuenta no tiene permiso para esta operación.", "autenticacion")
    if r.status_code >= 500:
        return ErrorEtapa(mensaje, "temporal")
    return ErrorEtapa(mensaje, "interno")


class YouTube:
    def __init__(self, secretos: Path, cliente: httpx.Client | None = None, espera: float = 2.0):
        self.secretos = secretos
        self.f_cliente = secretos / "client_secret.json"
        self.f_token = secretos / "youtube_token.json"
        self.http = cliente or httpx.Client(timeout=httpx.Timeout(60, read=300, write=300))
        self.espera = espera
        self._pendiente: dict = {}   # state -> {verificador, redirect, t}

    # ------------------------------------------------------------ credenciales
    def _credenciales(self) -> dict:
        if not self.f_cliente.exists():
            raise ErrorEtapa("Falta client_secret.json. Cárgalo en Ajustes → YouTube.", "configuracion")
        datos = json.loads(self.f_cliente.read_text(encoding="utf-8"))
        tipo = "installed" if "installed" in datos else "web" if "web" in datos else ""
        if not tipo:
            raise ErrorEtapa("client_secret.json no tiene el formato de Google (falta 'installed').", "configuracion")
        return {**datos[tipo], "tipo": tipo}

    def estado(self) -> dict:
        e = {"credenciales": self.f_cliente.exists(), "conectado": False, "tipo_cliente": ""}
        if e["credenciales"]:
            try:
                e["tipo_cliente"] = self._credenciales()["tipo"]
            except (ErrorEtapa, ValueError):
                e["credenciales"] = False
        if self.f_token.exists():
            try:
                e["conectado"] = bool(json.loads(self.f_token.read_text(encoding="utf-8")).get("refresh_token"))
            except ValueError:
                pass
        return e

    def guardar_credenciales(self, contenido: bytes) -> str:
        try:
            datos = json.loads(contenido.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ErrorEtapa("El archivo no es un JSON válido.", "configuracion")
        tipo = "installed" if "installed" in datos else "web" if "web" in datos else ""
        if not tipo or not datos[tipo].get("client_id"):
            raise ErrorEtapa("No parece un client_secret.json de Google Cloud.", "configuracion")
        self.secretos.mkdir(parents=True, exist_ok=True)
        self.f_cliente.write_bytes(contenido)
        _solo_propietario(self.f_cliente)
        return tipo

    def url_autorizacion(self, redirect: str) -> str:
        cred = self._credenciales()
        estado, verificador = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
        self._pendiente = {estado: {"verificador": verificador, "redirect": redirect, "t": time.time()}}
        return cred.get("auth_uri", "https://accounts.google.com/o/oauth2/auth") + "?" + urlencode({
            "client_id": cred["client_id"], "redirect_uri": redirect, "response_type": "code",
            "scope": " ".join(ALCANCES), "access_type": "offline", "prompt": "consent select_account",
            "state": estado, "code_challenge": reto, "code_challenge_method": "S256"})

    def completar_autorizacion(self, codigo: str, estado: str) -> None:
        p = self._pendiente.pop(estado, None)
        if not p or time.time() - p["t"] > 900:
            raise ErrorEtapa("La autorización caducó o no corresponde a esta sesión. Inténtalo de nuevo.", "autenticacion")
        cred = self._credenciales()
        r = self.http.post(cred.get("token_uri", "https://oauth2.googleapis.com/token"), data={
            "code": codigo, "client_id": cred["client_id"], "client_secret": cred.get("client_secret", ""),
            "redirect_uri": p["redirect"], "grant_type": "authorization_code", "code_verifier": p["verificador"]})
        if r.status_code != 200:
            raise _error_api(r, "Google rechazó la autorización")
        t = r.json()
        if not t.get("refresh_token"):
            raise ErrorEtapa("Google no entregó un token de renovación. Revoca el acceso de la app en "
                             "myaccount.google.com/permissions y vuelve a conectar.", "autenticacion")
        self._guardar_token({"refresh_token": t["refresh_token"], "access_token": t["access_token"],
                             "caduca": time.time() + int(t.get("expires_in", 3600)) - 60})

    def _guardar_token(self, token: dict) -> None:
        self.secretos.mkdir(parents=True, exist_ok=True)
        self.f_token.write_text(json.dumps(token), encoding="utf-8")
        _solo_propietario(self.f_token)

    def desconectar(self) -> None:
        self.f_token.unlink(missing_ok=True)

    def _acceso(self) -> str:
        if not self.f_token.exists():
            raise ErrorEtapa("YouTube no está conectado. Conéctalo en Ajustes → YouTube.", "configuracion")
        token = json.loads(self.f_token.read_text(encoding="utf-8"))
        if token.get("access_token") and token.get("caduca", 0) > time.time():
            return token["access_token"]
        cred = self._credenciales()
        try:
            r = self.http.post(cred.get("token_uri", "https://oauth2.googleapis.com/token"), data={
                "client_id": cred["client_id"], "client_secret": cred.get("client_secret", ""),
                "refresh_token": token["refresh_token"], "grant_type": "refresh_token"})
        except httpx.HTTPError as e:
            raise ErrorEtapa(f"Sin conexión con Google ({type(e).__name__}).", "temporal")
        if r.status_code != 200:
            raise _error_api(r, "No se pudo renovar el acceso a YouTube")
        t = r.json()
        token.update(access_token=t["access_token"], caduca=time.time() + int(t.get("expires_in", 3600)) - 60)
        self._guardar_token(token)
        return token["access_token"]

    def _get(self, ruta: str, **params) -> dict:
        try:
            r = self.http.get(f"{API}/{ruta}", params=params, headers={"Authorization": f"Bearer {self._acceso()}"})
        except httpx.HTTPError as e:
            raise ErrorEtapa(f"Sin conexión con YouTube ({type(e).__name__}).", "temporal")
        if r.status_code != 200:
            raise _error_api(r, "YouTube")
        return r.json()

    # ------------------------------------------------------------ canal
    def canales(self) -> list[dict]:
        """Canales a los que da acceso la cuenta autorizada (normalmente uno)."""
        datos = self._get("channels", part="snippet,contentDetails", mine="true", maxResults=50)
        return [{"id": c["id"], "titulo": c["snippet"].get("title", ""),
                 "identificador": c["snippet"].get("customUrl", ""),
                 "lista_subidas": c.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")}
                for c in datos.get("items", [])]

    def _buscar_reciente(self, canal: dict, titulo: str, desde: float) -> str:
        """ID de un video ya subido con ese título después de `desde`, o ''."""
        if not canal.get("lista_subidas"):
            return ""
        datos = self._get("playlistItems", part="snippet", playlistId=canal["lista_subidas"], maxResults=25)
        for it in datos.get("items", []):
            s = it.get("snippet", {})
            try:
                publicado = _instante_iso(s.get("publishedAt", ""))
            except ValueError:
                log.warning("Fecha de YouTube no reconocida: %r", s.get("publishedAt", "")[:40])
                continue
            if s.get("title") == titulo and publicado >= desde - 120:
                return s.get("resourceId", {}).get("videoId", "")
        return ""

    # ------------------------------------------------------------ subida
    def _consultar(self, sesion: str, total: int) -> tuple[str, object]:
        """Pregunta a YouTube cuánto recibió: ('completo', id) | ('parcial', bytes) | ('perdida', None)."""
        r = self.http.put(sesion, headers={"Content-Range": f"bytes */{total}", "Content-Length": "0"})
        if r.status_code in (200, 201):
            return "completo", r.json().get("id", "")
        if r.status_code == 308:
            rango = r.headers.get("Range", "")
            return "parcial", int(rango.split("-")[1]) + 1 if "-" in rango else 0
        if r.status_code in (404, 410, 400):
            return "perdida", None
        raise _error_api(r, "No se pudo consultar la subida")

    def subir(self, archivo: Path, titulo: str, descripcion: str, canal_id: str, es_gaming: bool,
              para_ninos: bool, subida: dict, guardar: Callable[[dict], None],
              progreso: Callable[[int, int], None] = lambda a, b: None) -> str:
        """Sube `archivo` en privado y devuelve el ID del video.

        `subida` es el estado persistente de este trabajo; `guardar` lo escribe en
        la base de datos antes de enviar datos, para poder retomar tras un corte.
        """
        if not canal_id:
            raise ErrorEtapa("No hay un canal de destino confirmado. Confírmalo en Ajustes → YouTube.", "configuracion")
        canal = next((c for c in self.canales() if c["id"] == canal_id), None)
        if not canal:
            raise ErrorEtapa("La cuenta conectada no da acceso al canal confirmado. No se subió nada. "
                             "Revisa la cuenta en Ajustes → YouTube.", "configuracion")
        total = archivo.stat().st_size
        desplazamiento = 0
        sesion = subida.get("sesion", "")

        if subida.get("inicio") and subida.get("tamano") not in (None, total):
            sesion = ""   # el archivo cambió (nuevo render): la sesión anterior ya no sirve
        if sesion:
            estado, valor = self._consultar(sesion, total)
            if estado == "completo":
                return str(valor)
            if estado == "parcial":
                desplazamiento = int(valor)
            else:
                sesion = ""
        if not sesion and subida.get("inicio"):
            # Hubo un intento anterior cuyo final desconocemos: buscar antes de subir otra vez.
            previo = self._buscar_reciente(canal, subida.get("titulo", titulo), subida["inicio"])
            if previo:
                log.info("Se recuperó una subida anterior en lugar de duplicarla.")
                return previo
        if not sesion:
            cuerpo = {"snippet": {"title": titulo, "description": descripcion, "defaultLanguage": "es",
                                  "categoryId": CATEGORIA_GAMING if es_gaming else CATEGORIA_ENTRETENIMIENTO},
                      "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": bool(para_ninos)}}
            r = self.http.post(SUBIDA, params={"uploadType": "resumable", "part": "snippet,status"}, json=cuerpo,
                               headers={"Authorization": f"Bearer {self._acceso()}",
                                        "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(total)})
            if r.status_code != 200 or "Location" not in r.headers:
                raise _error_api(r, "YouTube no aceptó iniciar la subida")
            sesion = r.headers["Location"]
            subida.update(sesion=sesion, tamano=total, inicio=time.time(), titulo=titulo, canal_id=canal_id)
            guardar(subida)

        fallos = 0
        with open(archivo, "rb") as f:
            while True:
                f.seek(desplazamiento)
                bloque = f.read(BLOQUE)
                fin = desplazamiento + len(bloque) - 1
                try:
                    r = self.http.put(sesion, content=bloque, headers={
                        "Content-Length": str(len(bloque)), "Content-Range": f"bytes {desplazamiento}-{fin}/{total}"})
                    codigo = r.status_code
                except httpx.HTTPError as e:
                    r, codigo = None, 0
                    log.warning("Corte durante la subida: %s", type(e).__name__)
                if codigo in (200, 201):
                    return r.json()["id"]
                if codigo == 308:
                    rango = r.headers.get("Range", "")
                    desplazamiento = int(rango.split("-")[1]) + 1 if "-" in rango else 0
                    progreso(desplazamiento, total)
                    fallos = 0
                    continue
                if codigo and codigo < 500 and codigo != 408 and codigo != 429:
                    raise _error_api(r, "YouTube rechazó la subida")
                # Corte o error temporal: no sabemos qué llegó. Preguntar antes de reenviar.
                fallos += 1
                if fallos > 5:
                    raise ErrorEtapa("La subida se interrumpió varias veces. Se conserva el avance: "
                                     "al reintentar continuará desde donde quedó.", "temporal")
                time.sleep(self.espera * fallos)
                try:
                    estado, valor = self._consultar(sesion, total)
                except (httpx.HTTPError, ErrorEtapa):
                    continue
                if estado == "completo":
                    return str(valor)
                if estado == "perdida":
                    raise ErrorEtapa("YouTube descartó la sesión de subida. Al reintentar se verificará "
                                     "si el video llegó antes de subirlo otra vez.", "incierto")
                desplazamiento = int(valor)


def _solo_propietario(ruta: Path) -> None:
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass
