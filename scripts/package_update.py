"""Wrap a shared, verified payload with the native installer for one OS."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import zipfile

from check_release import check_archive


def build_update(source: Path, native: Path, output: Path, platform: str, *, legacy=False):
    if platform not in ('macos', 'windows'):
        raise ValueError('Choose macos or windows.')
    with zipfile.ZipFile(source) as archive:
        roots = {info.filename.split('/')[0] for info in archive.infolist()}
        if len(roots) != 1:
            raise ValueError('Expected one source package root.')
        prefix = roots.pop() + '/'
        identity = json.loads(archive.read(prefix + 'release.json'))
        check_archive(source, identity['version'])
        files = {info.filename[len(prefix):]: (archive.read(info), info.external_attr >> 16)
                 for info in archive.infolist() if not info.is_dir()
                 and info.filename != prefix + 'package-manifest.json'}
    files.pop('CapForge Setup.exe', None)
    if platform == 'macos':
        if native.name != 'CapForge.app' or not (native / 'Contents/MacOS/CapForge').is_file():
            raise ValueError('A built CapForge.app is required.')
        for path in sorted(native.rglob('*')):
            if path.is_symlink():
                raise ValueError('Native app must not contain symbolic links.')
            if path.is_file():
                relative = path.relative_to(native).as_posix()
                mode = stat.S_IFREG | 0o755 if relative == 'Contents/MacOS/CapForge' or path.suffix in ('.sh', '.command') else path.stat().st_mode
                files['CapForge.app/' + relative] = (path.read_bytes(), mode)
    else:
        if not native.is_file() or native.is_symlink() or not native.read_bytes().startswith(b'MZ'):
            raise ValueError('A built Windows EXE is required.')
        files['CapForge Setup.exe'] = (native.read_bytes(), stat.S_IFREG | 0o644)
    if not legacy:
        identity['platform'] = platform
    files['release.json'] = (json.dumps(identity, indent=2).encode(), stat.S_IFREG | 0o644)
    manifest = []
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, (data, mode) in sorted(files.items()):
            info = zipfile.ZipInfo(prefix + name)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | (0o755 if mode & 0o111 else 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
            manifest.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        archive.writestr(prefix + 'package-manifest.json', json.dumps(manifest, indent=2))
    output.with_suffix(output.suffix + '.sha256').write_text(hashlib.sha256(output.read_bytes()).hexdigest() + '  ' + output.name + '\n')
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--platform', choices=['macos', 'windows'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--legacy', action='store_true', help='Migration archive recognized by 0.3.2 updates')
    args = parser.parse_args()
    if args.archive.resolve() == args.output.resolve():
        parser.error('Output must differ from the source archive.')
    print(json.dumps(build_update(args.archive, args.native, args.output, args.platform, legacy=args.legacy)))


if __name__ == '__main__':
    main()
