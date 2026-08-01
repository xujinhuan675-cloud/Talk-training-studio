#requires -Version 5.1

param(
    [switch]$SkipInstall,
    [switch]$UseSqlite,
    [switch]$UsePostgres,
    [switch]$NoSqliteFallback,
    [switch]$ShowServiceWindows,
    [switch]$NoBrowser,
    [switch]$SkipHealthCheck,
    [switch]$SkipGateway,
    [switch]$LegacyViteFrontend,
    [switch]$AutoPort,
    [int]$GatewayPort = 0,
    [int]$BackendPort = 0,
    [int]$FrontendPort = 0,
    [int]$DockerTimeoutSeconds = 180,
    [int]$PostgresTimeoutSeconds = 120,
    [int]$ServiceTimeoutSeconds = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($UseSqlite -and $UsePostgres) {
    throw "Use either -UseSqlite or -UsePostgres, not both."
}

$RepoRoot = $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

$UserPythonScripts = Join-Path $env:APPDATA "Python\Scripts"
$CandidatePathAdds = @($UserPythonScripts)
if (Test-Path -LiteralPath (Join-Path $env:APPDATA "Python")) {
    $CandidatePathAdds += Get-ChildItem -LiteralPath (Join-Path $env:APPDATA "Python") -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "Scripts" }
}

foreach ($pathToAdd in $CandidatePathAdds) {
    if (Test-Path -LiteralPath $pathToAdd) {
        $pathParts = $env:Path -split ";"
        if ($pathParts -notcontains $pathToAdd) {
            $env:Path = "$pathToAdd;$env:Path"
        }
    }
}

$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$NewApiDir = Join-Path $RepoRoot "outside-project\new-api-main"
$NewApiWebDir = Join-Path $NewApiDir "web"
$NewApiExePath = Join-Path $NewApiDir "new-api-talkwise.exe"
$NewApiDbPath = Join-Path $NewApiDir "one-api.db"
$LogDir = Join-Path $RepoRoot "logs"
$BackendVenvDir = Join-Path $RepoRoot ".venv-backend"
$RootEnvPath = Join-Path $RepoRoot ".env"
$BackendEnvPath = Join-Path $BackendDir ".env"
$FrontendEnvPath = Join-Path $FrontendDir ".env"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "OK  $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "WARN $Message" -ForegroundColor Yellow
}

function Test-CommandExists {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

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
    foreach ($line in Get-Content -LiteralPath $Path) {
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

function Ensure-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )

    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType File -Path $Path -Force | Out-Null
    }

    $pattern = "^\s*" + [regex]::Escape($Key) + "\s*="
    $exists = Select-String -LiteralPath $Path -Pattern $pattern -Quiet
    if (-not $exists) {
        Add-Content -LiteralPath $Path -Value "$Key=$Value"
        Write-Ok "Added $Key to $Path"
    }
}

function Set-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )

    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType File -Path $Path -Force | Out-Null
    }

    $pattern = "^\s*" + [regex]::Escape($Key) + "\s*="
    $lines = @(Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue)
    $updated = $false
    $newLines = foreach ($line in $lines) {
        if (-not $updated -and $line -match $pattern) {
            $updated = $true
            "$Key=$Value"
        } else {
            $line
        }
    }

    if (-not $updated) {
        $newLines += "$Key=$Value"
    }

    Set-Content -LiteralPath $Path -Value $newLines
}

function Join-OptionalPath {
    param(
        [AllowNull()][string]$BasePath,
        [string]$ChildPath
    )

    if ([string]::IsNullOrWhiteSpace($BasePath)) {
        return $null
    }

    return Join-Path $BasePath $ChildPath
}

function Test-DockerEngine {
    if (-not (Test-CommandExists "docker")) {
        return $false
    }

    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker info 1>$null 2>$null
        return $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }
}

function Start-DockerDesktopIfNeeded {
    if (Test-DockerEngine) {
        Write-Ok "Docker engine is running."
        return
    }

    if (-not (Test-CommandExists "docker")) {
        throw "Docker CLI was not found. Install Docker Desktop first."
    }

    $candidatePaths = @(
        (Join-OptionalPath $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-OptionalPath ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe"),
        (Join-OptionalPath $env:LocalAppData "Docker\Docker Desktop.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    $dockerDesktopPath = $candidatePaths | Select-Object -First 1
    if (-not $dockerDesktopPath) {
        throw "Docker Desktop is not running, and Docker Desktop.exe was not found in common install paths."
    }

    $desktopProcess = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -eq "Docker Desktop" } |
        Select-Object -First 1

    if (-not $desktopProcess) {
        Write-Step "Starting Docker Desktop"
        Start-Process -FilePath $dockerDesktopPath -WindowStyle Hidden
    } else {
        Write-Step "Waiting for Docker Desktop"
    }

    $deadline = (Get-Date).AddSeconds($DockerTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerEngine) {
            Write-Host ""
            Write-Ok "Docker engine is ready."
            return
        }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 2
    }

    Write-Host ""
    throw "Docker Desktop started, but Docker engine was not ready after $DockerTimeoutSeconds seconds."
}

function Invoke-DockerCompose {
    param([string[]]$Arguments)

    Push-Location -LiteralPath $RepoRoot
    try {
        $oldErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & docker compose @Arguments 2>&1 | ForEach-Object { Write-Host $_ }
            $exitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $oldErrorActionPreference
        }

        if ($exitCode -ne 0) {
            throw "docker compose $($Arguments -join ' ') failed."
        }
    } finally {
        Pop-Location
    }
}

function Stop-DockerAppServices {
    Push-Location -LiteralPath $RepoRoot
    try {
        $oldErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $runningServices = @(& docker compose ps --services --status running 2>$null)
            $exitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $oldErrorActionPreference
        }

        if ($exitCode -ne 0) {
            throw "docker compose ps --services --status running failed."
        }

        $dockerAppServices = @($runningServices | Where-Object { $_ -in @("app", "grpc") })
        if ($dockerAppServices.Count -gt 0) {
            Write-Step "Stopping Docker app/grpc services"
            Invoke-DockerCompose @("stop", "app", "grpc")
        }
    } finally {
        Pop-Location
    }
}

function Stop-DockerNewApiServicesIfRunning {
    if (-not (Test-CommandExists "docker")) {
        return
    }

    if (-not (Test-DockerEngine)) {
        return
    }

    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $containerIds = @(& docker ps -q --filter "name=talkwise_newapi" 2>$null)
    } finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }

    $containerIds = @($containerIds | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($containerIds.Count -eq 0) {
        return
    }

    Write-Step "Stopping Docker NewAPI services"
    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker stop @containerIds 2>&1 | ForEach-Object { Write-Host $_ }
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }

    if ($exitCode -ne 0) {
        Write-Warn "Could not stop all Docker NewAPI containers; continuing with local gateway startup."
    }
}

function Wait-PostgresHealthy {
    param([int]$HostPort)

    Write-Step "Waiting for Postgres"
    $attempt = 1
    $maxAttempts = 2

    while ($attempt -le $maxAttempts) {
        $deadline = (Get-Date).AddSeconds($PostgresTimeoutSeconds)
        $unreachableDeadline = $null

        while ((Get-Date) -lt $deadline) {
            Push-Location -LiteralPath $RepoRoot
            try {
                $oldErrorActionPreference = $ErrorActionPreference
                $ErrorActionPreference = "Continue"
                try {
                    $containerId = ((& docker compose ps -q postgres 2>$null) | Select-Object -First 1)
                } finally {
                    $ErrorActionPreference = $oldErrorActionPreference
                }

                $containerId = "$containerId".Trim()
                if ($containerId) {
                    $oldErrorActionPreference = $ErrorActionPreference
                    $ErrorActionPreference = "Continue"
                    try {
                        $health = ((& docker inspect --format '{{.State.Health.Status}}' $containerId 2>$null) | Select-Object -First 1)
                    } finally {
                        $ErrorActionPreference = $oldErrorActionPreference
                    }

                    $health = "$health".Trim()
                    if ($health -eq "healthy") {
                        $publishedPort = $null
                        $oldErrorActionPreference = $ErrorActionPreference
                        $ErrorActionPreference = "Continue"
                        try {
                            $publishedPort = ((& docker compose port postgres 5432 2>$null) | Select-Object -First 1)
                        } finally {
                            $ErrorActionPreference = $oldErrorActionPreference
                        }

                        $publishedPort = "$publishedPort".Trim()
                        if ($publishedPort -match ":(\d+)$" -and [int]$Matches[1] -eq $HostPort) {
                            if (Test-TcpPort -HostName "127.0.0.1" -Port $HostPort) {
                                Write-Ok "Postgres is healthy and reachable on localhost:$HostPort."
                                return
                            }

                            if (-not $unreachableDeadline) {
                                $unreachableDeadline = (Get-Date).AddSeconds(10)
                            } elseif ((Get-Date) -ge $unreachableDeadline) {
                                break
                            }
                        } else {
                            $unreachableDeadline = $null
                        }
                    } else {
                        $unreachableDeadline = $null
                    }
                }
            } finally {
                Pop-Location
            }

            Write-Host "." -NoNewline
            Start-Sleep -Seconds 2
        }

        if ($unreachableDeadline -and (Get-Date) -ge $unreachableDeadline -and $attempt -lt $maxAttempts) {
            Write-Host ""
            Write-Warn "Postgres container is healthy, but Windows cannot connect to localhost:$HostPort. Recreating only the postgres container."
            Invoke-DockerCompose @("up", "-d", "--force-recreate", "postgres")
            $attempt++
            continue
        }

        break
    }

    Write-Host ""
    throw "Postgres is healthy in Docker, but Windows cannot connect to localhost:$HostPort. Docker Desktop port publishing may be stuck; restart Docker Desktop or run 'wsl --shutdown', then rerun start-dev.cmd."
}

function Test-PortListening {
    param([int]$Port)

    try {
        $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return $null -ne $listeners
    } catch {
        return $false
    }
}

function Test-PortBindable {
    param([int]$Port)

    $listener = $null
    try {
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Parse("127.0.0.1"), $Port)
        $listener.Server.ExclusiveAddressUse = $true
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) {
            $listener.Stop()
        }
    }
}

function Get-PortBindFailureSummary {
    param([int]$Port)

    $listener = $null
    try {
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Parse("127.0.0.1"), $Port)
        $listener.Server.ExclusiveAddressUse = $true
        $listener.Start()
        return ""
    } catch {
        $exception = $_.Exception
        while ($exception.InnerException) {
            $exception = $exception.InnerException
        }
        return $exception.Message
    } finally {
        if ($listener) {
            $listener.Stop()
        }
    }
}

function Get-PortListenerOwnerIds {
    param([int]$Port)

    try {
        $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } catch {
        return @()
    }

    return @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Test-PortHasOnlyStaleOwners {
    param([int]$Port)

    $ownerIds = @(Get-PortListenerOwnerIds -Port $Port)
    if ($ownerIds.Count -eq 0) {
        return $false
    }

    foreach ($ownerId in $ownerIds) {
        if (Get-Process -Id $ownerId -ErrorAction SilentlyContinue) {
            return $false
        }
    }

    return $true
}

function Get-PortOwnerSummary {
    param([int]$Port)

    try {
        $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } catch {
        return "unknown process"
    }

    if ($listeners.Count -eq 0) {
        return "no listener"
    }

    $ownerIds = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    $summaries = foreach ($ownerId in $ownerIds) {
        $process = Get-Process -Id $ownerId -ErrorAction SilentlyContinue
        if ($process) {
            "$($process.ProcessName) pid=$ownerId"
        } else {
            "stale pid=$ownerId (process not found)"
        }
    }

    return ($summaries -join ", ")
}

function Get-ConfiguredPort {
    param(
        [string]$Key,
        [int]$DefaultValue,
        [int]$OverrideValue
    )

    if ($OverrideValue -gt 0) {
        return $OverrideValue
    }

    $rawValue = Get-EnvValue $RootEnvPath $Key "$DefaultValue"
    [int]$port = 0
    if (-not [int]::TryParse($rawValue, [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
        throw "$Key must be an integer TCP port between 1 and 65535, got '$rawValue'."
    }

    return $port
}

function Resolve-DevPort {
    param(
        [string]$Name,
        [int]$Port,
        [switch]$AllowAutoPort
    )

    if (Test-PortBindable $Port) {
        return $Port
    }

    $ownerSummary = Get-PortOwnerSummary $Port
    $bindFailure = Get-PortBindFailureSummary $Port
    if ([string]::IsNullOrWhiteSpace($bindFailure)) {
        $bindFailure = "bind check failed for an unknown reason"
    }

    $hasOnlyStaleOwners = Test-PortHasOnlyStaleOwners $Port
    $hasNoListener = $ownerSummary -eq "no listener"
    if ($AllowAutoPort -or $hasOnlyStaleOwners -or $hasNoListener) {
        $fallbackPort = Get-AvailablePort ($Port + 1)
        $fallbackReason = if ($AllowAutoPort) {
            "because -AutoPort was passed"
        } elseif ($hasOnlyStaleOwners) {
            "because the listener appears stale"
        } else {
            "because no listener was visible but the port could not be bound"
        }
        Write-Warn "$Name port $Port is unavailable ($ownerSummary; $bindFailure); using $fallbackPort $fallbackReason."
        return $fallbackPort
    }

    throw "$Name port $Port is unavailable ($ownerSummary; $bindFailure). Stop that process, change $Name port in .env, or rerun start-dev.cmd -AutoPort."
}

function Get-DecodedPowerShellCommandLine {
    param([AllowNull()][string]$CommandLine)

    if ([string]::IsNullOrWhiteSpace($CommandLine)) {
        return $null
    }

    $match = [regex]::Match($CommandLine, "(?i)(?:-EncodedCommand|-enc|-e)\s+([A-Za-z0-9+/=]+)")
    if (-not $match.Success) {
        return $null
    }

    try {
        $bytes = [Convert]::FromBase64String($match.Groups[1].Value)
        return [Text.Encoding]::Unicode.GetString($bytes)
    } catch {
        return $null
    }
}

function Stop-ExistingDevProcesses {
    Write-Step "Stopping existing project dev processes"

    $escapedRoot = [regex]::Escape($RepoRoot)
    $processes = @(Get-CimInstance Win32_Process |
        Where-Object {
            $commandText = $_.CommandLine
            $decodedCommandText = Get-DecodedPowerShellCommandLine $_.CommandLine
            if ($decodedCommandText) {
                $commandText = "$commandText`n$decodedCommandText"
            }

            $_.ProcessId -ne $PID -and
            $commandText -and
            $commandText -match $escapedRoot -and
            $commandText -match "vite|rsbuild|bun run|npm|uv\.exe|uv run|uvicorn|main\.py|\.venv-backend|backend\\\.venv|Start-Transcript|new-api|newapi"
        })

    $stoppedProcessIds = @()
    foreach ($process in $processes) {
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
            $stoppedProcessIds += [int]$process.ProcessId
            Write-Ok "Stopped process $($process.ProcessId) ($($process.Name))"
        } catch {
            if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) {
                Write-Warn "Could not stop process $($process.ProcessId): $($_.Exception.Message)"
            }
        }
    }

    if ($stoppedProcessIds.Count -gt 0) {
        $deadline = (Get-Date).AddSeconds(10)
        do {
            $remainingProcessIds = @($stoppedProcessIds | Where-Object {
                Get-Process -Id $_ -ErrorAction SilentlyContinue
            })
            if ($remainingProcessIds.Count -eq 0) {
                Start-Sleep -Milliseconds 500
                return
            }
            Start-Sleep -Milliseconds 500
        } while ((Get-Date) -lt $deadline)

        Write-Warn "Some stopped processes are still exiting: $($remainingProcessIds -join ', ')"
    }
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port
    )

    $client = $null
    try {
        $client = [Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(1000, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        if ($client) {
            $client.Close()
        }
    }
}

function Test-HttpEndpoint {
    param(
        [string]$Url,
        [string]$ExpectedContentPattern = ""
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        $statusOk = [int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 500
        if (-not $statusOk) {
            return $false
        }

        if ([string]::IsNullOrWhiteSpace($ExpectedContentPattern)) {
            return $true
        }

        return "$($response.Content)" -match $ExpectedContentPattern
    } catch {
        return $false
    }
}

function Write-LogTail {
    param(
        [string]$Path,
        [int]$Lines = 80
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Warn "Log file not found: $Path"
        return
    }

    Write-Host ""
    Write-Warn "Last $Lines lines from $Path"
    Get-Content -LiteralPath $Path -Tail $Lines | ForEach-Object { Write-Host $_ }
}

function Wait-HttpEndpoint {
    param(
        [string]$Name,
        [string]$Url,
        [string]$LogPath,
        [int]$TimeoutSeconds,
        [string]$ExpectedContentPattern = ""
    )

    Write-Step "Waiting for $Name"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
        if (Test-HttpEndpoint -Url $Url -ExpectedContentPattern $ExpectedContentPattern) {
            Write-Host ""
            Write-Ok "$Name is responding at $Url"
            return
        }

        Write-Host "." -NoNewline
        Start-Sleep -Seconds 2
    }

    Write-Host ""
    Write-LogTail -Path $LogPath
    $expectedMessage = if ([string]::IsNullOrWhiteSpace($ExpectedContentPattern)) { "" } else { " with expected content '$ExpectedContentPattern'" }
    throw "$Name did not respond at $Url$expectedMessage after $TimeoutSeconds seconds."
}

function Get-AvailablePort {
    param(
        [int]$StartAt,
        [int]$MaxAttempts = 50
    )

    for ($offset = 0; $offset -lt $MaxAttempts; $offset++) {
        $port = $StartAt + $offset
        if ($port -gt 65535) {
            break
        }

        if (Test-PortBindable $port) {
            return $port
        }
    }

    throw "No available port found from $StartAt."
}

function Start-DevWindow {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [string]$Command,
        [string]$LogPath,
        [switch]$ShowWindow
    )

    $script = @"
`$ErrorActionPreference = "Stop"
`$host.UI.RawUI.WindowTitle = "$Title"
Set-Location -LiteralPath "$WorkingDirectory"
Start-Transcript -Path "$LogPath" -Append
$Command
"@

    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
    $argumentList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-EncodedCommand", $encoded
    )

    if ($ShowWindow) {
        $argumentList = @(
            "-NoProfile",
            "-NoExit",
            "-ExecutionPolicy", "Bypass",
            "-EncodedCommand", $encoded
        )
        Start-Process -FilePath "powershell.exe" -ArgumentList $argumentList
    } else {
        Start-Process -FilePath "powershell.exe" -ArgumentList $argumentList -WindowStyle Hidden
    }
}

function Start-LocalNewApiGateway {
    param(
        [int]$Port,
        [string]$GatewayBaseUrl,
        [string]$TrainingUpstreamUrl,
        [string]$RedirectUri,
        [string]$LogPath,
        [string]$ErrLogPath
    )

    if (-not (Test-Path -LiteralPath $NewApiExePath)) {
        throw "Local NewAPI executable was not found at $NewApiExePath."
    }

    if (-not (Test-Path -LiteralPath $NewApiDbPath)) {
        throw "Local NewAPI database was not found at $NewApiDbPath."
    }

    $runtimeLogDir = Join-Path $NewApiDir "logs"
    if (-not (Test-Path -LiteralPath $runtimeLogDir)) {
        New-Item -ItemType Directory -Path $runtimeLogDir -Force | Out-Null
    }

    Remove-Item -LiteralPath $LogPath, $ErrLogPath -ErrorAction SilentlyContinue

    $redirectUris = Get-EnvValue $RootEnvPath "NEWAPI_TALKWISE_REDIRECT_URIS" "$RedirectUri,http://localhost:$frontendPort/login"
    $envValues = @{
        PORT = "$Port"
        SESSION_SECRET = Get-EnvValue $RootEnvPath "NEWAPI_SESSION_SECRET" "newapi-local-session-dev-change-me"
        TALKWISE_CLIENT_ID = Get-EnvValue $RootEnvPath "NEWAPI_TALKWISE_CLIENT_ID" "talkwise"
        TALKWISE_CLIENT_SECRET = Get-EnvValue $RootEnvPath "NEWAPI_TALKWISE_CLIENT_SECRET" "talkwise-local-handoff-dev-secret"
        TALKWISE_REDIRECT_URIS = $redirectUris
        TALKWISE_GATEWAY_BASE_URL = $GatewayBaseUrl
        TALKWISE_TRAINING_UPSTREAM_URL = $TrainingUpstreamUrl
        TZ = "Asia/Shanghai"
        NODE_NAME = "talkwise-newapi-local"
        SQL_DSN = ""
        REDIS_CONN_STRING = ""
    }

    $previousEnvValues = @{}
    foreach ($key in $envValues.Keys) {
        $previousEnvValues[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, $envValues[$key], "Process")
    }

    try {
        Start-Process `
            -FilePath $NewApiExePath `
            -ArgumentList @("--log-dir", $runtimeLogDir) `
            -WorkingDirectory $NewApiDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $LogPath `
            -RedirectStandardError $ErrLogPath | Out-Null
    } finally {
        foreach ($key in $previousEnvValues.Keys) {
            [Environment]::SetEnvironmentVariable($key, $previousEnvValues[$key], "Process")
        }
    }
}

function New-BackendCommand {
    param([int]$Port)

    $backendPython = Join-Path $BackendVenvDir "Scripts\python.exe"

    if (Test-CommandExists "uv") {
        if ($SkipInstall) {
            return @"
`$env:UV_PROJECT_ENVIRONMENT = "$BackendVenvDir"
`$env:UV_LINK_MODE = "copy"
uv run --no-sync --python 3.11 --default-index https://pypi.org/simple uvicorn main:app --host 127.0.0.1 --port $Port --reload
"@
        }

        return @"
`$env:UV_PROJECT_ENVIRONMENT = "$BackendVenvDir"
`$env:UV_LINK_MODE = "copy"
uv sync --python 3.11 --all-extras --default-index https://pypi.org/simple
if (`$LASTEXITCODE -ne 0) { throw "uv sync failed." }
uv run --no-sync --python 3.11 --default-index https://pypi.org/simple uvicorn main:app --host 127.0.0.1 --port $Port --reload
"@
    }

    if (Test-Path -LiteralPath $backendPython) {
        return @"
Write-Host "uv was not found on PATH; using existing backend environment: $backendPython"
& "$backendPython" -m uvicorn main:app --host 127.0.0.1 --port $Port --reload
"@
    }

    throw "uv was not found and $backendPython does not exist. Install uv or run backend dependency sync before starting the backend."
}

function New-FrontendCommand {
    param([int]$Port)

    if (-not (Test-CommandExists "npm")) {
        throw "npm was not found. Install Node.js first."
    }

    $viteBin = Join-Path $FrontendDir "node_modules\vite\bin\vite.js"
    $runVite = @"
if (-not (Test-Path -LiteralPath "$viteBin")) { throw "Vite binary not found at $viteBin. Run npm install in $FrontendDir." }
node "$viteBin" --host 127.0.0.1 --port $Port --strictPort
"@

    if ($SkipInstall) {
        return $runVite
    }

    return @"
npm install
if (`$LASTEXITCODE -ne 0) { throw "npm install failed." }
$runVite
"@
}

function New-NewApiWebCommand {
    param(
        [int]$Port,
        [string]$ServerUrl
    )

    if (-not (Test-CommandExists "bun")) {
        throw "bun was not found. Install Bun before starting the NewAPI web host."
    }

    $packagePath = Join-Path $NewApiWebDir "package.json"
    $runRsbuild = @"
if (-not (Test-Path -LiteralPath "$packagePath")) { throw "NewAPI web package was not found at $packagePath." }
`$env:VITE_REACT_APP_SERVER_URL = "$ServerUrl"
bun run dev -- --port $Port --strict-port
"@

    if ($SkipInstall) {
        return $runRsbuild
    }

    return @"
bun install --frozen-lockfile
if (`$LASTEXITCODE -ne 0) { throw "bun install failed." }
$runRsbuild
"@
}

Write-Step "Preparing local env files"
Write-Ok "Project root: $RepoRoot"
if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
Stop-ExistingDevProcesses
Remove-Item -LiteralPath `
    (Join-Path $LogDir "backend-dev.log"), `
    (Join-Path $LogDir "frontend-dev.log"), `
    (Join-Path $LogDir "newapi-dev.log"), `
    (Join-Path $LogDir "newapi-dev.err.log") `
    -ErrorAction SilentlyContinue

Ensure-EnvValue $RootEnvPath "POSTGRES_USER" "stakecoach"
Ensure-EnvValue $RootEnvPath "POSTGRES_PASSWORD" "stakecoach_dev_password"
Ensure-EnvValue $RootEnvPath "POSTGRES_DB" "stakecoachdb"
Ensure-EnvValue $RootEnvPath "POSTGRES_HOST_PORT" "15432"
Ensure-EnvValue $RootEnvPath "BACKEND_PORT" "8012"
Ensure-EnvValue $RootEnvPath "FRONTEND_PORT" "5177"
Ensure-EnvValue $RootEnvPath "NEWAPI_HOST_PORT" "18080"
Ensure-EnvValue $RootEnvPath "SECRET_KEY" "dev-secret-change-me"
Ensure-EnvValue $RootEnvPath "DEBUG" "true"
Ensure-EnvValue $RootEnvPath "NEWAPI_BASE_URL" "http://127.0.0.1:18080"
Ensure-EnvValue $RootEnvPath "NEWAPI_ACCESS_TOKEN" ""
Ensure-EnvValue $RootEnvPath "NEWAPI_GATEWAY_BASE_URL" "http://127.0.0.1:18080/v1"
Ensure-EnvValue $RootEnvPath "NEWAPI_PUBLIC_GATEWAY_BASE_URL" "http://127.0.0.1:18080/v1"
Ensure-EnvValue $RootEnvPath "NEWAPI_INTERNAL_BASE_URL" "http://127.0.0.1:18080"
Ensure-EnvValue $RootEnvPath "NEWAPI_AUTH_ENABLED" "true"
Ensure-EnvValue $RootEnvPath "NEWAPI_AUTH_ALLOW_MOCK_FALLBACK" "false"
Ensure-EnvValue $RootEnvPath "NEWAPI_AUTH_TIMEOUT_SECONDS" "5"
Ensure-EnvValue $RootEnvPath "NEWAPI_TALKWISE_CLIENT_ID" "talkwise"
Ensure-EnvValue $RootEnvPath "NEWAPI_TALKWISE_CLIENT_SECRET" "talkwise-local-handoff-dev-secret"
Ensure-EnvValue $RootEnvPath "NEWAPI_TALKWISE_AUTH_EXCHANGE_PATH" "/api/talkwise/auth/exchange"
Ensure-EnvValue $RootEnvPath "NEWAPI_TALKWISE_REDIRECT_URI" "http://127.0.0.1:5177/login"
Ensure-EnvValue $RootEnvPath "NEWAPI_TALKWISE_REDIRECT_URIS" "http://127.0.0.1:5177/login,http://localhost:5177/login"
Ensure-EnvValue $RootEnvPath "NEWAPI_SESSION_SECRET" "newapi-local-session-dev-change-me"
Ensure-EnvValue $RootEnvPath "TALKWISE_SESSION_COOKIE_NAME" "talkwise_session"
Ensure-EnvValue $RootEnvPath "TALKWISE_SESSION_TTL_SECONDS" "28800"
Ensure-EnvValue $RootEnvPath "VITE_NEWAPI_BASE_URL" "http://127.0.0.1:18080"
Ensure-EnvValue $RootEnvPath "VITE_NEWAPI_AUTH_ENABLED" "true"
Ensure-EnvValue $RootEnvPath "VITE_NEWAPI_LOGIN_URL" "http://127.0.0.1:18080/sign-in"
Ensure-EnvValue $RootEnvPath "VITE_NEWAPI_LOGIN_MODE" "embedded"
Ensure-EnvValue $RootEnvPath "VITE_NEWAPI_CONSOLE_URL" "http://127.0.0.1:18080"
Ensure-EnvValue $RootEnvPath "VITE_NEWAPI_USAGE_URL" "http://127.0.0.1:18080/usage-logs/common"
Ensure-EnvValue $RootEnvPath "VITE_NEWAPI_API_KEYS_URL" "http://127.0.0.1:18080/keys"
Ensure-EnvValue $RootEnvPath "VITE_NEWAPI_TALKWISE_CLIENT_ID" "talkwise"
Ensure-EnvValue $RootEnvPath "VITE_NEWAPI_TALKWISE_REDIRECT_URI" "http://127.0.0.1:5177/login"

if (-not $SkipGateway) {
    Stop-DockerNewApiServicesIfRunning
}

$pgUser = Get-EnvValue $RootEnvPath "POSTGRES_USER" "stakecoach"
$pgPassword = Get-EnvValue $RootEnvPath "POSTGRES_PASSWORD" "stakecoach_dev_password"
$pgDb = Get-EnvValue $RootEnvPath "POSTGRES_DB" "stakecoachdb"
$pgHostPort = [int](Get-EnvValue $RootEnvPath "POSTGRES_HOST_PORT" "15432")
$configuredGatewayPort = if ($SkipGateway) { 0 } else { Get-ConfiguredPort -Key "NEWAPI_HOST_PORT" -DefaultValue 18080 -OverrideValue $GatewayPort }
$configuredBackendPort = Get-ConfiguredPort -Key "BACKEND_PORT" -DefaultValue 8012 -OverrideValue $BackendPort
$configuredFrontendPort = Get-ConfiguredPort -Key "FRONTEND_PORT" -DefaultValue 5177 -OverrideValue $FrontendPort
$resolvedGatewayPort = if ($SkipGateway) { 0 } else { Resolve-DevPort -Name "gateway" -Port $configuredGatewayPort -AllowAutoPort:$AutoPort }
$backendPort = Resolve-DevPort -Name "backend" -Port $configuredBackendPort -AllowAutoPort:$AutoPort
$frontendPort = Resolve-DevPort -Name "frontend" -Port $configuredFrontendPort -AllowAutoPort:$AutoPort
if ($backendPort -eq $frontendPort) {
    throw "BACKEND_PORT and FRONTEND_PORT must be different; both resolved to $backendPort."
}
if (-not $SkipGateway -and ($resolvedGatewayPort -eq $backendPort -or $resolvedGatewayPort -eq $frontendPort)) {
    throw "NEWAPI_HOST_PORT must be different from BACKEND_PORT and FRONTEND_PORT; gateway resolved to $resolvedGatewayPort."
}
if (-not $SkipGateway) {
    Set-EnvValue $RootEnvPath "NEWAPI_HOST_PORT" "$resolvedGatewayPort"
}
Set-EnvValue $RootEnvPath "BACKEND_PORT" "$backendPort"
Set-EnvValue $RootEnvPath "FRONTEND_PORT" "$frontendPort"
$encodedPgUser = [uri]::EscapeDataString($pgUser)
$encodedPgPassword = [uri]::EscapeDataString($pgPassword)
$encodedPgDb = [uri]::EscapeDataString($pgDb)
$sqliteDatabaseUrl = "sqlite+aiosqlite:///./app.db"
$postgresDatabaseUrl = "postgresql+asyncpg://${encodedPgUser}:${encodedPgPassword}@127.0.0.1:${pgHostPort}/${encodedPgDb}"
$databaseUrl = if ($UsePostgres) { $postgresDatabaseUrl } else { $sqliteDatabaseUrl }
$usingSqlite = -not [bool]$UsePostgres
$frontendUrl = "http://127.0.0.1:$frontendPort"
$backendUrl = "http://127.0.0.1:$backendPort"
$newApiUrl = if ($SkipGateway) { Get-EnvValue $RootEnvPath "NEWAPI_BASE_URL" "https://newapi.flowguide.cc" } else { "http://127.0.0.1:$resolvedGatewayPort" }
$newApiGatewayUrl = if ($SkipGateway) { Get-EnvValue $RootEnvPath "NEWAPI_GATEWAY_BASE_URL" "$newApiUrl/v1" } else { "$newApiUrl/v1" }
$legacyFrontendRedirectUri = "$frontendUrl/login"
$newApiRedirectUri = if ($LegacyViteFrontend) { $legacyFrontendRedirectUri } else { "$frontendUrl/training" }
$newApiRedirectUris = "$newApiRedirectUri,$legacyFrontendRedirectUri,http://localhost:$frontendPort/login"
$backendLogPath = Join-Path $LogDir "backend-dev.log"
$frontendLogPath = Join-Path $LogDir "frontend-dev.log"
$newApiLogPath = Join-Path $LogDir "newapi-dev.log"
$newApiErrLogPath = Join-Path $LogDir "newapi-dev.err.log"
$corsOriginsValue = "[`"http://127.0.0.1:$frontendPort`",`"http://localhost:$frontendPort`",`"http://127.0.0.1:$backendPort`",`"http://localhost:$backendPort`"]"

if (-not $SkipGateway) {
    Set-EnvValue $RootEnvPath "NEWAPI_BASE_URL" $newApiUrl
    Set-EnvValue $RootEnvPath "NEWAPI_GATEWAY_BASE_URL" $newApiGatewayUrl
    Set-EnvValue $RootEnvPath "NEWAPI_PUBLIC_GATEWAY_BASE_URL" $newApiGatewayUrl
    Set-EnvValue $RootEnvPath "NEWAPI_INTERNAL_BASE_URL" $newApiUrl
    Set-EnvValue $RootEnvPath "NEWAPI_AUTH_ENABLED" "true"
    Set-EnvValue $RootEnvPath "NEWAPI_TALKWISE_REDIRECT_URI" $newApiRedirectUri
    Set-EnvValue $RootEnvPath "NEWAPI_TALKWISE_REDIRECT_URIS" $newApiRedirectUris
    Set-EnvValue $RootEnvPath "VITE_NEWAPI_BASE_URL" $newApiUrl
    Set-EnvValue $RootEnvPath "VITE_NEWAPI_AUTH_ENABLED" "true"
    Set-EnvValue $RootEnvPath "VITE_NEWAPI_LOGIN_URL" "$newApiUrl/sign-in"
    Set-EnvValue $RootEnvPath "VITE_NEWAPI_CONSOLE_URL" $newApiUrl
    Set-EnvValue $RootEnvPath "VITE_NEWAPI_USAGE_URL" "$newApiUrl/usage-logs/common"
    Set-EnvValue $RootEnvPath "VITE_NEWAPI_API_KEYS_URL" "$newApiUrl/keys"
    Set-EnvValue $RootEnvPath "VITE_NEWAPI_TALKWISE_REDIRECT_URI" $newApiRedirectUri
}

$newApiBaseUrl = Get-EnvValue $RootEnvPath "NEWAPI_BASE_URL" "https://newapi.flowguide.cc"
$newApiAccessToken = Get-EnvValue $RootEnvPath "NEWAPI_ACCESS_TOKEN" ""
$newApiGatewayBaseUrl = Get-EnvValue $RootEnvPath "NEWAPI_GATEWAY_BASE_URL" "$newApiBaseUrl/v1"
$newApiAuthEnabled = Get-EnvValue $RootEnvPath "NEWAPI_AUTH_ENABLED" "false"
$newApiAuthAllowMockFallback = Get-EnvValue $RootEnvPath "NEWAPI_AUTH_ALLOW_MOCK_FALLBACK" "false"
$newApiAuthTimeoutSeconds = Get-EnvValue $RootEnvPath "NEWAPI_AUTH_TIMEOUT_SECONDS" "5"
$newApiTalkwiseClientId = Get-EnvValue $RootEnvPath "NEWAPI_TALKWISE_CLIENT_ID" "talkwise"
$newApiTalkwiseClientSecret = Get-EnvValue $RootEnvPath "NEWAPI_TALKWISE_CLIENT_SECRET" ""
$newApiTalkwiseAuthExchangePath = Get-EnvValue $RootEnvPath "NEWAPI_TALKWISE_AUTH_EXCHANGE_PATH" "/api/talkwise/auth/exchange"
$newApiTalkwiseRedirectUri = Get-EnvValue $RootEnvPath "NEWAPI_TALKWISE_REDIRECT_URI" ""
$talkwiseSessionCookieName = Get-EnvValue $RootEnvPath "TALKWISE_SESSION_COOKIE_NAME" "talkwise_session"
$talkwiseSessionTtlSeconds = Get-EnvValue $RootEnvPath "TALKWISE_SESSION_TTL_SECONDS" "28800"
$viteNewApiBaseUrl = Get-EnvValue $RootEnvPath "VITE_NEWAPI_BASE_URL" $newApiBaseUrl
$viteNewApiAuthEnabled = Get-EnvValue $RootEnvPath "VITE_NEWAPI_AUTH_ENABLED" $newApiAuthEnabled
$viteNewApiLoginUrl = Get-EnvValue $RootEnvPath "VITE_NEWAPI_LOGIN_URL" "$newApiBaseUrl/login"
$viteNewApiLoginMode = Get-EnvValue $RootEnvPath "VITE_NEWAPI_LOGIN_MODE" "embedded"
$viteNewApiConsoleUrl = Get-EnvValue $RootEnvPath "VITE_NEWAPI_CONSOLE_URL" $newApiBaseUrl
$viteNewApiUsageUrl = Get-EnvValue $RootEnvPath "VITE_NEWAPI_USAGE_URL" "$newApiBaseUrl/usage-logs/common"
$viteNewApiApiKeysUrl = Get-EnvValue $RootEnvPath "VITE_NEWAPI_API_KEYS_URL" "$newApiBaseUrl/keys"
$viteNewApiTalkwiseClientId = Get-EnvValue $RootEnvPath "VITE_NEWAPI_TALKWISE_CLIENT_ID" $newApiTalkwiseClientId
$viteNewApiTalkwiseRedirectUri = Get-EnvValue $RootEnvPath "VITE_NEWAPI_TALKWISE_REDIRECT_URI" $newApiTalkwiseRedirectUri

Set-EnvValue $BackendEnvPath "SECRET_KEY" "dev-secret-change-me"
Set-EnvValue $BackendEnvPath "DEBUG" "true"
Set-EnvValue $BackendEnvPath "RELOAD" "true"
Set-EnvValue $BackendEnvPath "AUTO_RUN_MIGRATIONS" "true"
Set-EnvValue $BackendEnvPath "PORT" "$backendPort"
Set-EnvValue $BackendEnvPath "DATABASE__URL" $databaseUrl
Set-EnvValue $BackendEnvPath "CORS_ORIGINS" $corsOriginsValue
Set-EnvValue $BackendEnvPath "LOG_FILE" "../logs/backend-runtime.log"
Set-EnvValue $BackendEnvPath "STORAGE__LOCAL_BASE_PATH" "./storage"
Set-EnvValue $BackendEnvPath "NEWAPI_BASE_URL" $newApiBaseUrl
Set-EnvValue $BackendEnvPath "NEWAPI_ACCESS_TOKEN" $newApiAccessToken
Set-EnvValue $BackendEnvPath "NEWAPI_GATEWAY_BASE_URL" $newApiGatewayBaseUrl
Set-EnvValue $BackendEnvPath "NEWAPI_AUTH_ENABLED" $newApiAuthEnabled
Set-EnvValue $BackendEnvPath "NEWAPI_AUTH_ALLOW_MOCK_FALLBACK" $newApiAuthAllowMockFallback
Set-EnvValue $BackendEnvPath "NEWAPI_AUTH_TIMEOUT_SECONDS" $newApiAuthTimeoutSeconds
Set-EnvValue $BackendEnvPath "NEWAPI_TALKWISE_CLIENT_ID" $newApiTalkwiseClientId
Set-EnvValue $BackendEnvPath "NEWAPI_TALKWISE_CLIENT_SECRET" $newApiTalkwiseClientSecret
Set-EnvValue $BackendEnvPath "NEWAPI_TALKWISE_AUTH_EXCHANGE_PATH" $newApiTalkwiseAuthExchangePath
Set-EnvValue $BackendEnvPath "NEWAPI_TALKWISE_REDIRECT_URI" $newApiTalkwiseRedirectUri
Set-EnvValue $BackendEnvPath "TALKWISE_SESSION_COOKIE_NAME" $talkwiseSessionCookieName
Set-EnvValue $BackendEnvPath "TALKWISE_SESSION_TTL_SECONDS" $talkwiseSessionTtlSeconds

Set-EnvValue $FrontendEnvPath "VITE_API_URL" $backendUrl
Set-EnvValue $FrontendEnvPath "VITE_NEWAPI_BASE_URL" $viteNewApiBaseUrl
Set-EnvValue $FrontendEnvPath "VITE_NEWAPI_AUTH_ENABLED" $viteNewApiAuthEnabled
Set-EnvValue $FrontendEnvPath "VITE_NEWAPI_LOGIN_URL" $viteNewApiLoginUrl
Set-EnvValue $FrontendEnvPath "VITE_NEWAPI_LOGIN_MODE" $viteNewApiLoginMode
Set-EnvValue $FrontendEnvPath "VITE_NEWAPI_CONSOLE_URL" $viteNewApiConsoleUrl
Set-EnvValue $FrontendEnvPath "VITE_NEWAPI_USAGE_URL" $viteNewApiUsageUrl
Set-EnvValue $FrontendEnvPath "VITE_NEWAPI_API_KEYS_URL" $viteNewApiApiKeysUrl
Set-EnvValue $FrontendEnvPath "VITE_NEWAPI_TALKWISE_CLIENT_ID" $viteNewApiTalkwiseClientId
Set-EnvValue $FrontendEnvPath "VITE_NEWAPI_TALKWISE_REDIRECT_URI" $viteNewApiTalkwiseRedirectUri

if ($UsePostgres) {
    try {
        Write-Step "Checking Docker"
        Start-DockerDesktopIfNeeded

        Write-Step "Starting Postgres container"
        Stop-DockerAppServices
        Invoke-DockerCompose @("up", "-d", "postgres")
        Wait-PostgresHealthy -HostPort $pgHostPort
    } catch {
        if ($NoSqliteFallback) {
            throw
        }

        Write-Warn "Postgres startup failed; falling back to SQLite so local dev can still start."
        Write-Warn "Postgres detail: $($_.Exception.Message)"
        Write-Warn "Pass -NoSqliteFallback if this run must use Postgres."
        $databaseUrl = $sqliteDatabaseUrl
        $usingSqlite = $true
        Set-EnvValue $BackendEnvPath "DATABASE__URL" $databaseUrl
    }
} else {
    Write-Ok "Using SQLite for local development; Docker/Postgres is skipped."
    Write-Host "Pass -UsePostgres to run against the local Docker Postgres database."
}

if (-not $SkipGateway) {
    Write-Step "Starting local NewAPI gateway on port $resolvedGatewayPort"
    Start-LocalNewApiGateway `
        -Port $resolvedGatewayPort `
        -GatewayBaseUrl $newApiGatewayUrl `
        -TrainingUpstreamUrl $backendUrl `
        -RedirectUri $newApiRedirectUri `
        -LogPath $newApiLogPath `
        -ErrLogPath $newApiErrLogPath
}

Write-Step "Starting backend locally with FastAPI on port $backendPort"
Start-DevWindow `
    -Title "Talk Training Studio - Backend" `
    -WorkingDirectory $BackendDir `
    -Command (New-BackendCommand -Port $backendPort) `
    -LogPath $backendLogPath `
    -ShowWindow:$ShowServiceWindows

if ($LegacyViteFrontend) {
    Write-Step "Starting legacy Vite frontend on port $frontendPort"
    Start-DevWindow `
        -Title "Talk Training Studio - Legacy Frontend" `
        -WorkingDirectory $FrontendDir `
        -Command (New-FrontendCommand -Port $frontendPort) `
        -LogPath $frontendLogPath `
        -ShowWindow:$ShowServiceWindows
} else {
    Write-Step "Starting NewAPI web host with Rsbuild on port $frontendPort"
    Start-DevWindow `
        -Title "Talk Training Studio - NewAPI Web" `
        -WorkingDirectory $NewApiWebDir `
        -Command (New-NewApiWebCommand -Port $frontendPort -ServerUrl $newApiUrl) `
        -LogPath $frontendLogPath `
        -ShowWindow:$ShowServiceWindows
}

if (-not $SkipHealthCheck) {
    if (-not $SkipGateway) {
        Wait-HttpEndpoint `
            -Name "NewAPI gateway" `
            -Url "$newApiUrl/api/status" `
            -LogPath $newApiLogPath `
            -TimeoutSeconds $ServiceTimeoutSeconds `
            -ExpectedContentPattern '"success":true'
    }

    Wait-HttpEndpoint `
        -Name "backend" `
        -Url "$backendUrl/health/live" `
        -LogPath $backendLogPath `
        -TimeoutSeconds $ServiceTimeoutSeconds `
        -ExpectedContentPattern "alive"

    Wait-HttpEndpoint `
        -Name "frontend" `
        -Url $frontendUrl `
        -LogPath $frontendLogPath `
        -TimeoutSeconds $ServiceTimeoutSeconds

    if ($LegacyViteFrontend) {
        Wait-HttpEndpoint `
            -Name "legacy frontend API proxy" `
            -Url "$frontendUrl/health/live" `
            -LogPath $frontendLogPath `
            -TimeoutSeconds $ServiceTimeoutSeconds `
            -ExpectedContentPattern "alive"
    } else {
        Wait-HttpEndpoint `
            -Name "NewAPI web same-origin proxy" `
            -Url "$frontendUrl/api/status" `
            -LogPath $frontendLogPath `
            -TimeoutSeconds $ServiceTimeoutSeconds `
            -ExpectedContentPattern '"success":true'
    }
}

if (-not $NoBrowser) {
    Start-Process $frontendUrl
}

Write-Host ""
Write-Ok "Dev startup finished."
Write-Host "Frontend: $frontendUrl"
Write-Host "Backend docs: $backendUrl/docs"
Write-Host "Backend health: $backendUrl/health/live"
if ($LegacyViteFrontend) {
    Write-Host "Legacy frontend API proxy health: $frontendUrl/health/live"
} else {
    Write-Host "NewAPI web same-origin proxy health: $frontendUrl/api/status"
}
if (-not $SkipGateway) {
    Write-Host "NewAPI status: $newApiUrl/api/status"
    Write-Host "NewAPI login: $newApiUrl/sign-in"
}
Write-Host "NewAPI console: $viteNewApiConsoleUrl"
Write-Host "NewAPI API keys: $viteNewApiApiKeysUrl"
Write-Host "NewAPI usage: $viteNewApiUsageUrl"
Write-Host "NewAPI gateway: $newApiGatewayBaseUrl"
Write-Host "Logs: $LogDir"
Write-Host ""
if (-not $usingSqlite) {
    Write-Host "To stop Postgres later: docker compose stop postgres"
} else {
    Write-Host "Database: SQLite ($BackendDir\app.db)"
}
