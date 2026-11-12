"""Build a small distributable from an explicit allowlist, never a repo snapshot."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "CapForge-0.3.2"
FOLDERS = ("panel", "ae", "backend", "installer", "agents", "docs", "scripts")
FILES = ("README.md", "AGENTS.md", "LICENSE", "Install Windows.cmd", "Install macOS.command", "run_backend.bat", "run_backend.sh")
EXTENSIONS = {".py", ".ps1", ".sh", ".cs", ".jsx", ".js", ".html", ".css", ".xml", ".md", ".txt", ".example"}
# Data files are individually allowed: arbitrary JSON/env files may hold keys.
DATA_FILES = {
    "backend/config.example.env", "installer/runtime_assets.json", "docs/studio-narrow.png",
    "backend/tests/fixtures/georgian_short.json", "backend/tests/fixtures/english_short.json",
    "backend/tests/fixtures/provider_elevenlabs_raw.json",
    "backend/tests/fixtures/provider_openai_whisper_raw.json",
}
REQUIRED = FILES + (
    "panel/CSXS/manifest.xml", "panel/index.html", "panel/host.jsx",
    "panel/js/bridge.js", "panel/js/api.js", "panel/js/app.js",
    "ae/KartuliCaptionForge.jsx", "ae/lib/json2.js", "ae/lib/presets.jsx",
    "ae/lib/title_registry.jsx", "ae/lib/style_shuffle.jsx", "ae/lib/text_measure.jsx",
    "ae/lib/layer_builder.jsx", "ae/lib/http_client.jsx", "backend/app.py",
    "backend/start_service.py", "backend/requirements.txt", "installer/install.py",
    "installer/bootstrap_macos.sh", "installer/bootstrap_windows.ps1",
    "installer/runtime_windows.ps1", "installer/runtime_assets.json",
    "backend/services/updates.py", "panel/js/updates.js", "backend/requirements-lock.txt",
    "installer/service_control.py",
)


def members():
    for name in FILES:
        yield ROOT / name
    if (ROOT / "CapForge Setup.exe").is_file():
        yield ROOT / "CapForge Setup.exe"
    for folder in FOLDERS:
        for path in sorted((ROOT / folder).rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or any(
                part.startswith(".") or part in {"__pycache__", "node_modules", "exports", "models", "backups"}
                for part in relative.parts
            ) or any(parent.is_symlink() for parent in (path, *path.parents) if parent != ROOT and ROOT in parent.parents):
                continue
            if path.name in {".env", "config.env", ".local-token", "install.json"} or path.name.startswith(".env-"):
                continue
            if path.suffix in EXTENSIONS or relative.as_posix() in DATA_FILES:
                yield path


def release_identity():
    commit = os.environ.get("GITHUB_SHA", "")
    if not commit:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        commit = result.stdout.strip() if result.returncode == 0 else "0" * 40
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("A release needs a valid commit identifier.")
    tag = os.environ.get("CAPFORGE_RELEASE_TAG", "local-" + commit)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", tag):
        raise ValueError("Invalid release tag.")
    return {"version": NAME.removeprefix("CapForge-"), "tag": tag, "commit": commit}


def build_archive(archive):
    paths = list(members())
    included = {path.relative_to(ROOT).as_posix() for path in paths}
    for name in REQUIRED:
        path = ROOT / name
        if name not in included or not path.is_file() or path.is_symlink():
            raise ValueError("Missing or unsafe release component: " + name)
    manifest = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        def add(relative, data):
            info = zipfile.ZipInfo(NAME + "/" + relative)
            info.create_system = 3
            info.external_attr = (0o100755 if Path(relative).suffix in (".command", ".sh") else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(info, data)
            manifest.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        for path in paths:
            data = path.read_bytes()
            if path.suffix in (".command", ".sh"):
                data = data.replace(b"\r\n", b"\n")
            add(path.relative_to(ROOT).as_posix(), data)
        add("release.json", json.dumps(release_identity(), indent=2).encode("utf-8"))
        package.writestr(NAME + "/package-manifest.json", json.dumps(manifest, indent=2))
    return manifest


def main():
    from sync_preview_styles import build
    build()
    if sys.platform == "win32":
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/build_windows_launcher.ps1")], check=True)
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    archive = destination / (NAME + ".zip")
    manifest = build_archive(archive)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(checksum + "  " + archive.name + "\n", encoding="utf-8")
    print(f"Created {archive}\n{len(manifest)} files · {archive.stat().st_size:,} bytes")


if __name__ == "__main__": main()
