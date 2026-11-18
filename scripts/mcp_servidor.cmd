@echo off
rem Fabrica Studio - servidor MCP para Claude Code (lo abre Claude Code, no hace falta ejecutarlo a mano).
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m fabrica_studio.mcp_servidor
