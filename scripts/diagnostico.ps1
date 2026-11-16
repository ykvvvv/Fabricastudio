# Fábrica Studio - comprueba qué funciona en este PC.
# Uso (PowerShell, dentro de la carpeta del proyecto):   .\scripts\diagnostico.ps1
# Copia la salida completa y pégala en el chat si algo falla.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Falta la instalación. Ejecuta primero:  .\scripts\instalar.ps1" -ForegroundColor Yellow
    exit 1
}
& .\.venv\Scripts\python.exe -m fabrica_studio.diagnostico
exit $LASTEXITCODE
