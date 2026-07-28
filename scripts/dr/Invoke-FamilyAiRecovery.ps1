[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [ValidateSet("TotalLoss", "DatabaseSalvage")]
    [string]$Scenario,

    [Parameter(Mandatory)]
    [string]$GatewayHost,

    [Parameter(Mandatory)]
    [string]$DatabaseHost,

    [Parameter(Mandatory)]
    [string]$SpeechHost,

    [string]$SourceDatabaseHost = "",
    [string]$SshUser = "root",
    [string]$SourceSshUser = "",
    [string]$ServiceUser = "familyai-deploy",
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\family-ai-deploy",
    [string]$BundlePath = ".dr\family-ai-dr-kit.dpapi",
    [string]$Commit = "origin/main",
    [switch]$DryRun,
    [switch]$ConfirmTargetsAreDisposable
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ReleaseScript = Join-Path $RepoRoot "scripts\deploy\release.ps1"
$RemoteAssets = Join-Path $PSScriptRoot "remote"
$StartedAt = [DateTime]::UtcNow
Import-Module (Join-Path $PSScriptRoot "FamilyAiDr.Common.psm1") -Force
Initialize-FamilyAiDr -IdentityFile $IdentityFile

foreach ($entry in @{
    GatewayHost = $GatewayHost
    DatabaseHost = $DatabaseHost
    SpeechHost = $SpeechHost
    SshUser = $SshUser
    ServiceUser = $ServiceUser
}.GetEnumerator()) {
    Assert-SafeToken $entry.Value $entry.Key
}
if (($GatewayHost, $DatabaseHost, $SpeechHost | Select-Object -Unique).Count -ne 3) {
    throw "GatewayHost, DatabaseHost and SpeechHost must be three different hosts"
}
if (-not $DryRun -and -not $ConfirmTargetsAreDisposable) {
    throw "Recovery changes all three target hosts. Add -ConfirmTargetsAreDisposable."
}
if (-not (Test-Path -LiteralPath $IdentityFile)) {
    throw "SSH identity file not found: $IdentityFile"
}
if (-not (Test-Path -LiteralPath $BundlePath)) {
    throw "Encrypted DR kit not found: $BundlePath"
}

function Assert-DisposableTargets {
    $gatewayCurrent = Invoke-Remote $GatewayHost $SshUser `
        "if [ -e /srv/family-ai/gateway/current ]; then echo occupied; else echo empty; fi"
    if (($gatewayCurrent | Select-Object -Last 1).Trim() -ne "empty") {
        throw "Gateway target already contains an active Family AI release"
    }
    $speechCurrent = Invoke-Remote $SpeechHost $SshUser `
        "if [ -e /srv/family-ai/speech/current ]; then echo occupied; else echo empty; fi"
    if (($speechCurrent | Select-Object -Last 1).Trim() -ne "empty") {
        throw "Speech target already contains an active Family AI release"
    }
    $databaseState = Invoke-Remote $DatabaseHost $SshUser `
        "if command -v psql >/dev/null 2>&1 && sudo -u postgres psql -At -d postgres -c `"SELECT 1 FROM pg_database WHERE datname='${DatabaseName}'`" 2>/dev/null | grep -qx 1; then echo occupied; else echo empty; fi"
    if (($databaseState | Select-Object -Last 1).Trim() -ne "empty") {
        throw "Database target already contains $DatabaseName; destructive overwrite is forbidden"
    }
}

$kit = Read-DrKit -BundlePath $BundlePath
$gatewayValues = ConvertFrom-EnvText $kit.gateway_environment
$speechValues = ConvertFrom-EnvText $kit.speech_environment
$databaseSettings = Resolve-DatabaseSettings `
    $gatewayValues["FAMILY_AI_DATABASE_URL"] `
    $DatabaseHost
$DatabaseRole = $databaseSettings.Username
$DatabaseName = $databaseSettings.DatabaseName
Assert-SafeToken $DatabaseRole "DatabaseRole"
Assert-SafeToken $DatabaseName "DatabaseName"
if (-not $SourceDatabaseHost) {
    $SourceDatabaseHost = $databaseSettings.SourceHost
}
if (-not $SourceSshUser) {
    $SourceSshUser = $SshUser
}
Assert-SafeToken $SourceDatabaseHost "SourceDatabaseHost"
Assert-SafeToken $SourceSshUser "SourceSshUser"
if ($Scenario -eq "DatabaseSalvage" -and $SourceDatabaseHost -eq $DatabaseHost) {
    throw "SourceDatabaseHost and target DatabaseHost must be different"
}

$fullCommit = (& git -C $RepoRoot rev-parse --verify "$Commit^{commit}").Trim()
if ($LASTEXITCODE -ne 0 -or $fullCommit -notmatch "^[0-9a-f]{40}$") {
    throw "Cannot resolve Git commit: $Commit"
}

$gatewayValues["FAMILY_AI_DATABASE_URL"] = $databaseSettings.RewrittenUrl
$gatewayValues["FAMILY_AI_SPEECH_BASE_URL"] = "http://${SpeechHost}:8010/v1"
$gatewayValues["FAMILY_AI_DATABASE_NODE_METRICS_URL"] = "http://${DatabaseHost}:9100/metrics"
$gatewayValues["FAMILY_AI_SPEECH_NODE_METRICS_URL"] = "http://${SpeechHost}:9100/metrics"
foreach ($key in @("FAMILY_AI_STT_BASE_URL", "FAMILY_AI_TTS_BASE_URL")) {
    if (-not $gatewayValues.Contains($key) -or
        -not $gatewayValues[$key] -or
        $gatewayValues[$key] -match [regex]::Escape([string]$kit.source_speech_host)) {
        $gatewayValues[$key] = ""
    }
}

Write-Output "=== Family AI DR preflight ==="
Write-Output "scenario=$Scenario commit=$fullCommit"
Write-Output "targets: gateway=$GatewayHost database=$DatabaseHost speech=$SpeechHost"
if ($Scenario -eq "DatabaseSalvage") {
    Write-Output "source database=$SourceDatabaseHost"
}
Write-Output "DR kit exported at $($kit.exported_at_utc)"

Test-SshHost $GatewayHost $SshUser
Test-SshHost $DatabaseHost $SshUser
Test-SshHost $SpeechHost $SshUser
if ($Scenario -eq "DatabaseSalvage") {
    Test-SshHost $SourceDatabaseHost $SourceSshUser
    Invoke-Remote $SourceDatabaseHost $SourceSshUser `
        "systemctl is-active --quiet postgresql && sudo -u postgres psql -At -d postgres -c `"SELECT 1 FROM pg_database WHERE datname='${DatabaseName}'`" | grep -qx 1"
    $sourcePostgresMajor = [int](
        Invoke-Remote $SourceDatabaseHost $SourceSshUser `
            "pg_dump --version | awk '{print `$3}' | cut -d. -f1"
    )
}
Assert-DisposableTargets

if ($DryRun) {
    Write-Output "Dry-run completed. No target host was changed."
    exit 0
}

$workRoot = [IO.Path]::GetFullPath((Join-Path $RepoRoot ".dr\work"))
[IO.Directory]::CreateDirectory($workRoot) | Out-Null
$recoveryId = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$workDirectory = Join-Path $workRoot $recoveryId
[IO.Directory]::CreateDirectory($workDirectory) | Out-Null
$gatewayEnvironmentPath = Join-Path $workDirectory "gateway.env"
$speechEnvironmentPath = Join-Path $workDirectory "speech.env"
$speechRuntimePath = Join-Path $workDirectory "runtime.env"
$passwordPath = Join-Path $workDirectory "database-password"
$dumpPath = Join-Path $workDirectory "family_ai.dump"
$sourceManifestPath = Join-Path $workDirectory "source.manifest"
$remoteDump = "/tmp/family-ai-${recoveryId}.dump"

try {
    [IO.File]::WriteAllText(
        $gatewayEnvironmentPath,
        (ConvertTo-EnvText $gatewayValues),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $speechEnvironmentPath,
        (ConvertTo-EnvText $speechValues),
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $speechRuntimePath,
        ([string]$kit.speech_runtime_environment).TrimEnd() + "`n",
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $passwordPath,
        $databaseSettings.Password,
        [Text.UTF8Encoding]::new($false)
    )

    if ($Scenario -eq "DatabaseSalvage") {
        $sourceRemoteDirectory = "/tmp/family-ai-dr"
        Invoke-Remote $SourceDatabaseHost $SourceSshUser `
            "rm -rf '$sourceRemoteDirectory' && mkdir -p '$sourceRemoteDirectory'"
        foreach ($asset in @("database_manifest.sh", "create_database_snapshot.sh")) {
            Copy-ToRemote `
                (Join-Path $RemoteAssets $asset) `
                $SourceDatabaseHost `
                $SourceSshUser `
                "$sourceRemoteDirectory/$asset"
        }
        Invoke-Remote $SourceDatabaseHost $SourceSshUser `
            "chmod 0700 '$sourceRemoteDirectory/'*.sh"
        Invoke-ElevatedScript `
            $SourceDatabaseHost `
            $SourceSshUser `
            "$sourceRemoteDirectory/create_database_snapshot.sh" `
            @($remoteDump, $SourceSshUser, $DatabaseName)
        Copy-FromRemote $SourceDatabaseHost $SourceSshUser $remoteDump $dumpPath
        Copy-FromRemote `
            $SourceDatabaseHost `
            $SourceSshUser `
            "${remoteDump}.manifest" `
            $sourceManifestPath
        $expectedDumpSha = (
            Invoke-Remote $SourceDatabaseHost $SourceSshUser "cat '${remoteDump}.sha256'"
        ).Trim()
        $dumpBytes = [long](
            Invoke-Remote $SourceDatabaseHost $SourceSshUser "stat -c %s '$remoteDump'"
        )
        $workDrive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($workDirectory))
        if ($workDrive.AvailableFreeSpace -lt ($dumpBytes * 2)) {
            throw "Workstation does not have twice the dump size in free space"
        }
        $targetFreeBytes = [long](
            Invoke-Remote $DatabaseHost $SshUser `
                "df -PB1 / | tail -1 | awk '{print `$4}'"
        )
        if ($targetFreeBytes -lt ($dumpBytes * 2)) {
            throw "Target database host does not have twice the dump size in free space"
        }
        $localDumpSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $dumpPath).Hash.ToLower()
        if ($localDumpSha -ne $expectedDumpSha) {
            throw "Downloaded database dump checksum mismatch"
        }
        Write-Output "Source database snapshot captured and verified."
    }

    foreach ($target in @(
        @{ Host = $GatewayHost; Role = "gateway" },
        @{ Host = $DatabaseHost; Role = "database" },
        @{ Host = $SpeechHost; Role = "speech" }
    )) {
        $bootstrap = "/tmp/family-ai-bootstrap-host.sh"
        Copy-ToRemote `
            (Join-Path $RemoteAssets "bootstrap_host.sh") `
            $target.Host `
            $SshUser `
            $bootstrap
        Invoke-ElevatedScript `
            $target.Host `
            $SshUser `
            $bootstrap `
            @($target.Role, $ServiceUser, $target.Host)
    }
    if ($Scenario -eq "DatabaseSalvage") {
        $targetPostgresMajor = [int](
            Invoke-Remote $DatabaseHost $SshUser `
                "pg_restore --version | awk '{print `$3}' | cut -d. -f1"
        )
        if ($targetPostgresMajor -lt $sourcePostgresMajor) {
            throw "Target PostgreSQL major version is older than the source"
        }
    }

    Install-Configuration `
        $gatewayEnvironmentPath `
        $GatewayHost `
        $SshUser `
        "/etc/family-ai/gateway.env" `
        $ServiceUser
    Install-Configuration `
        $speechEnvironmentPath `
        $SpeechHost `
        $SshUser `
        "/etc/family-ai/speech.env" `
        $ServiceUser
    Install-Configuration `
        $speechRuntimePath `
        $SpeechHost `
        $SshUser `
        "/var/lib/family-ai-speech/runtime.env" `
        $ServiceUser

    Copy-ToRemote $passwordPath $DatabaseHost $SshUser "/tmp/family-ai-db-password"
    Copy-ToRemote `
        (Join-Path $RemoteAssets "configure_postgres.sh") `
        $DatabaseHost `
        $SshUser `
        "/tmp/configure_postgres.sh"
    Invoke-ElevatedScript `
        $DatabaseHost `
        $SshUser `
        "/tmp/configure_postgres.sh" `
        @(
            $DatabaseHost,
            $GatewayHost,
            "/tmp/family-ai-db-password",
            $DatabaseRole,
            $DatabaseName
        )

    if ($Scenario -eq "DatabaseSalvage") {
        Copy-ToRemote $dumpPath $DatabaseHost $SshUser $remoteDump
        Invoke-Remote $DatabaseHost $SshUser "chmod 0600 '$remoteDump'"
        foreach ($asset in @("database_manifest.sh", "restore_database_snapshot.sh")) {
            Copy-ToRemote `
                (Join-Path $RemoteAssets $asset) `
                $DatabaseHost `
                $SshUser `
                "/tmp/$asset"
        }
        Invoke-ElevatedScript `
            $DatabaseHost `
            $SshUser `
            "/tmp/restore_database_snapshot.sh" `
            @($remoteDump, $expectedDumpSha, $DatabaseName, $DatabaseRole)
        $targetManifest = Invoke-Remote $DatabaseHost $SshUser `
            "sudo bash /tmp/database_manifest.sh '$DatabaseName'"
        $sourceManifest = Get-Content -LiteralPath $sourceManifestPath
        if (Compare-Object $sourceManifest $targetManifest) {
            throw "Restored database manifest differs from the source snapshot"
        }
        Write-Output "Restored database row counts and schema version match the source."
    }

    & $ReleaseScript prepare gateway `
        -HostName $GatewayHost `
        -Commit $fullCommit `
        -SshUser $SshUser `
        -ServiceUser $ServiceUser `
        -IdentityFile $IdentityFile
    if ($LASTEXITCODE -ne 0) { throw "Gateway prepare failed" }

    & $ReleaseScript prepare speech `
        -HostName $SpeechHost `
        -Commit $fullCommit `
        -SshUser $SshUser `
        -ServiceUser $ServiceUser `
        -IdentityFile $IdentityFile
    if ($LASTEXITCODE -ne 0) { throw "Speech prepare failed" }

    & $ReleaseScript migrate gateway `
        -HostName $GatewayHost `
        -TargetVersion $fullCommit `
        -SshUser $SshUser `
        -ServiceUser $ServiceUser `
        -IdentityFile $IdentityFile
    if ($LASTEXITCODE -ne 0) { throw "Gateway migration failed" }

    & $ReleaseScript activate speech `
        -HostName $SpeechHost `
        -TargetVersion $fullCommit `
        -SshUser $SshUser `
        -ServiceUser $ServiceUser `
        -IdentityFile $IdentityFile
    if ($LASTEXITCODE -ne 0) { throw "Speech activation failed" }

    Copy-ToRemote `
        (Join-Path $RepoRoot "scripts\speech\install-admin-control.sh") `
        $SpeechHost `
        $SshUser `
        "/tmp/install-speech-admin-control.sh"
    Invoke-ElevatedScript `
        $SpeechHost `
        $SshUser `
        "/tmp/install-speech-admin-control.sh" `
        @($ServiceUser)

    & $ReleaseScript activate gateway `
        -HostName $GatewayHost `
        -TargetVersion $fullCommit `
        -SshUser $SshUser `
        -ServiceUser $ServiceUser `
        -IdentityFile $IdentityFile
    if ($LASTEXITCODE -ne 0) { throw "Gateway activation failed" }

    Copy-ToRemote `
        (Join-Path $RepoRoot "infrastructure\sudoers\family-ai-admin") `
        $GatewayHost `
        $SshUser `
        "/tmp/family-ai-admin.sudoers"
    Invoke-Remote $GatewayHost $SshUser `
        "sudo install -o root -g root -m 0440 /tmp/family-ai-admin.sudoers /etc/sudoers.d/family-ai-admin && sudo visudo -cf /etc/sudoers.d/family-ai-admin >/dev/null && rm -f /tmp/family-ai-admin.sudoers"

    Invoke-Remote $GatewayHost $SshUser `
        "timeout 90 bash -c 'until curl --silent --fail http://127.0.0.1:8000/healthz >/dev/null && curl --silent --fail http://127.0.0.1:8001/api/healthz >/dev/null; do sleep 2; done'"
    Invoke-Remote $SpeechHost $SshUser `
        "timeout 300 bash -c 'until curl --silent --fail http://127.0.0.1:8010/healthz >/dev/null; do sleep 2; done'"
    Invoke-Remote $DatabaseHost $SshUser `
        "sudo -u postgres psql -At -d '$DatabaseName' -c 'SELECT version_num FROM alembic_version' >/dev/null"

    foreach ($target in @(
        @{ Host = $DatabaseHost; Role = "database" },
        @{ Host = $SpeechHost; Role = "speech" }
    )) {
        Copy-ToRemote `
            (Join-Path $RemoteAssets "harden_network.sh") `
            $target.Host `
            $SshUser `
            "/tmp/harden_network.sh"
        Invoke-ElevatedScript `
            $target.Host `
            $SshUser `
            "/tmp/harden_network.sh" `
            @($target.Role, $GatewayHost)
    }
    Invoke-Remote $GatewayHost $SshUser `
        "curl --silent --show-error --fail 'http://${SpeechHost}:8010/healthz' >/dev/null && timeout 5 bash -c '</dev/tcp/${DatabaseHost}/5432'"

    $reportDirectory = Join-Path $RepoRoot ".dr\reports"
    [IO.Directory]::CreateDirectory($reportDirectory) | Out-Null
    $reportPath = Join-Path $reportDirectory "$recoveryId.json"
    $report = [ordered]@{
        schema = "family-ai/dr-report/v1"
        recovery_id = $recoveryId
        scenario = $Scenario
        commit = $fullCommit
        started_at_utc = $StartedAt.ToString("o")
        completed_at_utc = [DateTime]::UtcNow.ToString("o")
        gateway_host = $GatewayHost
        database_host = $DatabaseHost
        speech_host = $SpeechHost
        source_database_host = if ($Scenario -eq "DatabaseSalvage") {
            $SourceDatabaseHost
        } else {
            $null
        }
        status = "success"
    }
    [IO.File]::WriteAllText(
        $reportPath,
        ($report | ConvertTo-Json -Depth 4),
        [Text.UTF8Encoding]::new($false)
    )
    Write-Output "Recovery completed successfully."
    Write-Output "Report: $reportPath"
} finally {
    if ($Scenario -eq "DatabaseSalvage") {
        try {
            Invoke-Remote $SourceDatabaseHost $SourceSshUser `
                "rm -f '$remoteDump' '${remoteDump}.before' '${remoteDump}.manifest' '${remoteDump}.sha256'; rm -rf /tmp/family-ai-dr" 2>$null
        } catch {
            Write-Warning "Could not clean temporary source database files."
        }
        try {
            Invoke-Remote $DatabaseHost $SshUser "rm -f '$remoteDump'" 2>$null
        } catch {
            Write-Warning "Could not clean the temporary target database dump."
        }
    }
    if (Test-Path -LiteralPath $workDirectory) {
        $resolvedWork = [IO.Path]::GetFullPath($workDirectory)
        if (-not $resolvedWork.StartsWith($workRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove unexpected work directory: $resolvedWork"
        }
        Remove-Item -LiteralPath $resolvedWork -Recurse -Force
    }
}
