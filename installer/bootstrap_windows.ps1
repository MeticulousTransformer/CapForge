param(
    [switch]$Headless,
    [switch]$BootstrapOnly,
    [string]$RuntimeRoot,
    [string]$ExtensionRoot,
    [switch]$EnableUnsigned
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime_windows.ps1')
$manifest = Join-Path $PSScriptRoot 'runtime_assets.json'
if (-not $RuntimeRoot) { $RuntimeRoot = Get-CapForgeRoot }
foreach ($destination in @($RuntimeRoot, $ExtensionRoot)) {
    if ($destination -and $destination -notmatch '^(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\[^\\]+)') {
        throw 'Setup paths must be absolute drive or network folder paths.'
    }
}
$installArguments = @((Join-Path $PSScriptRoot 'install.py'), '--target', $RuntimeRoot)
if ($ExtensionRoot) { $installArguments += @('--extension-root', $ExtensionRoot) }
if ($EnableUnsigned) { $installArguments += '--enable-unsigned' }

if ($Headless) {
    try {
        [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
        $OutputEncoding = [Console]::OutputEncoding
        $python = Initialize-CapForgeRuntime $RuntimeRoot $manifest { param($message) Write-Host $message }
        if ($BootstrapOnly) { Write-Output $python; exit 0 }
        $arguments = ($installArguments + '--headless') | ForEach-Object { ConvertTo-CapForgeArgument $_ }
        $info = New-Object Diagnostics.ProcessStartInfo
        $info.FileName = $python
        $info.Arguments = $arguments -join ' '
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        $info.StandardOutputEncoding = [Text.Encoding]::UTF8
        $info.StandardErrorEncoding = [Text.Encoding]::UTF8
        $info.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'
        $info.EnvironmentVariables['PYTHONUNBUFFERED'] = '1'
        $setup = New-Object Diagnostics.Process
        $setup.StartInfo = $info
        try {
            [void]$setup.Start()
            # Drain both streams concurrently so a full error pipe cannot deadlock setup.
            $stdout = $setup.StandardOutput.ReadToEndAsync()
            $stderr = $setup.StandardError.ReadToEndAsync()
            $setup.WaitForExit()
            [Console]::Out.Write($stdout.Result)
            [Console]::Error.Write($stderr.Result)
            $exitCode = $setup.ExitCode
        } finally { $setup.Dispose() }
        exit $exitCode
    } catch { Write-Error $_ -ErrorAction Continue; exit 1 }
}

# Native loading window works before Python exists. Download work stays off the UI thread.
Add-Type -AssemblyName PresentationFramework
[xml]$markup = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" Title="CapForge Setup" Width="500" Height="280" ResizeMode="NoResize" WindowStartupLocation="CenterScreen" Background="#171922">
  <StackPanel Margin="32">
    <TextBlock Text="CAPFORGE" FontSize="22" FontWeight="SemiBold" Foreground="#F0F1F8"/>
    <TextBlock Text="Your captions. In motion." FontSize="13" Margin="0,5,0,28" Foreground="#ACAFC0"/>
    <TextBlock Name="Status" Text="Preparing your installer..." FontSize="14" TextWrapping="Wrap" Foreground="#B4A5FF"/>
    <ProgressBar Name="Progress" Height="4" Margin="0,18,0,15" IsIndeterminate="True" Foreground="#B4A5FF"/>
    <TextBlock Text="First setup needs internet. CapForge prepares its own runtime; no Python installation or PATH setup required." FontSize="12" TextWrapping="Wrap" Foreground="#ACAFC0"/>
  </StackPanel>
</Window>
'@
$reader = New-Object Xml.XmlNodeReader $markup
$window = [Windows.Markup.XamlReader]::Load($reader)
$state = [hashtable]::Synchronized(@{text='Preparing your installer...'; python=$null; error=$null; done=$false})
$worker = [PowerShell]::Create()
[void]$worker.AddScript({ param($core,$root,$manifest,$state)
    try {
        . $core
        $state.python = Initialize-CapForgeRuntime $root $manifest { param($message) $state.text = $message }
    } catch { $state.error = $_.Exception.Message }
    finally { $state.done = $true }
}).AddArgument((Join-Path $PSScriptRoot 'runtime_windows.ps1')).AddArgument($RuntimeRoot).AddArgument($manifest).AddArgument($state)
$pending = $worker.BeginInvoke()
$timer = New-Object Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromMilliseconds(150)
$timer.Add_Tick({
    $window.FindName('Status').Text = $state.text
    if ($state.done) { $timer.Stop(); $window.Close() }
})
$window.Add_Closing({ param($sender,$event) if (-not $state.done) { $event.Cancel = $true } })
$timer.Start()
[void]$window.ShowDialog()
$worker.EndInvoke($pending)
$worker.Dispose()
if ($state.error) {
    [void][Windows.MessageBox]::Show("CapForge could not finish setup. Check your internet connection and try again.`n`n" + $state.error, 'CapForge Setup')
    exit 1
}
$pythonw = Join-Path ([IO.Path]::GetDirectoryName($state.python)) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { $pythonw = $state.python }
$arguments = $installArguments | ForEach-Object { ConvertTo-CapForgeArgument $_ }
$setup = Start-Process -FilePath $pythonw -ArgumentList ($arguments -join ' ') -WindowStyle Normal -Wait -PassThru
if ($setup.ExitCode -ne 0) {
    [void][Windows.MessageBox]::Show('The setup window could not open. Run CapForge Setup again to repair it.', 'CapForge Setup')
    exit $setup.ExitCode
}
exit $setup.ExitCode
