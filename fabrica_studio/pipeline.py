"""El trabajador: recorre las etapas de cada trabajo y guarda los resultados intermedios.

Cada etapa deja un archivo en la carpeta del trabajo. Si el archivo ya existe,
la etapa no se repite: reintentar, cambiar el logo o corregir un texto no vuelve
a transcribir ni a consumir API.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path

from . import edicion, exportar, importar, media, momentos, reencuadre, render, subtitulos, textos, transcribe
from .config import AJUSTES_DE_DISENO, CAMPOS_PERFIL, Rutas
from .db import DB, perfil_como_ajustes
from .errores import ErrorEtapa, sin_secretos
from .youtube import YouTube

log = logging.getLogger("fabrica.pipeline")


def _leer(ruta: Path):
    return json.loads(ruta.read_text(encoding="utf-8"))


def _escribir(ruta: Path, datos) -> None:
    """Escritura atómica: un corte de luz no deja un JSON a medias."""
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ruta)


def res_recorte(carpeta: Path) -> dict | None:
    f = carpeta / "bordes.json"
    return _leer(f)["recorte"] if f.exists() else None


class sin_suspender:
    """Mientras se procesa o se sube un clip, pide a Windows que no suspenda el equipo
    (la pantalla sí puede apagarse). En otros sistemas no hace nada."""

    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001

    def __enter__(self):
        self._ok = False
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED)
                self._ok = True
            except Exception:
                log.debug("No se pudo pedir a Windows que no suspenda el equipo", exc_info=True)
        return self

    def __exit__(self, *exc):
        if self._ok:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
        return False


CONTEXTO_GTA6 = "Hablando de GTA 6 y GTA 5: Vice City, Leonida, Ambrosia, Lucía y Jason."


def contexto_transcripcion(a: dict) -> str:
    """Frase de contexto para Whisper; en modo GTA 6 se le suma el vocabulario del juego."""
    base = (a.get("vocabulario") or "").strip()
    if a.get("tema") == "gta6" and CONTEXTO_GTA6 not in base:
        base = f"{base} {CONTEXTO_GTA6}".strip()
    return base


MENSAJE_COPIANDO = "Esperando a que termine de copiarse…"


def _reloj(seg: float) -> str:
    return f"{int(seg) // 60}:{int(seg) % 60:02d}"


def _nombre_seguro(nombre: str) -> str:
    base = re.sub(r"[^\w\-. áéíóúüñÁÉÍÓÚÜÑ]", "_", Path(nombre).stem).strip(" .")[:80]
    return base or "clip"


class Fabrica:
    def __init__(self, rutas: Rutas | None = None, youtube: YouTube | None = None):
        self.rutas = rutas or Rutas()
        self.rutas.crear()
        self.db = DB(self.rutas.db)
        self.youtube = youtube or YouTube(self.rutas.secretos)
        self._parar = threading.Event()
        self._hilos: list[threading.Thread] = []
        self._vistos: dict[str, tuple] = {}       # carpeta vigilada: archivo -> (tamaño, mtime, desde)
        self.carpeta_estado: dict[str, str] = {}  # archivo -> motivo por el que aún no se importa
        self.progreso: dict[str, str] = {}        # trabajo -> texto de avance (no persistente)

    # ------------------------------------------------------------ perfiles de creador
    def perfil_de(self, t: dict) -> dict:
        """Perfil con el que se procesa un clip: el que se le asignó al importarlo, aunque después se active otro.
        Si ese perfil se eliminó, la copia que se le guardó al eliminarlo."""
        d = t["datos"]
        return self.db.perfil(d.get("perfil")) or d.get("perfil_copia") or self.db.perfil_activo()

    def ajustes_de(self, t: dict) -> dict:
        """Ajustes generales con los del perfil del clip encima (nombre, firma, contexto, tema…)."""
        return {**self.db.ajustes(), **perfil_como_ajustes(self.perfil_de(t))}

    def carpeta_logo(self, perfil: dict) -> Path:
        """Carpeta del logo.png que se dibuja: el propio del perfil o, si no tiene, el logo general."""
        propia = self.rutas.perfiles / perfil["id"]
        return propia if (propia / "logo.png").exists() else self.rutas.recursos

    def perfiles(self) -> list[dict]:
        """Perfiles con lo que el panel muestra: si tienen logo, cuántos clips los usan y el contexto que recibe Whisper."""
        uso = self.db.uso_perfiles()
        return [{**p, "logo": (self.rutas.perfiles / p["id"] / "logo.png").exists(), "en_uso": uso.get(p["id"], 0),
                 "contexto_efectivo": contexto_transcripcion(perfil_como_ajustes(p))} for p in self.db.perfiles()]

    def activar_perfil(self, pid: str) -> dict:
        """Los clips que se importen desde ahora usarán este perfil; los ya importados conservan el suyo."""
        p = self.db.perfil(pid)
        if not p:
            raise ErrorEtapa("Ese perfil de creador no existe.", "entrada")
        self.db.guardar_ajustes({"perfil_activo": pid})
        return p

    def duplicar_perfil(self, pid: str) -> dict:
        p = self.db.perfil(pid)
        if not p:
            raise ErrorEtapa("Ese perfil de creador no existe.", "entrada")
        usados = {x["nombre"].casefold() for x in self.db.perfiles()}
        base = f"{p['nombre'][:28]} (copia"
        nombre = next(n for n in [f"{base})"] + [f"{base} {i})" for i in range(2, 100)] if n.casefold() not in usados)
        nuevo = self.db.crear_perfil({**{k: p[k] for k in CAMPOS_PERFIL}, "nombre": nombre})
        logo = self.rutas.perfiles / pid / "logo.png"
        if logo.exists():
            (self.rutas.perfiles / nuevo["id"]).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(logo, self.rutas.perfiles / nuevo["id"] / "logo.png")
        return nuevo

    def eliminar_perfil(self, pid: str, confirmar: bool = False) -> None:
        """No se elimina el activo. Si hay clips con este perfil hace falta confirmar: cada uno guarda una copia de
        sus valores (nombre, firma, contexto, tema…) para seguir igual; el logo propio se borra (usarán el general)."""
        p = self.db.perfil(pid)
        if not p:
            raise ErrorEtapa("Ese perfil de creador no existe.", "entrada")
        if pid == self.db.perfil_activo()["id"]:
            raise ErrorEtapa("Es el perfil activo: activa otro antes de eliminarlo.", "entrada")
        usados = [t for t in self.db.trabajos() if t["datos"].get("perfil") == pid]
        if any(t["estado"] in ("procesando", "subiendo") for t in usados):
            raise ErrorEtapa("Hay clips de este perfil en proceso: espera a que terminen para eliminarlo.", "entrada")
        if usados and not confirmar:
            raise ErrorEtapa(f"Lo usan {len(usados)} clips. Si lo eliminas, esos clips conservan una copia de su "
                             "nombre, firma, contexto y tema; su logo propio se borra.", "confirmar")
        copia = {k: p[k] for k in ("id", *CAMPOS_PERFIL)}
        for t in usados:
            self.db.actualizar(t["id"], datos={**t["datos"], "perfil_copia": copia})
        self.db.borrar_perfil(pid)
        shutil.rmtree(self.rutas.perfiles / pid, ignore_errors=True)

    def _perfil_para_importar(self, perfil: str | None) -> str:
        if perfil and not self.db.perfil(perfil):
            raise ErrorEtapa("Ese perfil de creador no existe.", "entrada")
        return perfil or self.db.perfil_activo()["id"]

    # ------------------------------------------------------------ importación
    def importar_archivo(self, origen: Path, nombre: str, origen_tipo: str = "archivo",
                         publicar: bool = True, mover: bool = False, modo: str = "clip",
                         perfil: str | None = None) -> dict:
        """Crea un trabajo a partir de un archivo local con el perfil indicado (o el activo).
        Rechaza duplicados exactos."""
        if Path(nombre).suffix.lower() not in media.EXTENSIONES:
            raise ErrorEtapa(f"Formato no admitido: {Path(nombre).suffix or 'sin extensión'}. "
                             f"Usa {', '.join(sorted(media.EXTENSIONES))}.", "entrada")
        pid = self._perfil_para_importar(perfil)
        media.sondear(origen)                      # falla aquí si no es un video legible
        sha = media.sha256(origen)
        previo = self.db.por_sha(sha)
        if previo:
            raise ErrorEtapa(f"Este mismo archivo ya se importó como «{previo['nombre']}» "
                             f"(estado: {previo['estado']}). No se creó un trabajo duplicado.", "duplicado")
        modo = "largo" if modo == "largo" else "clip"
        t = self.db.crear_trabajo(_nombre_seguro(nombre), origen_tipo, modo=modo,
                                  origen_ref=str(origen) if origen_tipo == "carpeta" else nombre, publicar=publicar)
        carpeta = self.rutas.trabajo(t["id"])
        carpeta.mkdir(parents=True)
        destino = carpeta / f"entrada{Path(nombre).suffix.lower()}"
        if mover:
            shutil.move(str(origen), destino)
        else:
            shutil.copyfile(origen, destino)
        self.db.actualizar(t["id"], sha256=sha, datos={"perfil": pid})
        self.db.marcar_etapa(t["id"], "importar", "hecho")
        return self.db.trabajo(t["id"])

    def importar_enlace(self, url: str, publicar: bool = True, modo: str = "clip", perfil: str | None = None) -> dict:
        url = importar.validar_enlace(url)
        pid = self._perfil_para_importar(perfil)
        for t in self.db.trabajos():
            if t["origen_tipo"] == "enlace" and t["origen_ref"] == url:
                raise ErrorEtapa(f"Ese enlace ya está en la cola como «{t['nombre']}».", "duplicado")
        nombre = _nombre_seguro(url.rstrip("/").rsplit("/", 1)[-1] or "clip-kick")
        t = self.db.crear_trabajo(nombre, "enlace", origen_ref=url, publicar=publicar,
                                  modo="largo" if modo == "largo" else "clip")
        self.db.actualizar(t["id"], datos={"perfil": pid})
        self.rutas.trabajo(t["id"]).mkdir(parents=True)
        return self.db.trabajo(t["id"])

    # ------------------------------------------------------------ etapas
    def _entrada(self, carpeta: Path) -> Path | None:
        return next((p for p in sorted(carpeta.glob("entrada.*"))
                     if p.suffix.lower() in media.EXTENSIONES), None)

    def _etapa(self, jid: str, nombre: str, texto: str = "") -> None:
        self.db.marcar_etapa(jid, nombre, "en_curso")
        self.progreso[jid] = texto

    def procesar(self, jid: str) -> None:
        """Ejecuta las etapas pendientes de un trabajo hasta dejarlo renderizado."""
        t = self.db.trabajo(jid)
        carpeta = self.rutas.trabajo(jid)
        carpeta.mkdir(parents=True, exist_ok=True)
        perfil = self.perfil_de(t)
        a = {**self.db.ajustes(), **perfil_como_ajustes(perfil)}     # el perfil del clip, no el activo
        self.db.actualizar(jid, estado="procesando", error="", error_tipo="", subir_solicitado=False)

        # 1. Importar (solo los enlaces descargan aquí).
        entrada = self._entrada(carpeta)
        if not entrada and t["origen_tipo"] == "momento":
            self._etapa(jid, "importar", "Recortando el momento del video original…")
            entrada = self._recortar(jid, carpeta)
        elif not entrada:
            if t["origen_tipo"] != "enlace":
                raise ErrorEtapa("Falta el archivo de entrada de este trabajo.", "entrada")
            self._etapa(jid, "importar", "Descargando el enlace…")
            entrada = importar.descargar(t["origen_ref"], carpeta)
            sha = media.sha256(entrada)
            previo = self.db.por_sha(sha)
            if previo and previo["id"] != jid:
                entrada.unlink()
                raise ErrorEtapa(f"El video de este enlace ya existe como «{previo['nombre']}».", "duplicado")
            self.db.actualizar(jid, sha256=sha)
        self.db.marcar_etapa(jid, "importar", "hecho")

        # 1b. Edición de tiempos (no destructiva): se trabaja sobre editado.mp4.
        f_ed = carpeta / "edicion.json"
        if f_ed.exists():
            ed = _leer(f_ed)
            editado = carpeta / "editado.mp4"
            if ed.get("aplicado") != ed["huella"] or not editado.exists():
                self._etapa(jid, "importar", "Aplicando tu edición de tiempos…")
                edicion.cortar(entrada, ed["tramos"], carpeta, bool(ed.get("tiene_audio", True)))
                ed["aplicado"] = ed["huella"]
                _escribir(f_ed, ed)
                self.db.marcar_etapa(jid, "importar", "hecho", "con edición de tiempos")
            entrada = editado

        # 2. Comprobar.
        f_prop = carpeta / "propiedades.json"
        if not f_prop.exists():
            self._etapa(jid, "comprobar")
            _escribir(f_prop, media.sondear(entrada))
        prop = _leer(f_prop)
        if prop["duracion"] > 180 and t["modo"] != "largo":
            self.db.anadir_aviso(jid, f"Dura {prop['duracion']:.0f} s: YouTube solo trata como Short hasta 3 minutos. "
                                      "Para videos largos, impórtalo como «Video largo» y elige momentos.")
        if not prop["tiene_audio"]:
            self.db.anadir_aviso(jid, "El video no tiene audio: no habrá subtítulos.")
        self.db.marcar_etapa(jid, "comprobar", "hecho",
                             f"{prop['ancho']}×{prop['alto']}, {prop['duracion']:.1f} s, {prop['orientacion']}")

        # 3. Transcribir.
        f_trans = carpeta / "transcripcion.json"
        if not f_trans.exists():
            self._etapa(jid, "transcribir", "Transcribiendo el audio…")
            if prop["tiene_audio"]:
                wav = media.extraer_audio(entrada, carpeta / "audio.wav")
                tr = transcribe.transcribir(wav, a["whisper_modelo"], a["whisper_dispositivo"], a["idioma"],
                                            self.rutas.modelos, vocabulario=contexto_transcripcion(a))
                wav.unlink(missing_ok=True)
            else:
                tr = {"idioma": a["idioma"], "motor": "sin audio", "texto": "", "segmentos": [], "palabras": []}
            _escribir(f_trans, tr)
        tr = _leer(f_trans)
        if prop["tiene_audio"] and not tr["palabras"]:
            self.db.anadir_aviso(jid, "No se detectó voz en el audio: el Short no tendrá subtítulos.")
        self.db.marcar_etapa(jid, "transcribir", "hecho", f"{len(tr['palabras'])} palabras · {tr['motor']}")

        if t["modo"] == "largo":
            self._proponer_momentos(jid, carpeta, tr, a)
            return
        if self._recorte_automatico(jid, t, prop, tr, a):
            return self.procesar(jid)          # vuelve a empezar con el tramo elegido (sin transcribir otra vez)

        # 4. Textos.
        f_ia = carpeta / "textos_generados.json"
        if not f_ia.exists():
            self._etapa(jid, "textos", "Generando banner, título y descripción…")
            texto_corregido = " ".join(p["texto"] for p in subtitulos.corregir_palabras(
                tr["palabras"], subtitulos.leer_correcciones(a["correcciones"]))) or tr["texto"]
            gen = textos.generar(texto_corregido, a["creador"], a["proveedor_textos"],
                                 textos.leer_clave_gemini(self.rutas.secretos), a["gemini_modelo"],
                                 tema=a["tema"], hashtags_fijos=a["hashtags_fijos"], emojis=a["emojis_titulo"])
            _escribir(f_ia, gen)
        gen = _leer(f_ia)
        t = self.db.trabajo(jid)
        if not t["textos"]:
            self.db.actualizar(jid, textos={k: gen[k] for k in ("banner", "titulo", "descripcion", "es_gaming")}
                               | {"origen": gen["origen"]})
            if gen.get("aviso"):
                self.db.anadir_aviso(jid, gen["aviso"])
        t = self.db.trabajo(jid)
        self.db.marcar_etapa(jid, "textos", "hecho", f"origen: {t['textos'].get('origen', '')}")

        # 5. Subtítulos.
        f_sub = carpeta / "subtitulos.json"
        if not f_sub.exists():
            self._etapa(jid, "subtitulos")
            reglas = subtitulos.leer_correcciones(a["correcciones"])
            _escribir(f_sub, {"editado": False, "bloques": subtitulos.agrupar(
                subtitulos.corregir_palabras(tr["palabras"], reglas),
                int(a["sub_palabras_max"]), int(a["sub_caracteres_max"]))})
        sub = _leer(f_sub)
        self.db.marcar_etapa(jid, "subtitulos", "hecho", f"{len(sub['bloques'])} bloques")

        # 6. Render (solo si cambió algo que afecte a la imagen).
        recorte = None
        if a["recortar_bordes"]:
            f_bordes = carpeta / "bordes.json"
            if not f_bordes.exists():
                self._etapa(jid, "render", "Buscando bordes negros en el original…")
                _escribir(f_bordes, {"recorte": media.detectar_bordes(entrada, prop)})
            recorte = _leer(f_bordes)["recorte"]
        estilo = t["datos"].get("estilo") or a["estilo"]
        encuadre = None
        decision = None
        if estilo in ("completo", "dividido", "auto"):
            f_enc = carpeta / "encuadre.json"
            if not f_enc.exists():
                self._etapa(jid, "render", "Buscando rostros para el encuadre…")
                _escribir(f_enc, reencuadre.analizar(entrada, prop, recorte))
            encuadre = _leer(f_enc)
            aviso_encuadre = encuadre.get("aviso")
            if estilo in ("dividido", "auto"):
                arriba = int(round(1920 * int(a["dividido_proporcion"]) / 100)) // 2 * 2
                decision = reencuadre.decidir(encuadre, arriba, 1920 - arriba)
                if decision["tipo"] in ("camara", "dos"):
                    encuadre = {**encuadre, "dividido": decision["plan"]}
                    estilo = "dividido"
                elif estilo == "dividido":
                    estilo = "completo"
                    self.db.anadir_aviso(jid, "Vista dividida: no se encontró la cámara del streamer ni dos sujetos "
                                              "separados. Se usó pantalla completa con seguimiento.")
                elif decision["tipo"] == "seguir":
                    estilo = "completo"
                else:
                    estilo, encuadre = "clasico", None
            if aviso_encuadre and estilo != "clasico":   # el aviso habla del seguimiento: no aplica si «auto» eligió el clásico
                self.db.anadir_aviso(jid, aviso_encuadre)
        recursos = self.carpeta_logo(perfil)
        logo = recursos / "logo.png"
        huella = hashlib.sha256(json.dumps([
            t["textos"]["banner"], sub["bloques"], {k: a[k] for k in AJUSTES_DE_DISENO}, recorte, estilo,
            _leer(carpeta / "edicion.json")["huella"] if (carpeta / "edicion.json").exists() else "",
            (encuadre or {}).get("dividido"), (decision or {}).get("tipo"),
            logo.stat().st_mtime_ns if logo.exists() else 0]
            # con el logo general la huella es la de siempre: los Shorts ya hechos no se renderizan otra vez
            + ([logo.relative_to(self.rutas.base).as_posix()] if recursos != self.rutas.recursos else []),
            sort_keys=True).encode()).hexdigest()
        datos = t["datos"]
        if datos.get("huella_render") != huella or not (carpeta / "short.mp4").exists():
            self._etapa(jid, "render", "Renderizando el video vertical…")
            res = render.renderizar(carpeta, entrada.name, prop, t["textos"]["banner"], sub["bloques"], a,
                                    recursos, recorte=recorte, encuadre=encuadre)
            for aviso in res["disposicion"]["avisos"]:
                self.db.anadir_aviso(jid, aviso)
            datos.update(huella_render=huella, salida=res["propiedades"], disposicion=res["disposicion"])
            copia = self.rutas.renderizados / f"{t['nombre']}__{jid[-6:]}.mp4"
            try:
                shutil.copyfile(carpeta / "short.mp4", copia)
                datos["copia"] = copia.name
            except OSError:      # la copia anterior está abierta en un reproductor (Windows)
                self.db.anadir_aviso(jid, f"No se pudo actualizar la copia en 2_shorts_renderizados ({copia.name}): "
                                          "está abierta en otro programa. El Short del panel sí está al día.")
            self.db.actualizar(jid, datos=datos, subida={})   # un render nuevo invalida subidas a medias
        s = datos["salida"]
        datos.setdefault("copia", "")
        r = recorte
        self.db.marcar_etapa(jid, "render", "hecho", f"{s['ancho']}×{s['alto']}, {s['duracion']:.1f} s"
                             + (" · automático: " + decision["motivo"] if decision and
                                (t["datos"].get("estilo") or a["estilo"]) == "auto" else "")
                             + {"completo": " · pantalla completa con seguimiento",
                                "dividido": " · vista dividida"}.get(estilo, " · clásico")
                             + (f" · bordes negros recortados ({r['w']}×{r['h']})" if r else ""))
        self.progreso.pop(jid, None)
        self.db.actualizar(jid, estado="renderizado", etapa="render",
                           subir_solicitado=bool(t["publicar"] and a["subida_automatica"]))

    # ------------------------------------------------------------ video largo
    def _proponer_momentos(self, jid: str, carpeta: Path, tr: dict, a: dict) -> None:
        f = carpeta / "momentos.json"
        if not f.exists():
            self._etapa(jid, "momentos", "Buscando momentos para recortar…")
            res = momentos.proponer(tr["segmentos"], a["proveedor_textos"],
                                    textos.leer_clave_gemini(self.rutas.secretos),
                                    int(a["momentos_cantidad"]), a["gemini_modelo"])
            if res["aviso"]:
                self.db.anadir_aviso(jid, res["aviso"])
            _escribir(f, res)
        res = _leer(f)
        self.db.marcar_etapa(jid, "momentos", "hecho", f"{len(res['propuestas'])} propuestas · origen: {res['origen']}")
        self.progreso.pop(jid, None)
        self.db.actualizar(jid, estado="propuestas", etapa="momentos")
        if a["momentos_auto"]:
            self._crear_clips_automaticos(jid, res, a)

    def _crear_clips_automaticos(self, jid: str, res: dict, a: dict) -> None:
        """Convierte las propuestas en Shorts sin intervención. Con la heurística local solo lo hace si
        el usuario lo permitió (momentos_auto_solo_ia = False), porque no entiende el contenido."""
        if res["origen"] == "local" and a["momentos_auto_solo_ia"]:
            if res["propuestas"]:
                self.db.anadir_aviso(jid, "Creación automática en pausa: las propuestas vienen de la heurística "
                                          "local, no de Gemini. Revísalas y crea los Shorts a mano, o configura Gemini.")
            return
        creados = 0
        for p in res["propuestas"]:
            try:
                self.crear_clip(jid, p["inicio"], p["fin"])
                creados += 1
            except ErrorEtapa as e:
                if e.tipo != "duplicado":
                    self.db.anadir_aviso(jid, f"No se creó el momento {p.get('id', '?')}: {e}")
        if creados:
            self.db.anadir_aviso(jid, f"Se crearon automáticamente {creados} Shorts a partir de las propuestas.")

    def crear_clip(self, jid: str, inicio: float, fin: float) -> dict:
        """Crea un trabajo de clip a partir de un tramo de un video largo."""
        padre = self._trabajo(jid)
        carpeta = self.rutas.trabajo(jid)
        if padre["modo"] != "largo" or not (carpeta / "propiedades.json").exists():
            raise ErrorEtapa("Este trabajo no es un video largo ya analizado.", "entrada")
        try:
            inicio, fin = round(float(inicio), 2), round(float(fin), 2)
        except (TypeError, ValueError):
            raise ErrorEtapa("Los tiempos del momento no son válidos.", "entrada")
        duracion = _leer(carpeta / "propiedades.json")["duracion"]
        if inicio < 0 or fin > duracion + 0.5 or fin - inicio < 3:
            raise ErrorEtapa("El tramo debe estar dentro del video y durar al menos 3 segundos.", "entrada")
        if fin - inicio > 180:
            raise ErrorEtapa("El tramo supera los 3 minutos que admite un Short.", "entrada")
        ref = f"{jid}:{inicio:.2f}-{fin:.2f}"
        if any(t["origen_tipo"] == "momento" and t["origen_ref"] == ref for t in self.db.trabajos()):
            raise ErrorEtapa("Ya existe un clip creado con ese mismo tramo.", "duplicado")
        hijo = self.db.crear_trabajo(f"{padre['nombre']} {_reloj(inicio)}-{_reloj(fin)}".replace(":", "m"),
                                     "momento", origen_ref=ref, publicar=padre["publicar"])
        self.rutas.trabajo(hijo["id"]).mkdir(parents=True)
        herencia = {k: padre["datos"][k] for k in ("perfil", "perfil_copia") if k in padre["datos"]}   # su mismo creador
        self.db.actualizar(hijo["id"], datos={"padre": jid, "inicio": inicio, "fin": fin, **herencia})
        return self.db.trabajo(hijo["id"])

    def _recortar(self, jid: str, carpeta: Path) -> Path:
        """Corta el tramo del video original y reutiliza su transcripción (no se transcribe otra vez)."""
        d = self.db.trabajo(jid)["datos"]
        origen = self.rutas.trabajo(d["padre"])
        fuente = self._entrada(origen) if origen.exists() else None
        if not fuente or not (origen / "transcripcion.json").exists():
            raise ErrorEtapa("El video largo original ya no está disponible; no se puede recortar.", "entrada")
        media.ejecutar([media.herramienta("ffmpeg"), "-y", "-v", "error", "-ss", f"{d['inicio']:.3f}",
                        "-i", str(fuente), "-t", f"{d['fin'] - d['inicio']:.3f}", "-map", "0:v:0", "-map", "0:a:0?",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "recorte_tmp.mp4"], cwd=carpeta)
        render.reemplazar(carpeta / "recorte_tmp.mp4", carpeta / "entrada.mp4")
        _escribir(carpeta / "transcripcion.json",
                  momentos.recortar_transcripcion(_leer(origen / "transcripcion.json"), d["inicio"], d["fin"]))
        self.db.actualizar(jid, sha256=media.sha256(carpeta / "entrada.mp4"))
        return carpeta / "entrada.mp4"

    def proponer_de_nuevo(self, jid: str) -> None:
        t = self._trabajo(jid)
        if t["modo"] != "largo" or t["estado"] not in ("propuestas", "error"):
            raise ErrorEtapa("Solo se pueden volver a proponer momentos en un video largo ya analizado.", "entrada")
        (self.rutas.trabajo(jid) / "momentos.json").unlink(missing_ok=True)
        self.db.actualizar(jid, estado="pendiente", error="", error_tipo="",
                           avisos=[x for x in t["avisos"] if not x.startswith("Momentos propuestos")])

    def subir(self, jid: str) -> None:
        t = self.db.trabajo(jid)
        if t["youtube_id"]:
            self.db.actualizar(jid, estado="publicado", subir_solicitado=False)
            return
        a = self.db.ajustes()
        carpeta = self.rutas.trabajo(jid)
        self.db.actualizar(jid, estado="subiendo", subir_solicitado=False, error="", error_tipo="")
        self._etapa(jid, "subir", "Subiendo a YouTube en privado…")

        def guardar(estado: dict) -> None:
            self.db.actualizar(jid, subida=estado)

        def progreso(enviado: int, total: int) -> None:
            self.progreso[jid] = f"Subiendo a YouTube… {enviado * 100 // total} %"

        vid = self.youtube.subir(carpeta / "short.mp4", t["textos"]["titulo"], t["textos"]["descripcion"],
                                 a["youtube_canal_id"], bool(t["textos"].get("es_gaming")),
                                 bool(a["contenido_para_ninos"]), dict(t["subida"]), guardar, progreso)
        if not vid:
            raise ErrorEtapa("YouTube no devolvió el ID del video; revisa YouTube Studio antes de reintentar.", "incierto")
        self.db.actualizar(jid, youtube_id=vid, estado="publicado",
                           subida={"canal_id": a["youtube_canal_id"], "terminado": time.time(), "privacidad": "private"})
        self.db.marcar_etapa(jid, "subir", "hecho", f"privado · {vid}")
        self.progreso.pop(jid, None)
        # El original solo sale de la carpeta de crudos cuando la subida está confirmada.
        if t["origen_tipo"] == "carpeta":
            origen = Path(t["origen_ref"])
            if origen.exists():
                destino = self.rutas.procesados / origen.name
                if destino.exists():
                    destino = self.rutas.procesados / f"{origen.stem}__{jid[-6:]}{origen.suffix}"
                try:
                    shutil.move(str(origen), destino)
                except OSError:
                    self.db.anadir_aviso(jid, f"Subido, pero no se pudo mover {origen.name} a 3_procesados_ok "
                                              "(¿abierto en otro programa?). Muévelo a mano.")

    def _ejecutar(self, t: dict) -> None:
        jid = t["id"]
        subiendo = t["estado"] == "renderizado"
        try:
            self.subir(jid) if subiendo else self.procesar(jid)
        except ErrorEtapa as e:
            if subiendo and e.tipo == "cuota":
                self._pausar_subidas(jid, str(e))
            else:
                self._fallo(jid, str(e), e.tipo)
        except Exception as e:   # un fallo inesperado no debe tumbar al trabajador ni a los demás clips
            log.error("Fallo inesperado en %s:\n%s", jid, sin_secretos(traceback.format_exc()))
            self._fallo(jid, f"Error interno ({type(e).__name__}): {e}", "interno")

    def _pausar_subidas(self, jid: str, mensaje: str) -> None:
        """Límite diario de YouTube: el trabajo queda en cola para subir y todas las subidas se pausan
        hasta después del reinicio (medianoche del Pacífico = 07:00 u 08:00 UTC; se usa 09:00 UTC)."""
        ahora = time.time()
        hasta = (int(ahora // 86400) * 86400) + 9 * 3600
        if hasta <= ahora + 600:
            hasta += 86400
        self.db.guardar_ajustes({"subidas_pausadas_hasta": int(hasta)})
        hora = time.strftime("%d-%m %H:%M", time.localtime(hasta))
        self.db.actualizar(jid, estado="renderizado", subir_solicitado=True, error="", error_tipo="")
        self.db.marcar_etapa(jid, "subir", "pendiente", f"en espera hasta {hora}")
        self.db.anadir_aviso(jid, f"YouTube alcanzó su límite diario ({sin_secretos(mensaje)[:160]}). "
                                  f"La subida se reintentará sola después de las {hora}.")
        self.progreso.pop(jid, None)

    def reanudar_subidas(self) -> None:
        """Quitar la pausa manualmente (botón del panel)."""
        self.db.guardar_ajustes({"subidas_pausadas_hasta": 0})

    def _fallo(self, jid: str, mensaje: str, tipo: str) -> None:
        t = self.db.trabajo(jid)
        if not t:
            return
        mensaje = sin_secretos(mensaje)
        etapa = t["etapa"] or "importar"
        self.db.marcar_etapa(jid, etapa, "error", mensaje[:200])
        self.db.actualizar(jid, estado="error", error=mensaje, error_tipo=tipo, subir_solicitado=False)
        self.progreso.pop(jid, None)

    # ------------------------------------------------------------ acciones del panel
    def reintentar(self, jid: str) -> None:
        t = self._trabajo(jid)
        if t["estado"] != "error":
            raise ErrorEtapa("Solo se pueden reintentar trabajos con error.", "entrada")
        if t["etapa"] == "subir" and (self.rutas.trabajo(jid) / "short.mp4").exists():
            self.db.actualizar(jid, estado="renderizado", subir_solicitado=True, error="", error_tipo="")
        else:
            self.db.actualizar(jid, estado="pendiente", error="", error_tipo="")

    def solicitar_subida(self, jid: str) -> None:
        t = self._trabajo(jid)
        if t["youtube_id"]:
            raise ErrorEtapa("Este Short ya se subió; no se sube dos veces.", "duplicado")
        if t["estado"] != "renderizado":
            raise ErrorEtapa("El Short aún no está renderizado.", "entrada")
        if not self.db.ajustes()["youtube_canal_id"]:
            raise ErrorEtapa("Primero conecta YouTube y confirma el canal en Ajustes.", "configuracion")
        self.db.actualizar(jid, subir_solicitado=True)

    def _editable(self, jid: str) -> dict:
        t = self._trabajo(jid)
        if t["estado"] in ("procesando", "subiendo") or t["subir_solicitado"]:
            raise ErrorEtapa("El trabajo está en proceso; espera a que termine.", "entrada")
        if t["youtube_id"]:
            raise ErrorEtapa("Este Short ya se subió. Edita el título o la descripción en YouTube Studio.", "entrada")
        if t["modo"] == "largo":
            raise ErrorEtapa("Un video largo no se edita ni renderiza: crea clips a partir de sus momentos.", "entrada")
        return t

    def editar_textos(self, jid: str, cambios: dict) -> dict:
        t = self._editable(jid)
        if not t["textos"]:
            raise ErrorEtapa("Los textos aún no se han generado.", "entrada")
        nuevo = textos.normalizar({**t["textos"], **{k: v for k, v in cambios.items()
                                                    if k in ("banner", "titulo", "descripcion", "es_gaming")}},
                                  manual=True)
        nuevo["origen"] = "editado" if any(nuevo[k] != t["textos"].get(k) for k in ("banner", "titulo", "descripcion")) \
            else t["textos"].get("origen", "")
        self.db.actualizar(jid, textos=nuevo)
        if nuevo["banner"] != t["textos"].get("banner") and t["estado"] in ("renderizado", "error"):
            self.db.actualizar(jid, estado="pendiente", error="", error_tipo="")
        return self.db.trabajo(jid)

    def regenerar_textos(self, jid: str) -> None:
        self._editable(jid)
        (self.rutas.trabajo(jid) / "textos_generados.json").unlink(missing_ok=True)
        t = self.db.trabajo(jid)
        self.db.actualizar(jid, textos={}, estado="pendiente", error="", error_tipo="",
                           avisos=[x for x in t["avisos"] if not x.startswith("Textos generados")])

    def editar_subtitulos(self, jid: str, bloques: list) -> None:
        self._editable(jid)
        limpios = []
        for b in bloques:
            try:
                ini, fin, txt = float(b["inicio"]), float(b["fin"]), str(b.get("texto", "")).strip()[:120]
            except (KeyError, TypeError, ValueError):
                raise ErrorEtapa("Subtítulos con formato incorrecto.", "entrada")
            if txt and fin > ini >= 0:
                bloque = {"inicio": round(ini, 3), "fin": round(fin, 3), "texto": txt}
                palabras = b.get("palabras")
                if isinstance(palabras, list) and " ".join(str(p.get("texto", "")) for p in palabras) == txt:
                    bloque["palabras"] = palabras     # texto intacto: se mantiene el resaltado por palabra
                limpios.append(bloque)
        _escribir(self.rutas.trabajo(jid) / "subtitulos.json", {"editado": True, "bloques": limpios})
        self.db.actualizar(jid, estado="pendiente", error="", error_tipo="")

    def restaurar_subtitulos(self, jid: str) -> None:
        self._editable(jid)
        (self.rutas.trabajo(jid) / "subtitulos.json").unlink(missing_ok=True)
        self.db.actualizar(jid, estado="pendiente", error="", error_tipo="")

    def cambiar_estilo(self, jid: str, estilo: str) -> dict:
        if estilo not in ("clasico", "completo", "dividido", "auto", ""):
            raise ErrorEtapa("Estilo desconocido.", "entrada")
        t = self._editable(jid)
        datos = t["datos"]
        datos["estilo"] = estilo            # "" = usar el estilo general de Ajustes
        self.db.actualizar(jid, datos=datos, estado="pendiente", error="", error_tipo="")
        return self.db.trabajo(jid)

    def editar_tiempos(self, jid: str, tramos) -> dict:
        """Guarda qué tramos del original conservar. Lista vacía o el clip completo = quitar la edición."""
        self._editable(jid)
        self._aplicar_tramos(jid, tramos)
        self.db.actualizar(jid, estado="pendiente", error="", error_tipo="")
        return self.db.trabajo(jid)

    def _aplicar_tramos(self, jid: str, tramos) -> list:
        carpeta = self.rutas.trabajo(jid)
        original = self._entrada(carpeta)
        if not original or not (carpeta / "transcripcion.json").exists():
            raise ErrorEtapa("Espera a que el clip termine de procesarse antes de editarlo.", "entrada")
        prop_original = media.sondear(original)
        tramos = edicion.validar_tramos(tramos, prop_original["duracion"])
        subs_editados = (carpeta / "subtitulos.json").exists() and _leer(carpeta / "subtitulos.json").get("editado")
        f_tr, f_tr_orig = carpeta / "transcripcion.json", carpeta / "transcripcion_original.json"
        if not f_tr_orig.exists():
            os.replace(f_tr, f_tr_orig)                       # primera edición: guardar la transcripción original
        # Lo que dependía del video anterior se recalcula (la transcripción no: se remapea).
        for nombre in ("propiedades.json", "bordes.json", "encuadre.json", "subtitulos.json", "editado.mp4"):
            (carpeta / nombre).unlink(missing_ok=True)
        if not tramos or edicion.es_completo(tramos, prop_original["duracion"]):
            (carpeta / "edicion.json").unlink(missing_ok=True)
            os.replace(f_tr_orig, f_tr)
            tramos = []
        else:
            _escribir(carpeta / "edicion.json", {"tramos": tramos, "huella": edicion.huella(tramos),
                                                 "tiene_audio": prop_original["tiene_audio"],
                                                 "duracion_original": prop_original["duracion"]})
            _escribir(f_tr, edicion.remapear_transcripcion(_leer(f_tr_orig), tramos))
        if subs_editados:
            self.db.anadir_aviso(jid, "Al cambiar los tiempos se regeneraron los subtítulos a partir de la transcripción.")
        return tramos

    def _recorte_automatico(self, jid: str, t: dict, prop: dict, tr: dict, a: dict) -> bool:
        """Si el clip supera recorte_auto_segundos, conserva el mejor tramo (Gemini o heurística) con el
        editor de tiempos (no destructivo: se puede deshacer). Devuelve True si recortó."""
        limite = int(a["recorte_auto_segundos"])
        carpeta = self.rutas.trabajo(jid)
        if (not limite or prop["duracion"] <= limite + 0.5 or t["modo"] != "clip" or t["origen_tipo"] == "momento"
                or (carpeta / "edicion.json").exists() or t["datos"].get("recorte_auto")):
            return False
        self._etapa(jid, "transcribir", f"El clip dura {prop['duracion']:.0f} s: buscando el mejor tramo…")
        res = momentos.proponer(tr.get("segmentos", []), a["proveedor_textos"],
                                textos.leer_clave_gemini(self.rutas.secretos), 1, a["gemini_modelo"])
        if res["propuestas"]:
            p = res["propuestas"][0]
            ini, fin = p["inicio"], min(p["fin"], p["inicio"] + limite)
            motivo = p.get("motivo", "")
        else:
            ini, fin, motivo = 0.0, float(limite), "sin voz detectada: se conservan los primeros segundos"
        datos = t["datos"]
        datos["recorte_auto"] = {"inicio": ini, "fin": fin, "origen": res["origen"]}
        self.db.actualizar(jid, datos=datos)
        self._aplicar_tramos(jid, [[ini, fin]])
        self.db.anadir_aviso(jid, f"El clip duraba {prop['duracion']:.0f} s (más de {limite} s): se conservó el tramo "
                                  f"{_reloj(ini)}–{_reloj(fin)} ({res['origen']}{': ' + motivo if motivo else ''}). "
                                  "Puedes cambiarlo en «Editar tiempos».")
        return True

    def linea_de_tiempo(self, jid: str) -> dict:
        """Datos para el editor: duración del original, tramos actuales, forma de onda y palabras con tiempos."""
        carpeta = self.rutas.trabajo(jid)
        original = self._entrada(carpeta) if carpeta.exists() else None
        if not original:
            raise ErrorEtapa("Este clip no tiene archivo original.", "entrada")
        f_picos = carpeta / "picos.json"
        if not f_picos.exists():
            _escribir(f_picos, {"picos": edicion.picos_audio(original)})
        tr_f = carpeta / ("transcripcion_original.json" if (carpeta / "transcripcion_original.json").exists()
                          else "transcripcion.json")
        tr = _leer(tr_f) if tr_f.exists() else {"palabras": []}
        ed = _leer(carpeta / "edicion.json") if (carpeta / "edicion.json").exists() else None
        duracion = ed["duracion_original"] if ed else media.sondear(original)["duracion"]
        return {"duracion": duracion, "tramos": ed["tramos"] if ed else [[0.0, duracion]], "editado": bool(ed),
                "picos": _leer(f_picos)["picos"],
                "palabras": [{k: p[k] for k in ("inicio", "fin", "texto")} for p in tr.get("palabras", [])]}

    def _se_puede_retranscribir(self, t: dict) -> None:
        if (self.rutas.trabajo(t["id"]) / "edicion.json").exists():
            raise ErrorEtapa("Quita primero la edición de tiempos («Volver al clip completo») y vuelve a transcribir.",
                             "entrada")
        if t["origen_tipo"] == "momento":
            raise ErrorEtapa("Este clip usa la transcripción de su video largo: vuelve a transcribir el video largo.",
                             "entrada")

    def retranscribir(self, jid: str) -> None:
        """Vuelve a transcribir (p. ej. tras cambiar el modelo o el vocabulario). Rehace subtítulos;
        conserva los textos editados a mano."""
        t = self._editable(jid)
        self._se_puede_retranscribir(t)
        carpeta = self.rutas.trabajo(jid)
        for nombre in ("transcripcion.json", "subtitulos.json", "picos.json"):
            (carpeta / nombre).unlink(missing_ok=True)
        self.db.actualizar(jid, estado="pendiente", error="", error_tipo="")

    def cambiar_perfil(self, jid: str, pid: str, retranscribir: bool = False) -> dict:
        """Asigna otro perfil a un clip: se vuelven a generar los textos y el render con sus valores, sin transcribir
        otra vez salvo que se pida (`retranscribir`, p. ej. porque el contexto de transcripción es otro).
        Devuelve el trabajo y si el contexto que recibiría Whisper cambia."""
        t = self._editable(jid)
        if not self.db.perfil(pid):
            raise ErrorEtapa("Ese perfil de creador no existe.", "entrada")
        if retranscribir:
            self._se_puede_retranscribir(t)          # se comprueba antes de tocar nada
        if t["datos"].get("perfil") == pid and not t["datos"].get("perfil_copia") and not retranscribir:
            return {"trabajo": t, "contexto_cambia": False}
        antes = self.ajustes_de(t)
        datos = {**t["datos"], "perfil": pid}
        datos.pop("perfil_copia", None)
        self.db.actualizar(jid, datos=datos)
        despues = self.ajustes_de(self.db.trabajo(jid))
        carpeta = self.rutas.trabajo(jid)
        borrar = ["textos_generados.json"]
        if retranscribir:
            borrar += ["transcripcion.json", "subtitulos.json", "picos.json"]
        elif antes["correcciones"] != despues["correcciones"]:
            f_sub = carpeta / "subtitulos.json"
            if f_sub.exists() and _leer(f_sub).get("editado"):
                self.db.anadir_aviso(jid, "Se conservaron tus subtítulos editados a mano. «Restaurar originales» "
                                          "aplica las correcciones de escritura del nuevo perfil.")
            else:
                borrar.append("subtitulos.json")
        for nombre in borrar:
            (carpeta / nombre).unlink(missing_ok=True)
        t = self.db.trabajo(jid)
        self.db.actualizar(jid, textos={}, estado="pendiente", error="", error_tipo="",
                           avisos=[x for x in t["avisos"] if not x.startswith("Textos generados")])
        cambia = contexto_transcripcion(antes) != contexto_transcripcion(despues)
        return {"trabajo": self.db.trabajo(jid), "contexto_cambia": cambia and not retranscribir}

    def exportar(self, jid: str, plataforma: str) -> dict:
        """Copia el Short a 4_exportados/<plataforma>/ con su texto y avisos de zona segura. No publica nada."""
        return exportar.exportar(self._trabajo(jid), self.rutas.trabajo(jid), self.rutas.exportados, plataforma)

    def renderizar_de_nuevo(self, jid: str) -> None:
        self._editable(jid)
        self.db.actualizar(jid, estado="pendiente", error="", error_tipo="")

    def eliminar(self, jid: str) -> None:
        t = self._trabajo(jid)
        if t["estado"] in ("procesando", "subiendo"):
            raise ErrorEtapa("No se puede eliminar un trabajo mientras se procesa.", "entrada")
        shutil.rmtree(self.rutas.trabajo(jid), ignore_errors=True)
        self.db.borrar_trabajo(jid)

    def _trabajo(self, jid: str) -> dict:
        t = self.db.trabajo(jid)
        if not t:
            raise ErrorEtapa("Ese trabajo no existe.", "entrada")
        return t

    def detalle(self, jid: str) -> dict:
        carpeta = self.rutas.trabajo(jid)
        d = {"transcripcion": "", "bloques": [], "subtitulos_editados": False, "propiedades": None,
             "momentos": None, "clips": [], "entrada": "", "editado": (carpeta / "edicion.json").exists()}
        entrada = self._entrada(carpeta) if carpeta.exists() else None
        if entrada and entrada.suffix.lower() in (".mp4", ".m4v", ".webm", ".mov"):
            d["entrada"] = entrada.name
        if (carpeta / "momentos.json").exists():
            d["momentos"] = _leer(carpeta / "momentos.json")
            d["clips"] = [{"id": t["id"], "nombre": t["nombre"], "estado": t["estado"], **{k: t["datos"].get(k) for k in ("inicio", "fin")}}
                          for t in self.db.trabajos() if t["origen_tipo"] == "momento" and t["datos"].get("padre") == jid]
        if (carpeta / "transcripcion.json").exists():
            d["transcripcion"] = _leer(carpeta / "transcripcion.json")["texto"]
        if (carpeta / "subtitulos.json").exists():
            s = _leer(carpeta / "subtitulos.json")
            d["bloques"], d["subtitulos_editados"] = s["bloques"], s.get("editado", False)
        if (carpeta / "propiedades.json").exists():
            d["propiedades"] = _leer(carpeta / "propiedades.json")
        return d

    # ------------------------------------------------------------ carpeta vigilada
    def revisar_carpeta(self, ahora: float | None = None) -> list[dict]:
        """Importa los archivos de 1_clips_crudos que ya terminaron de copiarse."""
        ahora = ahora or time.time()
        a = self.db.ajustes()
        nuevos, presentes = [], set()
        conocidos = {t["origen_ref"] for t in self.db.trabajos() if t["origen_tipo"] == "carpeta"}
        for ruta in sorted(self.rutas.crudos.iterdir()):
            if not ruta.is_file() or ruta.suffix.lower() not in media.EXTENSIONES or ruta.name.startswith("."):
                continue
            clave = str(ruta)
            presentes.add(clave)
            if clave in conocidos:
                self.carpeta_estado.pop(ruta.name, None)
                continue
            try:
                st = ruta.stat()
            except OSError:
                continue
            firma = (st.st_size, st.st_mtime_ns)
            previo = self._vistos.get(clave)
            if not previo or previo[:2] != firma:
                self._vistos[clave] = (*firma, ahora, False)
                self.carpeta_estado[ruta.name] = MENSAJE_COPIANDO
                continue
            if previo[3]:                      # ya se intentó con este mismo contenido y no sirvió
                continue
            if ahora - previo[2] < int(a["segundos_estable"]) or st.st_size == 0 or not importar.esta_libre(ruta):
                continue
            try:
                t = self.importar_archivo(ruta, ruta.name, "carpeta")
                nuevos.append(t)
                self.carpeta_estado.pop(ruta.name, None)
            except ErrorEtapa as e:
                self._vistos[clave] = (*firma, previo[2], True)
                self.carpeta_estado[ruta.name] = str(e)
        for clave in [c for c in self._vistos if c not in presentes]:
            self._vistos.pop(clave)
            self.carpeta_estado.pop(Path(clave).name, None)
        return nuevos

    # ------------------------------------------------------------ hilos
    def _recuperar_por_cuota(self) -> int:
        """Clips que quedaron en error por el límite de YouTube (versiones anteriores): vuelven a la cola de
        subida. Si el límite sigue activo, el primer intento vuelve a pausar las subidas."""
        n = 0
        for t in self.db.trabajos():
            if t["estado"] == "error" and t["error_tipo"] == "cuota" and t["etapa"] == "subir" and not t["youtube_id"] \
                    and (self.rutas.trabajo(t["id"]) / "short.mp4").exists():
                self.db.actualizar(t["id"], estado="renderizado", subir_solicitado=True, error="", error_tipo="")
                n += 1
        return n

    def iniciar(self) -> None:
        if self._recuperar_por_cuota():
            log.info("Clips con límite de YouTube devueltos a la cola de subida.")
        n = self.db.recuperar_interrumpidos()
        if n:
            log.info("Se retomaron %d trabajos interrumpidos.", n)
        for objetivo in (self._bucle_trabajos, self._bucle_carpeta):
            h = threading.Thread(target=objetivo, daemon=True)
            h.start()
            self._hilos.append(h)

    def detener(self) -> None:
        self._parar.set()

    def _bucle_trabajos(self) -> None:
        while not self._parar.is_set():
            try:
                t = self.db.siguiente()
            except Exception:
                log.exception("Error leyendo la cola")
                t = None
            if t:
                with sin_suspender():
                    self._ejecutar(t)
            else:
                self._parar.wait(1.0)

    def _bucle_carpeta(self) -> None:
        while not self._parar.is_set():
            try:
                if self.db.ajustes()["vigilar_carpeta"]:
                    self.revisar_carpeta()
            except Exception:
                log.exception("Error revisando la carpeta de clips crudos")
            self._parar.wait(2.0)
