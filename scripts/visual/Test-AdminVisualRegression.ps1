[CmdletBinding()]
param(
    [switch]$UpdateBaselines,
    [string]$BrowserPath = "",
    [string]$CaseName = "",
    [double]$MaxDifferentRatio = 0.002
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BaselineRoot = Join-Path $RepoRoot "gateway\tests\visual\admin"
$PanelPath = Join-Path $RepoRoot "gateway\admin\panel.html"
$CssPath = Join-Path $RepoRoot "gateway\admin\static\admin.css"
$FixtureScriptPath = Join-Path $PSScriptRoot "admin-fixture.js"
$Comparator = Join-Path $PSScriptRoot "compare_png.py"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}

if (-not $BrowserPath) {
    $Candidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
    )
    $BrowserPath = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $BrowserPath -or -not (Test-Path -LiteralPath $BrowserPath)) {
    throw "Headless Edge or Chrome was not found. Pass -BrowserPath explicitly."
}

$Cases = @(
    @{ Name = "settings-desktop"; Screen = "settings"; Width = 1440; Height = 1000 },
    @{ Name = "agents-desktop"; Screen = "agents"; Width = 1440; Height = 1000 },
    @{ Name = "studio-desktop"; Screen = "studio"; Width = 1440; Height = 1000 },
    @{ Name = "infrastructure-desktop"; Screen = "infrastructure"; Width = 1440; Height = 1000 },
    @{ Name = "configuration-preview-desktop"; Screen = "settings"; Dialog = $true; Width = 1440; Height = 1000 },
    @{ Name = "settings-mobile"; Screen = "settings"; Width = 390; Height = 844 },
    @{ Name = "studio-mobile"; Screen = "studio"; Width = 390; Height = 844 },
    @{ Name = "infrastructure-mobile"; Screen = "infrastructure"; Width = 390; Height = 844 },
    @{ Name = "configuration-preview-mobile"; Screen = "settings"; Dialog = $true; Width = 390; Height = 844 }
)
if ($CaseName) {
    $Cases = @($Cases | Where-Object { $_.Name -eq $CaseName })
    if ($Cases.Count -eq 0) {
        throw "Unknown Admin visual case: $CaseName"
    }
}

$TempRoot = Join-Path ([IO.Path]::GetTempPath()) ("family-ai-visual-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null
New-Item -ItemType Directory -Force -Path $BaselineRoot | Out-Null

function Invoke-HeadlessBrowser {
    param(
        [string[]]$BrowserArguments,
        [string]$Label,
        [switch]$ExpectDom
    )

    $StdOutPath = Join-Path $TempRoot "$Label.stdout.txt"
    $StdErrPath = Join-Path $TempRoot "$Label.stderr.txt"
    $Process = Start-Process -FilePath $BrowserPath `
        -ArgumentList $BrowserArguments `
        -RedirectStandardOutput $StdOutPath `
        -RedirectStandardError $StdErrPath `
        -WindowStyle Hidden `
        -PassThru
    if (-not $Process.WaitForExit(30000)) {
        $Process.Kill($true)
        throw "Headless browser timed out during $Label"
    }
    $Process.WaitForExit()
    if (-not $ExpectDom) {
        return ""
    }
    $Content = ""
    for ($Attempt = 0; $Attempt -lt 100; $Attempt++) {
        if (Test-Path -LiteralPath $StdOutPath) {
            $Stream = [IO.File]::Open(
                $StdOutPath,
                [IO.FileMode]::Open,
                [IO.FileAccess]::Read,
                [IO.FileShare]::ReadWrite
            )
            try {
                $Reader = [IO.StreamReader]::new($Stream)
                $Content = $Reader.ReadToEnd()
                $Reader.Dispose()
            } finally {
                $Stream.Dispose()
            }
            if ($Content -match '</html>') {
                return $Content
            }
        }
        Start-Sleep -Milliseconds 100
    }
    throw "Headless browser returned incomplete DOM during $Label"
}

try {
    $Panel = [IO.File]::ReadAllText($PanelPath)
    $CssUri = ([uri]$CssPath).AbsoluteUri
    $Panel = $Panel.Replace('/admin-assets/admin.css', $CssUri)
    $Panel = [regex]::Replace(
        $Panel,
        '<script\s+type="module"\s+src="/admin-assets/js/app.js"></script>',
        ''
    )
    $FixtureScript = [IO.File]::ReadAllText($FixtureScriptPath)

    foreach ($Case in $Cases) {
        $HtmlPath = Join-Path $TempRoot "$($Case.Name).html"
        $ActualPath = Join-Path $TempRoot "$($Case.Name).png"
        $BaselinePath = Join-Path $BaselineRoot "$($Case.Name).png"
        $FailureCopy = Join-Path $BaselineRoot "$($Case.Name).actual.png"
        $Fixture = "<style>*{animation:none!important;transition:none!important;caret-color:transparent!important}</style>" +
            "<script>window.__VISUAL_SCREEN__='$($Case.Screen)';</script>" +
            "<script>window.__VISUAL_DIALOG__='$($Case.Dialog)' === 'True';</script>" +
            "<script>$FixtureScript</script>"
        [IO.File]::WriteAllText(
            $HtmlPath,
            $Panel.Replace('</body>', "$Fixture</body>"),
            [Text.UTF8Encoding]::new($false)
        )
        $Arguments = @(
            "--headless=new",
            "--disable-gpu",
            "--disable-background-networking",
            "--hide-scrollbars",
            "--no-first-run",
            "--force-device-scale-factor=1",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=1000",
            "--window-size=$($Case.Width),$($Case.Height)"
        )
        $RenderedDom = Invoke-HeadlessBrowser `
            ($Arguments + @(
                "--user-data-dir=$(Join-Path $TempRoot "dom-$($Case.Name)")",
                "--dump-dom",
                ([uri]$HtmlPath).AbsoluteUri
            )) `
            "dom-$($Case.Name)" `
            -ExpectDom
        if ($RenderedDom -match 'data-visual-overflow="true"') {
            throw "Horizontal overflow detected in $($Case.Name)"
        }
        $null = Invoke-HeadlessBrowser `
            ($Arguments + @(
                "--user-data-dir=$(Join-Path $TempRoot "capture-$($Case.Name)")",
                "--screenshot=$ActualPath",
                ([uri]$HtmlPath).AbsoluteUri
            )) `
            "capture-$($Case.Name)"
        for ($Attempt = 0; $Attempt -lt 20 -and -not (Test-Path -LiteralPath $ActualPath); $Attempt++) {
            Start-Sleep -Milliseconds 100
        }
        if (-not (Test-Path -LiteralPath $ActualPath)) {
            throw "Browser failed to capture $($Case.Name)"
        }

        if ($UpdateBaselines) {
            Copy-Item -LiteralPath $ActualPath -Destination $BaselinePath -Force
            Remove-Item -LiteralPath $FailureCopy -Force -ErrorAction SilentlyContinue
            Write-Host "[UPDATED] $($Case.Name)"
            continue
        }
        if (-not (Test-Path -LiteralPath $BaselinePath)) {
            throw "Missing baseline $BaselinePath. Run with -UpdateBaselines and review it."
        }
        & $Python $Comparator $BaselinePath $ActualPath `
            --max-different-ratio $MaxDifferentRatio
        if ($LASTEXITCODE -ne 0) {
            Copy-Item -LiteralPath $ActualPath -Destination $FailureCopy -Force
            throw "Visual regression in $($Case.Name). Actual image: $FailureCopy"
        }
        Remove-Item -LiteralPath $FailureCopy -Force -ErrorAction SilentlyContinue
        Write-Host "[PASSED] $($Case.Name)"
    }
} finally {
    Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

exit 0
