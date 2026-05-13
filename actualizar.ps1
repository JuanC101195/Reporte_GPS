<#
.SYNOPSIS
  Regenera el dashboard de Reporte_GPS y lo publica en GitHub Pages.

.DESCRIPTION
  Si no le pasas el Excel, abre un cuadro para seleccionarlo. Detecta
  automaticamente la hoja con la estructura esperada y arma un label de
  periodo desde el rango de fechas. Genera el HTML con la API key de Maps
  embebida (desde la env var GOOGLE_MAPS_API_KEY del User scope) y publica
  a docs/index.html con commit + push + merge a main.

.EXAMPLE
  # Lo mas comun:
  .\actualizar.ps1

.EXAMPLE
  # Forzar Excel, hoja o periodo explicitos:
  .\actualizar.ps1 -Excel "C:\...\trabajadores.xlsx" -Hoja "Report" -Periodo "Semana 13-18 Abril 2026"

.EXAMPLE
  # Solo regenerar local sin tocar git ni miniaturas:
  .\actualizar.ps1 -SoloLocal
#>
[CmdletBinding()]
param(
    [string]$Excel,
    [string]$Periodo,
    [string]$Hoja,
    [switch]$SoloLocal
)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
$python = "C:\Users\LeNoVo\AppData\Local\Programs\Python\Python312\python.exe"

function Fail($msg) {
    Write-Host "[ERROR] $msg" -ForegroundColor Red
    exit 1
}

function Select-Excel($titulo) {
    Add-Type -AssemblyName System.Windows.Forms | Out-Null
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Title = $titulo
    $dlg.Filter = "Excel (*.xlsx;*.xls;*.xlsm)|*.xlsx;*.xls;*.xlsm|Todos|*.*"
    $dlg.InitialDirectory = Join-Path $env:USERPROFILE "Downloads"
    $dlg.Multiselect = $false
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        return $dlg.FileName
    }
    return $null
}

# 1. Pre-flight
if (-not (Test-Path $python)) { Fail "No encuentro Python 3.12 en $python" }
Set-Location $repo

if (-not $Excel) {
    Write-Host "Selecciona el Excel del GPS..." -ForegroundColor Cyan
    $Excel = Select-Excel "Excel GPS (ej. INFORME DE X-X MES.xlsx)"
    if (-not $Excel) { Fail "Cancelado: no se selecciono Excel" }
}
if (-not (Test-Path $Excel)) { Fail "No existe el Excel: $Excel" }

if (-not $SoloLocal) {
    $dirty = git status --porcelain
    if ($dirty) {
        Fail "Working tree no esta limpio. Commitea o stashea antes de seguir.`n$dirty"
    }
    $branchActual = git branch --show-current
    if ($branchActual -ne "main") {
        Fail "Estas en '$branchActual'. Cambiate a main antes: git checkout main"
    }
}

# 2. Inspeccionar Excel (detectar hoja + periodo)
$excelAbs = (Resolve-Path $Excel).Path
Write-Host ""
Write-Host "=== Inspeccionando el Excel ===" -ForegroundColor Cyan
$infoJson = & $python "inspect_excel.py" $excelAbs
if ($LASTEXITCODE -ne 0) { Fail "Error inspeccionando el Excel: $infoJson" }
try {
    $info = $infoJson | ConvertFrom-Json
} catch {
    Fail "No pude parsear la salida del inspector: $infoJson"
}
if ($info.error) { Fail "El Excel no tiene la estructura esperada: $($info.error)" }

if (-not $Hoja)    { $Hoja = $info.sheet }
if (-not $Periodo) { $Periodo = $info.periodo }

Write-Host ("  Archivo : {0}" -f $excelAbs)
Write-Host ("  Hoja    : {0}" -f $Hoja)
Write-Host ("  Periodo : {0}" -f $Periodo)
Write-Host ("  Filas   : {0} ({1} movimientos, {2} conductores)" -f $info.filas, $info.movimientos, $info.conductores)

# 3. SoloLocal: a reportes/ sin key
if ($SoloLocal) {
    Write-Host ""
    Write-Host "=== Generando local en reportes/ (sin miniaturas, file:// no las muestra) ===" -ForegroundColor Cyan
    & $python cli.py anomalias --input $excelAbs --sheet $Hoja --out-dir reportes --periodo $Periodo
    if ($LASTEXITCODE -ne 0) { Fail "El CLI fallo (exit $LASTEXITCODE)" }
    $local = Join-Path $repo "reportes\reporte_anomalias.html"
    Write-Host ""
    Write-Host "Reporte local: $local" -ForegroundColor Green
    Start-Process $local
    return
}

# 4. Confirmacion
Write-Host ""
$resp = Read-Host "Publicar a GitHub Pages (commit + push + merge a main)? [S/n]"
if ($resp -match '^[nN]') {
    Write-Host "Cancelado." -ForegroundColor Yellow
    return
}

# 5. Verificar API key (es lo que permite ver las miniaturas online)
$key = [System.Environment]::GetEnvironmentVariable('GOOGLE_MAPS_API_KEY','User')
if (-not $key) {
    Fail "GOOGLE_MAPS_API_KEY no esta seteada en User scope. Sin la key las miniaturas Maps no se embeben."
}

# 6. Crear rama (con sufijo HHmmss si la base ya existe)
$baseName = "docs/actualiza-$(Get-Date -Format 'yyyy-MM-dd')"
git show-ref --verify --quiet "refs/heads/$baseName"
if ($LASTEXITCODE -eq 0) {
    $branch = "$baseName-$(Get-Date -Format 'HHmmss')"
    Write-Host "Rama '$baseName' ya existe; usando '$branch'." -ForegroundColor Yellow
} else {
    $branch = $baseName
}

Write-Host ""
Write-Host "=== Publicando en rama $branch ===" -ForegroundColor Cyan
git checkout -b $branch
if ($LASTEXITCODE -ne 0) { Fail "No pude crear la rama $branch" }

# 7. Regenerar con key embebida a docs_tmp/
$env:GOOGLE_MAPS_API_KEY = $key
$env:PYTHONIOENCODING = "utf-8"

& $python cli.py anomalias --input $excelAbs --sheet $Hoja --out-dir docs_tmp --periodo $Periodo
if ($LASTEXITCODE -ne 0) { Fail "El CLI fallo (exit $LASTEXITCODE)" }

# 8. Sanity check: la key se embebio en el HTML?
$tmpHtml = Join-Path $repo "docs_tmp\reporte_anomalias.html"
$apariciones = ([regex]::Matches((Get-Content $tmpHtml -Raw), "key=AIza")).Count
if ($apariciones -lt 10) {
    Fail "El HTML salio con muy pocas referencias a la key Maps ($apariciones). Algo no cuadra."
}
Write-Host ("  Key embebida en {0} URLs Maps" -f $apariciones)

# 9. Mover a docs/index.html y limpiar tmp
Copy-Item $tmpHtml (Join-Path $repo "docs\index.html") -Force
Remove-Item (Join-Path $repo "docs_tmp") -Recurse -Force

# 10. Commit + push + merge a main + push main
$msgFile = Join-Path $repo ".commit_msg.tmp"
@"
docs(pages): actualiza dashboard con $Periodo

Procesado con $(Split-Path $excelAbs -Leaf) (hoja '$Hoja'):
  $($info.filas) filas, $($info.movimientos) movimientos, $($info.conductores) conductores.
"@ | Set-Content -Path $msgFile -Encoding utf8

git add docs/index.html
try {
    git commit -F $msgFile
    if ($LASTEXITCODE -ne 0) { Fail "git commit fallo" }
} finally {
    Remove-Item $msgFile -Force -ErrorAction SilentlyContinue
}

git push -u origin $branch
if ($LASTEXITCODE -ne 0) { Fail "git push de la rama fallo" }

git checkout main
git merge --no-ff $branch -m "Merge $branch"
if ($LASTEXITCODE -ne 0) { Fail "git merge a main fallo" }

git push origin main
if ($LASTEXITCODE -ne 0) { Fail "git push de main fallo" }

Write-Host ""
Write-Host "OK -> Publicado en https://juanc101195.github.io/Reporte_GPS/" -ForegroundColor Green
Write-Host "     (GitHub Pages tarda 1-2 min en propagar)" -ForegroundColor Green
