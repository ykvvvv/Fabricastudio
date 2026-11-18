"""Servidor MCP: herramientas (llamadas directas) y protocolo real por stdio."""
import asyncio
import json
import os
import shutil
import sys

import pytest

mcp = pytest.importorskip("mcp")
from fabrica_studio import mcp_servidor as m  # noqa: E402


def _llamar(nombre, **args):
    r = asyncio.run(m.servidor.call_tool(nombre, args))
    if getattr(r, "structured_content", None) is not None:
        return r.structured_content.get("result", r.structured_content)
    return json.loads(r.content[0].text)


@pytest.fixture
def fab_mcp(fabrica, monkeypatch):
    monkeypatch.setattr(m, "_fab", fabrica)
    monkeypatch.setattr(m, "panel_activo", lambda: False)
    return fabrica


def test_importar_procesar_exportar_y_subir_por_mcp(fab_mcp, clip, tmp_path):
    carpeta = tmp_path / "clips"
    carpeta.mkdir()
    shutil.copyfile(clip, carpeta / "uno.mp4")
    (carpeta / "notas.txt").write_text("no es video")
    r = _llamar("importar_carpeta", carpeta=str(carpeta), modo="clip", subir_a_youtube=False)
    assert [x["ok"] for x in r["resultados"]] == [True] and r["panel_activo"] is False
    jid = r["resultados"][0]["id"]
    assert _llamar("importar_archivos", rutas=[str(carpeta / "uno.mp4")])["resultados"][0]["tipo"] == "duplicado"
    assert _llamar("estado")["clips_por_estado"] == {"pendiente": 1}
    fab_mcp._ejecutar(fab_mcp.db.siguiente())                    # lo que haría el panel
    c = _llamar("ver_clip", id=jid)
    assert c["estado"] == "renderizado" and c["textos"]["titulo"].endswith("#Shorts")
    assert _llamar("editar_textos", id=jid, titulo="Un título nuevo")["ok"]
    assert fab_mcp.db.trabajo(jid)["textos"]["titulo"] == "Un título nuevo #Shorts"
    e = _llamar("exportar", id=jid, plataforma="tiktok")
    assert e["ok"] and os.path.exists(e["video"]) and "#Shorts" not in e["texto"]
    assert _llamar("exportar", id=jid, plataforma="myspace")["ok"] is False
    s = _llamar("subir_a_youtube", id=jid)
    assert s["ok"] is False and s["tipo"] == "configuracion"     # sin canal confirmado no se sube


def test_ajustes_por_mcp_validados_y_sin_acciones_sensibles(fab_mcp):
    assert _llamar("cambiar_ajustes", creador="Chetalonso", tema="gta6")["aplicados"] == {"creador": "Chetalonso", "tema": "gta6"}
    assert fab_mcp.db.perfil_activo()["nombre"] == "Chetalonso"        # nombre y tema son del perfil activo
    antes = fab_mcp.db.perfil_activo()
    assert _llamar("cambiar_ajustes", estilo="inventado", firma="@no_se_aplica")["ok"] is False
    assert fab_mcp.db.perfil_activo()["firma"] == antes["firma"]       # todo o nada
    nombres = {t.name for t in asyncio.run(m.servidor.list_tools())}
    for prohibida in ("youtube_canal", "eliminar", "secreto", "contrasena", "dispositivo"):
        assert not any(prohibida in n for n in nombres)


def test_perfiles_por_mcp(fab_mcp, clip):
    beto = fab_mcp.db.crear_perfil({"nombre": "Beto", "tema": "gta6"})
    r = _llamar("listar_perfiles")
    assert r["activo"] != beto["id"] and {p["nombre"] for p in r["perfiles"]} >= {"Beto"}
    assert _llamar("activar_perfil", perfil="beto")["activo"] == {"id": beto["id"], "nombre": "Beto"}   # por nombre
    assert _llamar("activar_perfil", perfil="nadie")["ok"] is False
    assert _llamar("estado")["perfil_activo"]["nombre"] == "Beto" and _llamar("estado")["tema"] == "gta6"
    jid = _llamar("importar_archivos", rutas=[str(clip)])["resultados"][0]["id"]
    assert fab_mcp.db.trabajo(jid)["datos"]["perfil"] == beto["id"]         # se importa con el activo
    assert next(p for p in _llamar("listar_perfiles")["perfiles"] if p["id"] == beto["id"])["clips"] == 1


def test_protocolo_mcp_real_por_stdio(tmp_path):
    """Arranca el servidor como lo haría Claude Code y llama herramientas por el protocolo MCP."""
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def probar():
        params = StdioServerParameters(command=sys.executable, args=["-m", "fabrica_studio.mcp_servidor"],
                                       env={**os.environ, "FABRICA_DATOS": str(tmp_path / "datos"), "FABRICA_PUERTO": "1"},
                                       cwd=os.path.dirname(os.path.dirname(__file__)))
        async with stdio_client(params) as (leer, escribir):
            async with ClientSession(leer, escribir) as sesion:
                await sesion.initialize()
                herramientas = (await sesion.list_tools()).tools
                r = await sesion.call_tool("estado", {})
                return [h.name for h in herramientas], r
    nombres, r = asyncio.run(probar())
    assert "importar_carpeta" in nombres and "exportar" in nombres
    datos = r.structured_content.get("result", r.structured_content) if r.structured_content else json.loads(r.content[0].text)
    assert datos["clips_por_estado"] == {} and datos["panel_activo"] is False
