"""Run the release checks. Uses the selected Python and Node; downloads nothing."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

from package_release import REQUIRED

ROOT = Path(__file__).resolve().parents[1]


def assignment(path: Path, name: str) -> str:
    for statement in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in statement.targets):
            return ast.literal_eval(statement.value)
    raise ValueError(f"Missing {name} in {path}")


def check_versions(root: Path = ROOT) -> str:
    version = assignment(root / "installer/deployment.py", "VERSION")
    manifest = ET.parse(root / "panel/CSXS/manifest.xml").getroot()
    api = re.search(r'\bserviceVersion\s*=\s*[\'"]([^\'"]+)', (root / "panel/js/api.js").read_text(encoding="utf-8"))
    if not api:
        raise ValueError("Missing serviceVersion in panel/js/api.js")
    versions = {
        "backend/app.py": assignment(root / "backend/app.py", "VERSION"),
        "scripts/package_release.py": assignment(root / "scripts/package_release.py", "NAME").removeprefix("CapForge-"),
        "panel/js/api.js": api.group(1),
        "CEP bundle": manifest.attrib["ExtensionBundleVersion"],
        "CEP panel": manifest.find("ExtensionList/Extension").attrib["Version"],
    }
    launcher = (root / "installer/Launcher.cs").read_text(encoding="utf-8")
    for field in ("AssemblyVersion", "AssemblyFileVersion"):
        match = re.search(field + r'\("([^"\n]+)"\)', launcher)
        versions[field] = match.group(1).removesuffix(".0") if match else "missing"
    drift = [f"{name}: {value}" for name, value in versions.items() if value != version]
    if drift:
        raise ValueError(f"Release versions must match installer {version}: " + ", ".join(drift))
    return version


def check_archive(path: Path, version: str, *, require_windows_launcher: bool = False) -> None:
    checksum = path.with_suffix(path.suffix + ".sha256").read_text(encoding="utf-8").split()[0]
    if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise ValueError("The release ZIP checksum does not match.")
    prefix = "CapForge-" + version + "/"
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        if len(names) != len(set(names)):
            raise ValueError("The release ZIP contains duplicate files.")
        manifest = json.loads(package.read(prefix + "package-manifest.json"))
        expected = {prefix + "package-manifest.json"}
        for entry in manifest:
            relative = PurePosixPath(entry["path"])
            if relative.is_absolute() or ".." in relative.parts or "\\" in entry["path"]:
                raise ValueError("Unsafe release path: " + entry["path"])
            name = prefix + entry["path"]
            if name in expected:
                raise ValueError("Duplicate manifest entry: " + entry["path"])
            expected.add(name)
            data = package.read(name)
            if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError("Damaged release component: " + entry["path"])
            mode = package.getinfo(name).external_attr >> 16
            if mode & 0o170000 == 0o120000:
                raise ValueError("Symlink in release: " + entry["path"])
            if relative.suffix in (".command", ".sh") and mode & 0o111 != 0o111:
                raise ValueError("Mac launcher is not executable: " + entry["path"])
        if set(names) != expected:
            raise ValueError("The release ZIP contains unlisted files.")
        for name in (*REQUIRED, "release.json"):
            if prefix + name not in expected:
                raise ValueError("Missing release component: " + name)
        release = json.loads(package.read(prefix + "release.json"))
        if release.get("version") != version:
            raise ValueError("release.json version does not match the application.")
        for key, variable in (("tag", "CAPFORGE_RELEASE_TAG"), ("commit", "GITHUB_SHA")):
            if os.environ.get(variable) and release.get(key) != os.environ[variable]:
                raise ValueError("release.json has the wrong " + key)
        if require_windows_launcher:
            name = prefix + "CapForge Setup.exe"
            if name not in expected or not package.read(name).startswith(b"MZ"):
                raise ValueError("Missing or invalid CapForge Setup.exe")


def run(arguments: list[str]) -> None:
    print("\n> " + " ".join(arguments), flush=True)
    subprocess.run(arguments, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", action="store_true", help="Build the ZIP after all checks pass")
    parser.add_argument("--archive", type=Path, help="Also validate an existing ZIP and its .sha256 file")
    parser.add_argument("--require-windows-launcher", action="store_true", help="Require the native EXE in --archive")
    args = parser.parse_args()
    version = check_versions()
    print("Checking CapForge " + version, flush=True)
    for folder in ("backend/tests", "installer/tests", "scripts/tests"):
        run([sys.executable, "-m", "unittest", "discover", "-s", folder, "-v"])
    for folder in ("ae/tests", "panel/tests", "scripts/tests"):
        for file in sorted((ROOT / folder).glob("test_*.js")):
            run(["node", str(file)])
    if sys.platform == "win32":
        run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "installer/tests/test_runtime_windows.ps1"])
    else:
        for file in ("Install macOS.command", "installer/bootstrap_macos.sh", "run_backend.sh"):
            run(["/bin/bash", "-n", file])
    if args.package:
        run([sys.executable, "scripts/package_release.py"])
    if args.archive:
        check_archive(args.archive.resolve(), version, require_windows_launcher=args.require_windows_launcher)
    print("Release checks passed.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print("Release check failed: " + str(error), file=sys.stderr)
        raise SystemExit(1)
