#requires -Version 5.1

[CmdletBinding()]
param(
    [ValidateSet("voice", "frontend", "backend", "agent-sdk", "all")]
    [string]$Slice = "voice",
    [switch]$Full,
    [switch]$WithLint
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$FrontendDir = Join-Path $RepoRoot "frontend"
$BackendDir = Join-Path $RepoRoot "backend"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-External {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string]$FilePath,
        [string[]]$Arguments
    )

    Write-Step $Name
    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $FilePath @Arguments
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode."
    }
}

function Get-BackendPython {
    $candidates = @(
        (Join-Path $RepoRoot ".venv-backend\Scripts\python.exe"),
        (Join-Path $BackendDir ".venv\Scripts\python.exe"),
        "python"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -eq "python") {
            if (Get-Command "python" -ErrorAction SilentlyContinue) {
                return "python"
            }
        } elseif (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw "Python was not found. Create .venv-backend or make python available on PATH."
}

function Invoke-Npm {
    param(
        [string]$Name,
        [string[]]$NpmArgs
    )

    Invoke-External -Name $Name -WorkingDirectory $FrontendDir -FilePath "npm" -Arguments $NpmArgs
}

function Invoke-Pytest {
    param(
        [string]$Name,
        [string[]]$PytestArgs
    )

    $python = Get-BackendPython
    $hadSecret = $null -ne [Environment]::GetEnvironmentVariable("SECRET_KEY", "Process")
    $oldSecret = [Environment]::GetEnvironmentVariable("SECRET_KEY", "Process")

    if (-not $hadSecret) {
        [Environment]::SetEnvironmentVariable("SECRET_KEY", "test-secret-key", "Process")
    }

    try {
        $arguments = @("-m", "pytest") + $PytestArgs
        Invoke-External -Name $Name -WorkingDirectory $BackendDir -FilePath $python -Arguments $arguments
    } finally {
        if ($hadSecret) {
            [Environment]::SetEnvironmentVariable("SECRET_KEY", $oldSecret, "Process")
        } else {
            [Environment]::SetEnvironmentVariable("SECRET_KEY", $null, "Process")
        }
    }
}

function Invoke-FrontendCore {
    Invoke-Npm -Name "frontend training-mode tests" -NpmArgs @("run", "test:training-mode")

    if ($WithLint) {
        Invoke-Npm -Name "frontend lint" -NpmArgs @("run", "lint")
    }

    if ($Full) {
        Invoke-Npm -Name "frontend build" -NpmArgs @("run", "build")
    }
}

function Invoke-BackendVoiceCore {
    Invoke-Pytest -Name "backend voice chat tests" -PytestArgs @(
        "tests/test_voice_websocket.py",
        "tests/test_message_api.py"
    )
}

function Invoke-BackendAll {
    Invoke-Pytest -Name "backend pytest" -PytestArgs @()
}

function Invoke-AgentSdkCore {
    Invoke-Pytest -Name "backend agent-sdk tests" -PytestArgs @(
        "tests/infrastructure/external/agent_sdk/"
    )
}

switch ($Slice) {
    "voice" {
        Invoke-FrontendCore
        Invoke-BackendVoiceCore
    }
    "frontend" {
        Invoke-FrontendCore
    }
    "backend" {
        Invoke-BackendAll
    }
    "agent-sdk" {
        Invoke-AgentSdkCore
    }
    "all" {
        Invoke-FrontendCore
        Invoke-BackendVoiceCore
        Invoke-AgentSdkCore

        if ($Full) {
            Invoke-BackendAll
        }
    }
}

Write-Host ""
Write-Host "Core loop passed for slice: $Slice" -ForegroundColor Green
