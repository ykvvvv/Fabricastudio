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

from .config import AJUSTES_POR_DEFECTO, CAMPOS_PERFIL, COLORES, LIMITES, OPCIONES
from .errores import ErrorEtapa

ETAPAS = ["importar", "comprobar", "transcribir", "textos", "subtitulos", "render", "subir"]
ESTADOS = ["pendiente", "procesando", "propuestas", "renderizado", "subiendo", "publicado", "error"]

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
CREATE TABLE IF NOT EXISTS cuenta (
    id INTEGER PRIMARY KEY CHECK (id = 1), nombre TEXT NOT NULL, hash TEXT NOT NULL,
    creado REAL NOT NULL, cambiado REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sesiones (
    id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, agente TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '', creado REAL NOT NULL, visto REAL NOT NULL, expira REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS dispositivos (
    id TEXT PRIMARY KEY, nombre TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
    creado REAL NOT NULL, visto REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS perfiles (
    id TEXT PRIMARY KEY, creado REAL NOT NULL, actualizado REAL NOT NULL,
    nombre TEXT NOT NULL, valores TEXT NOT NULL DEFAULT '{}'
);
"""
_JSON = {"etapas", "avisos", "textos", "datos", "subida"}


NOMBRES_AJUSTES = {
    "video_desplazamiento_y": "desplazamiento del video", "video_alto_max": "alto máximo del video",
    "banner_tamano": "tamaño del banner", "banner_ancho": "ancho de la tarjeta", "sub_tamano": "tamaño de subtítulos",
    "logo_alto": "alto del logo", "nombre_tamano": "tamaño de la firma", "completo_zoom": "zoom",
}


NOMBRES_CAMPO_PERFIL = {"nombre": "Nombre", "firma": "Firma", "contexto_transcripcion": "Contexto de transcripción",
                        "correcciones": "Correcciones de escritura", "hashtags_fijos": "Hashtags fijos"}


def validar_perfil(campos: dict, otros: list[dict]) -> dict:
    """Normaliza los campos conocidos de un perfil (los demás se ignoran). Un valor que no vale rechaza todo el
    cambio. `otros`: los demás perfiles, para no repetir nombres."""
    if not isinstance(campos, dict):
        raise ErrorEtapa("Datos del perfil no válidos.", "entrada")
    limpio = {}
    for k, v in campos.items():
        if k not in CAMPOS_PERFIL:
            continue
        v = str(v if v is not None else "").strip()
        largo = CAMPOS_PERFIL[k][1]
        if k == "tema" and v not in OPCIONES["tema"]:
            raise ErrorEtapa(f"Tema no válido: {v}.", "entrada")
        if k == "estilo" and v and v not in OPCIONES["estilo"]:
            raise ErrorEtapa(f"Estilo no válido: {v}.", "entrada")
        if largo and len(v) > largo:
            raise ErrorEtapa(f"«{NOMBRES_CAMPO_PERFIL[k]}» admite hasta {largo} caracteres (tiene {len(v)}).", "entrada")
        limpio[k] = v
    if "nombre" in limpio:
        if not limpio["nombre"]:
            raise ErrorEtapa("El perfil necesita un nombre.", "entrada")
        if any(p["nombre"].casefold() == limpio["nombre"].casefold() for p in otros):
            raise ErrorEtapa(f"Ya hay un perfil llamado «{limpio['nombre']}».", "duplicado")
    return limpio


def perfil_como_ajustes(p: dict) -> dict:
    """Valores de un perfil con el nombre del ajuste que sustituyen al procesar un clip (nombre → creador,
    contexto_transcripcion → vocabulario…). Un estilo vacío no sustituye nada: vale el general."""
    a = {clave: p.get(campo, "") for campo, (clave, _) in CAMPOS_PERFIL.items()}
    if not a["estilo"]:
        a.pop("estilo")
    return a


def validar_ajustes(cambios: dict) -> None:
    import re

    for k, v in cambios.items():
        nombre = NOMBRES_AJUSTES.get(k, k.replace("_", " "))
        if k in LIMITES:
            try:
                n = int(float(v))
            except (TypeError, ValueError):
                raise ErrorEtapa(f"«{nombre}» debe ser un número.", "entrada")
            lo, hi = LIMITES[k]
            if not lo <= n <= hi:
                raise ErrorEtapa(f"«{nombre}» debe estar entre {lo} y {hi} (recibido: {n}).", "entrada")
        elif k in OPCIONES and str(v) not in OPCIONES[k]:
            raise ErrorEtapa(f"Valor no válido para «{nombre}»: {v}.", "entrada")
        elif k in COLORES and not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(v).strip()):
            raise ErrorEtapa(f"«{nombre}» debe ser un color como #E3222A.", "entrada")


class DB:
    def __init__(self, ruta: Path):
        self._lock = threading.RLock()
        self._c = sqlite3.connect(str(ruta), check_same_thread=False, isolation_level=None)
        self._c.row_factory = sqlite3.Row
        self._c.execute("PRAGMA journal_mode=WAL")
        self._c.executescript(_ESQUEMA)
        self._migrar_perfiles()

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

    def proxima_subida(self, ahora: float | None = None) -> float:
        """Momento (epoch) desde el que se puede subir otro video según el ritmo de publicación
        y la pausa por límite diario. Si ya se puede, devuelve un valor <= ahora."""
        ahora = ahora or time.time()
        a = self.ajustes()
        with self._lock:
            filas = self._c.execute("SELECT subida FROM trabajos WHERE youtube_id != ''").fetchall()
        hechas = sorted(t for t in (json.loads(r["subida"]).get("terminado") for r in filas) if t)
        desde = a["subidas_pausadas_hasta"]
        if hechas and a["subidas_intervalo_min"]:
            desde = max(desde, hechas[-1] + a["subidas_intervalo_min"] * 60)
        recientes = [t for t in hechas if t > ahora - 86400]
        if a["subidas_max_dia"] and len(recientes) >= a["subidas_max_dia"]:
            desde = max(desde, recientes[-a["subidas_max_dia"]] + 86400)    # cuando la más antigua cumpla 24 h
        return desde

    def siguiente(self) -> dict | None:
        """Siguiente trabajo que necesita al trabajador (el más antiguo primero).
        Las subidas esperan su turno según el ritmo de publicación o la pausa por límite diario;
        mientras tanto se sigue procesando y renderizando."""
        subir = time.time() >= self.proxima_subida()
        with self._lock:
            return self._fila(self._c.execute(
                "SELECT * FROM trabajos WHERE estado='pendiente'"
                + (" OR (estado='renderizado' AND subir_solicitado=1)" if subir else "")
                + " ORDER BY creado LIMIT 1").fetchone())

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
        """Guarda solo claves conocidas y convierte al tipo del valor por defecto.
        Un valor fuera de rango rechaza todo el cambio (no se guarda nada a medias)."""
        validar_ajustes(cambios)
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

    # ---------- perfiles de creador ----------
    def _migrar_perfiles(self) -> None:
        """La primera vez, el perfil inicial copia los valores que se usan hoy (también los que vienen por defecto
        y nunca se guardaron) y los clips ya importados quedan con él: para ellos nada cambia. Un único INSERT
        condicional: si el panel y el servidor MCP arrancan a la vez, solo uno lo crea."""
        a = self.ajustes()
        valores = {campo: a[clave] for campo, (clave, _) in CAMPOS_PERFIL.items() if campo != "nombre"}
        valores["estilo"] = ""                      # sigue al estilo general de la Plantilla, como hasta ahora
        pid, ahora = uuid.uuid4().hex[:8], time.time()
        with self._lock:
            creado = self._c.execute(
                "INSERT INTO perfiles SELECT ?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM perfiles)",
                (pid, ahora, ahora, (a["creador"] or "Mi canal").strip()[:40] or "Mi canal",
                 json.dumps(valores, ensure_ascii=False))).rowcount
            if creado:
                self._c.execute("UPDATE trabajos SET datos=json_set(datos, '$.perfil', ?) "
                                "WHERE json_extract(datos, '$.perfil') IS NULL", (pid,))
        if creado or not self.perfil(a["perfil_activo"]):
            self.guardar_ajustes({"perfil_activo": pid if creado else self.perfiles()[0]["id"]})

    def _perfil(self, r: sqlite3.Row) -> dict:
        vacios = {k: "" for k in CAMPOS_PERFIL if k != "nombre"}
        return {"id": r["id"], "nombre": r["nombre"], "creado": r["creado"], "actualizado": r["actualizado"],
                **vacios, **{k: v for k, v in json.loads(r["valores"]).items() if k in vacios}}

    def perfiles(self) -> list[dict]:
        with self._lock:
            filas = self._c.execute("SELECT * FROM perfiles ORDER BY creado, nombre").fetchall()
        return [self._perfil(r) for r in filas]

    def perfil(self, pid: str | None) -> dict | None:
        if not pid:
            return None
        with self._lock:
            r = self._c.execute("SELECT * FROM perfiles WHERE id=?", (pid,)).fetchone()
        return self._perfil(r) if r else None

    def perfil_activo(self) -> dict:
        """El que reciben los clips nuevos. Siempre existe: el activo no se puede eliminar."""
        return self.perfil(self.ajustes()["perfil_activo"]) or self.perfiles()[0]

    def crear_perfil(self, campos: dict) -> dict:
        limpio = validar_perfil(campos, self.perfiles())
        if not limpio.get("nombre"):
            raise ErrorEtapa("El perfil necesita un nombre.", "entrada")
        valores = {k: limpio.get(k, "") for k in CAMPOS_PERFIL if k != "nombre"}
        pid, ahora = uuid.uuid4().hex[:8], time.time()
        with self._lock:
            self._c.execute("INSERT INTO perfiles VALUES (?,?,?,?,?)",
                            (pid, ahora, ahora, limpio["nombre"], json.dumps(valores, ensure_ascii=False)))
        return self.perfil(pid)

    def editar_perfil(self, pid: str, campos: dict) -> dict:
        """Cambia solo los campos indicados. Sin campos, solo marca el perfil como actualizado (p. ej. logo nuevo)."""
        p = self.perfil(pid)
        if not p:
            raise ErrorEtapa("Ese perfil de creador no existe.", "entrada")
        nuevo = {**p, **validar_perfil(campos, [x for x in self.perfiles() if x["id"] != pid])}
        valores = {k: nuevo[k] for k in CAMPOS_PERFIL if k != "nombre"}
        with self._lock:
            self._c.execute("UPDATE perfiles SET nombre=?, valores=?, actualizado=? WHERE id=?",
                            (nuevo["nombre"], json.dumps(valores, ensure_ascii=False), time.time(), pid))
        return self.perfil(pid)

    def borrar_perfil(self, pid: str) -> None:
        with self._lock:
            self._c.execute("DELETE FROM perfiles WHERE id=?", (pid,))

    def uso_perfiles(self) -> dict[str, int]:
        """Cuántos clips guardan cada perfil."""
        with self._lock:
            filas = self._c.execute("SELECT json_extract(datos, '$.perfil') AS p, count(*) AS n "
                                    "FROM trabajos GROUP BY p").fetchall()
        return {r["p"]: r["n"] for r in filas if r["p"]}

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

    # ---------- cuenta y sesiones ----------
    def cuenta(self) -> dict | None:
        with self._lock:
            r = self._c.execute("SELECT * FROM cuenta WHERE id=1").fetchone()
        return dict(r) if r else None

    def crear_cuenta(self, nombre: str, hash_: str) -> bool:
        """Crea la cuenta solo si no existe (devuelve False si ya había una)."""
        with self._lock:
            try:
                self._c.execute("INSERT INTO cuenta VALUES (1,?,?,?,?)", (nombre, hash_, time.time(), time.time()))
                return True
            except sqlite3.IntegrityError:
                return False

    def cambiar_contrasena(self, hash_: str) -> None:
        with self._lock:
            self._c.execute("UPDATE cuenta SET hash=?, cambiado=? WHERE id=1", (hash_, time.time()))
            self._c.execute("DELETE FROM sesiones")

    def borrar_cuenta(self) -> None:
        with self._lock:
            self._c.execute("DELETE FROM cuenta")
            self._c.execute("DELETE FROM sesiones")

    def crear_sesion(self, token_hash: str, agente: str, ip: str, duracion: float) -> str:
        sid = uuid.uuid4().hex[:12]
        ahora = time.time()
        with self._lock:
            self._c.execute("DELETE FROM sesiones WHERE expira < ?", (ahora,))
            self._c.execute("INSERT INTO sesiones VALUES (?,?,?,?,?,?,?)",
                            (sid, token_hash, agente[:120], ip[:60], ahora, ahora, ahora + duracion))
        return sid

    def sesion_por_token(self, token_hash: str) -> dict | None:
        ahora = time.time()
        with self._lock:
            r = self._c.execute("SELECT * FROM sesiones WHERE token_hash=? AND expira>=?", (token_hash, ahora)).fetchone()
            if r and ahora - r["visto"] > 60:
                self._c.execute("UPDATE sesiones SET visto=? WHERE id=?", (ahora, r["id"]))
        return dict(r) if r else None

    def sesiones(self) -> list[dict]:
        with self._lock:
            return [{k: r[k] for k in ("id", "agente", "ip", "creado", "visto", "expira")} for r in
                    self._c.execute("SELECT * FROM sesiones WHERE expira>=? ORDER BY visto DESC", (time.time(),)).fetchall()]

    def borrar_sesion(self, sid: str | None = None, token_hash: str | None = None) -> None:
        with self._lock:
            if sid:
                self._c.execute("DELETE FROM sesiones WHERE id=?", (sid,))
            if token_hash:
                self._c.execute("DELETE FROM sesiones WHERE token_hash=?", (token_hash,))

