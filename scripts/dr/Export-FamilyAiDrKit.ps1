[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$GatewayHost,

    [Parameter(Mandatory)]
    [string]$SpeechHost,

    [string]$GatewaySshUser = "familyai-deploy",
    [string]$SpeechSshUser = "familyai-deploy",
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\family-ai-deploy",
    [string]$OutputPath = ".dr\family-ai-dr-kit.dpapi"
)

$ErrorActionPreference = "Stop"
$Entropy = [Text.Encoding]::UTF8.GetBytes("family-ai/dr-kit/v1")
Add-Type -AssemblyName System.Security

if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") {
    throw "DPAPI DR-kit export is supported only on Windows"
}
if (-not (Test-Path -LiteralPath $IdentityFile)) {
    throw "SSH identity file not found: $IdentityFile"
}

function Read-RemoteFile {
    param(
        [string]$HostName,
        [string]$UserName,
        [string]$Path,
        [switch]$Optional
    )

    $remote = "$UserName@$HostName"
    $command = if ($Optional) {
        "if [ -r '$Path' ]; then cat '$Path'; elif sudo -n test -r '$Path' 2>/dev/null; then sudo -n cat '$Path'; fi"
    } else {
        "if [ -r '$Path' ]; then cat '$Path'; else sudo -n cat '$Path'; fi"
    }
    $content = & ssh -i $IdentityFile -o BatchMode=yes $remote $command
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot read required DR configuration from $remote`:$Path"
    }
    return ($content -join "`n").TrimEnd()
}

$gatewayEnvironment = Read-RemoteFile `
    -HostName $GatewayHost `
    -UserName $GatewaySshUser `
    -Path "/etc/family-ai/gateway.env"
$speechEnvironment = Read-RemoteFile `
    -HostName $SpeechHost `
    -UserName $SpeechSshUser `
    -Path "/etc/family-ai/speech.env"
$speechRuntimeEnvironment = Read-RemoteFile `
    -HostName $SpeechHost `
    -UserName $SpeechSshUser `
    -Path "/var/lib/family-ai-speech/runtime.env" `
    -Optional

if ($gatewayEnvironment -notmatch "(?m)^FAMILY_AI_DATABASE_URL=.+$") {
    throw "Gateway environment does not contain FAMILY_AI_DATABASE_URL"
}
if ($gatewayEnvironment -notmatch "(?m)^FAMILY_AI_OPENAI_API_KEY=.+$") {
    throw "Gateway environment does not contain FAMILY_AI_OPENAI_API_KEY"
}
if (-not $speechEnvironment) {
    throw "Speech environment is empty"
}

$payload = [ordered]@{
    schema = "family-ai/dr-kit/v1"
    exported_at_utc = [DateTime]::UtcNow.ToString("o")
    source_gateway_host = $GatewayHost
    source_speech_host = $SpeechHost
    gateway_environment = $gatewayEnvironment
    speech_environment = $speechEnvironment
    speech_runtime_environment = $speechRuntimeEnvironment
}
$plainBytes = [Text.Encoding]::UTF8.GetBytes(
    ($payload | ConvertTo-Json -Depth 4 -Compress)
)
try {
    $protectedBytes = [System.Security.Cryptography.ProtectedData]::Protect(
        $plainBytes,
        $Entropy,
        [System.Security.Cryptography.DataProtectionScope]::CurrentUser
    )
} finally {
    [Array]::Clear($plainBytes, 0, $plainBytes.Length)
}

$resolvedOutput = [IO.Path]::GetFullPath(
    (Join-Path (Get-Location) $OutputPath)
)
$outputDirectory = Split-Path -Parent $resolvedOutput
[IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
[IO.File]::WriteAllText(
    $resolvedOutput,
    [Convert]::ToBase64String($protectedBytes),
    [Text.Encoding]::ASCII
)

Write-Output "Encrypted DR kit created: $resolvedOutput"
Write-Output "It can be decrypted only by the current Windows user on this computer."
