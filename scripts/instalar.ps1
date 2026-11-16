# Fábrica Studio - instalación en Windows 11.
# Uso (PowerShell, dentro de la carpeta del proyecto):   .\scripts\instalar.ps1
# No modifica configuraciones globales: todo queda en la carpeta .venv del proyecto.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Buscar-Python {
    foreach ($c in @(@("py", "-3"), @("python"))) {
        try {
            $v = & $c[0] $c[1..($c.Length)] -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and [version]$v -ge [version]"3.10") { return ,$c }
        } catch {}
    }
    return $null
}

$py = Buscar-Python
if (-not $py) {
    Write-Host "No se encontró Python 3.10 o superior." -ForegroundColor Yellow
    Write-Host "Instálalo con:  winget install Python.Python.3.12"
    Write-Host "Después cierra y vuelve a abrir PowerShell, y ejecuta este script otra vez."
    exit 1
}
Write-Host "Python encontrado." -ForegroundColor Green

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    Write-Host "No se encontró FFmpeg." -ForegroundColor Yellow
    Write-Host "Instálalo con:  winget install Gyan.FFmpeg"
    Write-Host "Después cierra y vuelve a abrir PowerShell, y ejecuta este script otra vez."
    exit 1
}
Write-Host "FFmpeg encontrado." -ForegroundColor Green

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creando el entorno virtual (.venv)..."
    & $py[0] $py[1..($py.Length)] -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno virtual." }
}
Write-Host "Instalando dependencias (puede tardar unos minutos)..."
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Falló la instalación de dependencias. Revisa el mensaje anterior." }

Write-Host ""
Write-Host "Instalación terminada. Para abrir el panel ejecuta:  .\scripts\iniciar.ps1" -ForegroundColor Green
