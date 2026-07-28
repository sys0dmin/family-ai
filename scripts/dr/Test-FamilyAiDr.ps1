$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "FamilyAiDr.Common.psm1") -Force
Initialize-FamilyAiDr -IdentityFile "unused-in-local-tests"

$environment = ConvertFrom-EnvText @"
FAMILY_AI_DATABASE_URL=postgresql+psycopg://family_ai:p%40ss@192.168.31.163:5432/family_ai
FAMILY_AI_TTS_MODEL=silero-v5_2-ru
"@
if ($environment["FAMILY_AI_TTS_MODEL"] -ne "silero-v5_2-ru") {
    throw "Environment parser self-test failed"
}

$database = Resolve-DatabaseSettings `
    $environment["FAMILY_AI_DATABASE_URL"] `
    "192.168.31.181"
if ($database.Username -ne "family_ai" -or
    $database.Password -ne "p@ss" -or
    $database.DatabaseName -ne "family_ai" -or
    $database.SourceHost -ne "192.168.31.163" -or
    $database.RewrittenUrl -notmatch "@192\.168\.31\.181:5432/") {
    throw "Database URL rewrite self-test failed"
}

$roundTrip = ConvertFrom-EnvText (ConvertTo-EnvText $environment)
if ($roundTrip["FAMILY_AI_DATABASE_URL"] -ne
    $environment["FAMILY_AI_DATABASE_URL"]) {
    throw "Environment round-trip self-test failed"
}

Write-Output "Family AI DR local self-test passed."
