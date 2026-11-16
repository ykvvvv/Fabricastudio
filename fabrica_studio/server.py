"""Servidor del panel (FastAPI). Sirve la interfaz, la API y los videos."""
from __future__ import annotations

import io
import logging
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, acceso, render, textos
from .config import AJUSTES_POR_DEFECTO, FUENTES, LIENZO_ALTO, LIENZO_ANCHO, PUERTO, WEB, Rutas
from .errores import ErrorEtapa, sin_secretos
from .pipeline import Fabrica

log = logging.getLogger("fabrica.server")
_CODIGOS = {"duplicado": 409, "configuracion": 409, "autenticacion": 502, "cuota": 502, "temporal": 502,
            "modelo": 502, "herramienta": 500, "interno": 500}


def crear_app(fabrica: Fabrica | None = None, iniciar_hilos: bool = True) -> FastAPI:
    fab = fabrica or Fabrica(Rutas())
    vinc = acceso.Vinculacion()

    @asynccontextmanager
    async def ciclo(app: FastAPI):
        if iniciar_hilos:
            fab.iniciar()
        yield
        fab.detener()

    app = FastAPI(title="Fábrica Studio", version=__version__, lifespan=ciclo, docs_url=None, redoc_url=None)
    app.state.fabrica = fab
    app.state.vinculacion = vinc

    # ------------------------------------------------------------ acceso
    def _local(request: Request) -> bool:
        return acceso.es_local(request.client.host if request.client else None)

    def _autorizado(request: Request) -> bool:
        if _local(request):
            return True
        token = request.cookies.get(acceso.COOKIE, "")
        return bool(token) and fab.db.dispositivo_por_token(acceso.hash_token(token)) is not None

    def _solo_pc(request: Request) -> None:
        if not _local(request):
            raise ErrorEtapa("Por seguridad, esta acción solo se puede hacer desde el panel abierto en el PC.", "prohibido")

    @app.middleware("http")
    async def guardia(request: Request, call_next):
        ruta = request.url.path
        if not acceso.host_permitido(request.headers.get("host", "")):
            return JSONResponse({"error": "Dirección no permitida."}, status_code=403)
        origen = request.headers.get("origin")
        if origen and request.method not in ("GET", "HEAD") and urlparse(origen).netloc != request.headers.get("host"):
            return JSONResponse({"error": "Origen no permitido."}, status_code=403)
        publico = not (ruta.startswith("/api/") or ruta.startswith("/media/")) \
            or ruta in ("/api/sesion", "/api/vincular", "/api/youtube/callback")
        if not publico and not _autorizado(request):
            return JSONResponse({"error": "Dispositivo no vinculado."}, status_code=401)
        respuesta = await call_next(request)
        if ruta.startswith("/api/"):
            respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    @app.exception_handler(ErrorEtapa)
    async def error_etapa(request: Request, e: ErrorEtapa):
        codigo = 403 if e.tipo == "prohibido" else _CODIGOS.get(e.tipo, 400)
        return JSONResponse({"error": sin_secretos(str(e)), "tipo": e.tipo}, status_code=codigo)

    @app.get("/api/sesion")
    def sesion(request: Request):
        return {"autorizado": _autorizado(request), "local": _local(request), "version": __version__}

    @app.post("/api/vincular")
    async def vincular(request: Request):
        cuerpo = await request.json()
        token = vinc.canjear(str(cuerpo.get("codigo", "")))
        if not token:
            time.sleep(0.5)
            return JSONResponse({"error": "Código incorrecto o caducado. Genera uno nuevo en el PC."}, status_code=403)
        fab.db.crear_dispositivo(str(cuerpo.get("nombre", "")).strip() or "Tablet", acceso.hash_token(token))
        r = JSONResponse({"ok": True})
        r.set_cookie(acceso.COOKIE, token, max_age=365 * 86400, httponly=True, samesite="strict")
        return r

    @app.post("/api/vincular/codigo")
    def codigo_vinculacion(request: Request):
        _solo_pc(request)
        ip = acceso.ip_red_local()
        return {**vinc.nuevo_codigo(), "direccion": f"http://{ip}:{PUERTO}" if ip else ""}

    @app.get("/api/dispositivos")
    def dispositivos():
        return fab.db.dispositivos()

    @app.delete("/api/dispositivos/{did}")
    def borrar_dispositivo(did: str, request: Request):
        _solo_pc(request)
        fab.db.borrar_dispositivo(did)
        return {"ok": True}

    # ------------------------------------------------------------ estado general
    def _publico(t: dict) -> dict:
        """Versión del trabajo para el panel: sin sesiones de subida ni rutas internas."""
        s = t["subida"]
        return {**{k: t[k] for k in ("id", "creado", "actualizado", "nombre", "origen_tipo", "estado", "etapa",
                                     "etapas", "error", "error_tipo", "avisos", "publicar", "subir_solicitado",
                                     "textos", "youtube_id", "modo")},
                "origen_ref": t["origen_ref"] if t["origen_tipo"] == "enlace" else Path(t["origen_ref"]).name,
                "salida": t["datos"].get("salida"), "copia": t["datos"].get("copia", ""),
                "tiene_video": (fab.rutas.trabajo(t["id"]) / "short.mp4").exists(),
                "subida": {k: s[k] for k in ("canal_id", "terminado", "privacidad") if k in s},
                "progreso": fab.progreso.get(t["id"], "")}

    def _proveedores() -> dict:
        a = fab.db.ajustes()
        clave = textos.leer_clave_gemini(fab.rutas.secretos)
        return {
            "ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe")),
            "whisper": {"modelo": a["whisper_modelo"], "dispositivo": a["whisper_dispositivo"],
                        "descargado": any(fab.rutas.modelos.glob(f"*whisper-{a['whisper_modelo']}*"))},
            "gemini": {"clave": bool(clave), "modelo": a["gemini_modelo"]},
            "textos": a["proveedor_textos"],
        }

    @app.get("/api/estado")
    def estado():
        a = fab.db.ajustes()
        return {"trabajos": [_publico(t) for t in fab.db.trabajos()],
                "carpeta": {"activa": a["vigilar_carpeta"], "ruta": str(fab.rutas.crudos),
                            "pendientes": [{"archivo": k, "motivo": v} for k, v in fab.carpeta_estado.items()]},
                "youtube": {**fab.youtube.estado(), "canal_id": a["youtube_canal_id"],
                            "canal_nombre": a["youtube_canal_nombre"]},
                "proveedores": _proveedores(), "subida_automatica": a["subida_automatica"]}

    # ------------------------------------------------------------ importación
    @app.post("/api/importar/archivo")
    def importar_archivo(archivo: UploadFile = File(...), publicar: bool = Form(True), modo: str = Form("clip")):
        nombre = Path(archivo.filename or "clip.mp4").name
        with tempfile.NamedTemporaryFile(delete=False, dir=fab.rutas.trabajos, suffix=".subiendo") as tmp:
            shutil.copyfileobj(archivo.file, tmp, 1 << 20)
            ruta_tmp = Path(tmp.name)
        try:
            return _publico(fab.importar_archivo(ruta_tmp, nombre, "archivo", publicar=publicar, mover=True, modo=modo))
        finally:
            ruta_tmp.unlink(missing_ok=True)

    @app.post("/api/importar/enlace")
    async def importar_enlace(request: Request):
        c = await request.json()
        return _publico(fab.importar_enlace(str(c.get("url", "")), publicar=bool(c.get("publicar", True)),
                                            modo=str(c.get("modo", "clip"))))

    # ------------------------------------------------------------ trabajos
    @app.get("/api/trabajos/{jid}")
    def trabajo(jid: str):
        return {**_publico(fab._trabajo(jid)), **fab.detalle(jid)}

    @app.post("/api/trabajos/{jid}/clips")
    async def crear_clip(jid: str, request: Request):
        c = await request.json()
        return _publico(fab.crear_clip(jid, c.get("inicio"), c.get("fin")))

    @app.post("/api/trabajos/{jid}/{accion}")
    def accion(jid: str, accion: str):
        acciones = {"reintentar": fab.reintentar, "subir": fab.solicitar_subida,
                    "renderizar": fab.renderizar_de_nuevo, "regenerar-textos": fab.regenerar_textos,
                    "restaurar-subtitulos": fab.restaurar_subtitulos, "proponer-momentos": fab.proponer_de_nuevo}
        if accion not in acciones:
            raise ErrorEtapa("Acción desconocida.", "entrada")
        acciones[accion](jid)
        return _publico(fab._trabajo(jid))

    @app.put("/api/trabajos/{jid}/textos")
    async def editar_textos(jid: str, request: Request):
        return _publico(fab.editar_textos(jid, await request.json()))

    @app.put("/api/trabajos/{jid}/subtitulos")
    async def editar_subtitulos(jid: str, request: Request):
        fab.editar_subtitulos(jid, (await request.json()).get("bloques", []))
        return _publico(fab._trabajo(jid))

    @app.delete("/api/trabajos/{jid}")
    def eliminar(jid: str):
        fab.eliminar(jid)
        return {"ok": True}

    @app.get("/media/{jid}/{archivo}")
    def medio(jid: str, archivo: str):
        permitidos = {"short.mp4": "video/mp4", "miniatura.jpg": "image/jpeg"}
        fab._trabajo(jid)
        if archivo == "entrada":                 # video original, para revisar momentos de un video largo
            nombre = fab.detalle(jid)["entrada"]
            if not nombre:
                return JSONResponse({"error": "No disponible."}, status_code=404)
            tipos = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}
            return FileResponse(fab.rutas.trabajo(jid) / nombre, media_type=tipos[Path(nombre).suffix.lower()])
        ruta = fab.rutas.trabajo(jid) / archivo
        if archivo not in permitidos or not ruta.exists():
            return JSONResponse({"error": "No disponible."}, status_code=404)
        return FileResponse(ruta, media_type=permitidos[archivo], headers={"Cache-Control": "no-cache"})

    # ------------------------------------------------------------ ajustes y diseño
    @app.get("/api/ajustes")
    def ajustes():
        return {"valores": fab.db.ajustes(), "defecto": AJUSTES_POR_DEFECTO,
                "logo_propio": (fab.rutas.recursos / "logo.png").exists()}

    @app.put("/api/ajustes")
    async def guardar_ajustes(request: Request):
        cambios = await request.json()
        # El canal de destino solo se cambia con la confirmación explícita de /api/youtube/canal.
        for k in ("youtube_canal_id", "youtube_canal_nombre"):
            cambios.pop(k, None)
        return {"valores": fab.db.guardar_ajustes(cambios)}

    @app.post("/api/logo")
    def subir_logo(archivo: UploadFile = File(...)):
        from PIL import Image
        try:
            img = Image.open(io.BytesIO(archivo.file.read(20 << 20)))
            img.load()
        except Exception:
            raise ErrorEtapa("El logo debe ser una imagen (PNG con fondo transparente, de preferencia).", "entrada")
        img.convert("RGBA").save(fab.rutas.recursos / "logo.png")
        return {"ok": True}

    @app.delete("/api/logo")
    def quitar_logo():
        (fab.rutas.recursos / "logo.png").unlink(missing_ok=True)
        return {"ok": True}

    @app.get("/api/diseno/vista")
    def vista_diseno(request: Request, banner: str = "ASÍ SE VERÁ TU BANNER"):
        """Maqueta rápida del diseño con los ajustes actuales (o los que lleguen por parámetro)."""
        from PIL import Image, ImageDraw
        a = fab.db.ajustes()
        for k, v in request.query_params.items():
            if k in AJUSTES_POR_DEFECTO and k != "youtube_canal_id":
                base = AJUSTES_POR_DEFECTO[k]
                try:
                    a[k] = (v == "true") if isinstance(base, bool) else int(float(v)) if isinstance(base, int) else v
                except ValueError:
                    pass
        try:
            b = render.componer_banner(textos.normalizar_banner(banner) or "BANNER", a)
            d = render.calcular_disposicion(1920, 1080, a, b)
            capa = render.dibujar_capa(d, b, a, fab.rutas.recursos)
        except Exception as e:
            raise ErrorEtapa(f"Ajustes de diseño no válidos: {e}", "entrada")
        lienzo = Image.new("RGBA", (LIENZO_ANCHO, LIENZO_ALTO), "black")
        dib = ImageDraw.Draw(lienzo)
        v, s = d["video"], d["subtitulos"]
        dib.rectangle((v["x"], v["y"], v["x"] + v["w"], v["y"] + v["h"]), fill="#2a2d33")
        dib.text((LIENZO_ANCHO // 2, v["y"] + v["h"] // 2), "VIDEO", font=render._fuente(render.FUENTE_BOLD, 60),
                 fill="#4a4e57", anchor="mm")
        lienzo.alpha_composite(capa)
        fuente = render._fuente(render.FUENTE_BOLD, s["tamano"])
        dib = ImageDraw.Draw(lienzo)
        dib.text((LIENZO_ANCHO // 2, s["y"]), "así se ven los subtítulos", font=fuente, fill="white", anchor="ma",
                 stroke_width=max(3, round(s["tamano"] * 0.09)), stroke_fill="black")
        salida = io.BytesIO()
        lienzo.convert("RGB").resize((540, 960)).save(salida, "JPEG", quality=85)
        return Response(salida.getvalue(), media_type="image/jpeg",
                        headers={"X-Avisos": str(len(d["avisos"])), "Cache-Control": "no-store"})

    # ------------------------------------------------------------ proveedores
    @app.put("/api/secretos/gemini")
    async def guardar_gemini(request: Request):
        _solo_pc(request)
        clave = str((await request.json()).get("clave", "")).strip()
        if not clave:
            raise ErrorEtapa("La clave está vacía.", "entrada")
        modelos = textos.listar_modelos_gemini(clave, forzar=True)   # valida la clave antes de guardarla
        f = fab.rutas.secretos / "gemini_api_key.txt"
        f.write_text(clave, encoding="utf-8")
        from .youtube import _solo_propietario
        _solo_propietario(f)
        return {"ok": True, "modelos": modelos}

    @app.delete("/api/secretos/gemini")
    def borrar_gemini(request: Request):
        _solo_pc(request)
        (fab.rutas.secretos / "gemini_api_key.txt").unlink(missing_ok=True)
        return {"ok": True}

    @app.get("/api/proveedores/gemini")
    def probar_gemini():
        clave = textos.leer_clave_gemini(fab.rutas.secretos)
        if not clave:
            return {"clave": False, "modelos": [], "elegido": ""}
        modelos = textos.listar_modelos_gemini(clave, forzar=True)
        return {"clave": True, "modelos": modelos,
                "elegido": textos.elegir_modelo(modelos, fab.db.ajustes()["gemini_modelo"])}

    @app.get("/api/diagnostico")
    def diagnostico(autoprueba: bool = False):
        from . import diagnostico as diag
        return diag.revisar(fab.rutas, fab.db.ajustes(), autoprueba=autoprueba)

    # ------------------------------------------------------------ YouTube
    def _redirect() -> str:
        return f"http://127.0.0.1:{PUERTO}/api/youtube/callback"

    @app.post("/api/youtube/credenciales")
    def yt_credenciales(request: Request, archivo: UploadFile = File(...)):
        _solo_pc(request)
        return {"ok": True, "tipo": fab.youtube.guardar_credenciales(archivo.file.read(1 << 20))}

    @app.get("/api/youtube/conectar")
    def yt_conectar(request: Request):
        _solo_pc(request)
        return RedirectResponse(fab.youtube.url_autorizacion(_redirect()))

    @app.get("/api/youtube/callback")
    def yt_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        _solo_pc(request)
        if error or not code:
            return HTMLResponse(f"<p>Autorización cancelada ({sin_secretos(error) or 'sin código'}). "
                                "<a href='/#ajustes'>Volver al panel</a></p>", status_code=400)
        try:
            fab.youtube.completar_autorizacion(code, state)
        except ErrorEtapa as e:
            return HTMLResponse(f"<p>{sin_secretos(str(e))} <a href='/#ajustes'>Volver al panel</a></p>", status_code=400)
        # Una cuenta nueva obliga a confirmar de nuevo el canal de destino.
        fab.db.guardar_ajustes({"youtube_canal_id": "", "youtube_canal_nombre": ""})
        return RedirectResponse("/#ajustes")

    @app.get("/api/youtube/canales")
    def yt_canales():
        return [{k: c[k] for k in ("id", "titulo", "identificador")} for c in fab.youtube.canales()]

    @app.post("/api/youtube/canal")
    async def yt_confirmar_canal(request: Request):
        _solo_pc(request)
        cid = str((await request.json()).get("id", ""))
        canal = next((c for c in fab.youtube.canales() if c["id"] == cid), None)
        if not canal:
            raise ErrorEtapa("Ese canal no pertenece a la cuenta conectada.", "configuracion")
        fab.db.guardar_ajustes({"youtube_canal_id": canal["id"], "youtube_canal_nombre": canal["titulo"]})
        return {"ok": True}

    @app.post("/api/youtube/desconectar")
    def yt_desconectar(request: Request):
        _solo_pc(request)
        fab.youtube.desconectar()
        fab.db.guardar_ajustes({"youtube_canal_id": "", "youtube_canal_nombre": ""})
        return {"ok": True}

    # ------------------------------------------------------------ interfaz
    app.mount("/fuentes", StaticFiles(directory=FUENTES), name="fuentes")
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    return app


def main() -> None:
    import sys

    import uvicorn
    if hasattr(sys.stdout, "reconfigure"):          # consolas de Windows sin UTF-8
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ip = acceso.ip_red_local()
    print(f"\n  Fábrica Studio {__version__}\n  En este PC:   http://127.0.0.1:{PUERTO}"
          + (f"\n  En la tablet: http://{ip}:{PUERTO}  (pide un código de vinculación en el PC)" if ip else "")
          + "\n  Para detener: Ctrl+C\n")
    uvicorn.run(crear_app(), host="0.0.0.0", port=PUERTO, log_level="warning")


if __name__ == "__main__":
    main()
