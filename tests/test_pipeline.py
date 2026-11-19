import os
import shutil
from pathlib import Path

import pytest

from fabrica_studio import media, render
from fabrica_studio.errores import ErrorEtapa


def _procesar(f, t):
    f._ejecutar(f.db.trabajo(t["id"]))
    return f.db.trabajo(t["id"])


def test_mp4_horizontal_produce_vertical_1080x1920(fabrica, clip):
    t = _procesar(fabrica, fabrica.importar_archivo(clip, "horizontal.mp4"))
    assert t["estado"] == "renderizado", t["error"]
    salida = media.sondear(fabrica.rutas.trabajo(t["id"]) / "short.mp4")
    assert (salida["ancho"], salida["alto"]) == (1080, 1920)
    assert salida["codec_video"] == "h264" and salida["codec_audio"] == "aac"
    assert abs(salida["duracion"] - 3.0) < 0.2
    assert (fabrica.rutas.renderizados / t["datos"]["copia"]).exists()
    assert len(t["textos"]["titulo"]) <= 80 and len(t["textos"]["banner"].split()) <= 6
    assert not t["subir_solicitado"]          # sin subida automática: espera revisión


def test_importar_el_mismo_archivo_no_duplica(fabrica, clip):
    fabrica.importar_archivo(clip, "a.mp4")
    with pytest.raises(ErrorEtapa) as e:
        fabrica.importar_archivo(clip, "otro_nombre.mp4")
    assert e.value.tipo == "duplicado" and len(fabrica.db.trabajos()) == 1


def test_archivo_que_no_es_video_se_rechaza(fabrica, tmp_path):
    falso = tmp_path / "falso.mp4"
    falso.write_bytes(b"esto no es un video" * 100)
    with pytest.raises(ErrorEtapa):
        fabrica.importar_archivo(falso, "falso.mp4")
    assert fabrica.db.trabajos() == []


def test_un_fallo_conserva_lo_intermedio_y_reintentar_no_repite(fabrica, clip, monkeypatch):
    original = render.renderizar
    monkeypatch.setattr(render, "renderizar", lambda *a, **k: (_ for _ in ()).throw(ErrorEtapa("ffmpeg falló", "herramienta")))
    t = _procesar(fabrica, fabrica.importar_archivo(clip, "a.mp4"))
    carpeta = fabrica.rutas.trabajo(t["id"])
    assert t["estado"] == "error" and t["etapa"] == "render" and "ffmpeg falló" in t["error"]
    assert (carpeta / "transcripcion.json").exists() and (carpeta / "textos_generados.json").exists()
    monkeypatch.setattr(render, "renderizar", original)
    fabrica.reintentar(t["id"])
    t = _procesar(fabrica, t)
    assert t["estado"] == "renderizado" and fabrica.transcripciones["n"] == 1


def test_un_clip_con_error_no_detiene_al_siguiente(fabrica, clip, tmp_path):
    malo = fabrica.db.crear_trabajo("roto", "archivo")       # trabajo sin archivo de entrada
    otro = tmp_path / "b.mp4"
    shutil.copyfile(clip, otro)
    with open(otro, "ab") as fh:
        fh.write(b"\0")                                       # mismo video, distinto hash
    bueno = fabrica.importar_archivo(otro, "b.mp4")
    for _ in range(2):
        fabrica._ejecutar(fabrica.db.siguiente())
    assert fabrica.db.trabajo(malo["id"])["estado"] == "error"
    assert fabrica.db.trabajo(bueno["id"])["estado"] == "renderizado"


def test_cambiar_banner_renderiza_de_nuevo_sin_transcribir(fabrica, clip):
    t = _procesar(fabrica, fabrica.importar_archivo(clip, "a.mp4"))
    huella = t["datos"]["huella_render"]
    t = fabrica.editar_textos(t["id"], {"banner": "otro banner distinto", "descripcion": "Todo en una línea #Kick"})
    assert t["estado"] == "pendiente" and t["textos"]["descripcion"] == "Todo en una línea\n#Shorts #Kick"
    t = _procesar(fabrica, t)
    assert t["estado"] == "renderizado" and t["datos"]["huella_render"] != huella
    assert fabrica.transcripciones["n"] == 1


def test_reinicio_retoma_trabajos_a_medias(fabrica, clip):
    t = fabrica.importar_archivo(clip, "a.mp4")
    fabrica.db.actualizar(t["id"], estado="procesando")
    assert fabrica.db.recuperar_interrumpidos() == 1
    assert fabrica.db.siguiente()["id"] == t["id"]


def test_carpeta_no_importa_archivos_que_aun_se_copian(fabrica, clip):
    destino = fabrica.rutas.crudos / "nuevo.mp4"
    datos = clip.read_bytes()
    destino.write_bytes(datos[: len(datos) // 2])             # copia a medias
    assert fabrica.revisar_carpeta(ahora=1000) == []
    assert fabrica.revisar_carpeta(ahora=1003) == []          # aún no pasaron los segundos de espera
    destino.write_bytes(datos)                                # termina la copia: cambia y se vuelve a esperar
    os.utime(destino, (2000, 2000))
    assert fabrica.revisar_carpeta(ahora=1004) == []
    assert fabrica.revisar_carpeta(ahora=1009) == []
    nuevos = fabrica.revisar_carpeta(ahora=1012)
    assert len(nuevos) == 1 and nuevos[0]["origen_tipo"] == "carpeta"
    assert fabrica.revisar_carpeta(ahora=1030) == []          # no se importa dos veces
    assert destino.exists()                                   # el original sigue en crudos hasta subir


def test_enlace_no_compatible_se_explica(fabrica):
    with pytest.raises(ErrorEtapa) as e:
        fabrica.importar_enlace("https://example.com/video")
    assert "no compatible" in str(e.value)
    with pytest.raises(ErrorEtapa):
        fabrica.importar_enlace("javascript:alert(1)")


class YouTubeFalso:
    def __init__(self):
        self.subidas = []
        self.fallar = None

    def subir(self, archivo, titulo, descripcion, canal_id, es_gaming, para_ninos, subida, guardar, progreso=None):
        if self.fallar:
            raise self.fallar
        self.subidas.append((archivo.name, titulo, canal_id))
        return f"vid{len(self.subidas)}"


def test_subida_guarda_id_mueve_original_y_no_se_repite(fabrica, clip):
    fabrica.youtube = YouTubeFalso()
    fabrica.db.guardar_ajustes({"youtube_canal_id": "UC_ok", "segundos_estable": 0})
    crudo = fabrica.rutas.crudos / "clip.mp4"
    shutil.copyfile(clip, crudo)
    fabrica.revisar_carpeta(ahora=1)
    (t,) = fabrica.revisar_carpeta(ahora=2)
    t = _procesar(fabrica, t)
    assert t["estado"] == "renderizado" and crudo.exists()

    # Un fallo temporal de subida deja el original en su sitio y el render intacto.
    fabrica.youtube.fallar = ErrorEtapa("sin red", "temporal")
    fabrica.solicitar_subida(t["id"])
    t = _procesar(fabrica, t)
    assert t["estado"] == "error" and t["error_tipo"] == "temporal" and crudo.exists()

    fabrica.youtube.fallar = None
    fabrica.reintentar(t["id"])
    t = fabrica.db.trabajo(t["id"])
    assert t["estado"] == "renderizado" and t["subir_solicitado"]      # reintenta la subida, no el render
    t = _procesar(fabrica, t)
    assert t["estado"] == "publicado" and t["youtube_id"] == "vid1"
    assert not crudo.exists() and (fabrica.rutas.procesados / "clip.mp4").exists()

    with pytest.raises(ErrorEtapa) as e:
        fabrica.solicitar_subida(t["id"])
    assert e.value.tipo == "duplicado" and len(fabrica.youtube.subidas) == 1
    with pytest.raises(ErrorEtapa):
        fabrica.editar_textos(t["id"], {"banner": "cambio tardío"})


def test_sin_canal_confirmado_no_se_puede_pedir_subida(fabrica, clip):
    t = _procesar(fabrica, fabrica.importar_archivo(clip, "a.mp4"))
    with pytest.raises(ErrorEtapa) as e:
        fabrica.solicitar_subida(t["id"])
    assert e.value.tipo == "configuracion"


def test_clip_con_franjas_negras_se_recorta_al_ancho_completo(fabrica, tmp_path):
    import subprocess
    ruta = tmp_path / "vertical_con_bordes.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=3",
                    "-f", "lavfi", "-i", "sine=f=440:d=3", "-vf", "pad=720:1280:40:300:black",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(ruta)], check=True)
    t = _procesar(fabrica, fabrica.importar_archivo(ruta, "v.mp4"))
    assert t["estado"] == "renderizado", t["error"]
    assert t["datos"]["disposicion"]["video"]["w"] == 1080            # ocupa todo el ancho, sin franjas
    assert "bordes negros recortados" in t["etapas"]["render"]["detalle"]
    fabrica.db.guardar_ajustes({"recortar_bordes": False})              # desactivado: vuelve el encuadre original
    fabrica.renderizar_de_nuevo(t["id"])
    t = _procesar(fabrica, t)
    assert t["datos"]["disposicion"]["video"]["w"] < 1080


def test_solo_se_aceptan_enlaces_a_un_clip_o_video_de_kick(fabrica):
    from fabrica_studio import importar
    validos = ["https://kick.com/jongottii/clips/clip_01JTZ79TQ46787D3MCG4FAY56P",
               "https://kick.com/jongottii?clip=clip_01JTZ79TQ46787D3MCG4FAY56P",
               "https://kick.com/jongottii/videos/3f9a2c1e-1111-2222-3333-444455556666",
               "https://kick.com/video/3f9a2c1e-1111-2222-3333-444455556666"]
    for url in validos:
        assert importar.validar_enlace(url) == url
    invalidos = ["https://kick.com/jongottii/clips?sort=date&range=all", "https://kick.com/jongottii",
                 "https://kick.com/jongottii/clips", "https://kick.com/", "https://kick.com/jongottii/videos"]
    for url in invalidos:
        with pytest.raises(ErrorEtapa) as e:
            fabrica.importar_enlace(url)
        assert "no es de un clip" in str(e.value)
    assert fabrica.db.trabajos() == []                     # no se crea ningún trabajo


def test_limite_diario_pausa_las_subidas_y_se_reanudan_solas(fabrica, clip, tmp_path, monkeypatch):
    import time as _t
    fabrica.youtube = YouTubeFalso()
    fabrica.db.guardar_ajustes({"youtube_canal_id": "UC_ok"})
    t = _procesar(fabrica, fabrica.importar_archivo(clip, "a.mp4"))
    fabrica.solicitar_subida(t["id"])
    fabrica.youtube.fallar = ErrorEtapa("YouTube: límite de subidas (400, uploadLimitExceeded)", "cuota")
    fabrica._ejecutar(fabrica.db.siguiente())
    t = fabrica.db.trabajo(t["id"])
    assert t["estado"] == "renderizado" and t["subir_solicitado"] and not t["error"]   # no queda en error
    assert any("se reintentará sola" in a for a in t["avisos"])
    hasta = fabrica.db.ajustes()["subidas_pausadas_hasta"]
    assert hasta > _t.time() + 500
    # Mientras dura la pausa, los demás clips se procesan pero nadie intenta subir.
    otro = tmp_path / "b.mp4"
    shutil.copyfile(clip, otro)
    with open(otro, "ab") as fh:
        fh.write(b"\0")
    b = fabrica.importar_archivo(otro, "b.mp4")
    assert fabrica.db.siguiente()["id"] == b["id"]
    fabrica._ejecutar(fabrica.db.siguiente())
    assert fabrica.db.siguiente() is None
    # Pasada la hora, la subida pendiente se retoma sin intervención.
    monkeypatch.setattr("fabrica_studio.db.time.time", lambda: hasta + 1)
    fabrica.youtube.fallar = None
    sig = fabrica.db.siguiente()
    assert sig["id"] == t["id"]
    fabrica._ejecutar(sig)
    assert fabrica.db.trabajo(t["id"])["estado"] == "publicado"


def test_clips_viejos_en_error_por_cuota_vuelven_a_la_cola(fabrica, clip):
    t = _procesar(fabrica, fabrica.importar_archivo(clip, "a.mp4"))
    fabrica.db.actualizar(t["id"], estado="error", error_tipo="cuota", etapa="subir", error="límite")
    assert fabrica._recuperar_por_cuota() == 1
    t = fabrica.db.trabajo(t["id"])
    assert t["estado"] == "renderizado" and t["subir_solicitado"] and not t["error"]


def test_exportar_para_otras_plataformas(fabrica, clip):
    from fabrica_studio import exportar as ex
    t = _procesar(fabrica, fabrica.importar_archivo(clip, "Clip GTA (1).mp4"))
    fabrica.db.actualizar(t["id"], textos={**t["textos"], "titulo": "GTA 6 | Escapa #Shorts",
                                            "descripcion": "Escapa de la policía\n#Shorts #GTA6 #GTA"})
    r = fabrica.exportar(t["id"], "reels")
    assert r["video"].endswith(".mp4") and (fabrica.rutas.exportados / "reels").exists()
    assert r["texto"] == "GTA 6 | Escapa\n\nEscapa de la policía\n\n#GTA6 #GTA\n"
    assert "#Shorts" in fabrica.exportar(t["id"], "shorts")["texto"]
    avisos = ex.revisar_zonas({"logo": {"y": 1810, "h": 52}, "subtitulos": {"y": 1250, "h": 200},
                               "tarjeta": {"y": 100, "h": 200}}, "tiktok")
    assert any("El logo" in a and "inferior" in a for a in avisos) and any("El banner" in a for a in avisos)
    assert not any("subtítulos" in a for a in avisos)
    pendiente = fabrica.importar_archivo(fabrica.rutas.renderizados / Path(t["datos"]["copia"]).name, "otro.mp4")
    with pytest.raises(ErrorEtapa):
        fabrica.exportar(pendiente["id"], "tiktok")             # aún no renderizado


def test_ritmo_de_publicacion(fabrica, clip, monkeypatch):
    import json as _json
    import time as _t
    ahora = 1_800_000_000
    monkeypatch.setattr("fabrica_studio.db.time.time", lambda: ahora)
    fabrica.db.guardar_ajustes({"subidas_max_dia": 2, "subidas_intervalo_min": 30})
    assert fabrica.db.proxima_subida() <= ahora                          # sin subidas previas: se puede ya
    t1 = fabrica.db.crear_trabajo("a", "archivo")
    fabrica.db.actualizar(t1["id"], estado="publicado", youtube_id="v1", subida={"terminado": ahora - 600})
    assert fabrica.db.proxima_subida() == ahora - 600 + 1800            # espera el intervalo de 30 min
    t2 = fabrica.db.crear_trabajo("b", "archivo")
    fabrica.db.actualizar(t2["id"], estado="publicado", youtube_id="v2", subida={"terminado": ahora - 7200})
    fabrica.db.guardar_ajustes({"subidas_intervalo_min": 0})
    assert fabrica.db.proxima_subida() == ahora - 7200 + 86400          # 2 en 24 h: espera a que venza la más antigua
    # Un clip listo para subir espera su turno; los pendientes de procesar no.
    t3 = fabrica.db.crear_trabajo("c", "archivo")
    fabrica.db.actualizar(t3["id"], estado="renderizado", subir_solicitado=True)
    assert fabrica.db.siguiente() is None
    fabrica.db.guardar_ajustes({"subidas_max_dia": 0})
    assert fabrica.db.siguiente()["id"] == t3["id"]


def _listo(fabrica, nombre, creado, publicar=True, **extra):
    """Clip ya renderizado sin pasar por FFmpeg: para probar la cola de subidas (YouTubeFalso no lee el archivo)."""
    t = fabrica.db.crear_trabajo(nombre, "archivo", publicar=publicar)
    fabrica.db.actualizar(t["id"], creado=creado, estado="renderizado",
                          textos={"titulo": f"{nombre} #Shorts", "descripcion": "", "es_gaming": False}, **extra)
    return fabrica.db.trabajo(t["id"])


def test_subir_ahora_se_salta_el_ritmo_pero_no_la_pausa_de_youtube(fabrica, clip, monkeypatch):
    fabrica.youtube = YouTubeFalso()
    t = _procesar(fabrica, fabrica.importar_archivo(clip, "a.mp4"))   # antes de congelar el reloj
    ahora = 1_800_000_000.0
    monkeypatch.setattr("fabrica_studio.db.time.time", lambda: ahora)
    fabrica.db.guardar_ajustes({"youtube_canal_id": "UC_ok", "subidas_max_dia": 1, "subidas_intervalo_min": 60})
    previa = fabrica.db.crear_trabajo("previa", "archivo")
    fabrica.db.actualizar(previa["id"], estado="publicado", youtube_id="v0", subida={"terminado": ahora - 60})
    fabrica.solicitar_subida(t["id"])
    assert fabrica.db.siguiente() is None                 # con el ritmo, espera: ya hubo 1 subida hoy y hace 1 min

    fabrica.subir_ahora(t["id"])
    assert fabrica.db.trabajo(t["id"])["subir_ya"] == ahora
    fabrica.db.guardar_ajustes({"subidas_pausadas_hasta": int(ahora) + 3600})       # límite diario de YouTube
    assert fabrica.db.siguiente() is None                 # la pausa de YouTube no se salta
    fabrica.reanudar_subidas()
    sig = fabrica.db.siguiente()
    assert sig["id"] == t["id"]
    fabrica._ejecutar(sig)
    t = fabrica.db.trabajo(t["id"])
    assert t["estado"] == "publicado" and t["youtube_id"] == "vid1" and t["subir_ya"] == 0
    assert fabrica.youtube.subidas == [("short.mp4", t["textos"]["titulo"], "UC_ok")]     # una vez, al canal confirmado
    with pytest.raises(ErrorEtapa) as e:
        fabrica.subir_ahora(t["id"])
    assert e.value.tipo == "duplicado" and len(fabrica.youtube.subidas) == 1
    assert fabrica.db.siguiente() is None


def test_subir_ahora_va_primero_en_el_orden_pedido_y_no_duplica(fabrica):
    fabrica.youtube = YouTubeFalso()
    fabrica.db.guardar_ajustes({"youtube_canal_id": "UC_ok", "subidas_max_dia": 0, "subidas_intervalo_min": 0})
    a, b, c = (_listo(fabrica, n, creado=1000 + i) for i, n in enumerate("abc"))
    pendiente = fabrica.db.crear_trabajo("por_procesar", "archivo")
    fabrica.db.actualizar(pendiente["id"], creado=1)                  # el más antiguo de todos
    fabrica.solicitar_subida(a["id"])                                  # cola normal
    fabrica.subir_ahora(c["id"])
    fabrica.subir_ahora(b["id"])
    fabrica.subir_ahora(c["id"])                                       # pedirlo otra vez no cambia su turno
    orden = []
    while (sig := fabrica.db.siguiente()) and sig["estado"] == "renderizado":
        orden.append(sig["nombre"])
        fabrica.subir(sig["id"])
    assert orden == ["c", "b"] and sig["id"] == pendiente["id"]       # «Subir ahora» primero; luego lo más antiguo
    assert [s[1] for s in fabrica.youtube.subidas] == ["c #Shorts", "b #Shorts"]


def test_subir_todos_ahora_y_quitar_de_la_cola(fabrica):
    fabrica.youtube = YouTubeFalso()
    with pytest.raises(ErrorEtapa) as e:
        fabrica.subir_todos_ahora()
    assert e.value.tipo == "configuracion"                             # sin canal confirmado, nada
    fabrica.db.guardar_ajustes({"youtube_canal_id": "UC_ok", "subidas_max_dia": 1, "subidas_intervalo_min": 600})
    nuevo = _listo(fabrica, "nuevo", creado=2000)
    viejo = _listo(fabrica, "viejo", creado=1000)
    local = _listo(fabrica, "solo_local", creado=1500, publicar=False)    # importado sin destinar a YouTube
    _listo(fabrica, "ya_subido", creado=500, youtube_id="v9")
    fabrica.db.actualizar(fabrica.db.trabajos()[-1]["id"], estado="publicado")
    fabrica.db.guardar_ajustes({"subidas_pausadas_hasta": 4_000_000_000})
    r = fabrica.subir_todos_ahora()
    assert (r["encolados"], r["omitidos"], r["pausa_hasta"]) == (2, 1, 4_000_000_000)
    assert fabrica.db.siguiente() is None                              # la pausa de YouTube se respeta
    fabrica.reanudar_subidas()
    fabrica.cancelar_subida(nuevo["id"])                               # quitarlo de la cola antes de que suba
    with pytest.raises(ErrorEtapa):
        fabrica.cancelar_subida(nuevo["id"])
    fabrica.subir(fabrica.db.siguiente()["id"])
    assert [s[1] for s in fabrica.youtube.subidas] == ["viejo #Shorts"]
    assert fabrica.db.siguiente() is None                              # «nuevo» salió de la cola; el ritmo no importa aquí
    assert not fabrica.db.trabajo(local["id"])["subir_solicitado"] and fabrica.db.trabajo(viejo["id"])["youtube_id"]
    assert fabrica.subir_todos_ahora()["encolados"] == 1               # otra vez: solo «nuevo»; nada se sube dos veces


def test_regenerar_textos_de_varios_no_toca_los_subidos(fabrica, clip):
    t = _procesar(fabrica, fabrica.importar_archivo(clip, "a.mp4"))          # renderizado, con transcripción

    def con_transcripcion(nombre, **campos):
        x = fabrica.db.crear_trabajo(nombre, "archivo")
        carpeta = fabrica.rutas.trabajo(x["id"])
        carpeta.mkdir(parents=True)
        (carpeta / "transcripcion.json").write_text('{"texto": "hola", "palabras": [], "segmentos": []}', encoding="utf-8")
        fabrica.db.actualizar(x["id"], **campos)
        return fabrica.db.trabajo(x["id"])
    subido = con_transcripcion("subido", estado="publicado", youtube_id="v1",
                               textos={"titulo": "Ya en YouTube #Shorts", "origen": "gemini:x"})
    editado = con_transcripcion("editado", estado="renderizado", textos={"titulo": "Mío #Shorts", "origen": "editado"})
    con_transcripcion("en_cola", estado="renderizado", subir_solicitado=True, textos={"titulo": "x", "origen": "local"})
    con_transcripcion("procesando", estado="procesando")
    sin = fabrica.db.crear_trabajo("sin_transcripcion", "archivo")
    fabrica.db.actualizar(sin["id"], estado="error")

    r = fabrica.regenerar_textos_varios()                                     # todos los que no se han subido
    assert r == {"regenerando": 1, "omitidos": {"editados": 1, "en_cola_de_subida": 1, "en_proceso": 1,
                                                "sin_transcripcion": 1}}
    assert fabrica.db.trabajo(subido["id"])["textos"]["titulo"] == "Ya en YouTube #Shorts"
    assert fabrica.db.trabajo(editado["id"])["textos"]["origen"] == "editado"   # lo editado a mano no se pisa
    p = fabrica.progreso_lote_textos()
    assert (p["total"], p["listos"], p["terminado"]) == (1, 0, False)
    fabrica._ejecutar(fabrica.db.trabajo(t["id"]))                            # el trabajador lo procesa
    p = fabrica.progreso_lote_textos()
    assert (p["listos"], p["errores"], p["terminado"]) == (1, 0, True) and fabrica.transcripciones["n"] == 1
    assert fabrica.db.trabajo(t["id"])["textos"]["titulo"] == t["textos"]["titulo"]   # misma transcripción, mismo borrador

    # Elegidos a mano: el subido tampoco se toca aunque se pida; con incluir_editados, el editado sí.
    r = fabrica.regenerar_textos_varios([subido["id"], editado["id"], "no-existe"], incluir_editados=True)
    assert r == {"regenerando": 1, "omitidos": {"no_existen": 1, "subidos": 1}}
    s = fabrica.db.trabajo(subido["id"])
    assert s["estado"] == "publicado" and s["textos"]["titulo"] == "Ya en YouTube #Shorts"
    assert fabrica.db.trabajo(editado["id"])["textos"] == {}
    fabrica.eliminar(editado["id"])                                           # sus clips se borran: el lote desaparece
    assert fabrica.progreso_lote_textos() is None and fabrica.lote_textos is None
    fabrica.regenerar_textos_varios([t["id"]])
    fabrica.cerrar_lote_textos()
    assert fabrica.progreso_lote_textos() is None


def test_sin_suspender_no_falla_fuera_de_windows():
    from fabrica_studio.pipeline import sin_suspender
    with sin_suspender() as s:
        assert s is not None
