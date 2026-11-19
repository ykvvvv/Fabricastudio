"""«Clip de ejemplo» de la Plantilla: muestras en video de cada estilo de encuadre.

Seis segundos de un clip real a 540×960 y calidad baja, guardados en datos/muestras/<huella>.mp4. La huella
resume todo lo que se ve (video de entrada, tramo, capa, subtítulos, encuadre y filtros de FFmpeg), así que un
ajuste que no cambia un estilo no rehace su muestra. Todo se escribe en esa carpeta: el short.mp4 del clip, sus
archivos de etapa y su estado no cambian.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

from . import media, reencuadre, render, subtitulos
from .db import perfil_como_ajustes
from .errores import ErrorEtapa

log = logging.getLogger(__name__)

DURACION = render.MUESTRA_CUADROS / render.MUESTRA_FPS
GUARDADAS = 40         # archivos en la carpeta de muestras (videos y análisis); los menos usados se borran
VERSION = 1            # súbelo si cambia la forma de hacer las muestras: las guardadas dejan de valer
NO_DIVIDIDO = "este clip no tiene la cámara del streamer ni dos sujetos separados: saldría en pantalla completa"


def _leer(f: Path) -> dict:
    return json.loads(f.read_text(encoding="utf-8"))


class Muestras:
    def __init__(self, fab):
        self.fab = fab
        self.carpeta = fab.rutas.muestras
        self._cv = threading.Condition()
        # shortcut: un solo pedido para todo el programa (manda el último): si el PC y la tablet comparan a la vez,
        # los dos ven el mismo. Separar por sesión si llega a molestar.
        self._pedido: dict | None = None       # el último: {n, clip, ajustes}
        self._atendido = 0
        self.estado: dict = {"n": 0, "fase": "sin_pedido", "muestras": {}}

    # ------------------------------------------------------------ para el servidor
    def entrada(self, carpeta: Path) -> Path | None:
        """El video con el que se renderiza el clip: el editado si tiene una edición de tiempos aplicada."""
        f_ed = carpeta / "edicion.json"
        if f_ed.exists():
            ed, editado = _leer(f_ed), carpeta / "editado.mp4"
            return editado if ed.get("aplicado") == ed.get("huella") and editado.exists() else None
        return self.fab._entrada(carpeta)

    def candidatos(self) -> list[dict]:
        """Clips que sirven de ejemplo (con su video, transcritos, con textos y quietos), el último renderizado primero."""
        r = []
        for t in self.fab.db.trabajos():
            c = self.fab.rutas.trabajo(t["id"])
            if t["modo"] != "largo" and t["estado"] not in ("pendiente", "procesando") and t["textos"] \
                    and (c / "propiedades.json").exists() and (c / "transcripcion.json").exists() and self.entrada(c):
                r.append(t)
        return sorted(r, key=lambda t: (t["estado"] in ("renderizado", "subiendo", "publicado"), t["actualizado"]),
                      reverse=True)

    def pedir(self, clip: str | None, ajustes: dict) -> dict:
        """Pide las muestras de `clip` (o del último renderizado) con estos ajustes de diseño, sin guardarlos.
        Las hace el hilo de muestras; el panel sigue el avance con ver()."""
        candidatos = self.candidatos()
        t = next((c for c in candidatos if c["id"] == clip), None) if clip else (candidatos or [None])[0]
        if not t:
            raise ErrorEtapa("Ese clip no sirve de ejemplo: tiene que estar transcrito, con textos y con su video."
                             if clip else "Aún no hay clips para usar de ejemplo: importa uno y espera a que se procese.",
                             "entrada")
        with self._cv:
            mismo = self.estado.get("clip", {}).get("id") == t["id"]
            n = self.estado["n"] + 1
            self._pedido = {"n": n, "clip": t["id"], "ajustes": ajustes}
            # Del mismo clip se conservan las muestras ya hechas: el panel las sigue mostrando mientras se comprueba.
            self.estado = {**(self.estado if mismo else {"muestras": {}}), "n": n, "fase": "preparando", "error": "",
                           "texto": "Comprobando qué muestras cambian…",
                           "clip": {"id": t["id"], "nombre": t["nombre"], "titulo": t["textos"].get("titulo", "")}}
            self._cv.notify_all()
        return self.ver()

    def ver(self) -> dict:
        with self._cv:
            return json.loads(json.dumps(self.estado))

    # ------------------------------------------------------------ hilo de muestras
    def iniciar(self) -> None:
        threading.Thread(target=self._bucle, daemon=True, name="muestras").start()

    def _bucle(self) -> None:
        while not self.fab._parar.is_set():
            with self._cv:
                if not self._pedido or self._pedido["n"] == self._atendido:
                    self._cv.wait(1.0)
                    continue
                p = self._pedido
            self.atender(p)

    def atender(self, p: dict) -> None:
        """Hace las muestras de un pedido. Si llega otro más nuevo, deja este a medias y se atiende el nuevo."""
        try:
            self._hacer(p)
        except ErrorEtapa as e:
            self._fijar(p, fase="error", error=str(e), texto="")
        except Exception as e:
            log.exception("Error haciendo las muestras de la Plantilla")
            self._fijar(p, fase="error", error=f"Error inesperado: {e}", texto="")
        finally:
            self._atendido = p["n"]

    def _superado(self, p: dict) -> bool:
        with self._cv:
            return self._pedido["n"] != p["n"]

    def _fijar(self, p: dict, **campos) -> None:
        with self._cv:
            if self.estado["n"] == p["n"]:
                self.estado.update(campos)

    def _marcar(self, p: dict, estilo: str, **campos) -> None:
        with self._cv:
            if self.estado["n"] == p["n"]:
                self.estado["muestras"][estilo] = {**self.estado["muestras"].get(estilo, {}), **campos}

    def _analisis(self, p: dict, propio: Path, guardado: Path, texto: str, calcular, sirve=lambda r: True) -> dict:
        """Un análisis del clip: el de su carpeta si lo tiene y sirve; si no, el de la carpeta de muestras
        (se calcula una vez y se guarda ahí, nunca en la carpeta del clip)."""
        for f in (propio, guardado):
            if f.exists() and sirve(r := _leer(f)):
                if f == guardado:
                    os.utime(f)                    # usado ahora: no es de los que se borran primero
                return r
        self._fijar(p, fase="analizando", texto=texto)
        r = calcular()
        guardado.write_text(json.dumps(r), encoding="utf-8")
        return r

    def _hacer(self, p: dict) -> None:
        t = self.fab._trabajo(p["clip"])
        carpeta = self.fab.rutas.trabajo(t["id"])
        entrada = self.entrada(carpeta)
        if not entrada:
            raise ErrorEtapa("Este clip ya no tiene su video: elige otro de ejemplo.", "entrada")
        prop, tr = _leer(carpeta / "propiedades.json"), _leer(carpeta / "transcripcion.json")
        perfil = self.fab.perfil_de(t)
        a = {**self.fab.db.ajustes(), **p["ajustes"], **perfil_como_ajustes(perfil)}   # como lo renderizaría hoy
        f_sub = carpeta / "subtitulos.json"
        sub = _leer(f_sub) if f_sub.exists() else {}
        bloques = sub["bloques"] if sub.get("editado") else subtitulos.agrupar(
            subtitulos.corregir_palabras(tr["palabras"], subtitulos.leer_correcciones(a["correcciones"])),
            int(a["sub_palabras_max"]), int(a["sub_caracteres_max"]))
        # Si se habla en los primeros 3 s, desde el principio (como empieza el Short, con su gancho); si no, justo
        # antes de la primera frase, para que se vean subtítulos.
        primera = bloques[0]["inicio"] if bloques else 0.0
        inicio = round(max(0.0, min(0.0 if primera <= 3 else primera - 0.3, prop["duracion"] - DURACION)), 2)
        st = entrada.stat()
        clave = hashlib.sha256(json.dumps([t["id"], entrada.name, st.st_size, st.st_mtime_ns]).encode()).hexdigest()[:16]
        recorte = None
        if a["recortar_bordes"]:
            recorte = self._analisis(p, carpeta / "bordes.json", self.carpeta / f"bordes-{clave}.json",
                                     "Buscando bordes negros en el clip…",
                                     lambda: {"recorte": media.detectar_bordes(entrada, prop)})["recorte"]
        medidas = (recorte["w"], recorte["h"]) if recorte else (prop["ancho"], prop["alto"])
        clave_rostros = hashlib.sha256(json.dumps([clave, recorte]).encode()).hexdigest()[:16]
        analisis = self._analisis(p, carpeta / "encuadre.json", self.carpeta / f"encuadre-{clave_rostros}.json",
                                  "Buscando rostros en el clip (solo la primera vez)…",
                                  lambda: reencuadre.analizar(entrada, prop, recorte),
                                  sirve=lambda r: (r["ancho"], r["alto"]) == medidas)

        # Lo mismo que decide el render de verdad (pipeline.procesar) para «dividido» y «auto».
        arriba = int(round(1920 * int(a["dividido_proporcion"]) / 100)) // 2 * 2
        decision = reencuadre.decidir(analisis, arriba, 1920 - arriba)
        planes = {"clasico": None, "completo": analisis}
        if decision["tipo"] in ("camara", "dos"):
            planes["dividido"] = {**analisis, "dividido": decision["plan"]}
        auto = {"camara": "dividido", "dos": "dividido", "seguir": "completo"}.get(decision["tipo"], "clasico")
        dividido = "dividido" if "dividido" in planes else "completo"

        recursos, banner = self.fab.carpeta_logo(perfil), t["textos"].get("banner", "")
        huellas = {}
        for estilo, encuadre in planes.items():
            pr = render.preparar(prop, banner, bloques, a, recursos, recorte, encuadre, muestra=True)
            h = hashlib.sha256(json.dumps([VERSION, clave, inicio, pr["ass"], pr["encuadre"], pr["filtros"]]).encode())
            h.update(pr["capa"].tobytes())
            if pr["gancho"]:
                h.update(pr["gancho"]["imagen"].tobytes())
            huellas[estilo] = h.hexdigest()[:32]
        muestras = {}
        for estilo, h in huellas.items():
            hecha = (self.carpeta / f"{h}.mp4").exists()
            muestras[estilo] = {"huella": h, "estado": "lista" if hecha else "en_espera",
                                "url": f"/api/diseno/muestras/{h}.mp4" if hecha else ""}
        self._fijar(p, fase="generando", texto="", inicio=inicio, muestras=muestras, aviso=analisis.get("aviso", ""),
                    auto={"estilo": auto, "motivo": decision["motivo"]},
                    dividido={"estilo": dividido, "motivo": "" if dividido == "dividido" else NO_DIVIDIDO})

        # Primero la del estilo elegido en la Plantilla; después, las demás.
        elegido = str(p["ajustes"].get("estilo") or a["estilo"])
        elegido = {"auto": auto, "dividido": dividido}.get(elegido, elegido)
        for estilo in sorted(planes, key=lambda e: e != elegido):
            if self._superado(p):
                return
            destino = self.carpeta / f"{huellas[estilo]}.mp4"
            if destino.exists():
                os.utime(destino)
                continue
            self._marcar(p, estilo, estado="generando")
            tmp = Path(tempfile.mkdtemp(prefix="tmp-", dir=self.carpeta))
            try:
                render.renderizar(tmp, str(entrada.resolve()), prop, banner, bloques, a, recursos, salida="muestra.mp4",
                                  recorte=recorte, encuadre=planes[estilo], muestra=inicio)
                os.replace(tmp / "muestra.mp4", destino)
                self._marcar(p, estilo, estado="lista", url=f"/api/diseno/muestras/{destino.name}")
            except ErrorEtapa as e:
                self._marcar(p, estilo, estado="error", error=str(e))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        self._fijar(p, fase="lista")
        self._limpiar()

    def _limpiar(self) -> None:
        """Deja los GUARDADAS archivos usados más recientemente y borra carpetas temporales abandonadas."""
        archivos = sorted((f for f in self.carpeta.iterdir() if f.is_file()), key=lambda f: f.stat().st_mtime,
                          reverse=True)
        for f in archivos[GUARDADAS:]:
            try:
                f.unlink()
            except OSError:                       # en Windows, abierto por el panel: se borrará la próxima vez
                pass
        for d in self.carpeta.glob("tmp-*"):
            if d.is_dir() and time.time() - d.stat().st_mtime > 3600:
                shutil.rmtree(d, ignore_errors=True)
