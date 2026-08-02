#requires -Version 5.1

param(
    [string]$FrontendUrl = "",
    [string]$BackendUrl = "",
    [int]$TimeoutSeconds = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$RootEnvPath = Join-Path $RepoRoot ".env"
$BackendEnvPath = Join-Path $RepoRoot "backend\.env"

function Get-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$DefaultValue
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $DefaultValue
    }

    $pattern = "^\s*" + [regex]::Escape($Key) + "\s*=\s*(.*)\s*$"
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line.TrimStart().StartsWith("#")) {
            continue
        }

        $match = [regex]::Match($line, $pattern)
        if ($match.Success) {
            $value = $match.Groups[1].Value.Trim()
            if (
                ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))
            ) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            return $value
        }
    }

    return $DefaultValue
}

function Get-EndpointStatus {
    param(
        [string]$Name,
        [string]$Url,
        [string]$ExpectedContentPattern = ""
    )

    $result = [ordered]@{
        Name = $Name
        Url = $Url
        Status = "failed"
        StatusCode = ""
        Detail = ""
    }

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $TimeoutSeconds
        $result.StatusCode = [string]$response.StatusCode
        if ([int]$response.StatusCode -lt 200 -or [int]$response.StatusCode -ge 500) {
            $result.Detail = "unexpected HTTP status"
            return [pscustomobject]$result
        }

        if (-not [string]::IsNullOrWhiteSpace($ExpectedContentPattern) -and "$($response.Content)" -notmatch $ExpectedContentPattern) {
            $result.Detail = "response did not match '$ExpectedContentPattern'"
            return [pscustomobject]$result
        }

        $result.Status = "ok"
        $result.Detail = "responding"
        return [pscustomobject]$result
    } catch {
        $result.Detail = $_.Exception.Message
        return [pscustomobject]$result
    }
}

if ([string]::IsNullOrWhiteSpace($BackendUrl)) {
    $backendPort = Get-EnvValue $BackendEnvPath "PORT" (Get-EnvValue $RootEnvPath "BACKEND_PORT" "8012")
    $BackendUrl = "http://127.0.0.1:$backendPort"
}

if ([string]::IsNullOrWhiteSpace($FrontendUrl)) {
    $frontendPort = Get-EnvValue $RootEnvPath "FRONTEND_PORT" "5177"
    $FrontendUrl = "http://127.0.0.1:$frontendPort"
}

$BackendUrl = $BackendUrl.TrimEnd("/")
$FrontendUrl = $FrontendUrl.TrimEnd("/")

$frontendProxyCheck = Get-EndpointStatus -Name "NewAPI web same-origin proxy" -Url "$FrontendUrl/api/status" -ExpectedContentPattern '"success":true'

$checks = @(
    (Get-EndpointStatus -Name "backend health" -Url "$BackendUrl/health/live" -ExpectedContentPattern "alive"),
    (Get-EndpointStatus -Name "NewAPI web shell" -Url $FrontendUrl),
    $frontendProxyCheck
)

$checks | Format-Table -AutoSize

$failed = @($checks | Where-Object { $_.Status -ne "ok" })
if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "Dev environment check failed." -ForegroundColor Red
    Write-Host "FrontendUrl: $FrontendUrl"
    Write-Host "BackendUrl:  $BackendUrl"
    Write-Host "Run .\start-dev.cmd to sync the backend env and restart TalkWise plus the NewAPI host."
    exit 1
}

Write-Host ""
Write-Host "Dev environment check passed." -ForegroundColor Green
