// Native Windows setup entry point. The standalone build embeds the shared source ZIP.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;

[assembly: AssemblyTitle("CapForge Setup")]
[assembly: AssemblyProduct("CapForge")]
[assembly: AssemblyVersion("0.3.3.0")]
[assembly: AssemblyFileVersion("0.3.3.0")]

internal static class Launcher
{
    private const string PayloadName = "CapForge.Payload.zip";
    private const string ChecksumName = "CapForge.Payload.sha256";
    private const long MaxPayloadBytes = 512L * 1024 * 1024;

    private sealed class Options
    {
        public bool Headless;
        public bool EnableUnsigned;
        public string Target;
        public string ExtensionRoot;
        public string ExtractOnly;
    }

    [STAThread]
    private static int Main(string[] args)
    {
        string ownedStage = null;
        bool keepStage = false;
        bool quiet = Array.IndexOf(args, "--headless") >= 0 || Array.IndexOf(args, "--extract-only") >= 0;
        try
        {
            if (quiet)
            {
                // A GUI-subsystem EXE has no console; use the caller's redirected handles.
                Console.SetOut(new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true });
                Console.SetError(new StreamWriter(Console.OpenStandardError(), new UTF8Encoding(false)) { AutoFlush = true });
            }
            Options options = ParseOptions(args);
            string folder = AppDomain.CurrentDomain.BaseDirectory;
            using (Stream payload = Assembly.GetExecutingAssembly().GetManifestResourceStream(PayloadName))
            {
                if (payload != null)
                {
                    VerifyPayload(payload);
                    string destination = options.ExtractOnly ?? Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                        "Temp", "CapForge-Setup-" + Guid.NewGuid().ToString("N"));
                    AssertNoReparsePoints(destination);
                    if (Directory.Exists(destination) || File.Exists(destination))
                        throw new IOException("The extraction folder already exists. Choose a new folder.");
                    Directory.CreateDirectory(destination);
                    ownedStage = destination;
                    folder = ExtractPayload(payload, destination);
                    if (options.ExtractOnly != null)
                    {
                        keepStage = true;
                        return 0;
                    }
                }
                else if (options.ExtractOnly != null)
                {
                    throw new IOException("This legacy launcher has no embedded payload.");
                }
            }
            string script = Path.Combine(folder, "installer", "bootstrap_windows.ps1");
            if (!File.Exists(script))
                throw new IOException("Setup is incomplete. Download the standalone CapForge Windows installer again.");
            string powershell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),
                "WindowsPowerShell", "v1.0", "powershell.exe");
            List<string> arguments = new List<string> {
                "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-STA", "-File", script
            };
            if (options.Headless) arguments.Add("-Headless");
            if (options.Target != null) { arguments.Add("-RuntimeRoot"); arguments.Add(options.Target); }
            if (options.ExtensionRoot != null) { arguments.Add("-ExtensionRoot"); arguments.Add(options.ExtensionRoot); }
            if (options.EnableUnsigned) arguments.Add("-EnableUnsigned");
            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = powershell;
            start.Arguments = JoinArguments(arguments);
            start.WorkingDirectory = folder;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            if (options.Headless)
            {
                start.RedirectStandardOutput = true;
                start.RedirectStandardError = true;
                start.StandardOutputEncoding = Encoding.UTF8;
                start.StandardErrorEncoding = Encoding.UTF8;
            }
            using (Process setup = new Process())
            {
                setup.StartInfo = start;
                if (options.Headless)
                {
                    setup.OutputDataReceived += delegate(object sender, DataReceivedEventArgs data) {
                        if (data.Data != null) Console.Out.WriteLine(data.Data);
                    };
                    setup.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs data) {
                        if (data.Data != null) Console.Error.WriteLine(data.Data);
                    };
                }
                setup.Start();
                if (options.Headless)
                {
                    setup.BeginOutputReadLine();
                    setup.BeginErrorReadLine();
                }
                // The parameterless wait also drains both asynchronous output readers.
                setup.WaitForExit();
                return setup.ExitCode;
            }
        }
        catch (Exception error)
        {
            string message = "CapForge Setup could not finish.\n\n" + error.Message;
            if (quiet) Console.Error.WriteLine(message);
            else MessageBox.Show(message, "CapForge Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        finally
        {
            // Only this invocation's newly created directory is eligible for cleanup.
            if (ownedStage != null && !keepStage)
            {
                try { RemoveOwnedStage(ownedStage); }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
            }
        }
    }

    private static Options ParseOptions(string[] args)
    {
        Options options = new Options();
        HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
        for (int i = 0; i < args.Length; i++)
        {
            string option = args[i];
            if (!seen.Add(option)) throw new ArgumentException("Duplicate setup option: " + option);
            if (option == "--headless") options.Headless = true;
            else if (option == "--enable-unsigned") options.EnableUnsigned = true;
            else if (option == "--target" || option == "--extension-root" || option == "--extract-only")
            {
                if (++i == args.Length) throw new ArgumentException("Missing path for " + option);
                string path = AbsolutePath(args[i]);
                if (option == "--target") options.Target = path;
                else if (option == "--extension-root") options.ExtensionRoot = path;
                else options.ExtractOnly = path;
            }
            else throw new ArgumentException("Unknown setup option: " + option);
        }
        if (options.ExtractOnly != null && (options.Headless || options.EnableUnsigned || options.Target != null || options.ExtensionRoot != null))
            throw new ArgumentException("Use --extract-only by itself, followed by a new absolute folder path.");
        return options;
    }

    private static string AbsolutePath(string path)
    {
        // Path.IsPathRooted also accepts drive-relative paths such as C:folder.
        if (!Regex.IsMatch(path, @"^(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+[\\/]?)") ||
            path.StartsWith(@"\\?\", StringComparison.Ordinal) || path.StartsWith(@"\\.\", StringComparison.Ordinal))
            throw new ArgumentException("Setup paths must be absolute drive or network folder paths.");
        return Path.GetFullPath(path);
    }

    private static void VerifyPayload(Stream payload)
    {
        string expected;
        using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream(ChecksumName))
        {
            if (resource == null) throw new IOException("The embedded payload checksum is missing.");
            using (StreamReader reader = new StreamReader(resource, Encoding.ASCII)) expected = reader.ReadToEnd().Trim();
        }
        if (!Regex.IsMatch(expected, "^[a-f0-9]{64}$") || payload.Length > MaxPayloadBytes)
            throw new IOException("The embedded payload metadata is invalid.");
        using (SHA256 sha = SHA256.Create())
        {
            string actual = BitConverter.ToString(sha.ComputeHash(payload)).Replace("-", "").ToLowerInvariant();
            if (!String.Equals(expected, actual, StringComparison.Ordinal))
                throw new IOException("The installer payload is damaged. Download CapForge again.");
        }
        payload.Position = 0;
    }

    private static string ExtractPayload(Stream payload, string destination)
    {
        string root = null;
        string boundary = Path.GetFullPath(destination).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        HashSet<string> paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        long total = 0;
        using (ZipArchive archive = new ZipArchive(payload, ZipArchiveMode.Read, true))
        {
            if (archive.Entries.Count == 0 || archive.Entries.Count > 10000)
                throw new IOException("Invalid installer payload size.");
            // Validate every entry before writing any payload files.
            foreach (ZipArchiveEntry entry in archive.Entries)
            {
                string[] parts = entry.FullName.Split('/');
                if (parts.Length < 2 || !Regex.IsMatch(parts[0], @"^CapForge-\d+\.\d+\.\d+$"))
                    throw new IOException("Invalid installer payload root.");
                if (root == null) root = parts[0];
                if (root != parts[0]) throw new IOException("The payload has multiple roots.");
                foreach (string part in parts)
                {
                    if (part.Length == 0 || part == "." || part == ".." || part.TrimEnd(' ', '.') != part ||
                        part.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 ||
                        Regex.IsMatch(part, @"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", RegexOptions.IgnoreCase))
                        throw new IOException("Unsafe path in the installer payload.");
                }
                string target = Path.GetFullPath(Path.Combine(destination, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                if (!target.StartsWith(boundary, StringComparison.OrdinalIgnoreCase) || !paths.Add(target))
                    throw new IOException("Unsafe or duplicate path in the installer payload.");
                total += entry.Length;
                if (entry.Length < 0 || entry.Length > MaxPayloadBytes || total > MaxPayloadBytes)
                    throw new IOException("The installer payload is too large.");
                // Unix symlinks are not legitimate source files.
                if (((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000)
                    throw new IOException("Links are not allowed in the installer payload.");
            }
            foreach (ZipArchiveEntry entry in archive.Entries)
            {
                string target = Path.Combine(destination, entry.FullName.Replace('/', Path.DirectorySeparatorChar));
                AssertNoReparsePoints(target);
                Directory.CreateDirectory(Path.GetDirectoryName(target));
                using (Stream input = entry.Open())
                using (FileStream output = new FileStream(target, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    byte[] buffer = new byte[81920];
                    long copied = 0;
                    int count;
                    while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        copied += count;
                        if (copied > entry.Length) throw new IOException("Invalid expanded payload size.");
                        output.Write(buffer, 0, count);
                    }
                    if (copied != entry.Length) throw new IOException("The payload file is incomplete.");
                }
            }
        }
        string folder = Path.Combine(destination, root);
        if (!File.Exists(Path.Combine(folder, "installer", "bootstrap_windows.ps1")))
            throw new IOException("The embedded installer is incomplete.");
        return folder;
    }

    private static void AssertNoReparsePoints(string path)
    {
        string cursor = Path.GetFullPath(path);
        while (!String.IsNullOrEmpty(cursor))
        {
            if ((Directory.Exists(cursor) || File.Exists(cursor)) &&
                (File.GetAttributes(cursor) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Setup folders cannot contain symbolic links or junctions.");
            cursor = Path.GetDirectoryName(cursor);
        }
    }

    private static void RemoveOwnedStage(string directory)
    {
        if (!Directory.Exists(directory)) return;
        if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0)
        {
            Directory.Delete(directory);
            return;
        }
        foreach (string child in Directory.GetDirectories(directory)) RemoveOwnedStage(child);
        foreach (string file in Directory.GetFiles(directory)) File.Delete(file);
        Directory.Delete(directory);
    }

    private static string JoinArguments(IEnumerable<string> arguments)
    {
        List<string> quoted = new List<string>();
        foreach (string value in arguments)
        {
            // Windows argv quoting. No cmd.exe and no PowerShell source interpolation.
            string escaped = Regex.Replace(value, "(\\\\*)\"", "$1$1\\\"");
            escaped = Regex.Replace(escaped, "(\\\\+)$", "$1$1");
            quoted.Add("\"" + escaped + "\"");
        }
        return String.Join(" ", quoted.ToArray());
    }
}
