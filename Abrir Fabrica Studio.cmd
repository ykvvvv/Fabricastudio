@echo off
rem Fabrica Studio - doble clic para abrir el panel. Deja esta ventana abierta; para cerrar: Ctrl+C.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\iniciar.ps1"
if errorlevel 1 pause
