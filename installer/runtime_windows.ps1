# Private runtime setup. No system Python, PATH changes, registry registration or admin rights.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-CapForgeOwned([string]$Root) {
    $marker = Join-Path $Root '.kcf-install.json'
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { return $false }
    try {
        $record = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
        return $record.tool -in @('CapForge', 'Kartuli Caption Forge')
    } catch { return $false }
}

function Get-CapForgeRoot {
    $legacy = Join-Path $env:LOCALAPPDATA 'Kartuli Caption Forge'
    if (Test-CapForgeOwned $legacy) { return $legacy }
    return (Join-Path $env:LOCALAPPDATA 'CapForge')
}

function Assert-CapForgePath([string]$Path, [string]$Root) {
    $absolute = [IO.Path]::GetFullPath($Path)
    $parent = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    if ($absolute -ne $parent -and -not $absolute.StartsWith($parent + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Setup path escaped the CapForge folder.'
    }
    $cursor = $absolute
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Choose an installation folder without symbolic links or junctions.'
            }
        }
        $next = [IO.Path]::GetDirectoryName($cursor)
        if ($next -eq $cursor) { break }
        $cursor = $next
    }
    return $absolute
}

function ConvertTo-CapForgeArgument([string]$Value) {
    # Windows CommandLineToArgvW quoting; ProcessStartInfo does not use a shell.
    if ($Value -notmatch '[\s"]' -and $Value.Length) { return $Value }
    return '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}

function Invoke-CapForgeTool([string]$Executable, [string[]]$Arguments, [hashtable]$Environment = @{}) {
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = ($Arguments | ForEach-Object { ConvertTo-CapForgeArgument $_ }) -join ' '
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($key in $Environment.Keys) { $info.EnvironmentVariables[$key] = $Environment[$key] }
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $result = @{ ExitCode = $process.ExitCode; Output = $stdout.Result; Error = $stderr.Result }
    $process.Dispose()
    if ($result.ExitCode -ne 0) { throw ($result.Error + $result.Output).Trim() }
    return $result.Output.Trim()
}

function Initialize-CapForgeRuntime {
    param([string]$Root, [string]$ManifestPath, [scriptblock]$Progress = {})
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'CapForge requires 64-bit Windows.' }
    $Root = Assert-CapForgePath $Root $Root
    if ((Test-Path -LiteralPath $Root) -and (Get-ChildItem -LiteralPath $Root -Force | Select-Object -First 1) -and -not (Test-CapForgeOwned $Root)) {
        throw 'This folder contains unrelated files. Choose an empty CapForge installation folder.'
    }
    [void][IO.Directory]::CreateDirectory($Root)
    if (-not (Test-CapForgeOwned $Root)) {
        $record = @{tool='CapForge'; version='0.3.3'; runtimeRoot=$Root; bootstrap=$true} | ConvertTo-Json
        [IO.File]::WriteAllText((Join-Path $Root '.kcf-install.json'), $record, (New-Object Text.UTF8Encoding $false))
    }
    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    $asset = $manifest.assets.windows_x64
    if ($asset.url -notmatch '^https://github\.com/astral-sh/uv/releases/download/' -or $asset.sha256 -notmatch '^[a-f0-9]{64}$') { throw 'Invalid runtime download manifest.' }
    $private = Assert-CapForgePath (Join-Path $Root '.runtime') $Root
    $uvFolder = Assert-CapForgePath (Join-Path $private ('uv\' + $manifest.version)) $Root
    $uv = Join-Path $uvFolder 'uv.exe'
    [void](Assert-CapForgePath $uv $Root)
    if (-not (Test-Path -LiteralPath $uv -PathType Leaf)) {
        & $Progress 'Downloading the CapForge setup tools...'
        $stage = Assert-CapForgePath (Join-Path $private ('.download-' + [guid]::NewGuid().ToString('N'))) $Root
        [void][IO.Directory]::CreateDirectory($stage)
        try {
            $archive = Join-Path $stage 'runtime.zip'
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $asset.url -OutFile $archive -UseBasicParsing -TimeoutSec 120
            if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.sha256) { throw 'The setup download could not be verified. Please retry.' }
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $zip = [IO.Compression.ZipFile]::OpenRead($archive)
            try {
                foreach ($entry in $zip.Entries) { [void](Assert-CapForgePath (Join-Path $stage $entry.FullName) $stage) }
            } finally { $zip.Dispose() }
            Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $stage 'unpacked')
            $binary = Get-ChildItem -LiteralPath (Join-Path $stage 'unpacked') -Filter 'uv.exe' -Recurse | Select-Object -First 1
            if (-not $binary) { throw 'The setup tools are incomplete. Please retry.' }
            [void][IO.Directory]::CreateDirectory($uvFolder)
            Copy-Item -LiteralPath $binary.FullName -Destination $uv
        } finally {
            [void](Assert-CapForgePath $stage $Root)
            Remove-Item -LiteralPath $stage -Recurse -Force
        }
    }
    $environment = @{
        UV_PYTHON_INSTALL_DIR = (Join-Path $private 'python')
        UV_CACHE_DIR = (Join-Path $private 'cache')
        UV_PYTHON_INSTALL_BIN = '0'
        UV_PYTHON_INSTALL_REGISTRY = '0'
    }
    & $Progress 'Preparing the private CapForge runtime...'
    [void](Invoke-CapForgeTool $uv @('python','install',$manifest.python,'--no-bin','--no-registry','--managed-python','--no-config') $environment)
    # uv creates a minor-version junction. Use the canonical patch directory so
    # our safety check can continue rejecting user-supplied junctions everywhere.
    $installed = Get-ChildItem -LiteralPath $environment.UV_PYTHON_INSTALL_DIR -Directory |
        Where-Object { $_.Name -match ('^cpython-' + [regex]::Escape($manifest.python) + '\.\d+-windows-x86_64-none$') } |
        Sort-Object { [version](($_.Name -split '-')[1]) } -Descending | Select-Object -First 1
    if (-not $installed) { throw 'The private runtime is incomplete. Please retry setup.' }
    $python = Join-Path $installed.FullName 'python.exe'
    [void](Assert-CapForgePath $python $Root)
    & $Progress 'Checking the installer...'
    [void](Invoke-CapForgeTool $python @('-I','-c','import tkinter, venv, ssl; tkinter.Tcl().eval("info patchlevel")'))
    return $python
}
