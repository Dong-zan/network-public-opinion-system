[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot

function Get-RequiredCommandPath {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required command '$Name' was not found. Install it before starting the system."
    }
    return $command.Source
}

function Resolve-ServicePython {
    param([Parameter(Mandatory = $true)][string]$ServiceDirectory)

    $candidates = @(
        (Join-Path $ServiceDirectory ".venv\Scripts\python.exe"),
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return Get-RequiredCommandPath -Name "python"
}

function Start-ServiceWindow {
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

function Wait-LocalPort {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 45
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $client = [Net.Sockets.TcpClient]::new()
        try {
            $connection = $client.ConnectAsync("127.0.0.1", $Port)
            if ($connection.Wait(500) -and $client.Connected) {
                Write-Host "Port $Port is ready."
                return
            }
        } catch {
            # The service may still be starting.
        } finally {
            $client.Dispose()
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Service on port $Port did not become ready within $TimeoutSeconds seconds. Check its PowerShell window."
}

$nodePath = Get-RequiredCommandPath -Name "node"
$packageManagerCommand = Get-Command "pnpm" -ErrorAction SilentlyContinue
if (-not $packageManagerCommand) {
    $packageManagerCommand = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
}
if (-not $packageManagerCommand) {
    throw "Neither pnpm nor npm was found. Install a frontend package manager first."
}

$aiDirectory = Join-Path $ProjectRoot "ai_service"
$analysisDirectory = Join-Path $ProjectRoot "analysis"
$backendDirectory = Join-Path $ProjectRoot "backend"
$frontendDirectory = Join-Path $ProjectRoot "frontend"

$aiPython = Resolve-ServicePython -ServiceDirectory $aiDirectory
$nlpPython = Resolve-ServicePython -ServiceDirectory $analysisDirectory
$backendPython = Resolve-ServicePython -ServiceDirectory $backendDirectory

Write-Host "Python and Node.js environment check passed."
Write-Host "Node.js: $nodePath"
Write-Host "Frontend package manager: $($packageManagerCommand.Source)"
Write-Warning "This script does not start MySQL. Confirm MySQL is ready before continuing."

foreach ($environmentFile in @(
    (Join-Path $aiDirectory ".env"),
    (Join-Path $backendDirectory ".env")
)) {
    if (-not (Test-Path -LiteralPath $environmentFile)) {
        Write-Warning "Missing local configuration: $environmentFile"
    }
}

$escapedAiPython = $aiPython.Replace("'", "''")
Start-ServiceWindow `
    -Title "Public Opinion - AI Service (8005)" `
    -WorkingDirectory $aiDirectory `
    -Command "& '$escapedAiPython' -m uvicorn app.main:app --host 127.0.0.1 --port 8005"
Wait-LocalPort -Port 8005

$escapedNlpPython = $nlpPython.Replace("'", "''")
Start-ServiceWindow `
    -Title "Public Opinion - NLP Service (9000)" `
    -WorkingDirectory $ProjectRoot `
    -Command "& '$escapedNlpPython' -m analysis.nlp_api_server --host 127.0.0.1 --port 9000"
Wait-LocalPort -Port 9000

$escapedBackendPython = $backendPython.Replace("'", "''")
Start-ServiceWindow `
    -Title "Public Opinion - Backend (8000)" `
    -WorkingDirectory $backendDirectory `
    -Command "& '$escapedBackendPython' -m uvicorn backend_app.main:app --host 127.0.0.1 --port 8000 --reload"
Wait-LocalPort -Port 8000

$packageManagerPath = $packageManagerCommand.Source.Replace("'", "''")
Start-ServiceWindow `
    -Title "Public Opinion - Frontend (5173)" `
    -WorkingDirectory $frontendDirectory `
    -Command "& '$packageManagerPath' run dev"

Write-Host "AI, NLP, backend, and frontend service windows have been opened."
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "The crawler was not started. Run 'python -m crawler.run' separately when needed."
