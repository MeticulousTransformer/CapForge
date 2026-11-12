"""Exercise the shipped ZIP, including download permissions and private files."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("package_release", ROOT / "scripts/package_release.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="CapForge package ქართული ")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        for name in package.FILES:
            shutil.copy2(ROOT / name, self.root / name)
        for name in package.FOLDERS:
            shutil.copytree(ROOT / name, self.root / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    def test_private_files_and_backup_trees_never_enter_download(self):
        private = ["backend/customer.env", "backend/.env.local", "backend/account.json",
                   "backend/backups/old.py", "panel/.cache/session.json",
                   "installer/.runtime/settings.json", "backend/config.env"]
        for name in private:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("PRIVATE TEST SENTINEL", encoding="utf-8")
        with patch.object(package, "ROOT", self.root):
            selected = {path.relative_to(self.root).as_posix() for path in package.members()}
        self.assertEqual(set(private) & selected, set())
        self.assertIn("backend/config.example.env", selected)
        self.assertIn("backend/tests/fixtures/georgian_short.json", selected)
        self.assertIn("installer/runtime_assets.json", selected)

    def test_zip_restores_executable_permissions_and_has_verified_manifest(self):
        # Windows checkouts and some extractors remove POSIX permissions.
        for name in ("Install macOS.command", "installer/bootstrap_macos.sh", "run_backend.sh"):
            (self.root / name).chmod(0o644)
        archive = self.root / "download.zip"
        with patch.object(package, "ROOT", self.root):
            package.build_archive(archive)
        with zipfile.ZipFile(archive) as release:
            prefix = package.NAME + "/"
            for name in ("Install macOS.command", "installer/bootstrap_macos.sh", "run_backend.sh"):
                mode = release.getinfo(prefix + name).external_attr >> 16
                self.assertTrue(stat.S_ISREG(mode))
                self.assertEqual(mode & 0o777, 0o755)
            manifest = json.loads(release.read(prefix + "package-manifest.json"))
            for entry in manifest:
                data = release.read(prefix + entry["path"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
                self.assertEqual(len(data), entry["bytes"])
            self.assertEqual(len(manifest) + 1, len(release.namelist()))

    def test_missing_engine_dependency_refuses_to_publish(self):
        (self.root / "ae/lib/presets.jsx").unlink()
        archive = self.root / "download.zip"
        with patch.object(package, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "presets.jsx"):
                package.build_archive(archive)
        self.assertFalse(archive.exists())

    def test_release_identity_is_hashed_and_changes_for_each_published_commit(self):
        archive = self.root / "download.zip"
        commit = "c" * 40
        with patch.object(package, "ROOT", self.root), patch.dict(os.environ, {
            "GITHUB_SHA": commit, "CAPFORGE_RELEASE_TAG": "build-" + commit
        }):
            package.build_archive(archive)
        with zipfile.ZipFile(archive) as release:
            prefix = package.NAME + "/"
            identity = json.loads(release.read(prefix + "release.json"))
            self.assertEqual(identity, {"version": "0.3.2", "tag": "build-" + commit, "commit": commit})
            manifest = json.loads(release.read(prefix + "package-manifest.json"))
            self.assertIn("release.json", [entry["path"] for entry in manifest])

    def test_windows_checkout_still_ships_runnable_mac_shell_scripts(self):
        launchers = ("Install macOS.command", "installer/bootstrap_macos.sh", "run_backend.sh")
        for name in launchers:
            path = self.root / name
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        archive = self.root / "download.zip"
        with patch.object(package, "ROOT", self.root):
            package.build_archive(archive)
        with zipfile.ZipFile(archive) as release:
            for name in launchers:
                self.assertNotIn(b"\r\n", release.read(package.NAME + "/" + name))


if __name__ == "__main__":
    unittest.main()
