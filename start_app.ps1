$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PidFile = Join-Path $ProjectRoot "logs\app.pid"
$OutLog = Join-Path $ProjectRoot "logs\flask.out.log"
$ErrLog = Join-Path $ProjectRoot "logs\flask.err.log"
$Port = 5000

if (-not (Test-Path ".env")) {
    throw "Missing .env file. Create it from .env.example first."
}

if (-not (Test-Path $PythonExe)) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

New-Item -ItemType Directory -Force -Path "logs" | Out-Null

& $PythonExe -m pip install -r requirements.txt | Out-Null

$existingConn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existingConn) {
    $existingPid = $existingConn.OwningProcess
    try {
        $existingProc = Get-Process -Id $existingPid -ErrorAction Stop
        if ($existingProc.Path -like "*\.venv\Scripts\python.exe" -or $existingProc.ProcessName -like "python*") {
            Write-Host "Stopping existing app process on port $Port (PID $existingPid)..."
            Stop-Process -Id $existingPid -Force
            Start-Sleep -Seconds 2
        }
    } catch {
    }
}

$process = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList "app.py" `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Set-Content -Path $PidFile -Value $process.Id

$healthy = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 5
        if ($response.ok -ne $null) {
            $healthy = $true
            break
        }
    } catch {
    }
}

if (-not $healthy) {
    Write-Host "Application did not become ready. Check logs\flask.err.log"
    exit 1
}

Write-Host "Application started successfully."
Write-Host "URL: http://localhost:$Port/"
Write-Host "PID: $($process.Id)"

Start-Process "http://localhost:$Port/" | Out-Null
