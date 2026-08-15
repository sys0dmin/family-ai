[CmdletBinding()]
param(
    [string]$HostName = "192.168.31.173",
    [string]$SshUser = "familyai-deploy",
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\family-ai-deploy",
    [ValidatePattern("^(1|2|4)(,(1|2|4))*$")]
    [string]$Levels = "1,2,4",
    [ValidateRange(1, 10)]
    [int]$Rounds = 2,
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not (Test-Path -LiteralPath $IdentityFile)) {
    throw "SSH identity file not found: $IdentityFile"
}
if (-not $OutputPath) {
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputPath = Join-Path $RepoRoot ".artifacts\voice-soak\voice-soak-$Timestamp.json"
}
$OutputPath = if ([IO.Path]::IsPathRooted($OutputPath)) {
    [IO.Path]::GetFullPath($OutputPath)
} else {
    [IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputPath))
}
$OutputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$Remote = "$SshUser@$HostName"
$SshOptions = @("-i", $IdentityFile, "-o", "BatchMode=yes")
$RemoteReport = "/tmp/family-ai-voice-soak-$([guid]::NewGuid().ToString('N')).json"
$RemoteCommand = @"
cd /srv/family-ai/gateway/current &&
PYTHONPATH=/srv/family-ai/gateway/current ./.venv/bin/python -m gateway.voice_soak \
  --env-file /etc/family-ai/gateway.env \
  --levels '$Levels' --rounds '$Rounds' --output '$RemoteReport'
"@

try {
    & ssh @SshOptions $Remote $RemoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Remote voice soak failed with exit code $LASTEXITCODE"
    }
    & scp @SshOptions "$Remote`:$RemoteReport" $OutputPath
    if ($LASTEXITCODE -ne 0) {
        throw "Could not copy voice soak report"
    }
    $Report = Get-Content -LiteralPath $OutputPath -Raw -Encoding utf8 | ConvertFrom-Json
    Write-Host "Report: $OutputPath"
    Write-Host "Status: $($Report.status); samples: $($Report.configuration.total_measured_samples); history delta: $($Report.privacy.history_message_delta)"
} finally {
    & ssh @SshOptions $Remote "rm -f '$RemoteReport'" 2>$null
}
