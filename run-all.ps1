#!/usr/bin/env pwsh
# Start both backend and frontend dev servers
# PowerShell version - simpler approach

$ErrorActionPreference = "Stop"

function PrintStatus {
    param([string]$Message)
    Write-Host "-> $Message" -ForegroundColor Cyan
}

function PrintError {
    param([string]$Message)
    Write-Host "X $Message" -ForegroundColor Red
}

function PrintSuccess {
    param([string]$Message)
    Write-Host "+ $Message" -ForegroundColor Green
}

$RepoRoot = Split-Path -Parent $PSCommandPath

Write-Host ""
Write-Host "Full Stack Launcher (PowerShell)" -ForegroundColor Magenta
Write-Host ""

# Check Python
PrintStatus "Checking Python..."
try {
    $pythonVersion = & python --version 2>&1
    PrintSuccess "$pythonVersion"
} catch {
    PrintError "Python not found"
    exit 1
}

# Check Node.js
PrintStatus "Checking Node.js..."
try {
    $nodeVersion = & node --version
    PrintSuccess "Node.js $nodeVersion"
} catch {
    PrintError "Node.js not found"
    exit 1
}

Write-Host ""
PrintStatus "Starting backend..."
Write-Host "The backend will run in this window." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop all services." -ForegroundColor Yellow
Write-Host ""

# Prepare backend startup script
$backendCmd = {
    param($RepoRoot)
    cd "$RepoRoot"

    if (-not (Test-Path ".venv")) {
        python -m venv .venv
    }

    Write-Host "Installing dependencies..." -ForegroundColor Cyan
    .\.venv\Scripts\python -m pip install -q -r backend/requirements.txt

    Write-Host "Starting Backend API..." -ForegroundColor Green
    Write-Host "API Docs: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
    Write-Host ""

    .\.venv\Scripts\python -m uvicorn backend.api.main:app --reload --host 127.0.0.1 --port 8000
}

# Start backend in background
$backend = Start-Job -ScriptBlock $backendCmd -ArgumentList $RepoRoot

Write-Host "Waiting for backend to be ready..."
Start-Sleep -Seconds 15

# Check if backend is running
$backendJob = Get-Job -Id $backend.Id
if ($backendJob.State -eq "Failed") {
    PrintError "Backend failed to start"
    Receive-Job -Id $backend.Id
    exit 1
}

PrintSuccess "Backend started! (Process ID: $($backend.Id))"
Write-Host ""

# Wait for port 8000 to be open
PrintStatus "Waiting for backend to listen on port 8000..."
$maxWait = 30
$waited = 0
while ($waited -lt $maxWait) {
    try {
        $connection = New-Object System.Net.Sockets.TcpClient("127.0.0.1", 8000)
        $connection.Close()
        PrintSuccess "Backend is listening!"
        break
    } catch {
        Write-Host -NoNewline "."
        Start-Sleep -Seconds 1
        $waited++
    }
}

Write-Host ""
Write-Host ""
PrintStatus "Starting frontend..."

# Start frontend
$frontendDir = Join-Path $RepoRoot "frontend"
cd $frontendDir

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env" -ErrorAction SilentlyContinue
}

Write-Host "Starting Frontend Dev Server..." -ForegroundColor Green
Write-Host "Open: http://127.0.0.1:5173" -ForegroundColor Cyan
Write-Host ""

& npm run dev

# Cleanup
Write-Host ""
Write-Host "Stopping backend..." -ForegroundColor Cyan
Stop-Job -Id $backend.Id -ErrorAction SilentlyContinue
Remove-Job -Id $backend.Id -ErrorAction SilentlyContinue
