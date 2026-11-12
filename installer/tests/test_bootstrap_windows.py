"""The shipped headless PowerShell bootstrap must forward destinations and status."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform == "win32", "Executes Windows PowerShell")
class WindowsBootstrapTests(unittest.TestCase):
    def test_headless_arguments_and_failure_status_are_forwarded_to_python(self):
        with tempfile.TemporaryDirectory(prefix="CapForge bootstrap ქართული ") as temporary:
            source = Path(temporary)
            shutil.copyfile(ROOT / "installer/bootstrap_windows.ps1", source / "bootstrap_windows.ps1")
            # Exercise the real bootstrap with a local runtime stub; no downloads or install mutations.
            (source / "runtime_windows.ps1").write_text(
                (ROOT / "installer/runtime_windows.ps1").read_text(encoding="utf-8") +
                "\nfunction Initialize-CapForgeRuntime { return $env:CAPFORGE_TEST_PYTHON }\n", encoding="utf-8")
            (source / "install.py").write_text(
                "import json, os, pathlib, sys\n"
                "pathlib.Path(os.environ['CAPFORGE_TEST_REPORT']).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n"
                "raise SystemExit(31)\n", encoding="utf-8")
            report = source / "arguments.json"
            runtime = source / "Runtime $literal & ქართული"
            extensions = str(source / "Extensions ქართული") + "\\"
            result = subprocess.run([
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(source / "bootstrap_windows.ps1"), "-Headless", "-RuntimeRoot", str(runtime),
                "-ExtensionRoot", str(extensions), "-EnableUnsigned",
            ], env={**os.environ, "CAPFORGE_TEST_PYTHON": sys.executable, "CAPFORGE_TEST_REPORT": str(report)}, timeout=30)
            self.assertEqual(result.returncode, 31)
            self.assertEqual(json.loads(report.read_text()), [
                "--target", str(runtime), "--extension-root", str(extensions), "--enable-unsigned", "--headless"])


if __name__ == "__main__":
    unittest.main()
