[CmdletBinding()]
param(
    [string]$Root = "."
)

$ErrorActionPreference = "Stop"
$ResolvedRoot = (Resolve-Path -LiteralPath $Root).Path
$Failures = [Collections.Generic.List[string]]::new()
$MarkdownFiles = Get-ChildItem `
    -LiteralPath $ResolvedRoot `
    -Filter "*.md" `
    -File `
    -Recurse |
    Where-Object {
        $_.FullName -notmatch "[\\/](?:\.git|\.artifacts|\.tools|tmp)[\\/]"
    }

foreach ($File in $MarkdownFiles) {
    $Content = [IO.File]::ReadAllText($File.FullName)
    foreach ($Match in [regex]::Matches($Content, "!?\[[^\]]*\]\(([^)]+)\)")) {
        $Target = $Match.Groups[1].Value.Trim()
        if (
            -not $Target -or
            $Target.StartsWith("#") -or
            $Target -match "^(?:https?|mailto):"
        ) {
            continue
        }
        $PathPart = [Uri]::UnescapeDataString(($Target -split "#", 2)[0])
        if (-not $PathPart) {
            continue
        }
        $Candidate = [IO.Path]::GetFullPath(
            (Join-Path $File.DirectoryName $PathPart)
        )
        if (-not (Test-Path -LiteralPath $Candidate)) {
            $RelativeFile = [IO.Path]::GetRelativePath(
                $ResolvedRoot,
                $File.FullName
            )
            $Failures.Add("$RelativeFile -> $Target")
        }
    }
}

if ($Failures.Count -gt 0) {
    $Failures | ForEach-Object { Write-Error "Broken Markdown link: $_" }
    throw "$($Failures.Count) broken Markdown link(s) found"
}

Write-Output "Checked $($MarkdownFiles.Count) Markdown files: all local links resolve."
