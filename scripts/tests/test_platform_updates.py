import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from package_release import NAME, build_archive
from package_update import build_update
import hashlib


class PlatformPackages(unittest.TestCase):
    def test_native_updates_keep_shared_identity_and_hash_every_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / (NAME + '.zip')
            build_archive(source, source_only=True)
            source.with_suffix('.zip.sha256').write_text(hashlib.sha256(source.read_bytes()).hexdigest())
            app = root / 'CapForge.app'
            binary = app / 'Contents/MacOS/CapForge'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'native test executable'); binary.chmod(0o755)
            exe = root / 'native.exe'; exe.write_bytes(b'MZtest')
            for platform, native in [('macos', app), ('windows', exe)]:
                output = root / (platform + '.zip')
                identity = build_update(source, native, output, platform)
                self.assertEqual(identity['platform'], platform)
                with zipfile.ZipFile(output) as archive:
                    prefix = NAME + '/'
                    manifest = json.loads(archive.read(prefix + 'package-manifest.json'))
                    self.assertEqual(len(archive.namelist()), len(manifest)+1)
                    for entry in manifest:
                        data = archive.read(prefix + entry['path'])
                        self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'])
                    name = 'CapForge.app/Contents/MacOS/CapForge' if platform == 'macos' else 'CapForge Setup.exe'
                    self.assertIn(prefix+name, archive.namelist())
                    if platform == 'macos':
                        self.assertTrue((archive.getinfo(prefix+name).external_attr >> 16) & 0o111)
                        self.assertNotIn(prefix+'CapForge Setup.exe', archive.namelist())
            identity = build_update(source, app, root / 'legacy.zip', 'macos', legacy=True)
            self.assertNotIn('platform', identity)
            with self.assertRaisesRegex(ValueError, 'EXE'):
                build_update(source, binary, root / 'bad.zip', 'windows')
