"""Build the standalone Windows installer from the verified, source-only release ZIP."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

from check_release import check_archive
from package_release import ROOT, members

MAX_PAYLOAD_BYTES = 512 * 1024 * 1024


def validate_archive(archive: Path) -> str:
    """Only the shared allowlisted payload may be embedded; never another EXE."""
    if archive.stat().st_size > MAX_PAYLOAD_BYTES:
        raise ValueError("The source payload is too large.")
    allowed = {path.relative_to(ROOT).as_posix() for path in members()}
    allowed.update({"release.json", "package-manifest.json"})
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if not entries or len(entries) > 10000:
            raise ValueError("Invalid source payload size.")
        root = entries[0].filename.split("/")[0]
        if not re.fullmatch(r"CapForge-\d+\.\d+\.\d+", root):
            raise ValueError("Invalid source payload root.")
        version = root.removeprefix("CapForge-")
        names = set()
        total = 0
        for entry in entries:
            parts = entry.filename.split("/")
            if len(parts) < 2 or parts[0] != root:
                raise ValueError("The source payload must have one release root.")
            for part in parts:
                if (not part or part in {".", ".."} or part.rstrip(" .") != part
                    or re.search(r'[\x00-\x1f<>:"\\|?*]', part)
                    or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part, re.I)):
                    raise ValueError("Unsafe Windows payload path: " + entry.filename)
            relative = "/".join(parts[1:])
            if relative.lower().endswith(".exe"):
                raise ValueError("Use a --source-only ZIP; the embedded payload cannot include an EXE.")
            if relative not in allowed:
                raise ValueError("Unallowlisted source component: " + relative)
            folded = entry.filename.casefold()
            if folded in names:
                raise ValueError("Duplicate Windows payload path: " + entry.filename)
            names.add(folded)
            total += entry.file_size
            if total > MAX_PAYLOAD_BYTES:
                raise ValueError("The expanded source payload is too large.")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Symlinks are not permitted in the source payload.")
    check_archive(archive, version)
    launcher = (ROOT / "installer/Launcher.cs").read_text(encoding="utf-8")
    for field in ("AssemblyVersion", "AssemblyFileVersion"):
        if f'{field}("{version}.0")' not in launcher:
            raise ValueError("Windows launcher and source payload versions differ.")
    return version


def find_compiler() -> Path:
    if sys.platform != "win32":
        raise RuntimeError("Build the Windows installer on Windows with the .NET Framework compiler.")
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    for framework in ("Framework64", "Framework"):
        candidate = windows / "Microsoft.NET" / framework / "v4.0.30319" / "csc.exe"
        if candidate.is_file():
            return candidate
    raise RuntimeError("The Windows .NET Framework compiler is unavailable.")


def compile_launcher(archive: Path, output: Path, compiler: Path) -> None:
    """Compile in a fresh folder and publish only the completed native executable."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="CapForge-Windows-build-") as temporary:
        stage = Path(temporary)
        payload = stage / "payload.zip"
        shutil.copyfile(archive, payload)
        (stage / "payload.sha256").write_text(hashlib.sha256(payload.read_bytes()).hexdigest(), encoding="ascii")
        shutil.copyfile(ROOT / "installer/Launcher.cs", stage / "Launcher.cs")
        subprocess.run([
            str(compiler), "/nologo", "/target:winexe", "/optimize+", "/platform:anycpu",
            "/reference:System.Windows.Forms.dll", "/reference:System.IO.Compression.dll",
            "/reference:System.IO.Compression.FileSystem.dll",
            "/resource:payload.zip,CapForge.Payload.zip",
            "/resource:payload.sha256,CapForge.Payload.sha256",
            "/out:CapForge-Setup.exe", "Launcher.cs",
        ], cwd=stage, check=True)
        executable = stage / "CapForge-Setup.exe"
        with executable.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError("The compiler did not produce a Windows executable.")
        shutil.copyfile(executable, output)
    output.with_suffix(output.suffix + ".sha256").write_text(
        hashlib.sha256(output.read_bytes()).hexdigest() + "  " + output.name + "\n", encoding="utf-8")


def build(archive: Path, output: Path | None = None) -> Path:
    archive = archive.resolve()
    version = validate_archive(archive)
    output = (output or archive.parent / f"CapForge-{version}-Windows.exe").resolve()
    if output == archive or output.suffix.lower() != ".exe":
        raise ValueError("Choose a separate .exe output path.")
    compile_launcher(archive, output, find_compiler())
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path, help="Verified source-only ZIP and adjacent .sha256")
    parser.add_argument("--output", type=Path, help="Defaults to CapForge-VERSION-Windows.exe beside the ZIP")
    args = parser.parse_args()
    output = build(args.archive, args.output)
    print(f"Created {output}\n{output.stat().st_size:,} bytes; payload SHA-256 verified at launch")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print("Windows package failed: " + str(error), file=sys.stderr)
        raise SystemExit(1)
