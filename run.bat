<# :
@echo off
setlocal
title DocClassifier Services (Backend + ARQ Worker + Frontend)
cd /d "%~dp0"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$rootDir = '%~dp0'; Invoke-Expression ([System.IO.File]::ReadAllText('%~f0'))"
exit /b %errorlevel%
#>

$ErrorActionPreference = "Continue"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " Starting DocClassifier Engine (Backend + ARQ Worker + Frontend)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Locate Python Virtual Environment
$pythonExe = $null
if (Test-Path "$($rootDir)venv\Scripts\python.exe") {
    $pythonExe = "$($rootDir)venv\Scripts\python.exe"
    Write-Host "[+] Using Python virtualenv at: venv\Scripts\python.exe" -ForegroundColor Green
} elseif (Test-Path "$($rootDir).venv\Scripts\python.exe") {
    $pythonExe = "$($rootDir).venv\Scripts\python.exe"
    Write-Host "[+] Using Python virtualenv at: .venv\Scripts\python.exe" -ForegroundColor Green
} else {
    $pythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        $pythonExe = $pythonCmd.Source
        Write-Host "[!] No local virtualenv found. Using system Python: $pythonExe" -ForegroundColor Yellow
    } else {
        Write-Host "[ERROR] Python was not found in venv, .venv, or system PATH." -ForegroundColor Red
        Write-Host "Please set up a Python virtual environment first."
        exit 1
    }
}

# 2. Check for npm
$npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCmd) {
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
}
if (-not $npmCmd) {
    Write-Host "[ERROR] 'npm' was not found in PATH." -ForegroundColor Red
    Write-Host "Please install Node.js (https://nodejs.org/) to run the frontend."
    exit 1
}

# 3. Ensure frontend dependencies are installed
$frontendDir = Join-Path $rootDir "frontend"
$frontendNodeModules = Join-Path $frontendDir "node_modules"
if (-not (Test-Path $frontendNodeModules)) {
    Write-Host "[+] Installing frontend dependencies (npm install)..." -ForegroundColor Yellow
    Start-Process -FilePath $npmCmd.Source -ArgumentList "install" -WorkingDirectory $frontendDir -Wait -NoNewWindow
}

Write-Host ""
Write-Host "[*] Initializing services..." -ForegroundColor Cyan

# 4. Start ARQ Distributed Worker
Write-Host "[1/3] Starting ARQ Distributed Worker (PaddleOCR + Classification)..." -ForegroundColor White
$arqProc = Start-Process -FilePath $pythonExe -ArgumentList "-m arq app.worker.WorkerSettings" -WorkingDirectory $rootDir -PassThru -NoNewWindow

# 5. Start FastAPI Backend Server
Write-Host "[2/3] Starting FastAPI Server on http://localhost:8000..." -ForegroundColor White
$apiProc = Start-Process -FilePath $pythonExe -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" -WorkingDirectory $rootDir -PassThru -NoNewWindow

# 6. Start Vite Frontend Dashboard
Write-Host "[3/3] Starting Vite Frontend on http://localhost:5173..." -ForegroundColor White
$frontendProc = Start-Process -FilePath $npmCmd.Source -ArgumentList "run dev" -WorkingDirectory $frontendDir -PassThru -NoNewWindow

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host "  DocClassifier Services Running Successfully!" -ForegroundColor Green
Write-Host "  - Enterprise UI:     http://localhost:5173" -ForegroundColor White
Write-Host "  - FastAPI API Root:  http://localhost:8000" -ForegroundColor White
Write-Host "  - Interactive Docs:  http://localhost:8000/docs" -ForegroundColor White
Write-Host "  - Health Check:      http://localhost:8000/health" -ForegroundColor White
Write-Host ""
Write-Host "  Press [Ctrl+C] or press 'q' to stop all services and close." -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Green

# 7. Supervision Loop and Cleanup Handler
try {
    while ($true) {
        # Check if user pressed 'q' or ESC
        try {
            if ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                if ($key.Key -eq [ConsoleKey]::Q -or $key.Key -eq [ConsoleKey]::Escape) {
                    Write-Host "`n[!] Stop signal received from keyboard..." -ForegroundColor Yellow
                    break
                }
            }
        } catch {}

        # Monitor process health
        if ($apiProc.HasExited) {
            Write-Host "`n[!] FastAPI server process stopped (exit code $($apiProc.ExitCode))." -ForegroundColor Yellow
            break
        }
        if ($arqProc.HasExited) {
            Write-Host "`n[!] ARQ worker process stopped (exit code $($arqProc.ExitCode))." -ForegroundColor Yellow
            break
        }
        if ($frontendProc.HasExited) {
            Write-Host "`n[!] Frontend dev server stopped (exit code $($frontendProc.ExitCode))." -ForegroundColor Yellow
            break
        }

        Start-Sleep -Milliseconds 500
    }
}
finally {
    Write-Host "`n[*] Terminating all DocClassifier services..." -ForegroundColor Yellow

    $procs = @($arqProc, $apiProc, $frontendProc)
    foreach ($p in $procs) {
        if ($p -and -not $p.HasExited) {
            cmd.exe /c "taskkill /F /T /PID $($p.Id) >nul 2>&1"
        }
    }

    # Ensure ports 8000 and 5173 are freed
    try {
        $ports = @(8000, 5173)
        foreach ($port in $ports) {
            $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
            if ($conns) {
                foreach ($conn in $conns) {
                    if ($conn.OwningProcess -gt 0) {
                        cmd.exe /c "taskkill /F /T /PID $($conn.OwningProcess) >nul 2>&1"
                    }
                }
            }
        }
    } catch {}

    Write-Host "[✓] All services stopped cleanly. Closing..." -ForegroundColor Green
    Start-Sleep -Milliseconds 800
}

exit 0
