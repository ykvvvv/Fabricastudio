# Fábrica Studio - arranca el servidor del panel.
# Uso (PowerShell, dentro de la carpeta del proyecto):   .\scripts\iniciar.ps1
# Deja esta ventana abierta mientras uses el panel. Para detener: Ctrl+C.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Falta la instalación. Ejecuta primero:  .\scripts\instalar.ps1" -ForegroundColor Yellow
    exit 1
}
& .\.venv\Scripts\python.exe -m fabrica_studio
