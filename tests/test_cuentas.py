import time

from fastapi.testclient import TestClient

from fabrica_studio import cuentas
from fabrica_studio.server import crear_app

PC = ("127.0.0.1", 50000)
TABLET = ("192.168.1.50", 50001)


def _clientes(fabrica):
    app = crear_app(fabrica, iniciar_hilos=False)
    return (TestClient(app, base_url="http://127.0.0.1:8765", client=PC),
            TestClient(app, base_url="http://192.168.1.10:8765", client=TABLET))


def test_hash_de_contrasena():
    h = cuentas.hash_contrasena("una clave larga")
    assert h.startswith("scrypt$") and "una clave larga" not in h
    assert cuentas.verificar_contrasena("una clave larga", h)
    assert not cuentas.verificar_contrasena("otra clave", h)
    assert cuentas.hash_contrasena("una clave larga") != h          # sal distinta cada vez
    assert not cuentas.verificar_contrasena("x", "basura")


def test_sin_cuenta_el_pc_entra_directo_como_antes(fabrica):
    pc, tablet = _clientes(fabrica)
    s = pc.get("/api/sesion").json()
    assert s["autorizado"] and not s["cuenta_creada"]
    assert pc.get("/api/estado").status_code == 200
    assert tablet.get("/api/estado").status_code == 401


def test_solo_el_pc_crea_la_cuenta_y_una_sola_vez(fabrica):
    pc, tablet = _clientes(fabrica)
    assert tablet.post("/api/cuenta/crear", json={"nombre": "cristobal", "contrasena": "unaclave-segura"}).status_code == 403
    assert pc.post("/api/cuenta/crear", json={"nombre": "cristobal", "contrasena": "corta"}).status_code == 400
    r = pc.post("/api/cuenta/crear", json={"nombre": "cristobal", "contrasena": "unaclave-segura"})
    assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower()
    assert pc.post("/api/cuenta/crear", json={"nombre": "otro", "contrasena": "otraclave-segura"}).status_code == 409


def test_con_cuenta_todos_necesitan_iniciar_sesion(fabrica):
    pc, tablet = _clientes(fabrica)
    pc.post("/api/cuenta/crear", json={"nombre": "cristobal", "contrasena": "unaclave-segura"})
    assert pc.get("/api/estado").status_code == 200                  # el PC quedó con sesión al crearla
    pc.post("/api/logout")
    assert pc.get("/api/estado").status_code == 401                  # ahora también el PC pide login
    s = pc.get("/api/sesion").json()
    assert s["cuenta_creada"] and not s["autorizado"] and s["usuario"] == ""   # no revela el usuario
    assert tablet.post("/api/login", json={"usuario": "cristobal", "contrasena": "mal-clave"}).status_code == 403
    r = tablet.post("/api/login", json={"usuario": "Cristobal", "contrasena": "unaclave-segura", "recordar": True})
    assert r.status_code == 200 and "max-age" in r.headers["set-cookie"].lower()
    assert tablet.get("/api/estado").status_code == 200
    assert tablet.get("/api/sesion").json()["usuario"] == "cristobal"
    # La tablet con sesión sigue sin poder hacer acciones sensibles.
    assert tablet.put("/api/secretos/gemini", json={"clave": "x"}).status_code == 403
    assert tablet.put("/api/cuenta/contrasena", json={"actual": "unaclave-segura", "nueva": "nuevaclave-123"}).status_code == 403


def test_bloqueo_por_intentos_fallidos(fabrica, monkeypatch):
    pc, tablet = _clientes(fabrica)
    pc.post("/api/cuenta/crear", json={"nombre": "cristobal", "contrasena": "unaclave-segura"})
    for _ in range(4):
        assert tablet.post("/api/login", json={"contrasena": "mala-mala"}).status_code == 403
    quinto = tablet.post("/api/login", json={"contrasena": "mala-mala"})
    assert quinto.status_code == 429 and quinto.json()["espera"] > 0      # el bloqueo se informa en el 5.º fallo
    assert tablet.get("/api/sesion").json()["espera_login"] > 0          # y sigue visible al recargar
    assert pc.get("/api/sesion").json()["espera_login"] == 0
    r = tablet.post("/api/login", json={"contrasena": "unaclave-segura"})
    assert r.status_code == 429 and r.json()["espera"] > 0               # bloqueada aunque ahora acierte
    assert pc.post("/api/login", json={"contrasena": "unaclave-segura"}).status_code == 200   # otra IP no afectada


def test_cambiar_contrasena_cierra_las_demas_sesiones(fabrica):
    pc, tablet = _clientes(fabrica)
    pc.post("/api/cuenta/crear", json={"nombre": "cristobal", "contrasena": "unaclave-segura"})
    tablet.post("/api/login", json={"contrasena": "unaclave-segura"})
    assert len(pc.get("/api/sesiones").json()) == 2
    assert pc.put("/api/cuenta/contrasena", json={"actual": "incorrecta", "nueva": "nuevaclave-123"}).status_code == 403
    assert pc.put("/api/cuenta/contrasena", json={"actual": "unaclave-segura", "nueva": "nuevaclave-123"}).status_code == 200
    assert tablet.get("/api/estado").status_code == 401                 # la tablet debe entrar de nuevo
    assert pc.get("/api/estado").status_code == 200
    assert tablet.post("/api/login", json={"contrasena": "unaclave-segura"}).status_code == 403
    assert tablet.post("/api/login", json={"contrasena": "nuevaclave-123"}).status_code == 200


def test_cerrar_sesion_remota_y_restablecer(fabrica):
    pc, tablet = _clientes(fabrica)
    pc.post("/api/cuenta/crear", json={"nombre": "cristobal", "contrasena": "unaclave-segura"})
    tablet.post("/api/login", json={"contrasena": "unaclave-segura"})
    otra = next(x for x in pc.get("/api/sesiones").json() if not x["actual"])
    assert pc.delete(f"/api/sesiones/{otra['id']}").status_code == 200
    assert tablet.get("/api/estado").status_code == 401
    fabrica.db.borrar_cuenta()                                           # lo que hace --restablecer
    assert pc.get("/api/sesion").json() == {**pc.get("/api/sesion").json(), "cuenta_creada": False, "autorizado": True}


def test_limitador_espera_creciente(monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(cuentas.time, "time", lambda: t[0])
    lim = cuentas.Limitador(gratis=2, espera_base=10, espera_max=100)
    lim.fallo("ip"); assert lim.espera("ip") == 0
    lim.fallo("ip"); assert lim.espera("ip") == 10
    lim.fallo("ip"); assert lim.espera("ip") == 20
    for _ in range(10):
        lim.fallo("ip")
    assert lim.espera("ip") == 100
    lim.exito("ip"); assert lim.espera("ip") == 0
