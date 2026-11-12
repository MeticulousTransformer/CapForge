"""Exercise a shipped native installer in a fresh isolated destination (CI)."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installer', type=Path, required=True)
    parser.add_argument('--platform', choices=['macos', 'windows'], required=True)
    args = parser.parse_args()
    if (sys.platform == 'win32') != (args.platform == 'windows'):
        parser.error('Native installer must be tested on its target OS.')
    with tempfile.TemporaryDirectory(prefix='CapForge native ქართული ') as folder:
        # macOS exposes TMPDIR through /var -> /private/var. Test the real
        # destination so the installer's symlink protection stays enabled.
        root = Path(folder).resolve()
        runtime, extensions = root / 'Fresh install/CapForge', root / 'Adobe extensions'
        # Give a Windows GUI-subsystem EXE real output handles, and preserve its
        # diagnostic output before the temporary installation is cleaned up.
        result = subprocess.run(
            [str(args.installer.resolve()), '--headless', '--target', str(runtime), '--extension-root', str(extensions)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=1500)
        print(result.stdout, flush=True)
        result.check_returncode()
        python = runtime / ('.venv/Scripts/python.exe' if args.platform == 'windows' else '.venv/bin/python')
        subprocess.run([str(python), '-m', 'pip', 'check'], check=True)
        subprocess.run([str(python), '-I', str(Path(__file__).parent / 'check_installed_runtime.py'), str(runtime)], check=True)
        identity = json.loads((runtime / 'release.json').read_text())
        if os.environ.get('GITHUB_SHA'):
            assert identity['commit'] == os.environ['GITHUB_SHA'], identity
        if os.environ.get('CAPFORGE_RELEASE_TAG'):
            assert identity['tag'] == os.environ['CAPFORGE_RELEASE_TAG'], identity
        assert (extensions / 'com.kartuli.captionforge/CSXS/manifest.xml').is_file()
        print(json.dumps({'nativeInstaller': str(args.installer), 'installedRelease': identity, 'result': 'passed'}))


if __name__ == '__main__':
    main()
