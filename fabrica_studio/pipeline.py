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
import threading
import time
import traceback
from pathlib import Path

from . import importar, media, render, subtitulos, textos, transcribe
from .config import AJUSTES_DE_DISENO, Rutas
from .db import DB
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

    # ------------------------------------------------------------ importación
    def importar_archivo(self, origen: Path, nombre: str, origen_tipo: str = "archivo",
                         publicar: bool = True, mover: bool = False) -> dict:
        """Crea un trabajo a partir de un archivo local. Rechaza duplicados exactos."""
        if Path(nombre).suffix.lower() not in media.EXTENSIONES:
            raise ErrorEtapa(f"Formato no admitido: {Path(nombre).suffix or 'sin extensión'}. "
                             f"Usa {', '.join(sorted(media.EXTENSIONES))}.", "entrada")
        media.sondear(origen)                      # falla aquí si no es un video legible
        sha = media.sha256(origen)
        previo = self.db.por_sha(sha)
        if previo:
            raise ErrorEtapa(f"Este mismo archivo ya se importó como «{previo['nombre']}» "
                             f"(estado: {previo['estado']}). No se creó un trabajo duplicado.", "duplicado")
        t = self.db.crear_trabajo(_nombre_seguro(nombre), origen_tipo,
                                  origen_ref=str(origen) if origen_tipo == "carpeta" else nombre, publicar=publicar)
        carpeta = self.rutas.trabajo(t["id"])
        carpeta.mkdir(parents=True)
        destino = carpeta / f"entrada{Path(nombre).suffix.lower()}"
        if mover:
            shutil.move(str(origen), destino)
        else:
            shutil.copyfile(origen, destino)
        self.db.actualizar(t["id"], sha256=sha)
        self.db.marcar_etapa(t["id"], "importar", "hecho")
        return self.db.trabajo(t["id"])

    def importar_enlace(self, url: str, publicar: bool = True) -> dict:
        url = importar.validar_enlace(url)
        for t in self.db.trabajos():
            if t["origen_tipo"] == "enlace" and t["origen_ref"] == url:
                raise ErrorEtapa(f"Ese enlace ya está en la cola como «{t['nombre']}».", "duplicado")
        nombre = _nombre_seguro(url.rstrip("/").rsplit("/", 1)[-1] or "clip-kick")
        t = self.db.crear_trabajo(nombre, "enlace", origen_ref=url, publicar=publicar)
        self.rutas.trabajo(t["id"]).mkdir(parents=True)
        return t

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
        a = self.db.ajustes()
        self.db.actualizar(jid, estado="procesando", error="", error_tipo="", subir_solicitado=False)

        # 1. Importar (solo los enlaces descargan aquí).
        entrada = self._entrada(carpeta)
        if not entrada:
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

        # 2. Comprobar.
        f_prop = carpeta / "propiedades.json"
        if not f_prop.exists():
            self._etapa(jid, "comprobar")
            _escribir(f_prop, media.sondear(entrada))
        prop = _leer(f_prop)
        if prop["duracion"] > 180:
            self.db.anadir_aviso(jid, f"Dura {prop['duracion']:.0f} s: YouTube solo trata como Short hasta 3 minutos.")
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
                                            self.rutas.modelos)
                wav.unlink(missing_ok=True)
            else:
                tr = {"idioma": a["idioma"], "motor": "sin audio", "texto": "", "segmentos": [], "palabras": []}
            _escribir(f_trans, tr)
        tr = _leer(f_trans)
        if prop["tiene_audio"] and not tr["palabras"]:
            self.db.anadir_aviso(jid, "No se detectó voz en el audio: el Short no tendrá subtítulos.")
        self.db.marcar_etapa(jid, "transcribir", "hecho", f"{len(tr['palabras'])} palabras · {tr['motor']}")

        # 4. Textos.
        f_ia = carpeta / "textos_generados.json"
        if not f_ia.exists():
            self._etapa(jid, "textos", "Generando banner, título y descripción…")
            gen = textos.generar(tr["texto"], a["creador"], a["proveedor_textos"],
                                 textos.leer_clave_gemini(self.rutas.secretos), a["gemini_modelo"])
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
            _escribir(f_sub, {"editado": False, "bloques": subtitulos.agrupar(
                tr["palabras"], int(a["sub_palabras_max"]), int(a["sub_caracteres_max"]))})
        sub = _leer(f_sub)
        self.db.marcar_etapa(jid, "subtitulos", "hecho", f"{len(sub['bloques'])} bloques")

        # 6. Render (solo si cambió algo que afecte a la imagen).
        logo = self.rutas.recursos / "logo.png"
        huella = hashlib.sha256(json.dumps([
            t["textos"]["banner"], sub["bloques"], {k: a[k] for k in AJUSTES_DE_DISENO},
            logo.stat().st_mtime_ns if logo.exists() else 0], sort_keys=True).encode()).hexdigest()
        datos = t["datos"]
        if datos.get("huella_render") != huella or not (carpeta / "short.mp4").exists():
            self._etapa(jid, "render", "Renderizando el video vertical…")
            res = render.renderizar(carpeta, entrada.name, prop, t["textos"]["banner"], sub["bloques"], a,
                                    self.rutas.recursos)
            for aviso in res["disposicion"]["avisos"]:
                self.db.anadir_aviso(jid, aviso)
            datos.update(huella_render=huella, salida=res["propiedades"], disposicion=res["disposicion"])
            copia = self.rutas.renderizados / f"{t['nombre']}__{jid[-6:]}.mp4"
            shutil.copyfile(carpeta / "short.mp4", copia)
            datos["copia"] = copia.name
            self.db.actualizar(jid, datos=datos, subida={})   # un render nuevo invalida subidas a medias
        s = datos["salida"]
        self.db.marcar_etapa(jid, "render", "hecho", f"{s['ancho']}×{s['alto']}, {s['duracion']:.1f} s")
        self.progreso.pop(jid, None)
        self.db.actualizar(jid, estado="renderizado", etapa="render",
                           subir_solicitado=bool(t["publicar"] and a["subida_automatica"]))

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
                shutil.move(str(origen), destino)

    def _ejecutar(self, t: dict) -> None:
        jid = t["id"]
        subiendo = t["estado"] == "renderizado"
        try:
            self.subir(jid) if subiendo else self.procesar(jid)
        except ErrorEtapa as e:
            self._fallo(jid, str(e), e.tipo)
        except Exception as e:   # un fallo inesperado no debe tumbar al trabajador ni a los demás clips
            log.error("Fallo inesperado en %s:\n%s", jid, sin_secretos(traceback.format_exc()))
            self._fallo(jid, f"Error interno ({type(e).__name__}): {e}", "interno")

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
                limpios.append({"inicio": round(ini, 3), "fin": round(fin, 3), "texto": txt})
        _escribir(self.rutas.trabajo(jid) / "subtitulos.json", {"editado": True, "bloques": limpios})
        self.db.actualizar(jid, estado="pendiente", error="", error_tipo="")

    def restaurar_subtitulos(self, jid: str) -> None:
        self._editable(jid)
        (self.rutas.trabajo(jid) / "subtitulos.json").unlink(missing_ok=True)
        self.db.actualizar(jid, estado="pendiente", error="", error_tipo="")

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
        d = {"transcripcion": "", "bloques": [], "subtitulos_editados": False, "propiedades": None}
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
                self.carpeta_estado[ruta.name] = "Esperando a que termine de copiarse…"
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
    def iniciar(self) -> None:
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
