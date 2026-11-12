"""Build the native universal Mac app and drag-to-Applications disk image.

Uses only Python's standard library and Apple's Command Line Tools. The source
ZIP is the allowlisted package from package_release.py, not an arbitrary folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "installer/macos"
BUNDLE_ID = "com.capforge.app"
MAX_PAYLOAD_BYTES = 128 * 1024 * 1024
REQUIRED = {"installer/bootstrap_macos.sh", "installer/install.py", "panel/CSXS/manifest.xml", "release.json"}


def unpack_source(archive: Path, destination: Path) -> dict:
    """Verify every source byte before extracting; never follow archive links."""
    with zipfile.ZipFile(archive) as package:
        files, seen = {}, set()
        total = 0
        prefix = None
        for info in package.infolist():
            parts = info.filename.rstrip("/").split("/")
            mode = info.external_attr >> 16
            if (not parts or not re.fullmatch(r"CapForge-\d+\.\d+\.\d+", parts[0])
                    or any(part in {"", ".", ".."} or part.endswith((" ", ".")) for part in parts)
                    or "\\" in info.filename or ":" in info.filename
                    or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)
                    or info.filename.casefold() in seen):
                raise ValueError("Unsafe or duplicate source archive path: " + info.filename)
            seen.add(info.filename.casefold())
            prefix = prefix or parts[0]
            if parts[0] != prefix:
                raise ValueError("The source archive contains multiple package roots.")
            total += info.file_size
            if total > MAX_PAYLOAD_BYTES or len(seen) > 5000:
                raise ValueError("The source payload exceeds its size limit.")
            if not info.is_dir():
                if len(parts) < 2:
                    raise ValueError("Invalid source file path.")
                files["/".join(parts[1:])] = info
        if not REQUIRED.issubset(files) or "package-manifest.json" not in files:
            raise ValueError("The source package is missing required components.")
        manifest = json.loads(package.read(files["package-manifest.json"]))
        if not isinstance(manifest, list):
            raise ValueError("Invalid source manifest.")
        listed = set()
        for entry in manifest:
            name = entry["path"]
            if name in listed or name not in files or name == "package-manifest.json":
                raise ValueError("Invalid or duplicate source manifest entry.")
            listed.add(name)
            data = package.read(files[name])
            if entry["bytes"] != len(data) or entry["sha256"] != hashlib.sha256(data).hexdigest():
                raise ValueError("Source package verification failed: " + name)
        if listed != set(files) - {"package-manifest.json"}:
            raise ValueError("The source archive contains unlisted files.")
        identity = json.loads(package.read(files["release.json"]))
        if identity.get("version") != prefix.removeprefix("CapForge-") or identity.get("platform") is not None:
            raise ValueError("Use the shared source package, not a platform update ZIP.")
        if not re.fullmatch(r"[a-f0-9]{40}", identity.get("commit", "")):
            raise ValueError("The source package has no valid release commit.")
        for name, info in files.items():
            output = destination / name
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as handle:
                handle.write(package.read(info))
            output.chmod(0o755 if output.suffix in {".sh", ".command"} else 0o644)
    return identity


def app_metadata(version: str) -> dict:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid app version.")
    return {
        "CFBundleName": "CapForge",
        "CFBundleDisplayName": "CapForge",
        "CFBundleExecutable": "CapForge",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundlePackageType": "APPL",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "CFBundleIconFile": "CapForge.icns",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
        "NSHumanReadableCopyright": "CapForge contributors. MIT license.",
    }


def run(*arguments: str | Path) -> None:
    subprocess.run([str(value) for value in arguments], check=True)


def build_app(archive: Path, output: Path, *, sign_identity: str = "-") -> tuple[Path, dict]:
    if sys.platform != "darwin":
        raise RuntimeError("Build the Mac app on macOS with Apple's Command Line Tools.")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".macos-build-", dir=output) as temporary:
        stage = Path(temporary)
        app = stage / "CapForge.app"
        contents = app / "Contents"
        resources = contents / "Resources"
        executable = contents / "MacOS/CapForge"
        executable.parent.mkdir(parents=True)
        identity = unpack_source(archive, resources / "payload")
        (contents / "Info.plist").write_bytes(plistlib.dumps(app_metadata(identity["version"]), sort_keys=False))
        (contents / "PkgInfo").write_bytes(b"APPL????")
        shutil.copy2(NATIVE / "Help.html", resources / "Help.html")
        iconset = stage / "CapForge.iconset"
        module_cache = stage / "module-cache"
        run("xcrun", "swift", "-module-cache-path", module_cache, NATIVE / "MakeIcon.swift", iconset)
        run("/usr/bin/iconutil", "-c", "icns", iconset, "-o", resources / "CapForge.icns")
        binaries = []
        for architecture in ("arm64", "x86_64"):
            binary = stage / ("CapForge-" + architecture)
            run("xcrun", "swiftc", "-swift-version", "5", "-O", "-module-cache-path", module_cache,
                "-target", architecture + "-apple-macos11.0", "-framework", "AppKit",
                NATIVE / "CapForge.swift", "-o", binary)
            binaries.append(binary)
        run("xcrun", "lipo", "-create", *binaries, "-output", executable)
        executable.chmod(0o755)
        if sign_identity == "-":
            run("/usr/bin/codesign", "--force", "--sign", "-", "--timestamp=none", app)
        else:
            run("/usr/bin/codesign", "--force", "--sign", sign_identity, "--options", "runtime", "--timestamp", app)
        run("/usr/bin/codesign", "--verify", "--deep", "--strict", app)
        run(executable, "--dry-run")
        destination = output / "CapForge.app"
        if destination.exists():
            info = destination / "Contents/Info.plist"
            if destination.is_symlink() or not info.is_file() or plistlib.loads(info.read_bytes()).get("CFBundleIdentifier") != BUNDLE_ID:
                raise ValueError("Refusing to replace an unrelated app at " + str(destination))
            shutil.rmtree(destination)
        shutil.move(str(app), str(destination))
    return destination, identity


def build_dmg(app: Path, output: Path, version: str) -> Path:
    destination = output / f"CapForge-{version}-macOS.dmg"
    with tempfile.TemporaryDirectory(prefix=".macos-dmg-", dir=output) as temporary:
        stage = Path(temporary)
        # ditto preserves the bundle's exact resource bytes and file modes.
        run("/usr/bin/ditto", app, stage / "CapForge.app")
        (stage / "Applications").symlink_to("/Applications", target_is_directory=True)
        run("/usr/bin/hdiutil", "create", "-volname", "CapForge", "-srcfolder", stage,
            "-format", "UDZO", "-fs", "HFS+", "-ov", destination)
    destination.with_suffix(".dmg.sha256").write_text(
        hashlib.sha256(destination.read_bytes()).hexdigest() + "  " + destination.name + "\n", encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path, help="Allowlisted source ZIP from package_release.py")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--skip-dmg", action="store_true", help="Compile and verify the .app only")
    parser.add_argument("--sign-identity", default=os.environ.get("CAPFORGE_MACOS_SIGNING_IDENTITY", "-"), help="Developer ID identity; defaults to ad-hoc preview signing")
    args = parser.parse_args()
    app, identity = build_app(args.archive.resolve(), args.output_dir.resolve(), sign_identity=args.sign_identity)
    print("Created " + str(app), flush=True)
    if not args.skip_dmg:
        print("Created " + str(build_dmg(app, args.output_dir.resolve(), identity["version"])), flush=True)
    if args.sign_identity == "-":
        print("Preview signing: ad-hoc. This app is not Apple notarized.", flush=True)


if __name__ == "__main__":
    main()
