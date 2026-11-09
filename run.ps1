# Levanta todo el entorno en Windows con un solo comando:  .\run.ps1
# (equivalente a run.sh para quien no tiene Git Bash). Si PowerShell bloquea el script:
#   powershell -ExecutionPolicy Bypass -File .\run.ps1
#
# Crea .env desde .env.example si falta, avisa si no hay llaves de IA (la app funciona igual
# con la explicación de plantilla), construye y levanta los contenedores, espera a que
# /api/salud responda y muestra las credenciales del primer arranque.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$Url = "http://localhost:8000"
$EsperaMaximaS = 180

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "No se encontró Docker. Instale Docker Desktop y vuelva a correr .\run.ps1." -ForegroundColor Red
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker está instalado pero no responde. Abra Docker Desktop, espere a que arranque y vuelva a intentar." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Se creó .env a partir de .env.example."
}

function Valor-Env([string]$Nombre) {
    $linea = Get-Content .env | Where-Object { $_ -match "^$Nombre=" } | Select-Object -Last 1
    if ($null -eq $linea) { return "" }
    return ($linea -replace "^$Nombre=", "").Trim().Trim('"').Trim("'")
}

$Gemini = Valor-Env "GEMINI_API_KEY"
$Claude = Valor-Env "ANTHROPIC_API_KEY"
if (-not $Gemini -and -not $Claude) {
    Write-Host "AVISO: .env no tiene GEMINI_API_KEY ni ANTHROPIC_API_KEY." -ForegroundColor Yellow
    Write-Host "       La app arranca igual: la regla bloquea los casos críticos y las explicaciones salen de la plantilla."
} elseif (-not $Claude) {
    Write-Host "AVISO: falta ANTHROPIC_API_KEY en .env; se usará solo Gemini (el respaldo)." -ForegroundColor Yellow
} elseif (-not $Gemini) {
    Write-Host "AVISO: falta GEMINI_API_KEY en .env; no habrá proveedor de respaldo si Claude falla." -ForegroundColor Yellow
}

Write-Host "Construyendo y levantando los contenedores (la primera vez tarda unos minutos)..."
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host -NoNewline "Esperando a que la app responda en $Url/api/salud "
$inicio = Get-Date
while ($true) {
    try {
        Invoke-WebRequest -Uri "$Url/api/salud" -UseBasicParsing -TimeoutSec 3 | Out-Null
        Write-Host " lista."
        break
    } catch {
        if (((Get-Date) - $inicio).TotalSeconds -gt $EsperaMaximaS) {
            Write-Host ""
            Write-Host "La app no respondió en $EsperaMaximaS s. Últimas líneas del log:" -ForegroundColor Red
            docker compose logs --tail=40 app
            exit 1
        }
        Write-Host -NoNewline "."
        Start-Sleep -Seconds 2
    }
}

Write-Host ""
Write-Host "Vista del analista: $Url" -ForegroundColor Green
$log = docker compose logs app 2>$null
$i = [array]::FindIndex([string[]]$log, [Predicate[string]]{ param($l) $l -match "CREDENCIALES DE LA APP" })
if ($i -ge 0) {
    Write-Host "Usuarios de la app (guárdelos; para restablecerlos: docker compose exec app python -m app.db.migrar --restablecer-claves):"
    $log[($i + 1)..($i + 2)] | ForEach-Object { Write-Host (($_ -split "\|", 2)[-1]).Trim() }
}
Write-Host "Para detener:        docker compose down"
