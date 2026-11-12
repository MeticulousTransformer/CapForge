// A small native entry point. Python is downloaded privately by the bootstrap.
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("CapForge Setup")]
[assembly: AssemblyProduct("CapForge")]
[assembly: AssemblyVersion("0.3.2.0")]
[assembly: AssemblyFileVersion("0.3.2.0")]

internal static class Launcher
{
    [STAThread]
    private static void Main()
    {
        string folder = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.Combine(folder, "installer", "bootstrap_windows.ps1");
        if (!File.Exists(script))
        {
            MessageBox.Show("Extract the entire CapForge ZIP first, then open CapForge Setup.exe from the extracted folder.", "CapForge Setup");
            return;
        }
        try
        {
            string powershell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe");
            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = powershell;
            start.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -STA -File \"" + script + "\"";
            start.WorkingDirectory = folder;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            using (Process setup = Process.Start(start)) { setup.WaitForExit(); }
        }
        catch (Exception error)
        {
            MessageBox.Show("CapForge Setup could not open. Extract the package again and retry.\n\n" + error.Message, "CapForge Setup");
        }
    }
}
