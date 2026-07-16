[CmdletBinding()]
param(
    [ValidateSet("Menu", "All", "Crawler", "Guide")]
    [string]$Mode = "Menu"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot

function Test-RequiredCommand {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found. Install project dependencies first; this script does not install them."
    }
}

function Start-ProjectWindow {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Command
    )

    $escapedDirectory = $WorkingDirectory.Replace("'", "''")
    $escapedTitle = $Title.Replace("'", "''")
    $windowCommand = "Set-Location -LiteralPath '$escapedDirectory'; `$Host.UI.RawUI.WindowTitle = '$escapedTitle'; $Command"
    $encodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($windowCommand))

    Write-Host "Starting $Title ..."
    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoExit",
        "-EncodedCommand",
        $encodedCommand
    ) | Out-Null
}

function Show-StartupGuide {
    Write-Host ""
    Write-Host "Network Public Opinion System - startup order"
    Write-Host "1. Start MySQL manually and ensure the backend database exists."
    Write-Host "2. Start AI service:  http://127.0.0.1:8005"
    Write-Host "3. Start NLP service: http://127.0.0.1:9000"
    Write-Host "4. Start backend:     http://127.0.0.1:8000"
    Write-Host "5. Start frontend:    http://localhost:5173"
    Write-Host "6. Run crawler only when data collection is required."
    Write-Host ""
    Write-Host "This script does not start MySQL, install dependencies, or modify environment variables."
    Write-Host "Backend configuration is read from backend/.env. AI configuration is read from ai_service/.env when present."
    Write-Host ""
}

function Start-AllServices {
    Test-RequiredCommand -Name "python"
    Test-RequiredCommand -Name "pnpm"

    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "backend\.env"))) {
        Write-Warning "backend/.env was not found. Create it from backend/.env.example before using the backend."
    }

    Show-StartupGuide
    Write-Warning "MySQL is not started by this script. Confirm that MySQL is ready before using the backend."

    Start-ProjectWindow `
        -Title "Public Opinion - AI Service (8005)" `
        -WorkingDirectory (Join-Path $ProjectRoot "ai_service") `
        -Command "python -m uvicorn app.main:app --host 127.0.0.1 --port 8005"

    Start-ProjectWindow `
        -Title "Public Opinion - NLP Service (9000)" `
        -WorkingDirectory $ProjectRoot `
        -Command "python -m analysis.nlp_api_server --host 127.0.0.1 --port 9000"

    Start-ProjectWindow `
        -Title "Public Opinion - Backend (8000)" `
        -WorkingDirectory (Join-Path $ProjectRoot "backend") `
        -Command "python -m uvicorn backend_app.main:app --host 127.0.0.1 --port 8000 --reload"

    Start-ProjectWindow `
        -Title "Public Opinion - Frontend (5173)" `
        -WorkingDirectory (Join-Path $ProjectRoot "frontend") `
        -Command "pnpm run dev"

    Write-Host "Application service windows were opened. Run the crawler separately after the backend is ready."
}

function Start-CrawlerOnce {
    Test-RequiredCommand -Name "python"

    Start-ProjectWindow `
        -Title "Public Opinion - Crawler" `
        -WorkingDirectory $ProjectRoot `
        -Command "python -m crawler.run"
}

function Show-Menu {
    while ($true) {
        Show-StartupGuide
        Write-Host "[1] Start AI, NLP, backend, and frontend"
        Write-Host "[2] Run crawler once"
        Write-Host "[3] Show startup guide"
        Write-Host "[Q] Quit"
        $selection = (Read-Host "Select an option").Trim().ToUpperInvariant()

        switch ($selection) {
            "1" { Start-AllServices; return }
            "2" { Start-CrawlerOnce; return }
            "3" { Show-StartupGuide }
            "Q" { return }
            default { Write-Warning "Unknown option: $selection" }
        }
    }
}

switch ($Mode) {
    "All" { Start-AllServices }
    "Crawler" { Start-CrawlerOnce }
    "Guide" { Show-StartupGuide }
    default { Show-Menu }
}
