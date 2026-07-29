[CmdletBinding()]
param(
    [string]$Commit = "HEAD",
    [string]$SigningProperties = "$env:USERPROFILE\.family-ai\android-signing\key.properties",
    [string]$OutputDirectory = ".artifacts\android"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Flutter = Join-Path $RepoRoot ".tools\flutter\bin\flutter.bat"
$JavaHome = Join-Path $RepoRoot ".tools\jdk-17.0.19+10"
$AndroidSdk = Join-Path $RepoRoot ".tools\android-sdk"
$BuildTools = Get-ChildItem `
    -LiteralPath (Join-Path $AndroidSdk "build-tools") `
    -Directory |
    Sort-Object Name -Descending |
    Select-Object -First 1
$ApkSigner = if ($BuildTools) {
    Join-Path $BuildTools.FullName "apksigner.bat"
}
$Aapt = if ($BuildTools) {
    Join-Path $BuildTools.FullName "aapt.exe"
}

foreach ($RequiredPath in @(
    $Flutter,
    (Join-Path $JavaHome "bin\java.exe"),
    $ApkSigner,
    $Aapt,
    $SigningProperties
)) {
    if (-not $RequiredPath -or -not (Test-Path -LiteralPath $RequiredPath)) {
        throw "Required Android build input was not found: $RequiredPath"
    }
}

$ExpectedSignerLine = Get-Content -LiteralPath $SigningProperties |
    Where-Object { $_ -match "^certificateSha256=([0-9a-fA-F]{64})$" } |
    Select-Object -First 1
if ($ExpectedSignerLine -notmatch "^certificateSha256=([0-9a-fA-F]{64})$") {
    throw "External signing properties do not contain certificateSha256"
}
$ExpectedSignerDigest = $Matches[1].ToLowerInvariant()

function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$Command,
        [string[]]$Arguments = @()
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

function Invoke-NativeCapture {
    param(
        [Parameter(Mandatory)][string]$Command,
        [string[]]$Arguments = @()
    )
    $Output = & $Command @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
    return $Output
}

$ResolvedCommit = (
    Invoke-NativeCapture "git" @(
        "-C", $RepoRoot, "rev-parse", "--verify", "$Commit^{commit}"
    ) |
    Select-Object -Last 1
).Trim()
if ($ResolvedCommit -notmatch "^[0-9a-f]{40}$") {
    throw "Git did not resolve an exact commit: $Commit"
}

$ArtifactsRoot = [IO.Path]::GetFullPath(
    (Join-Path $RepoRoot ".artifacts")
)
$BuildRoot = [IO.Path]::GetFullPath(
    (Join-Path $ArtifactsRoot "mobile-build\$ResolvedCommit")
)
$ResolvedOutputDirectory = [IO.Path]::GetFullPath(
    (Join-Path $RepoRoot $OutputDirectory)
)
if (
    -not $BuildRoot.StartsWith(
        "$ArtifactsRoot$([IO.Path]::DirectorySeparatorChar)",
        [StringComparison]::OrdinalIgnoreCase
    )
) {
    throw "Unsafe temporary build path: $BuildRoot"
}
if (Test-Path -LiteralPath $BuildRoot) {
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force
}
[IO.Directory]::CreateDirectory($BuildRoot) | Out-Null
[IO.Directory]::CreateDirectory($ResolvedOutputDirectory) | Out-Null

$ArchivePath = Join-Path $BuildRoot "source.zip"
$SourceRoot = Join-Path $BuildRoot "source"
try {
    Invoke-Native "git" @(
        "-C", $RepoRoot,
        "archive",
        "--format=zip",
        "--output=$ArchivePath",
        $ResolvedCommit
    )
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $SourceRoot

    $MobileRoot = Join-Path $SourceRoot "mobile"
    $LocalPropertiesPath = Join-Path $MobileRoot "android\local.properties"
    $LocalProperties = @(
        "sdk.dir=$($AndroidSdk.Replace('\', '/'))",
        "flutter.sdk=$((Join-Path $RepoRoot '.tools\flutter').Replace('\', '/'))"
    ) -join "`n"
    [IO.File]::WriteAllText(
        $LocalPropertiesPath,
        "$LocalProperties`n",
        [Text.UTF8Encoding]::new($false)
    )

    $PreviousEnvironment = @{
        ANDROID_HOME = $env:ANDROID_HOME
        ANDROID_SDK_ROOT = $env:ANDROID_SDK_ROOT
        FAMILY_AI_ANDROID_SIGNING_PROPERTIES = (
            $env:FAMILY_AI_ANDROID_SIGNING_PROPERTIES
        )
        JAVA_HOME = $env:JAVA_HOME
        PUB_CACHE = $env:PUB_CACHE
    }
    try {
        $env:ANDROID_HOME = $AndroidSdk
        $env:ANDROID_SDK_ROOT = $AndroidSdk
        $env:FAMILY_AI_ANDROID_SIGNING_PROPERTIES = (
            [IO.Path]::GetFullPath($SigningProperties)
        )
        $env:JAVA_HOME = $JavaHome
        $env:PUB_CACHE = Join-Path $RepoRoot ".tools\pub-cache"

        Push-Location $MobileRoot
        try {
            Invoke-Native $Flutter @("pub", "get")
            Invoke-Native $Flutter @("build", "apk", "--release")
        } finally {
            Pop-Location
        }
    } finally {
        foreach ($Name in $PreviousEnvironment.Keys) {
            $Value = $PreviousEnvironment[$Name]
            if ($null -eq $Value) {
                Remove-Item "Env:\$Name" -ErrorAction SilentlyContinue
            } else {
                Set-Item "Env:\$Name" $Value
            }
        }
    }

    $BuiltApk = Join-Path $MobileRoot (
        "build\app\outputs\flutter-apk\app-release.apk"
    )
    if (-not (Test-Path -LiteralPath $BuiltApk -PathType Leaf)) {
        throw "Flutter did not create the expected release APK"
    }

    $VersionLine = Get-Content `
        -LiteralPath (Join-Path $MobileRoot "pubspec.yaml") |
        Where-Object { $_ -match "^version:\s*(\S+)\s*$" } |
        Select-Object -First 1
    if ($VersionLine -notmatch "^version:\s*(\S+)\s*$") {
        throw "Cannot determine Android version from pubspec.yaml"
    }
    $Version = $Matches[1]
    $ShortCommit = $ResolvedCommit.Substring(0, 8)
    $ArtifactName = "family-ai-$Version-$ShortCommit-release.apk"
    $ArtifactPath = Join-Path $ResolvedOutputDirectory $ArtifactName
    Copy-Item -LiteralPath $BuiltApk -Destination $ArtifactPath -Force

    $PreviousJavaHome = $env:JAVA_HOME
    try {
        $env:JAVA_HOME = $JavaHome
        $SignerOutput = Invoke-NativeCapture $ApkSigner @(
            "verify", "--verbose", "--print-certs", $ArtifactPath
        )
    } finally {
        if ($null -eq $PreviousJavaHome) {
            Remove-Item Env:\JAVA_HOME -ErrorAction SilentlyContinue
        } else {
            $env:JAVA_HOME = $PreviousJavaHome
        }
    }
    $BadgingOutput = Invoke-NativeCapture $Aapt @(
        "dump", "badging", $ArtifactPath
    )
    $PackageLine = $BadgingOutput |
        Where-Object { $_ -match "^package: name='([^']+)'" } |
        Select-Object -First 1
    if ($PackageLine -notmatch "^package: name='([^']+)'") {
        throw "Cannot read package name from release APK"
    }
    $PackageName = $Matches[1]
    if ($PackageName -ne "ru.familyai.mentor") {
        throw "Unexpected Android package name: $PackageName"
    }
    $SignerLine = $SignerOutput |
        Where-Object { $_ -match "certificate SHA-256 digest:\s*(\S+)" } |
        Select-Object -First 1
    if ($SignerLine -notmatch "certificate SHA-256 digest:\s*(\S+)") {
        throw "Cannot read signer certificate digest from release APK"
    }
    $SignerDigest = $Matches[1].ToLowerInvariant()
    if ($SignerDigest -ne $ExpectedSignerDigest) {
        throw "Release APK was signed by an unexpected certificate"
    }
    $ArtifactHash = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash

    $Manifest = [ordered]@{
        schema = "family-ai/android-release/v1"
        source_commit = $ResolvedCommit
        version = $Version
        package_name = $PackageName
        artifact = $ArtifactName
        artifact_sha256 = $ArtifactHash
        signer_certificate_sha256 = $SignerDigest
        built_at_utc = [DateTime]::UtcNow.ToString("o")
    }
    $ManifestPath = "$ArtifactPath.json"
    $ChecksumPath = "$ArtifactPath.sha256"
    [IO.File]::WriteAllText(
        $ManifestPath,
        ($Manifest | ConvertTo-Json -Depth 4) + "`n",
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::WriteAllText(
        $ChecksumPath,
        "$ArtifactHash  $ArtifactName`n",
        [Text.Encoding]::ASCII
    )

    Write-Output "Android release built from $ResolvedCommit"
    Write-Output "APK: $ArtifactPath"
    Write-Output "SHA-256: $ArtifactHash"
    Write-Output "Signer certificate SHA-256: $SignerDigest"
} finally {
    $GradleWrapper = Join-Path $BuildRoot "source\mobile\android\gradlew.bat"
    if (Test-Path -LiteralPath $GradleWrapper -PathType Leaf) {
        $PreviousJavaHome = $env:JAVA_HOME
        try {
            $env:JAVA_HOME = $JavaHome
            Push-Location (Split-Path -Parent $GradleWrapper)
            try {
                & $GradleWrapper --stop *> $null
            } finally {
                Pop-Location
            }
        } finally {
            if ($null -eq $PreviousJavaHome) {
                Remove-Item Env:\JAVA_HOME -ErrorAction SilentlyContinue
            } else {
                $env:JAVA_HOME = $PreviousJavaHome
            }
        }
    }
    if (
        (Test-Path -LiteralPath $BuildRoot) -and
        $BuildRoot.StartsWith(
            "$ArtifactsRoot$([IO.Path]::DirectorySeparatorChar)",
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        $CleanupError = $null
        foreach ($Attempt in 1..5) {
            try {
                Remove-Item -LiteralPath $BuildRoot -Recurse -Force
                $CleanupError = $null
                break
            } catch {
                $CleanupError = $_
                Start-Sleep -Milliseconds (250 * $Attempt)
            }
        }
        if ($null -ne $CleanupError) {
            throw $CleanupError
        }
    }
}
