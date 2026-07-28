$script:IdentityFile = ""
$script:Entropy = [Text.Encoding]::UTF8.GetBytes("family-ai/dr-kit/v1")

function Initialize-FamilyAiDr {
    param([Parameter(Mandatory)][string]$IdentityFile)
    $script:IdentityFile = $IdentityFile
    Add-Type -AssemblyName System.Security
}

function Assert-SafeToken {
    param([string]$Value, [string]$Name)
    if ($Value -notmatch "^[a-zA-Z0-9_.:@-]+$") {
        throw "$Name contains unsupported characters"
    }
}

function Invoke-Native {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

function Invoke-Remote {
    param([string]$HostName, [string]$UserName, [string]$Command)
    $remote = "$UserName@$HostName"
    & ssh -i $script:IdentityFile -o BatchMode=yes $remote $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Remote command failed on $remote"
    }
}

function Copy-ToRemote {
    param([string]$Source, [string]$HostName, [string]$UserName, [string]$Target)
    Invoke-Native "scp" @(
        "-i", $script:IdentityFile,
        "-o", "BatchMode=yes",
        $Source,
        "$UserName@$HostName`:$Target"
    )
}

function Copy-FromRemote {
    param([string]$HostName, [string]$UserName, [string]$Source, [string]$Target)
    Invoke-Native "scp" @(
        "-i", $script:IdentityFile,
        "-o", "BatchMode=yes",
        "$UserName@$HostName`:$Source",
        $Target
    )
}

function Invoke-ElevatedScript {
    param(
        [string]$HostName,
        [string]$UserName,
        [string]$ScriptPath,
        [string[]]$Arguments = @()
    )
    $joined = ($Arguments | ForEach-Object { "'$_'" }) -join " "
    $command = "if [ `$(id -u) -eq 0 ]; then bash '$ScriptPath' $joined; else sudo -n bash '$ScriptPath' $joined; fi"
    Invoke-Remote $HostName $UserName $command
}

function Read-DrKit {
    param([Parameter(Mandatory)][string]$BundlePath)
    $encoded = [IO.File]::ReadAllText(
        [IO.Path]::GetFullPath((Join-Path (Get-Location) $BundlePath)),
        [Text.Encoding]::ASCII
    ).Trim()
    $protectedBytes = [Convert]::FromBase64String($encoded)
    $plainBytes = [System.Security.Cryptography.ProtectedData]::Unprotect(
        $protectedBytes,
        $script:Entropy,
        [System.Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    try {
        $json = [Text.Encoding]::UTF8.GetString($plainBytes)
        $kit = $json | ConvertFrom-Json
    } finally {
        [Array]::Clear($plainBytes, 0, $plainBytes.Length)
    }
    if ($kit.schema -ne "family-ai/dr-kit/v1") {
        throw "Unsupported DR kit schema"
    }
    return $kit
}

function ConvertFrom-EnvText {
    param([string]$Text)
    $values = [ordered]@{}
    foreach ($line in ($Text -split "\r?\n")) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }
        $key, $value = $trimmed.Split("=", 2)
        $values[$key.Trim()] = $value
    }
    return $values
}

function ConvertTo-EnvText {
    param([Collections.Specialized.OrderedDictionary]$Values)
    return (($Values.GetEnumerator() | ForEach-Object {
        "$($_.Key)=$($_.Value)"
    }) -join "`n") + "`n"
}

function Resolve-DatabaseSettings {
    param([string]$DatabaseUrl, [string]$TargetDatabaseHost)
    $pattern = "^(?<prefix>postgresql(?:\+psycopg)?://)(?<userinfo>[^@]+)@(?<host>\[[^\]]+\]|[^:/?#]+)(?<port>:\d+)?(?<suffix>/[^#]+)$"
    $match = [regex]::Match($DatabaseUrl, $pattern)
    if (-not $match.Success) {
        throw "FAMILY_AI_DATABASE_URL has an unsupported format"
    }
    $userInfo = $match.Groups["userinfo"].Value.Split(":", 2)
    if ($userInfo.Count -ne 2) {
        throw "FAMILY_AI_DATABASE_URL does not contain an application password"
    }
    return @{
        Password = [Uri]::UnescapeDataString($userInfo[1])
        Username = [Uri]::UnescapeDataString($userInfo[0])
        DatabaseName = $match.Groups["suffix"].Value.TrimStart("/").Split("?", 2)[0]
        SourceHost = $match.Groups["host"].Value.Trim("[", "]")
        RewrittenUrl = (
            $match.Groups["prefix"].Value +
            $match.Groups["userinfo"].Value +
            "@" + $TargetDatabaseHost +
            $match.Groups["port"].Value +
            $match.Groups["suffix"].Value
        )
    }
}

function Test-SshHost {
    param([string]$HostName, [string]$UserName)
    $result = Invoke-Remote $HostName $UserName `
        "test -d /run/systemd/system && command -v apt-get >/dev/null && (test `$(id -u) -eq 0 || sudo -n true) && df -Pk / | tail -1 | awk '{print `$4}'"
    $freeKilobytes = [long](($result | Select-Object -Last 1).Trim())
    if ($freeKilobytes -lt 5GB / 1KB) {
        throw "$HostName has less than 5 GiB free space"
    }
}

function Install-Configuration {
    param(
        [string]$LocalPath,
        [string]$HostName,
        [string]$UserName,
        [string]$RemotePath,
        [string]$Owner,
        [string]$Mode = "0600"
    )
    $temporary = "/tmp/family-ai-dr-$([IO.Path]::GetFileName($RemotePath))"
    Copy-ToRemote $LocalPath $HostName $UserName $temporary
    Invoke-Remote $HostName $UserName `
        "sudo install -o '$Owner' -g '$Owner' -m '$Mode' '$temporary' '$RemotePath' && rm -f '$temporary'"
}

Export-ModuleMember -Function @(
    "Initialize-FamilyAiDr",
    "Assert-SafeToken",
    "Invoke-Native",
    "Invoke-Remote",
    "Copy-ToRemote",
    "Copy-FromRemote",
    "Invoke-ElevatedScript",
    "Read-DrKit",
    "ConvertFrom-EnvText",
    "ConvertTo-EnvText",
    "Resolve-DatabaseSettings",
    "Test-SshHost",
    "Install-Configuration"
)
