<#
.SYNOPSIS
    Trigger and monitor the TalkWise GitHub Actions production deployment.

.DESCRIPTION
    GitHub-hosted runners build and push both TalkWise images to GHCR.
    The production server only pulls the images and switches the existing
    Compose services through scripts/remote-deploy.sh.

    Use -Push for the normal flow. It requires a clean worktree, pushes the
    current HEAD to the selected ref, and waits for the resulting run.
    Without -Push, the script dispatches the workflow manually.
#>
[CmdletBinding()]
param(
    [string]$Ref = 'main',
    [string]$Workflow = 'deploy.yml',
    [string]$HealthUrl = 'https://talkwise.flowguide.cc/',
    [int]$RunWaitSeconds = 180,
    [switch]$Push,
    [switch]$SkipHealthCheck
)

$ErrorActionPreference = 'Stop'

function Invoke-NativeCapture {
    param([Parameter(Mandatory)] [scriptblock]$ScriptBlock)
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $global:LASTEXITCODE = $null
        $output = & $ScriptBlock 2>&1 | ForEach-Object { "$_" }
        return @{ Output = $output; ExitCode = $LASTEXITCODE }
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

if ($Ref -notmatch '^[a-zA-Z0-9._/-]+$') { throw 'Ref contains unsupported characters.' }
if ($Workflow -notmatch '^[a-zA-Z0-9._-]+$') { throw 'Workflow contains unsupported characters.' }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'GitHub CLI (gh) is required. Run gh auth login with repo and workflow permissions.'
}

$auth = Invoke-NativeCapture { gh auth status }
if ($auth.ExitCode -ne 0) { throw 'gh is not authenticated.' }

$repo = Invoke-NativeCapture { gh repo view --json nameWithOwner --jq '.nameWithOwner' }
if ($repo.ExitCode -ne 0) { throw 'Could not determine the GitHub repository.' }
Write-Host "Repository: $(($repo.Output | Out-String).Trim())"

function Get-LatestRunId {
    $result = Invoke-NativeCapture { gh run list --workflow $Workflow --branch $Ref --limit 1 --json databaseId --jq '.[0].databaseId' }
    if ($result.ExitCode -ne 0) { return $null }
    $value = ($result.Output | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($value) -or $value -eq 'null') { return $null }
    return $value
}

$beforeRunId = Get-LatestRunId
$upToDate = $false

if ($Push) {
    $dirty = @(git status --porcelain)
    if ($dirty.Count -gt 0) {
        throw "Worktree is not clean. Commit or isolate changes first:`n$($dirty -join "`n")"
    }
    Write-Host "Pushing HEAD to origin/$Ref ..."
    $pushResult = Invoke-NativeCapture { git push origin "HEAD:$Ref" }
    $pushResult.Output | ForEach-Object { Write-Host $_ }
    if ($pushResult.ExitCode -ne 0) { throw "git push failed (exit code $($pushResult.ExitCode))." }
    $upToDate = (($pushResult.Output | Out-String) -match 'Everything up-to-date')
}

if ((-not $Push) -or $upToDate) {
    Write-Host "Dispatching $Workflow (ref=$Ref) ..."
    $dispatch = Invoke-NativeCapture { gh workflow run $Workflow --ref $Ref -f deploy=true }
    $dispatch.Output | ForEach-Object { Write-Host $_ }
    if ($dispatch.ExitCode -ne 0) { throw "Workflow dispatch failed (exit code $($dispatch.ExitCode))." }
}

$runId = $null
$deadline = (Get-Date).AddSeconds($RunWaitSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 4
    $candidate = Get-LatestRunId
    if ($candidate -and $candidate -ne $beforeRunId) { $runId = $candidate; break }
}
if (-not $runId) { throw "Could not identify the triggered run within $RunWaitSeconds seconds." }

Write-Host "Monitoring run $runId ..."
$watch = Invoke-NativeCapture { gh run watch $runId --exit-status --interval 15 }
$watch.Output | Select-Object -Last 60 | ForEach-Object { Write-Host $_ }
if ($watch.ExitCode -ne 0) {
    throw "Deployment run $runId failed. Use 'gh run view $runId --log-failed' for details."
}

if (-not $SkipHealthCheck) {
    $short = ((Invoke-NativeCapture { git rev-parse --short=12 HEAD }).Output | Out-String).Trim()
    $separator = if ($HealthUrl.Contains('?')) { '&' } else { '?' }
    $probeUrl = if ($short) { "${HealthUrl}${separator}deploy=$short" } else { $HealthUrl }
    $response = Invoke-WebRequest -Uri $probeUrl -Method Get -MaximumRedirection 5 -TimeoutSec 30 -UseBasicParsing
    if ($response.StatusCode -ne 200) { throw "Production health check failed: HTTP $($response.StatusCode)." }
    Write-Host "Production health check passed: $HealthUrl"
}

Write-Host "TalkWise deployment completed."
