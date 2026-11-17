"""Servidor del panel (FastAPI). Sirve la interfaz, la API y los videos."""
from __future__ import annotations

import io
import json
import logging
import secrets
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, acceso, cuentas, render, textos
from .config import AJUSTES_POR_DEFECTO, FUENTES, LIMITES, LIENZO_ALTO, LIENZO_ANCHO, PUERTO, WEB, Rutas
from .errores import ErrorEtapa, sin_secretos
from .pipeline import Fabrica

log = logging.getLogger("fabrica.server")
_CODIGOS = {"duplicado": 409, "configuracion": 409, "autenticacion": 502, "cuota": 502, "temporal": 502,
            "modelo": 502, "herramienta": 500, "interno": 500}


def crear_app(fabrica: Fabrica | None = None, iniciar_hilos: bool = True) -> FastAPI:
    fab = fabrica or Fabrica(Rutas())
    vinc = acceso.Vinculacion()
    limitador = cuentas.Limitador()

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

    def _sesion(request: Request) -> dict | None:
        token = request.cookies.get(cuentas.COOKIE_SESION, "")
        return fab.db.sesion_por_token(acceso.hash_token(token)) if token else None

    def _autorizado(request: Request) -> bool:
        """Sin cuenta creada: el PC entra directo y los demás necesitan estar vinculados.
        Con cuenta: hace falta una sesión iniciada (también en el PC) o un dispositivo vinculado."""
        if fab.db.cuenta() is None and _local(request):
            return True
        if _sesion(request):
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
            or ruta in ("/api/sesion", "/api/vincular", "/api/youtube/callback", "/api/login", "/api/cuenta/crear")
        if not publico and not _autorizado(request):
            return JSONResponse({"error": "Inicia sesión o vincula este dispositivo."}, status_code=401)
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
        cuenta = fab.db.cuenta()
        return {"autorizado": _autorizado(request), "local": _local(request), "version": __version__,
                "cuenta_creada": cuenta is not None, "usuario": cuenta["nombre"] if cuenta and _autorizado(request) else "",
                "sesion_iniciada": _sesion(request) is not None,
                "espera_login": int(limitador.espera(request.client.host if request.client else "?") + 0.999)}

    def _abrir_sesion(request: Request, recordar: bool) -> JSONResponse:
        token = secrets.token_urlsafe(32)
        duracion = cuentas.DURACION_RECORDAR if recordar else cuentas.DURACION_NORMAL
        fab.db.crear_sesion(acceso.hash_token(token), request.headers.get("user-agent", ""),
                            request.client.host if request.client else "", duracion)
        r = JSONResponse({"ok": True, "usuario": fab.db.cuenta()["nombre"]})
        r.set_cookie(cuentas.COOKIE_SESION, token, max_age=int(duracion) if recordar else None,
                     httponly=True, samesite="strict")
        return r

    @app.post("/api/cuenta/crear")
    async def crear_cuenta(request: Request):
        """Primera configuración: solo desde el PC y solo si aún no hay cuenta."""
        _solo_pc(request)
        c = await request.json()
        nombre, contrasena = cuentas.validar_nueva(str(c.get("nombre", "")), str(c.get("contrasena", "")))
        if not fab.db.crear_cuenta(nombre, cuentas.hash_contrasena(contrasena)):
            raise ErrorEtapa("Ya existe una cuenta. Inicia sesión.", "duplicado")
        return _abrir_sesion(request, bool(c.get("recordar", True)))

    @app.post("/api/login")
    async def login(request: Request):
        ip = request.client.host if request.client else "?"
        espera = limitador.espera(ip)
        if espera > 0:
            return JSONResponse({"error": f"Demasiados intentos. Espera {int(espera) + 1} segundos.",
                                 "espera": int(espera) + 1}, status_code=429)
        cuenta = fab.db.cuenta()
        if cuenta is None:
            raise ErrorEtapa("Todavía no hay una cuenta: créala desde el panel en el PC.", "configuracion")
        c = await request.json()
        nombre_ok = str(c.get("usuario", "")).strip().lower() in ("", cuenta["nombre"].lower())
        if not (cuentas.verificar_contrasena(str(c.get("contrasena", "")), cuenta["hash"]) and nombre_ok):
            limitador.fallo(ip)
            espera = limitador.espera(ip)
            if espera > 0:      # este fallo activó el bloqueo: se informa ya, no en el intento siguiente
                return JSONResponse({"error": f"Usuario o contraseña incorrectos. Demasiados intentos: espera "
                                              f"{int(espera) + 1} segundos.", "espera": int(espera) + 1}, status_code=429)
            return JSONResponse({"error": "Usuario o contraseña incorrectos."}, status_code=403)
        limitador.exito(ip)
        return _abrir_sesion(request, bool(c.get("recordar", False)))

    @app.post("/api/logout")
    def logout(request: Request):
        token = request.cookies.get(cuentas.COOKIE_SESION, "")
        if token:
            fab.db.borrar_sesion(token_hash=acceso.hash_token(token))
        r = JSONResponse({"ok": True})
        r.delete_cookie(cuentas.COOKIE_SESION)
        return r

    @app.put("/api/cuenta/contrasena")
    async def cambiar_contrasena(request: Request):
        _solo_pc(request)
        cuenta = fab.db.cuenta()
        if cuenta is None:
            raise ErrorEtapa("No hay cuenta creada.", "configuracion")
        c = await request.json()
        if not cuentas.verificar_contrasena(str(c.get("actual", "")), cuenta["hash"]):
            raise ErrorEtapa("La contraseña actual no es correcta.", "prohibido")
        _, nueva = cuentas.validar_nueva(cuenta["nombre"], str(c.get("nueva", "")))
        fab.db.cambiar_contrasena(cuentas.hash_contrasena(nueva))     # cierra todas las sesiones
        return _abrir_sesion(request, True)

    @app.get("/api/sesiones")
    def listar_sesiones(request: Request):
        actual = _sesion(request)
        return [{**x, "actual": bool(actual and actual["id"] == x["id"])} for x in fab.db.sesiones()]

    @app.delete("/api/sesiones/{sid}")
    def cerrar_sesion(sid: str, request: Request):
        _solo_pc(request)
        fab.db.borrar_sesion(sid=sid)
        return {"ok": True}

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
    duraciones: dict[str, float] = {}     # propiedades.json no cambia una vez escrito

    def _duracion(t: dict) -> float | None:
        """Duración real del clip (ffprobe); None hasta que termina la etapa «comprobar»."""
        if t["id"] not in duraciones:
            f = fab.rutas.trabajo(t["id"]) / "propiedades.json"
            try:
                duraciones[t["id"]] = float(json.loads(f.read_text(encoding="utf-8"))["duracion"])
            except (OSError, ValueError, KeyError):
                return None
        return duraciones[t["id"]]

    def _publico(t: dict) -> dict:
        """Versión del trabajo para el panel: sin sesiones de subida ni rutas internas."""
        s = t["subida"]
        return {**{k: t[k] for k in ("id", "creado", "actualizado", "nombre", "origen_tipo", "estado", "etapa",
                                     "etapas", "error", "error_tipo", "avisos", "publicar", "subir_solicitado",
                                     "textos", "youtube_id", "modo")},
                "origen_ref": t["origen_ref"] if t["origen_tipo"] == "enlace" else Path(t["origen_ref"]).name,
                "salida": t["datos"].get("salida"), "copia": t["datos"].get("copia", ""),
                "estilo": t["datos"].get("estilo", ""), "duracion": _duracion(t),
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
                "proveedores": _proveedores(), "subida_automatica": a["subida_automatica"], "estilo": a["estilo"],
                "subidas_pausadas_hasta": a["subidas_pausadas_hasta"] if a["subidas_pausadas_hasta"] > time.time() else 0}

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

    @app.put("/api/trabajos/{jid}/estilo")
    async def estilo_trabajo(jid: str, request: Request):
        return _publico(fab.cambiar_estilo(jid, str((await request.json()).get("estilo", ""))))

    @app.get("/api/trabajos/{jid}/linea")
    def linea_tiempo(jid: str):
        return fab.linea_de_tiempo(jid)

    @app.put("/api/trabajos/{jid}/edicion")
    async def editar_tiempos(jid: str, request: Request):
        t = fab.editar_tiempos(jid, (await request.json()).get("tramos", []))
        duraciones.pop(jid, None)                 # el clip cambia de duración
        return _publico(t)

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
        return {"valores": fab.db.ajustes(), "defecto": AJUSTES_POR_DEFECTO, "limites": LIMITES,
                "logo_propio": (fab.rutas.recursos / "logo.png").exists()}

    @app.put("/api/ajustes")
    async def guardar_ajustes(request: Request):
        cambios = await request.json()
        # El canal de destino solo se cambia con la confirmación explícita de /api/youtube/canal.
        for k in ("youtube_canal_id", "youtube_canal_nombre", "subidas_pausadas_hasta"):
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

    def _maqueta(request: Request, banner: str):
        """Ajustes guardados + los que lleguen por parámetro (sin guardarlos) y su disposición."""
        a = fab.db.ajustes()
        from .db import validar_ajustes
        validar_ajustes({k: v for k, v in request.query_params.items() if k in AJUSTES_POR_DEFECTO})
        for k, v in request.query_params.items():
            if k in AJUSTES_POR_DEFECTO and k != "youtube_canal_id":
                base = AJUSTES_POR_DEFECTO[k]
                try:
                    a[k] = (v == "true") if isinstance(base, bool) else int(float(v)) if isinstance(base, int) else v
                except ValueError:
                    pass
        try:
            completo = a["estilo"] in ("completo", "dividido")
            con_banner = {"completo": a["completo_banner"], "dividido": a["dividido_banner"]}.get(a["estilo"], True)
            b = render.componer_banner(textos.normalizar_banner(banner) or "BANNER", a) if con_banner else None
            if a["estilo"] == "dividido":
                d = render.calcular_disposicion_dividido(a, b)
            elif completo:
                d = render.calcular_disposicion_completo(a, b)
            else:
                d = render.calcular_disposicion(1920, 1080, a, b)
        except Exception as e:
            raise ErrorEtapa(f"Ajustes de diseño no válidos: {e}", "entrada")
        return a, b, d, completo

    @app.get("/api/diseno/disposicion")
    def disposicion_diseno(request: Request, banner: str = "ASÍ SE VERÁ TU BANNER"):
        """Cajas de cada elemento (lienzo 1080×1920) para el editor visual de la Plantilla."""
        a, _, d, completo = _maqueta(request, banner)
        return {"lienzo": {"w": LIENZO_ANCHO, "h": LIENZO_ALTO}, "estilo": a["estilo"] if a["estilo"] in ("completo", "dividido") else "clasico",
                "elementos": render.elementos_editables(d, a, fab.rutas.recursos), "avisos": d["avisos"]}

    @app.get("/api/diseno/vista")
    def vista_diseno(request: Request, banner: str = "ASÍ SE VERÁ TU BANNER"):
        """Maqueta rápida del diseño con los ajustes actuales (o los que lleguen por parámetro)."""
        from PIL import Image, ImageDraw
        a, b, d, completo = _maqueta(request, banner)
        try:
            capa = render.dibujar_capa(d, b, a, fab.rutas.recursos)
        except Exception as e:
            raise ErrorEtapa(f"Ajustes de diseño no válidos: {e}", "entrada")
        lienzo = Image.new("RGBA", (LIENZO_ANCHO, LIENZO_ALTO), "black")
        dib = ImageDraw.Draw(lienzo)
        v, s = d["video"], d["subtitulos"]
        paneles = d.get("paneles") or [{"id": "video", **v}]
        etiquetas = {"video": "VIDEO", "camara": "CÁMARA DEL STREAMER", "contenido": "CONTENIDO"}
        for i, pn in enumerate(paneles):
            dib.rectangle((pn["x"], pn["y"], pn["x"] + pn["w"], pn["y"] + pn["h"]), fill=("#2a2d33", "#23262c")[i % 2])
            dib.text((LIENZO_ANCHO // 2, pn["y"] + pn["h"] // 2), etiquetas[pn["id"]],
                     font=render._fuente(render.FUENTE_BOLD, 54), fill="#4a4e57", anchor="mm")
        lienzo.alpha_composite(capa)
        fuente = render._fuente(render.FUENTE_BLACK if completo else render.FUENTE_BOLD, s["tamano"])
        dib = ImageDraw.Draw(lienzo)
        partes = [("Mi gente ", "white"), ("linda", a["sub_color_resalte"] if a["sub_resaltar"] else "white")]
        if completo and a["completo_mayusculas"]:  # también en dividido
            partes = [(t.upper(), c) for t, c in partes]
        ancho_total = sum(dib.textlength(t, font=fuente) for t, _ in partes)
        x = (LIENZO_ANCHO - ancho_total) / 2
        for texto_parte, color in partes:
            dib.text((x, s["y"]), texto_parte, font=fuente, fill=color, anchor="la",
                     stroke_width=max(4, round(s["tamano"] * 0.09)) if completo else max(2, round(s["tamano"] * 0.06)),
                     stroke_fill="black")
            x += dib.textlength(texto_parte, font=fuente)
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

    @app.post("/api/youtube/reanudar")
    def yt_reanudar():
        """Quitar la pausa por límite diario (por si YouTube ya lo restableció antes)."""
        fab.reanudar_subidas()
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
