[CmdletBinding()]
param(
    [string]$SigningDirectory = "$env:USERPROFILE\.family-ai\android-signing",
    [string]$RecoveryKitPath = ".dr\android-signing-kit.dpapi",
    [string]$KeyAlias = "family-ai",
    [string]$DistinguishedName = "CN=Family AI Mentor, OU=Home, O=Family AI, L=Moscow, C=RU"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Keytool = Join-Path $RepoRoot ".tools\jdk-17.0.19+10\bin\keytool.exe"
$Entropy = [Text.Encoding]::UTF8.GetBytes("family-ai/android-signing/v1")

if (-not (Test-Path -LiteralPath $Keytool)) {
    throw "Bundled JDK keytool was not found: $Keytool"
}
if ($KeyAlias -notmatch "^[a-zA-Z0-9_.-]+$") {
    throw "KeyAlias contains unsupported characters"
}

$ResolvedSigningDirectory = [IO.Path]::GetFullPath($SigningDirectory)
$KeystorePath = Join-Path $ResolvedSigningDirectory "family-ai-release.p12"
$PropertiesPath = Join-Path $ResolvedSigningDirectory "key.properties"
$ResolvedRecoveryKit = [IO.Path]::GetFullPath(
    (Join-Path $RepoRoot $RecoveryKitPath)
)

if (
    (Test-Path -LiteralPath $KeystorePath) -or
    (Test-Path -LiteralPath $PropertiesPath) -or
    (Test-Path -LiteralPath $ResolvedRecoveryKit)
) {
    throw "Signing material already exists. Refusing to overwrite it."
}

function New-RandomPassword {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
        return [Convert]::ToBase64String($bytes).
            TrimEnd("=").
            Replace("+", "A").
            Replace("/", "B")
    } finally {
        $generator.Dispose()
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}

function Set-PrivateDirectoryAcl {
    param([Parameter(Mandatory)][string]$Path)
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $Acl = [Security.AccessControl.DirectorySecurity]::new()
    $Rule = [Security.AccessControl.FileSystemAccessRule]::new(
        $Identity,
        [Security.AccessControl.FileSystemRights]::FullControl,
        (
            [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
            [Security.AccessControl.InheritanceFlags]::ObjectInherit
        ),
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Allow
    )
    $Acl.SetAccessRuleProtection($true, $false)
    $Acl.AddAccessRule($Rule)
    Set-Acl -LiteralPath $Path -AclObject $Acl
}

[IO.Directory]::CreateDirectory($ResolvedSigningDirectory) | Out-Null
$Password = New-RandomPassword
$env:FAMILY_AI_ANDROID_KEYSTORE_PASSWORD = $Password
try {
    & $Keytool `
        -genkeypair `
        -noprompt `
        -keystore $KeystorePath `
        -storetype PKCS12 `
        -alias $KeyAlias `
        -keyalg RSA `
        -keysize 3072 `
        -validity 10000 `
        -dname $DistinguishedName `
        -storepass:env FAMILY_AI_ANDROID_KEYSTORE_PASSWORD `
        -keypass:env FAMILY_AI_ANDROID_KEYSTORE_PASSWORD
    if ($LASTEXITCODE -ne 0) {
        throw "keytool failed with exit code $LASTEXITCODE"
    }
    $CertificateOutput = & $Keytool `
        -list `
        -v `
        -keystore $KeystorePath `
        -storetype PKCS12 `
        -alias $KeyAlias `
        -storepass:env FAMILY_AI_ANDROID_KEYSTORE_PASSWORD 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "keytool certificate inspection failed with exit code $LASTEXITCODE"
    }
} finally {
    Remove-Item Env:\FAMILY_AI_ANDROID_KEYSTORE_PASSWORD -ErrorAction SilentlyContinue
}

$FingerprintLine = $CertificateOutput |
    Where-Object { $_ -match "SHA256:\s*([0-9A-Fa-f:]+)" } |
    Select-Object -First 1
if ($FingerprintLine -notmatch "SHA256:\s*([0-9A-Fa-f:]+)") {
    throw "Cannot read the release certificate SHA-256 fingerprint"
}
$CertificateSha256 = $Matches[1].Replace(":", "").ToLowerInvariant()
if ($CertificateSha256 -notmatch "^[0-9a-f]{64}$") {
    throw "Unexpected release certificate SHA-256 fingerprint"
}

$NormalizedStorePath = $KeystorePath.Replace("\", "/")
$Properties = @(
    "storeFile=$NormalizedStorePath",
    "storePassword=$Password",
    "keyAlias=$KeyAlias",
    "keyPassword=$Password",
    "certificateSha256=$CertificateSha256"
) -join "`n"
[IO.File]::WriteAllText(
    $PropertiesPath,
    "$Properties`n",
    [Text.UTF8Encoding]::new($false)
)
Set-PrivateDirectoryAcl $ResolvedSigningDirectory

Add-Type -AssemblyName System.Security
$Payload = [ordered]@{
    schema = "family-ai/android-signing/v1"
    exported_at_utc = [DateTime]::UtcNow.ToString("o")
    key_alias = $KeyAlias
    keystore_name = [IO.Path]::GetFileName($KeystorePath)
    keystore_base64 = [Convert]::ToBase64String(
        [IO.File]::ReadAllBytes($KeystorePath)
    )
    properties = "$Properties`n"
}
$PlainBytes = [Text.Encoding]::UTF8.GetBytes(
    ($Payload | ConvertTo-Json -Depth 4 -Compress)
)
try {
    $ProtectedBytes = [Security.Cryptography.ProtectedData]::Protect(
        $PlainBytes,
        $Entropy,
        [Security.Cryptography.DataProtectionScope]::CurrentUser
    )
} finally {
    [Array]::Clear($PlainBytes, 0, $PlainBytes.Length)
}

[IO.Directory]::CreateDirectory(
    (Split-Path -Parent $ResolvedRecoveryKit)
) | Out-Null
[IO.File]::WriteAllText(
    $ResolvedRecoveryKit,
    [Convert]::ToBase64String($ProtectedBytes),
    [Text.Encoding]::ASCII
)

$Password = $null
$Properties = $null
Write-Output "Android release signing initialized."
Write-Output "Properties: $PropertiesPath"
Write-Output "DPAPI recovery kit: $ResolvedRecoveryKit"
Write-Output "Certificate SHA-256: $CertificateSha256"
Write-Output "No signing password was printed or written to Git."
