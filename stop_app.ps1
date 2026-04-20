$ErrorActionPreference = "SilentlyContinue"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$PidFile = Join-Path $ProjectRoot "logs\app.pid"
$Port = 5000
$stopped = $false

if (Test-Path $PidFile) {
    $pidValue = Get-Content $PidFile | Select-Object -First 1
    if ($pidValue) {
        Stop-Process -Id ([int]$pidValue) -Force
        $stopped = $true
    }
    Remove-Item $PidFile -Force
}

$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    Stop-Process -Id $conn.OwningProcess -Force
    $stopped = $true
}

if ($stopped) {
    Write-Host "Application stopped."
} else {
    Write-Host "No running application found."
}
