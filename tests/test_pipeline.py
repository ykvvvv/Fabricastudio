import os
import shutil

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

    # Un fallo de subida deja el original en su sitio y el render intacto.
    fabrica.youtube.fallar = ErrorEtapa("sin cuota", "cuota")
    fabrica.solicitar_subida(t["id"])
    t = _procesar(fabrica, t)
    assert t["estado"] == "error" and t["error_tipo"] == "cuota" and crudo.exists()

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
