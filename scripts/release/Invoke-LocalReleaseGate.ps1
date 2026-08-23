[CmdletBinding()]
param(
    [string]$Commit = "HEAD",
    [string]$BrowserPath = "",
    [string]$MigrationAdminDatabaseUrl = $env:FAMILY_AI_MIGRATION_TEST_ADMIN_URL
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Uv = Join-Path $RepoRoot ".venv\Scripts\uv.exe"
$Flutter = Join-Path $RepoRoot ".tools\flutter\bin\flutter.bat"
$Results = [Collections.Generic.List[object]]::new()
$StartedAt = [DateTimeOffset]::UtcNow
$Failure = $null

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project Python environment was not found: $Python"
}
if (-not (Test-Path -LiteralPath $Uv)) {
    throw "Project uv executable was not found: $Uv"
}
if (-not (Test-Path -LiteralPath $Flutter)) {
    throw "Project Flutter SDK was not found: $Flutter"
}

$ResolvedCommit = (& git -C $RepoRoot rev-parse --verify "$Commit^{commit}").Trim()
if ($LASTEXITCODE -ne 0 -or $ResolvedCommit -notmatch "^[0-9a-f]{40}$") {
    throw "Cannot resolve Git commit: $Commit"
}
$HeadCommit = (& git -C $RepoRoot rev-parse HEAD).Trim()
if ($ResolvedCommit -ne $HeadCommit) {
    throw "Release gate tests the checked-out commit only: HEAD=$HeadCommit, requested=$ResolvedCommit"
}

$ArtifactRoot = Join-Path $RepoRoot ".artifacts\release-gate\$ResolvedCommit"
New-Item -ItemType Directory -Force -Path $ArtifactRoot | Out-Null
$ReportPath = Join-Path $ArtifactRoot "gate.json"

function Invoke-GateStage {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][scriptblock]$Action
    )
    $Timer = [Diagnostics.Stopwatch]::StartNew()
    Write-Host "[RUN] $Name"
    try {
        $global:LASTEXITCODE = 0
        & $Action
        if ($LASTEXITCODE -ne 0) {
            throw "$Name exited with code $LASTEXITCODE"
        }
        $Timer.Stop()
        $Results.Add([ordered]@{
            name = $Name
            status = "passed"
            duration_ms = $Timer.ElapsedMilliseconds
        })
        Write-Host "[PASSED] $Name $($Timer.ElapsedMilliseconds)ms"
    } catch {
        $Timer.Stop()
        $Results.Add([ordered]@{
            name = $Name
            status = "failed"
            duration_ms = $Timer.ElapsedMilliseconds
        })
        throw
    }
}

function Add-GateSkipped {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Reason
    )
    $Results.Add([ordered]@{
        name = $Name
        status = "skipped"
        duration_ms = 0
        reason = $Reason
    })
    Write-Warning "[SKIPPED] $Name - $Reason"
}

try {
    Invoke-GateStage "working_tree_clean" {
        $Changes = @(& git -C $RepoRoot status --porcelain)
        if ($LASTEXITCODE -ne 0) {
            throw "Git failed to inspect the working tree"
        }
        if ($Changes.Count -ne 0) {
            throw "Release gate requires a clean working tree"
        }
    }
    Invoke-GateStage "repository_policy" {
        & $Python (Join-Path $PSScriptRoot "repository_policy.py") `
            --repo $RepoRoot
    }
    Invoke-GateStage "diff_check" {
        & git -C $RepoRoot show --check --format= $ResolvedCommit
    }
    Invoke-GateStage "gateway_lock" {
        Push-Location $RepoRoot
        try {
            & $Uv lock --check
        } finally {
            Pop-Location
        }
    }
    Invoke-GateStage "speech_lock" {
        Push-Location (Join-Path $RepoRoot "speech")
        try {
            & $Uv lock --check
        } finally {
            Pop-Location
        }
    }
    Invoke-GateStage "character_assets" {
        & $Python (Join-Path $RepoRoot "scripts\assets\sync_character_assets.py") `
            --repo $RepoRoot
    }
    Invoke-GateStage "dependency_audit" {
        & $Python (Join-Path $PSScriptRoot "audit_dependencies.py") `
            --repo $RepoRoot --uv $Uv
    }
    Invoke-GateStage "ruff" {
        & $Python -m ruff check gateway alembic scripts speech
    }
    Invoke-GateStage "gateway_tests" {
        & $Python -m pytest -q
    }
    Invoke-GateStage "speech_tests" {
        Push-Location (Join-Path $RepoRoot "speech")
        try {
            & $Python -m pytest tests -q
        } finally {
            Pop-Location
        }
    }
    Invoke-GateStage "flutter_analyze" {
        Push-Location (Join-Path $RepoRoot "mobile")
        try {
            & $Flutter analyze --no-pub
        } finally {
            Pop-Location
        }
    }
    Invoke-GateStage "flutter_tests" {
        Push-Location (Join-Path $RepoRoot "mobile")
        try {
            & $Flutter test --no-pub
        } finally {
            Pop-Location
        }
    }
    Invoke-GateStage "admin_visual" {
        $Arguments = @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            (Join-Path $RepoRoot "scripts\visual\Test-AdminVisualRegression.ps1")
        )
        if ($BrowserPath) {
            $Arguments += @("-BrowserPath", $BrowserPath)
        }
        & powershell.exe @Arguments
    }
    Invoke-GateStage "markdown_links" {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
            (Join-Path $RepoRoot "scripts\docs\Test-MarkdownLinks.ps1") `
            -Root $RepoRoot
    }
    Invoke-GateStage "alembic_head" {
        $Heads = @(& $Python -m alembic -c (Join-Path $RepoRoot "alembic.ini") heads)
        if ($LASTEXITCODE -ne 0) {
            throw "Alembic failed to resolve heads"
        }
        $HeadLines = @($Heads | Where-Object { $_ -match "\(head\)" })
        if ($HeadLines.Count -ne 1) {
            throw "Expected exactly one Alembic head, got $($HeadLines.Count)"
        }
        Write-Host $HeadLines[0]
    }
    if ($MigrationAdminDatabaseUrl) {
        Invoke-GateStage "postgres_migrations" {
            $PreviousMigrationUrl = $env:FAMILY_AI_MIGRATION_TEST_ADMIN_URL
            try {
                $env:FAMILY_AI_MIGRATION_TEST_ADMIN_URL = $MigrationAdminDatabaseUrl
                & $Python (Join-Path $PSScriptRoot "test_postgres_migrations.py") `
                    --repo $RepoRoot
            } finally {
                $env:FAMILY_AI_MIGRATION_TEST_ADMIN_URL = $PreviousMigrationUrl
            }
        }
    } else {
        Add-GateSkipped "postgres_migrations" `
            "set FAMILY_AI_MIGRATION_TEST_ADMIN_URL to execute the disposable database test"
    }
    Invoke-GateStage "release_archives" {
        foreach ($Component in @("gateway", "speech")) {
            $Output = Join-Path $ArtifactRoot "$Component.tar.gz"
            & $Python (Join-Path $RepoRoot "scripts\deploy\build_release.py") `
                $Component --commit $ResolvedCommit --output $Output --repo $RepoRoot
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Output)) {
                throw "Failed to build $Component release archive"
            }
        }
    }
    Invoke-GateStage "final_repository_policy" {
        & $Python (Join-Path $PSScriptRoot "repository_policy.py") `
            --repo $RepoRoot
    }
} catch {
    $Failure = $_.Exception.Message
    throw
} finally {
    $FinishedAt = [DateTimeOffset]::UtcNow
    $Status = if ($Failure) { "failed" } else { "passed" }
    $Report = [ordered]@{
        schema = "family-ai/local-release-gate/v1"
        status = $Status
        commit = $ResolvedCommit
        started_at_utc = $StartedAt.ToString("O")
        finished_at_utc = $FinishedAt.ToString("O")
        duration_ms = [int]($FinishedAt - $StartedAt).TotalMilliseconds
        stages = $Results
    }
    if ($Failure) {
        $Report.failure = $Failure
    }
    $Report | ConvertTo-Json -Depth 6 | Set-Content `
        -LiteralPath $ReportPath -Encoding UTF8
    Write-Host "Release gate report: $ReportPath"
}

Write-Host "Local release gate passed for $ResolvedCommit"
