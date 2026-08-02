[CmdletBinding()]
param(
    [switch]$UpdateBaselines,
    [string]$BrowserPath = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$AdminScript = Join-Path $PSScriptRoot "Test-AdminVisualRegression.ps1"
$Flutter = Join-Path $RepoRoot ".tools\flutter\bin\flutter.bat"

if (-not (Test-Path -LiteralPath $Flutter)) {
    throw "Project Flutter SDK was not found: $Flutter"
}

$AdminArguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $AdminScript)
if ($UpdateBaselines) {
    $AdminArguments += "-UpdateBaselines"
}
if ($BrowserPath) {
    $AdminArguments += @("-BrowserPath", $BrowserPath)
}
& powershell.exe @AdminArguments
if ($LASTEXITCODE -ne 0) {
    throw "Admin visual regression failed"
}

Push-Location (Join-Path $RepoRoot "mobile")
try {
    $FlutterArguments = @("test")
    if ($UpdateBaselines) {
        $FlutterArguments += "--update-goldens"
    }
    $FlutterArguments += "test\visual\mobile_visual_test.dart"
    & $Flutter @FlutterArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Android visual regression failed"
    }
} finally {
    Pop-Location
}

Write-Output "Admin and Android visual regressions passed."
