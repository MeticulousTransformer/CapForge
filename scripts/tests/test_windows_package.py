"""Source ZIP safety on every platform; compiled launcher behavior on Windows."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_windows import compile_launcher, find_compiler, validate_archive
from package_release import NAME, build_archive


def checksum(path):
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n", encoding="utf-8")


class WindowsPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="CapForge payload ქართული ")
        cls.root = Path(cls.temporary.name)
        cls.source = cls.root / (NAME + ".zip")
        build_archive(cls.source, source_only=True)
        checksum(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def changed_archive(self, extra_name=None, mode=0o100644, damaged=False):
        destination = self.root / "modified.zip"
        with zipfile.ZipFile(self.source) as source, zipfile.ZipFile(destination, "w") as target:
            for entry in source.infolist():
                data = source.read(entry)
                if damaged and entry.filename == NAME + "/backend/app.py":
                    data = b"damaged"
                target.writestr(entry, data)
            if extra_name:
                entry = zipfile.ZipInfo(extra_name)
                entry.external_attr = mode << 16
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    target.writestr(entry, b"unexpected payload")
        checksum(destination)
        return destination

    def test_shared_source_only_archive_is_valid_windows_payload(self):
        self.assertEqual(validate_archive(self.source), NAME.removeprefix("CapForge-"))

    def test_embedded_payload_cannot_include_a_previous_installer(self):
        with self.assertRaisesRegex(ValueError, "source-only"):
            validate_archive(self.changed_archive(NAME + "/CapForge Setup.exe"))

    def test_windows_path_escapes_and_alternate_names_are_rejected(self):
        for name in ("../outside.py", "C:/outside.py", "installer/../outside.py", "installer\\outside.py",
                     "installer/file.py:secret", "installer/CON.py", "installer/file.py.",
                     "installer/file.py ", "installer//file.py", "installer/./file.py"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_archive(self.changed_archive(NAME + "/" + name))

    def test_unallowlisted_file_is_rejected_even_if_it_looks_like_source(self):
        with self.assertRaisesRegex(ValueError, "Unallowlisted"):
            validate_archive(self.changed_archive(NAME + "/backend/private_settings.py"))

    def test_file_damage_cannot_be_hidden_by_refreshing_archive_checksum(self):
        with self.assertRaisesRegex(ValueError, "Damaged release component"):
            validate_archive(self.changed_archive(damaged=True))

    def test_duplicate_or_symlink_entry_is_rejected(self):
        # These names are present in the allowlist, so metadata checks must catch them.
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_archive(self.changed_archive(NAME + "/installer/install.py"))
        with zipfile.ZipFile(self.source) as source, zipfile.ZipFile(self.root / "link.zip", "w") as target:
            for entry in source.infolist():
                if entry.filename == NAME + "/installer/install.py":
                    entry.external_attr = 0o120777 << 16
                target.writestr(entry, source.read(entry))
        checksum(self.root / "link.zip")
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            validate_archive(self.root / "link.zip")


@unittest.skipUnless(sys.platform == "win32", "Compiles and executes the real .NET launcher on Windows")
class WindowsLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="CapForge launcher ქართული ")
        cls.root = Path(cls.temporary.name)
        cls.archive = cls.root / "test-source.zip"
        bootstrap = '''param([switch]$Headless,[string]$RuntimeRoot,[string]$ExtensionRoot,[switch]$EnableUnsigned)
@{headless=$Headless.IsPresent; root=$RuntimeRoot; extensions=$ExtensionRoot; unsigned=$EnableUnsigned.IsPresent; source=$PSScriptRoot} |
    ConvertTo-Json | Set-Content -LiteralPath $RuntimeRoot -Encoding UTF8
exit 23
'''
        with zipfile.ZipFile(cls.archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(NAME + "/installer/bootstrap_windows.ps1", bootstrap)
        cls.executable = cls.root / "CapForge Windows.exe"
        compile_launcher(cls.archive, cls.executable, find_compiler())

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_headless_arguments_unicode_and_exit_code_survive_native_handoff(self):
        report = self.root / "installed result ქართული.json"
        extensions = str(self.root / "CEP $literal & ქართული") + "\\"
        result = subprocess.run([str(self.executable), "--headless", "--target", str(report),
                                 "--extension-root", extensions, "--enable-unsigned"], timeout=45)
        self.assertEqual(result.returncode, 23)
        captured = json.loads(report.read_text(encoding="utf-8-sig"))
        self.assertTrue(captured["headless"])
        self.assertTrue(captured["unsigned"])
        # .NET expands Windows 8.3 aliases (RUNNER~1) to their long paths.
        self.assertEqual(Path(captured["root"]).resolve(), report.resolve())
        self.assertEqual(Path(captured["extensions"]).resolve(), Path(extensions).resolve())
        self.assertEqual(Path(captured["extensions"]).name, "CEP $literal & ქართული")
        self.assertTrue(captured["extensions"].endswith("\\"))
        self.assertFalse(Path(captured["source"]).exists(), "Temporary source must be cleaned after child exits")

    def test_extract_only_preserves_source_and_refuses_existing_destination(self):
        destination = self.root / "extracted payload ქართული"
        result = subprocess.run([str(self.executable), "--extract-only", str(destination)], timeout=30)
        self.assertEqual(result.returncode, 0)
        bootstrap = destination / NAME / "installer/bootstrap_windows.ps1"
        original = bootstrap.read_bytes()
        result = subprocess.run([str(self.executable), "--extract-only", str(destination)], timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(bootstrap.read_bytes(), original)

    def test_legacy_adjacent_source_mode_still_works_without_embedded_resources(self):
        legacy = self.root / "legacy source ქართული"
        (legacy / "installer").mkdir(parents=True)
        with zipfile.ZipFile(self.archive) as package:
            (legacy / "installer/bootstrap_windows.ps1").write_bytes(
                package.read(NAME + "/installer/bootstrap_windows.ps1"))
        executable = legacy / "CapForge Setup.exe"
        source = Path(__file__).resolve().parents[2] / "installer/Launcher.cs"
        subprocess.run([str(find_compiler()), "/nologo", "/target:winexe",
                        "/reference:System.Windows.Forms.dll", "/reference:System.IO.Compression.dll",
                        "/reference:System.IO.Compression.FileSystem.dll", "/out:" + str(executable),
                        str(source)], check=True, timeout=30)
        report = legacy / "result.json"
        result = subprocess.run([str(executable), "--headless", "--target", str(report)], timeout=30)
        self.assertEqual(result.returncode, 23)
        self.assertTrue(report.exists())
        self.assertTrue((legacy / "installer/bootstrap_windows.ps1").exists())

    def test_relative_paths_are_rejected_without_starting_setup(self):
        result = subprocess.run([str(self.executable), "--headless", "--target", "relative"], timeout=30)
        self.assertNotEqual(result.returncode, 0)

    def test_corrupt_embedded_bytes_are_rejected_before_extraction(self):
        data = bytearray(self.executable.read_bytes())
        index = data.find(self.archive.read_bytes())
        self.assertGreaterEqual(index, 0)
        data[index + 30] ^= 1
        damaged = self.root / "damaged.exe"
        damaged.write_bytes(data)
        destination = self.root / "damaged output"
        result = subprocess.run([str(damaged), "--extract-only", str(destination)], timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(destination.exists())

    def test_even_a_correctly_hashed_payload_cannot_traverse_outside_its_root(self):
        archive = self.root / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr(NAME + "/../../escape.txt", "must not be written")
        executable = self.root / "unsafe.exe"
        compile_launcher(archive, executable, find_compiler())
        destination = self.root / "unsafe extraction"
        result = subprocess.run([str(executable), "--extract-only", str(destination)], timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "escape.txt").exists())
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
