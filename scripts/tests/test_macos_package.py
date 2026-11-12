"""Source verification and native app handoff; no live user installation."""
import hashlib
import importlib.util
import json
import os
import plistlib
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("build_macos", ROOT / "scripts/build_macos.py")
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


class MacSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def archive(self, *, extra=None, mutate=False, platform=None):
        identity = {"version": "0.3.3", "commit": "a" * 40, "tag": "test"}
        if platform:
            identity["platform"] = platform
        files = {name: b"fixture" for name in package.REQUIRED}
        files["release.json"] = json.dumps(identity).encode()
        manifest = [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in files.items()]
        if mutate:
            files["installer/install.py"] = b"changed"
        archive = self.root / "source.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            for name, data in files.items():
                handle.writestr("CapForge-0.3.3/" + name, data)
            handle.writestr("CapForge-0.3.3/package-manifest.json", json.dumps(manifest))
            if extra:
                handle.writestr(*extra)
        return archive

    def test_verified_payload_extracts_with_launch_permissions(self):
        identity = package.unpack_source(self.archive(), self.root / "payload")
        self.assertEqual(identity["version"], "0.3.3")
        script = self.root / "payload/installer/bootstrap_macos.sh"
        installer = self.root / "payload/installer/install.py"
        self.assertEqual(script.read_bytes(), b"fixture")
        self.assertEqual(installer.read_bytes(), b"fixture")
        if os.name != "nt":
            self.assertTrue(script.stat().st_mode & 0o111)
            self.assertFalse(installer.stat().st_mode & 0o111)

    def test_rejects_tampered_payload(self):
        with self.assertRaisesRegex(ValueError, "verification failed"):
            package.unpack_source(self.archive(mutate=True), self.root / "payload")
        self.assertFalse((self.root / "payload").exists())

    def test_rejects_traversal_and_unlisted_payload(self):
        for name in ("CapForge-0.3.3/../escape", "CapForge-0.3.3/unlisted"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                package.unpack_source(self.archive(extra=(name, b"bad")), self.root / "payload")

    def test_rejects_symlinks(self):
        link = zipfile.ZipInfo("CapForge-0.3.3/shortcut")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            package.unpack_source(self.archive(extra=(link, b"/tmp/elsewhere")), self.root / "payload")

    def test_rejects_platform_archive_as_source(self):
        with self.assertRaisesRegex(ValueError, "shared source package"):
            package.unpack_source(self.archive(platform="macos"), self.root / "payload")

    def test_bundle_metadata(self):
        metadata = plistlib.loads(plistlib.dumps(package.app_metadata("0.3.3")))
        self.assertEqual(metadata["CFBundlePackageType"], "APPL")
        self.assertEqual(metadata["CFBundleExecutable"], "CapForge")
        self.assertEqual(metadata["LSMinimumSystemVersion"], "11.0")
        self.assertEqual(metadata["CFBundleShortVersionString"], "0.3.3")


@unittest.skipUnless(sys.platform == "darwin", "Native Mac bundle validation runs on macOS")
class NativeMacTests(unittest.TestCase):
    def setUp(self):
        self.app = Path(os.environ.get("CAPFORGE_TEST_MACOS_APP", ROOT / "dist/CapForge.app"))
        self.executable = self.app / "Contents/MacOS/CapForge"
        if not self.executable.is_file():
            self.skipTest("Build CapForge.app to validate the native executable")

    def test_universal_bundle_is_signed_and_matches_payload(self):
        architectures = subprocess.check_output(["xcrun", "lipo", "-archs", str(self.executable)], text=True).split()
        self.assertEqual(set(architectures), {"arm64", "x86_64"})
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(self.app)], check=True, capture_output=True)
        metadata = plistlib.loads((self.app / "Contents/Info.plist").read_bytes())
        identity = json.loads((self.app / "Contents/Resources/payload/release.json").read_bytes())
        self.assertEqual(metadata["CFBundleShortVersionString"], identity["version"])

    def test_cli_preserves_unicode_custom_paths_without_writes(self):
        with tempfile.TemporaryDirectory(prefix="CapForge native ქართული ") as directory:
            target = Path(directory) / "Private Runtime"
            extensions = Path(directory) / "Adobe Extensions"
            result = subprocess.run([str(self.executable), "--dry-run", "--target", str(target), "--extension-root", str(extensions)], check=True, capture_output=True, text=True)
            details = json.loads(result.stdout)
            self.assertEqual(details["runtime"], str(target))
            self.assertEqual(details["extensions"], str(extensions))
            self.assertFalse(details["enableUnsigned"])
            self.assertFalse(target.exists())
            self.assertFalse(extensions.exists())

    def test_relative_cli_destination_is_rejected(self):
        result = subprocess.run([str(self.executable), "--headless", "--target", "relative"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute folder path", result.stderr)

    def test_older_app_repairs_newer_installed_payload(self):
        with tempfile.TemporaryDirectory(prefix="CapForge newer runtime ") as directory:
            target = Path(directory) / "Runtime"
            (target / "installer").mkdir(parents=True)
            (target / ".kcf-install.json").write_text(json.dumps({"tool": "CapForge"}))
            (target / "release.json").write_text(json.dumps({"version": "99.0.0", "builtAt": 1}))
            script = target / "installer/bootstrap_macos.sh"
            script.write_text("#!/bin/bash\n")
            result = subprocess.run([str(self.executable), "--dry-run", "--target", str(target)], check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout)["bootstrap"], str(script))

    def test_same_version_repairs_newer_commit_payload(self):
        identity = json.loads((self.app / "Contents/Resources/payload/release.json").read_bytes())
        with tempfile.TemporaryDirectory(prefix="CapForge newer commit ") as directory:
            target = Path(directory)
            (target / "installer").mkdir()
            (target / ".kcf-install.json").write_text(json.dumps({"tool": "CapForge"}))
            (target / "release.json").write_text(json.dumps({"version": identity["version"], "builtAt": identity.get("builtAt", 0) + 1}))
            script = target / "installer/bootstrap_macos.sh"
            script.write_text("#!/bin/bash\n")
            result = subprocess.run([str(self.executable), "--dry-run", "--target", str(target)], check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout)["bootstrap"], str(script))

    def test_headless_errors_come_from_the_bundled_installer(self):
        with tempfile.TemporaryDirectory(prefix="CapForge protected ქართული ") as directory:
            target = Path(directory).resolve() / "Unrelated Folder"
            target.mkdir()
            (target / "Keep.txt").write_text("Keep this file")
            result = subprocess.run([str(self.executable), "--headless", "--target", str(target), "--extension-root", str(Path(directory) / "Extensions")], capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unrelated files", result.stdout)
            self.assertEqual((target / "Keep.txt").read_text(), "Keep this file")
            self.assertEqual(list(target.iterdir()), [target / "Keep.txt"])


if __name__ == "__main__":
    unittest.main()
