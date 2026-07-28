[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [ValidateSet("prepare", "deploy", "activate", "migrate", "rollback", "status")]
    [string]$Action,

    [Parameter(Mandatory, Position = 1)]
    [ValidateSet("gateway", "speech")]
    [string]$Component,

    [Parameter(Mandatory)]
    [string]$HostName,

    [string]$Commit = "HEAD",
    [string]$TargetVersion = "",
    [string]$SshUser = "familyai-deploy",
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\family-ai-deploy"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Remote = "$SshUser@$HostName"
$SshOptions = @("-i", $IdentityFile, "-o", "BatchMode=yes")

function Invoke-Native {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

function Install-HostContract {
    $Bootstrap = "/tmp/family-ai-bootstrap-$Component"
    Invoke-Native "ssh" ($SshOptions + @($Remote, "rm -rf '$Bootstrap' && mkdir -p '$Bootstrap'"))
    Invoke-Native "scp" ($SshOptions + @(
        (Join-Path $PSScriptRoot "install_host.sh"),
        "$Remote`:$Bootstrap/install_host.sh"
    ))

    $UnitNames = if ($Component -eq "gateway") {
        @(
            "family-ai-gateway.service",
            "family-ai-admin.service",
            "family-ai-retention.service",
            "family-ai-retention.timer"
        )
    } else {
        @("family-ai-speech.service")
    }
    foreach ($Unit in $UnitNames) {
        Invoke-Native "scp" ($SshOptions + @(
            (Join-Path $RepoRoot "infrastructure\systemd\$Unit"),
            "$Remote`:$Bootstrap/$Unit"
        ))
    }
    Invoke-Native "ssh" ($SshOptions + @(
        $Remote,
        "sudo bash '$Bootstrap/install_host.sh' '$Component' '$Bootstrap' '$SshUser'"
    ))
}

function Install-Controller {
    $RemoteController = "/srv/family-ai/$Component/remote_release.sh"
    Invoke-Native "scp" ($SshOptions + @(
        (Join-Path $PSScriptRoot "remote_release.sh"),
        "$Remote`:$RemoteController"
    ))
    Invoke-Native "ssh" ($SshOptions + @($Remote, "chmod 0755 '$RemoteController'"))
    return $RemoteController
}

if (-not (Test-Path -LiteralPath $IdentityFile)) {
    throw "SSH identity file not found: $IdentityFile"
}

if ($Action -in @("prepare", "deploy")) {
    Install-HostContract
}
$Controller = Install-Controller

if ($Action -in @("prepare", "deploy")) {
    $FullCommit = (& git -C $RepoRoot rev-parse --verify "$Commit^{commit}").Trim()
    if ($LASTEXITCODE -ne 0 -or $FullCommit -notmatch "^[0-9a-f]{40}$") {
        throw "Cannot resolve Git commit: $Commit"
    }

    $ArtifactDir = Join-Path $RepoRoot ".artifacts"
    New-Item -ItemType Directory -Force -Path $ArtifactDir | Out-Null
    $Artifact = Join-Path $ArtifactDir "$Component-$FullCommit.tar.gz"
    $RepositoryPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $RepositoryPython)) {
        $RepositoryPython = (Get-Command python -ErrorAction Stop).Source
    }
    $ManifestJson = & $RepositoryPython `
        (Join-Path $PSScriptRoot "build_release.py") `
        $Component --commit $FullCommit --output $Artifact --repo $RepoRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Release builder failed"
    }
    $Manifest = $ManifestJson | ConvertFrom-Json
    $RemoteArtifact = "/srv/family-ai/$Component/incoming/$Component-$FullCommit.tar.gz"
    Invoke-Native "scp" ($SshOptions + @($Artifact, "$Remote`:$RemoteArtifact"))
    Invoke-Native "ssh" ($SshOptions + @(
        $Remote,
        "bash '$Controller' '$Action' '$Component' '$RemoteArtifact' '$($Manifest.archive_sha256)' '$FullCommit'"
    ))
    exit 0
}

$Version = if ($TargetVersion) { $TargetVersion } else { "" }
switch ($Action) {
    "activate" {
        if (-not $Version) { throw "-TargetVersion is required for activate" }
        Invoke-Native "ssh" ($SshOptions + @(
            $Remote, "bash '$Controller' activate '$Component' '$Version'"
        ))
    }
    "migrate" {
        if ($Component -ne "gateway") { throw "Only gateway owns database migrations" }
        $Command = "bash '$Controller' migrate gateway"
        if ($Version) { $Command += " '$Version'" }
        Invoke-Native "ssh" ($SshOptions + @($Remote, $Command))
    }
    "rollback" {
        $Command = "bash '$Controller' rollback '$Component'"
        if ($Version) { $Command += " '$Version'" }
        Invoke-Native "ssh" ($SshOptions + @($Remote, $Command))
    }
    "status" {
        Invoke-Native "ssh" ($SshOptions + @($Remote, "bash '$Controller' status '$Component'"))
    }
}
