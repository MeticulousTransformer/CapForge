"""Release checks reject version drift and damaged download artifacts."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_release import check_archive, check_versions
from package_release import REQUIRED


class ReleaseMetadataTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.sources = {
            "installer/deployment.py": 'VERSION = "1.2.3"\n',
            "backend/app.py": 'VERSION = "1.2.3"\n',
            "scripts/package_release.py": 'NAME = "CapForge-1.2.3"\n',
            "panel/js/api.js": 'var serviceVersion = "1.2.3";',
            "panel/CSXS/manifest.xml": '<ExtensionManifest ExtensionBundleVersion="1.2.3"><ExtensionList><Extension Version="1.2.3" /></ExtensionList></ExtensionManifest>',
            "installer/Launcher.cs": '[assembly: AssemblyVersion("1.2.3.0")]\n[assembly: AssemblyFileVersion("1.2.3.0")]\n',
        }
        for name, data in self.sources.items():
            file = self.root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(data, encoding="utf-8")

    def test_consistent_components_report_the_release_version(self):
        self.assertEqual(check_versions(self.root), "1.2.3")

    def test_any_component_version_drift_blocks_release(self):
        for name, data in self.sources.items():
            with self.subTest(component=name):
                file = self.root / name
                file.write_text(data.replace("1.2.3", "1.2.4"), encoding="utf-8")
                with self.assertRaises(ValueError):
                    check_versions(self.root)
                file.write_text(data, encoding="utf-8")

    def archive(self, *, damaged=False, executable=True, launcher=True):
        files = {name: b"test component" for name in REQUIRED}
        files["release.json"] = json.dumps({
            "version": "1.2.3", "tag": os.environ.get("CAPFORGE_RELEASE_TAG", "dev"),
            "commit": os.environ.get("GITHUB_SHA", "test-commit"),
        }).encode()
        if launcher:
            files["CapForge Setup.exe"] = b"MZtest launcher"
        manifest = [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in files.items()]
        if damaged:
            files["backend/app.py"] = b"damaged component"
        path = self.root / "CapForge-1.2.3.zip"
        with zipfile.ZipFile(path, "w") as package:
            for name, data in files.items():
                info = zipfile.ZipInfo("CapForge-1.2.3/" + name)
                info.create_system = 3
                mode = 0o755 if executable and name.endswith((".command", ".sh")) else 0o644
                info.external_attr = (0o100000 | mode) << 16
                package.writestr(info, data)
            package.writestr("CapForge-1.2.3/package-manifest.json", json.dumps(manifest))
        path.with_suffix(".zip.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n")
        return path

    def test_complete_distribution_passes_archive_checks(self):
        check_archive(self.archive(), "1.2.3", require_windows_launcher=True)

    def test_corrupted_component_blocks_release_even_with_valid_zip_checksum(self):
        with self.assertRaisesRegex(ValueError, "backend/app.py"):
            check_archive(self.archive(damaged=True), "1.2.3")

    def test_mac_launcher_without_execution_permission_blocks_release(self):
        with self.assertRaisesRegex(ValueError, "executable"):
            check_archive(self.archive(executable=False), "1.2.3")

    def test_windows_distribution_requires_native_launcher(self):
        with self.assertRaisesRegex(ValueError, "CapForge Setup.exe"):
            check_archive(self.archive(launcher=False), "1.2.3", require_windows_launcher=True)


if __name__ == "__main__":
    unittest.main()
