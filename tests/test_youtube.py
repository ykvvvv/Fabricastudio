"""Subida reanudable contra un YouTube simulado. No se conecta a internet."""
import json
import time
from datetime import datetime, timezone

import httpx
import pytest

from fabrica_studio import youtube
from fabrica_studio.errores import ErrorEtapa
from fabrica_studio.youtube import YouTube

CANAL = "UC_canal_confirmado"


class Falso:
    """Servidor simulado: guarda bytes recibidos y permite inyectar cortes."""

    def __init__(self):
        self.recibido = b""
        self.inicios = 0
        self.cuerpo_inicio = None
        self.cortar_en = set()      # números de PUT de datos en los que se simula un corte
        self.puts = 0
        self.sesion_perdida = False
        self.videos = []            # videos ya presentes en el canal
        self.total = 0

    def __call__(self, req: httpx.Request) -> httpx.Response:
        ruta = req.url.path
        if ruta == "/token":
            return httpx.Response(200, json={"access_token": "acceso", "expires_in": 3600})
        if ruta.endswith("/channels"):
            return httpx.Response(200, json={"items": [{"id": CANAL, "snippet": {"title": "Paltita", "customUrl": "@paltitaclips"},
                                                        "contentDetails": {"relatedPlaylists": {"uploads": "UU_x"}}}]})
        if ruta.endswith("/playlistItems"):
            return httpx.Response(200, json={"items": self.videos})
        if ruta == "/upload/youtube/v3/videos":
            self.inicios += 1
            self.cuerpo_inicio = json.loads(req.content)
            self.total = int(req.headers["X-Upload-Content-Length"])
            self.recibido = b""
            return httpx.Response(200, headers={"Location": "https://subida.test/sesion"})
        if ruta == "/sesion":
            if self.sesion_perdida:
                return httpx.Response(404)
            rango = req.headers["Content-Range"]
            if not rango.startswith("bytes */"):
                self.puts += 1
                inicio = int(rango.split(" ")[1].split("-")[0])
                assert inicio == len(self.recibido), "el cliente reenvió desde un punto incorrecto"
                self.recibido += req.content
                if self.puts in self.cortar_en:
                    raise httpx.ReadError("corte simulado")
            if len(self.recibido) == self.total:
                return httpx.Response(200, json={"id": "video123"})
            return httpx.Response(308, headers={"Range": f"bytes=0-{len(self.recibido) - 1}"} if self.recibido else {})
        return httpx.Response(404)


@pytest.fixture
def yt(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube, "BLOQUE", 1000)
    (tmp_path / "client_secret.json").write_text(json.dumps({"installed": {
        "client_id": "id", "client_secret": "s", "token_uri": "https://oauth.test/token"}}))
    (tmp_path / "youtube_token.json").write_text(json.dumps({"refresh_token": "r"}))
    falso = Falso()
    y = YouTube(tmp_path, httpx.Client(transport=httpx.MockTransport(falso)), espera=0)
    archivo = tmp_path / "short.mp4"
    archivo.write_bytes(bytes(range(256)) * 14)   # 3584 bytes -> 4 bloques
    return y, falso, archivo


def _subir(y, archivo, estado, canal=CANAL, gaming=False):
    return y.subir(archivo, "Título #Shorts", "desc\n#Shorts", canal, gaming, False, estado, lambda e: estado.update(e))


def test_subida_privada_completa(yt):
    y, falso, archivo = yt
    estado = {}
    assert _subir(y, archivo, estado) == "video123"
    assert falso.recibido == archivo.read_bytes()
    assert falso.cuerpo_inicio["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    assert falso.cuerpo_inicio["snippet"]["categoryId"] == "24"       # no es gaming
    assert estado["sesion"] and estado["canal_id"] == CANAL


def test_categoria_gaming_solo_si_corresponde(yt):
    y, falso, archivo = yt
    _subir(y, archivo, {}, gaming=True)
    assert falso.cuerpo_inicio["snippet"]["categoryId"] == "20"


def test_no_sube_a_un_canal_distinto_del_confirmado(yt):
    y, falso, archivo = yt
    with pytest.raises(ErrorEtapa) as e:
        _subir(y, archivo, {}, canal="UC_otro_canal")
    assert e.value.tipo == "configuracion" and falso.inicios == 0
    with pytest.raises(ErrorEtapa):
        _subir(y, archivo, {}, canal="")
    assert falso.inicios == 0


def test_corte_a_mitad_se_reanuda_sin_reiniciar(yt):
    y, falso, archivo = yt
    falso.cortar_en = {2}
    assert _subir(y, archivo, {}) == "video123"
    assert falso.inicios == 1 and falso.recibido == archivo.read_bytes()


def test_corte_tras_el_ultimo_bloque_no_duplica(yt):
    y, falso, archivo = yt
    falso.cortar_en = {4}                       # YouTube recibió todo pero la respuesta se perdió
    assert _subir(y, archivo, {}) == "video123"
    assert falso.inicios == 1 and falso.puts == 4


def test_reintento_con_sesion_guardada_continua(yt):
    y, falso, archivo = yt
    falso.cortar_en = {2, 3, 4, 5, 6, 7, 8}
    estado = {}
    falso_put = falso.__call__

    def siempre_falla(req):
        if req.url.path == "/sesion":
            raise httpx.ConnectError("sin red")
        return falso_put(req)
    y.http = httpx.Client(transport=httpx.MockTransport(siempre_falla))
    with pytest.raises(ErrorEtapa) as e:
        _subir(y, archivo, estado)
    assert e.value.tipo == "temporal" and estado["sesion"]
    falso.cortar_en = set()
    y.http = httpx.Client(transport=httpx.MockTransport(falso))
    assert _subir(y, archivo, estado) == "video123"
    assert falso.inicios == 1                   # se retomó la misma sesión


def test_fecha_de_youtube_respeta_su_zona_horaria():
    # Mismo instante escrito de tres formas; el resultado no depende de la zona del PC.
    utc = datetime(2026, 11, 16, 17, 0, 0, tzinfo=timezone.utc).timestamp()
    assert youtube._instante_iso("2026-11-16T17:00:00Z") == utc
    assert youtube._instante_iso("2026-11-16T17:00:00.123Z") == utc
    assert youtube._instante_iso("2026-11-16T14:00:00-03:00") == utc
    with pytest.raises(ValueError):
        youtube._instante_iso("2026-11-16T17:00:00")      # sin zona: ambiguo, no se adivina


def test_sesion_perdida_recupera_video_ya_subido(yt):
    y, falso, archivo = yt
    falso.sesion_perdida = True
    falso.videos = [{"snippet": {"title": "Título #Shorts", "resourceId": {"videoId": "ya_estaba"},
                                 "publishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}]
    estado = {"sesion": "https://subida.test/sesion", "tamano": archivo.stat().st_size,
              "inicio": time.time() - 30, "titulo": "Título #Shorts", "canal_id": CANAL}
    assert _subir(y, archivo, estado) == "ya_estaba"
    assert falso.inicios == 0                   # no se subió por segunda vez
