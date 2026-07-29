[CmdletBinding()]
param(
    [string]$SigningDirectory = "$env:USERPROFILE\.family-ai\android-signing",
    [string]$RecoveryKitPath = ".dr\android-signing-kit.dpapi"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Entropy = [Text.Encoding]::UTF8.GetBytes("family-ai/android-signing/v1")
$ResolvedSigningDirectory = [IO.Path]::GetFullPath($SigningDirectory)
$ResolvedRecoveryKit = [IO.Path]::GetFullPath(
    (Join-Path $RepoRoot $RecoveryKitPath)
)
$KeystorePath = Join-Path $ResolvedSigningDirectory "family-ai-release.p12"
$PropertiesPath = Join-Path $ResolvedSigningDirectory "key.properties"

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

if (-not (Test-Path -LiteralPath $ResolvedRecoveryKit -PathType Leaf)) {
    throw "DPAPI recovery kit was not found: $ResolvedRecoveryKit"
}
if (
    (Test-Path -LiteralPath $KeystorePath) -or
    (Test-Path -LiteralPath $PropertiesPath)
) {
    throw "Signing material already exists. Refusing to overwrite it."
}

Add-Type -AssemblyName System.Security
$Encoded = [IO.File]::ReadAllText(
    $ResolvedRecoveryKit,
    [Text.Encoding]::ASCII
).Trim()
$ProtectedBytes = [Convert]::FromBase64String($Encoded)
$PlainBytes = [Security.Cryptography.ProtectedData]::Unprotect(
    $ProtectedBytes,
    $Entropy,
    [Security.Cryptography.DataProtectionScope]::CurrentUser
)
try {
    $Payload = (
        [Text.Encoding]::UTF8.GetString($PlainBytes) |
            ConvertFrom-Json
    )
} finally {
    [Array]::Clear($PlainBytes, 0, $PlainBytes.Length)
}

if ($Payload.schema -ne "family-ai/android-signing/v1") {
    throw "Unsupported Android signing kit schema"
}
if ($Payload.keystore_name -ne "family-ai-release.p12") {
    throw "Unexpected keystore name in Android signing kit"
}

[IO.Directory]::CreateDirectory($ResolvedSigningDirectory) | Out-Null
$KeystoreBytes = [Convert]::FromBase64String($Payload.keystore_base64)
try {
    [IO.File]::WriteAllBytes($KeystorePath, $KeystoreBytes)
} finally {
    [Array]::Clear($KeystoreBytes, 0, $KeystoreBytes.Length)
}

$Properties = [string]$Payload.properties
$Properties = $Properties -replace (
    "(?m)^storeFile=.*$"
), "storeFile=$($KeystorePath.Replace('\', '/'))"
[IO.File]::WriteAllText(
    $PropertiesPath,
    $Properties,
    [Text.UTF8Encoding]::new($false)
)
Set-PrivateDirectoryAcl $ResolvedSigningDirectory

Write-Output "Android release signing restored."
Write-Output "Properties: $PropertiesPath"
Write-Output "The signing password was not printed."
