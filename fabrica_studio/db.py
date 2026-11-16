"""Persistencia en SQLite: trabajos, ajustes y dispositivos vinculados.

Una sola conexión protegida con un candado: el volumen es pequeño y así el
servidor web y el trabajador comparten estado sin sorpresas.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import AJUSTES_POR_DEFECTO

ETAPAS = ["importar", "comprobar", "transcribir", "textos", "subtitulos", "render", "subir"]
ESTADOS = ["pendiente", "procesando", "renderizado", "subiendo", "publicado", "error"]

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS trabajos (
    id TEXT PRIMARY KEY,
    creado REAL NOT NULL,
    actualizado REAL NOT NULL,
    nombre TEXT NOT NULL,
    origen_tipo TEXT NOT NULL,          -- archivo | carpeta | enlace
    origen_ref TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    modo TEXT NOT NULL DEFAULT 'clip',
    estado TEXT NOT NULL DEFAULT 'pendiente',
    etapa TEXT NOT NULL DEFAULT '',
    etapas TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    error_tipo TEXT NOT NULL DEFAULT '',
    avisos TEXT NOT NULL DEFAULT '[]',
    publicar INTEGER NOT NULL DEFAULT 1,
    subir_solicitado INTEGER NOT NULL DEFAULT 0,
    textos TEXT NOT NULL DEFAULT '{}',
    datos TEXT NOT NULL DEFAULT '{}',
    youtube_id TEXT NOT NULL DEFAULT '',
    subida TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS ajustes (clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dispositivos (
    id TEXT PRIMARY KEY, nombre TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
    creado REAL NOT NULL, visto REAL NOT NULL
);
"""
_JSON = {"etapas", "avisos", "textos", "datos", "subida"}


class DB:
    def __init__(self, ruta: Path):
        self._lock = threading.RLock()
        self._c = sqlite3.connect(str(ruta), check_same_thread=False, isolation_level=None)
        self._c.row_factory = sqlite3.Row
        self._c.execute("PRAGMA journal_mode=WAL")
        self._c.executescript(_ESQUEMA)

    # ---------- trabajos ----------
    def _fila(self, r: sqlite3.Row | None) -> dict | None:
        if r is None:
            return None
        d = dict(r)
        for k in _JSON:
            d[k] = json.loads(d[k])
        d["publicar"] = bool(d["publicar"])
        d["subir_solicitado"] = bool(d["subir_solicitado"])
        return d

    def crear_trabajo(self, nombre: str, origen_tipo: str, origen_ref: str = "",
                      publicar: bool = True, modo: str = "clip") -> dict:
        jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        ahora = time.time()
        with self._lock:
            self._c.execute(
                "INSERT INTO trabajos (id, creado, actualizado, nombre, origen_tipo, origen_ref, publicar, modo)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (jid, ahora, ahora, nombre, origen_tipo, origen_ref, int(publicar), modo))
        return self.trabajo(jid)

    def trabajo(self, jid: str) -> dict | None:
        with self._lock:
            return self._fila(self._c.execute("SELECT * FROM trabajos WHERE id=?", (jid,)).fetchone())

    def trabajos(self) -> list[dict]:
        with self._lock:
            filas = self._c.execute("SELECT * FROM trabajos ORDER BY creado DESC").fetchall()
        return [self._fila(r) for r in filas]

    def actualizar(self, jid: str, **campos: Any) -> None:
        if not campos:
            return
        campos["actualizado"] = time.time()
        sets, vals = [], []
        for k, v in campos.items():
            sets.append(f"{k}=?")
            if k in _JSON:
                v = json.dumps(v, ensure_ascii=False)
            elif isinstance(v, bool):
                v = int(v)
            vals.append(v)
        with self._lock:
            self._c.execute(f"UPDATE trabajos SET {', '.join(sets)} WHERE id=?", (*vals, jid))

    def marcar_etapa(self, jid: str, etapa: str, estado: str, detalle: str = "") -> None:
        with self._lock:
            t = self.trabajo(jid)
            if not t:
                return
            etapas = t["etapas"]
            etapas[etapa] = {"estado": estado, "detalle": detalle, "t": time.time()}
            self.actualizar(jid, etapas=etapas, etapa=etapa)

    def anadir_aviso(self, jid: str, aviso: str) -> None:
        with self._lock:
            t = self.trabajo(jid)
            if t and aviso not in t["avisos"]:
                self.actualizar(jid, avisos=t["avisos"] + [aviso])

    def borrar_trabajo(self, jid: str) -> None:
        with self._lock:
            self._c.execute("DELETE FROM trabajos WHERE id=?", (jid,))

    def por_sha(self, sha: str) -> dict | None:
        with self._lock:
            return self._fila(self._c.execute(
                "SELECT * FROM trabajos WHERE sha256=? ORDER BY creado LIMIT 1", (sha,)).fetchone())

    def siguiente(self) -> dict | None:
        """Siguiente trabajo que necesita al trabajador (el más antiguo primero)."""
        with self._lock:
            return self._fila(self._c.execute(
                "SELECT * FROM trabajos WHERE estado='pendiente'"
                " OR (estado='renderizado' AND subir_solicitado=1) ORDER BY creado LIMIT 1").fetchone())

    def recuperar_interrumpidos(self) -> int:
        """Tras un reinicio: lo que estaba a medias vuelve a la cola.

        Las etapas ya terminadas se conservan en disco, así que no se repite trabajo.
        Una subida a medias se retoma verificando primero su estado en YouTube.
        """
        with self._lock:
            n = self._c.execute("UPDATE trabajos SET estado='pendiente' WHERE estado='procesando'").rowcount
            n += self._c.execute(
                "UPDATE trabajos SET estado='renderizado', subir_solicitado=1 WHERE estado='subiendo'").rowcount
        return n

    # ---------- ajustes ----------
    def ajustes(self) -> dict:
        with self._lock:
            filas = self._c.execute("SELECT clave, valor FROM ajustes").fetchall()
        a = dict(AJUSTES_POR_DEFECTO)
        for r in filas:
            if r["clave"] in a:
                a[r["clave"]] = json.loads(r["valor"])
        return a

    def guardar_ajustes(self, cambios: dict) -> dict:
        """Guarda solo claves conocidas y convierte al tipo del valor por defecto."""
        with self._lock:
            for k, v in cambios.items():
                if k not in AJUSTES_POR_DEFECTO:
                    continue
                base = AJUSTES_POR_DEFECTO[k]
                try:
                    if isinstance(base, bool):
                        v = bool(v)
                    elif isinstance(base, int):
                        v = int(float(v))
                    else:
                        v = str(v).strip()
                except (TypeError, ValueError):
                    continue
                self._c.execute("INSERT INTO ajustes (clave, valor) VALUES (?,?)"
                                " ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                                (k, json.dumps(v)))
        return self.ajustes()

    # ---------- dispositivos ----------
    def crear_dispositivo(self, nombre: str, token_hash: str) -> str:
        did = uuid.uuid4().hex[:10]
        with self._lock:
            self._c.execute("INSERT INTO dispositivos VALUES (?,?,?,?,?)",
                            (did, nombre[:60] or "Dispositivo", token_hash, time.time(), time.time()))
        return did

    def dispositivo_por_token(self, token_hash: str) -> dict | None:
        with self._lock:
            r = self._c.execute("SELECT * FROM dispositivos WHERE token_hash=?", (token_hash,)).fetchone()
            if r:
                self._c.execute("UPDATE dispositivos SET visto=? WHERE id=?", (time.time(), r["id"]))
        return dict(r) if r else None

    def dispositivos(self) -> list[dict]:
        with self._lock:
            return [{k: r[k] for k in ("id", "nombre", "creado", "visto")}
                    for r in self._c.execute("SELECT * FROM dispositivos ORDER BY creado").fetchall()]

    def borrar_dispositivo(self, did: str) -> None:
        with self._lock:
            self._c.execute("DELETE FROM dispositivos WHERE id=?", (did,))
