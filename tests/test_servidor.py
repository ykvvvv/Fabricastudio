import time

from fastapi.testclient import TestClient

from fabrica_studio.server import crear_app

PC = ("127.0.0.1", 50000)
TABLET = ("192.168.1.50", 50001)


def _clientes(fabrica):
    app = crear_app(fabrica, iniciar_hilos=False)
    return (TestClient(app, base_url="http://127.0.0.1:8765", client=PC),
            TestClient(app, base_url="http://192.168.1.10:8765", client=TABLET), app)


def test_tablet_sin_vincular_no_accede(fabrica):
    pc, tablet, _ = _clientes(fabrica)
    assert pc.get("/api/estado").status_code == 200
    assert tablet.get("/api/estado").status_code == 401
    assert tablet.get("/media/x/short.mp4").status_code == 401
    assert tablet.get("/api/sesion").json()["autorizado"] is False
    assert tablet.get("/").status_code == 200              # la pantalla de vinculación sí carga


def test_vinculacion_con_codigo_de_un_solo_uso(fabrica):
    pc, tablet, _ = _clientes(fabrica)
    assert tablet.post("/api/vincular/codigo").status_code == 401     # solo el PC genera códigos
    codigo = pc.post("/api/vincular/codigo").json()["codigo"]
    assert tablet.post("/api/vincular", json={"codigo": "000000" if codigo != "000000" else "111111"}).status_code == 403
    r = tablet.post("/api/vincular", json={"codigo": codigo, "nombre": "MatePad"})
    assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower()
    assert tablet.get("/api/estado").status_code == 200
    assert pc.get("/api/dispositivos").json()[0]["nombre"] == "MatePad"
    otro = TestClient(tablet.app, base_url="http://192.168.1.10:8765", client=("192.168.1.77", 1))
    assert otro.post("/api/vincular", json={"codigo": codigo}).status_code == 403   # el código ya se usó
    # Acciones sensibles: solo desde el PC, aunque la tablet esté vinculada.
    assert tablet.put("/api/secretos/gemini", json={"clave": "x"}).status_code == 403
    assert tablet.post("/api/youtube/canal", json={"id": "UC_x"}).status_code == 403
    assert tablet.get("/api/youtube/conectar", follow_redirects=False).status_code == 403
    # Revocar el dispositivo corta el acceso.
    pc.delete(f"/api/dispositivos/{pc.get('/api/dispositivos').json()[0]['id']}")
    assert tablet.get("/api/estado").status_code == 401


def test_codigo_se_invalida_tras_varios_fallos(fabrica, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    pc, tablet, _ = _clientes(fabrica)
    codigo = pc.post("/api/vincular/codigo").json()["codigo"]
    malo = "000000" if codigo != "000000" else "111111"
    for _ in range(5):
        tablet.post("/api/vincular", json={"codigo": malo})
    assert tablet.post("/api/vincular", json={"codigo": codigo}).status_code == 403


def test_origen_y_host_ajenos_se_rechazan(fabrica):
    pc, _, _ = _clientes(fabrica)
    assert pc.post("/api/vincular/codigo", headers={"Origin": "https://sitio-malicioso.example"}).status_code == 403
    assert pc.get("/api/estado", headers={"Host": "sitio-malicioso.example"}).status_code == 403


def test_el_panel_no_recibe_secretos_ni_puede_cambiar_canal_por_ajustes(fabrica, clip):
    pc, _, _ = _clientes(fabrica)
    with open(clip, "rb") as fh:
        r = pc.post("/api/importar/archivo", files={"archivo": ("clip.mp4", fh, "video/mp4")}, data={"publicar": "true"})
    assert r.status_code == 200
    jid = r.json()["id"]
    fabrica.db.actualizar(jid, subida={"sesion": "https://secreto/upload_id=abc", "canal_id": "UC"})
    texto = pc.get("/api/estado").text + pc.get(f"/api/trabajos/{jid}").text
    assert "upload_id" not in texto and "secreto" not in texto
    pc.put("/api/ajustes", json={"youtube_canal_id": "UC_intruso", "creador": "Otro"})
    a = pc.get("/api/ajustes").json()["valores"]
    assert a["youtube_canal_id"] == "" and a["creador"] == "Otro"
    with open(clip, "rb") as fh:
        assert pc.post("/api/importar/archivo", files={"archivo": ("otra.mp4", fh, "video/mp4")}).status_code == 409
    assert pc.post(f"/api/trabajos/{jid}/subir").status_code == 400       # aún no está renderizado
    assert pc.get("/api/diseno/vista").headers["content-type"] == "image/jpeg"
