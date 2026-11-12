"""Verified official releases, staged separately, installed by the existing wizard."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from threading import Lock
from urllib.parse import quote, urljoin, urlsplit

import requests

REPOSITORY = "MeticulousTransformer/Georgian-Kartuli-After-Effects-Transcribtion-Tool"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 128 * 1024 * 1024
REQUIRED_FILES = {
    "installer/install.py", "installer/deployment.py", "installer/environment.py", "installer/theme.py",
    "installer/runtime_assets.json", "installer/service_control.py", "backend/app.py", "backend/requirements.txt",
    "panel/CSXS/manifest.xml", "panel/host.jsx", "ae/lib/json2.js", "run_backend.sh", "run_backend.bat", "release.json"
}
_install_lock = Lock()
_installer_process = None


class UpdateError(RuntimeError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise UpdateError("CapForge update information is missing or invalid. Run the installer to repair this installation.") from error


def _same_directory(value, directory):
    if not isinstance(value, str) or not Path(value).is_absolute():
        return False
    try:
        return Path(value).samefile(directory)
    except (OSError, ValueError):
        return False


def _owned(root):
    root = Path(root)
    marker_path = root / ".kcf-install.json"
    if root.is_symlink() or marker_path.is_symlink() or not marker_path.is_file():
        raise UpdateError("Updates are available in an installed copy of CapForge. Open the installer first.")
    marker = _json(marker_path)
    if not isinstance(marker, dict) or marker.get("tool") not in {"CapForge", "Kartuli Caption Forge"} or not _same_directory(marker.get("runtimeRoot"), root):
        raise UpdateError("This folder is not a recognized CapForge installation.")
    extension_path = marker.get("extension")
    if not isinstance(extension_path, str):
        raise UpdateError("The installed Adobe extension location is invalid. Run CapForge Setup to repair it.")
    extension = Path(extension_path)
    if not extension.is_absolute() or extension.name != "com.kartuli.captionforge" or extension.is_symlink():
        raise UpdateError("The installed Adobe extension location is invalid. Run CapForge Setup to repair it.")
    ext_marker = _json(extension / "install.json")
    if not isinstance(ext_marker, dict) or ext_marker.get("tool") not in {"CapForge", "Kartuli Caption Forge"} or not _same_directory(ext_marker.get("runtimeRoot"), root):
        raise UpdateError("The Adobe extension belongs to a different installation. Run CapForge Setup to repair it.")
    return root.resolve(), extension.parent


def _fetch(url, limit, *, missing_ok=False):
    """Bound every response and redirect; no local panel token leaves this app."""
    deadline = time.monotonic() + 180
    allowed_hosts = {"api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
    for _ in range(5):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise UpdateError("The update download redirected outside GitHub's trusted release servers.")
        try:
            with requests.get(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "CapForge-Updater"}, timeout=(10, 30), allow_redirects=False, stream=True) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, response.headers.get("Location", ""))
                    continue
                if response.status_code == 404 and missing_ok:
                    return None
                response.raise_for_status()
                size = response.headers.get("Content-Length")
                if size and (not size.isdigit() or int(size) > limit):
                    raise UpdateError("The update download exceeds its size limit.")
                data = bytearray()
                for chunk in response.iter_content(65536):
                    if time.monotonic() > deadline:
                        raise UpdateError("The update download took too long. Check the connection and try again.", 502)
                    if len(data) + len(chunk) > limit:
                        raise UpdateError("The update download exceeds its size limit.")
                    data.extend(chunk)
                return bytes(data)
        except requests.RequestException as error:
            raise UpdateError("Could not reach CapForge updates. Check your internet connection and try again.", 502) from error
    raise UpdateError("The update download redirected too many times.", 502)


def _latest():
    raw = _fetch(LATEST_URL, 2 * 1024 * 1024, missing_ok=True)
    if raw is None:
        return None
    try:
        release = json.loads(raw)
        tag = release["tag_name"]
        if not isinstance(tag, str) or not tag or len(tag) > 200 or release.get("draft") or release.get("prerelease"):
            raise ValueError("Invalid public release")
        assets = release["assets"]
        packages = [a for a in assets if re.fullmatch(r"CapForge-(\d+\.\d+\.\d+)\.zip", a.get("name", ""))]
        if len(packages) != 1:
            raise ValueError("Missing release package")
        archive = packages[0]
        checksums = [a for a in assets if a.get("name") == archive["name"] + ".sha256"]
        if len(checksums) != 1:
            raise ValueError("Missing checksum")
        checksum = checksums[0]
        for asset in (archive, checksum):
            expected = f"https://github.com/{REPOSITORY}/releases/download/{quote(tag, safe='')}/{asset['name']}"
            if asset.get("browser_download_url") != expected or not isinstance(asset.get("size"), int) or not 0 < asset["size"] <= MAX_DOWNLOAD_BYTES:
                raise ValueError("Invalid release asset")
        version = re.fullmatch(r"CapForge-(\d+\.\d+\.\d+)\.zip", archive["name"]).group(1)
        return {"version": version, "tag": tag, "notes": str(release.get("body") or "")[:12000], "archive": archive, "checksum": checksum}
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise UpdateError("The latest release does not contain a complete verified CapForge update yet. Try again later.", 502) from error


def _status(root, current_version, release):
    record = _json(root / "release.json") if (root / "release.json").exists() else {}
    if not isinstance(record, dict):
        raise UpdateError("The installed release information is invalid. Run CapForge Setup to repair it.")
    current = record.get("version", current_version)
    if not isinstance(current, str) or not re.fullmatch(r"\d+\.\d+\.\d+", current):
        raise UpdateError("The installed version is invalid. Run CapForge Setup to repair it.")
    tag = record.get("tag", "")
    available = bool(release and release["tag"] != tag and tuple(map(int, release["version"].split("."))) >= tuple(map(int, current.split("."))))
    return {"available": available, "currentVersion": current, "currentTag": tag,
            "version": release["version"] if release else "", "tag": release["tag"] if release else "",
            "notes": release["notes"] if release else "",
            "message": "An update is ready to install." if available else "CapForge is up to date." if release else "No published update is available yet."}


def check(root, current_version):
    root, _ = _owned(root)
    return _status(root, current_version, _latest())


def _unpack(archive_path, destination, release):
    prefix = "CapForge-" + release["version"]
    files, seen, total = {}, set(), 0
    try:
        with zipfile.ZipFile(archive_path) as archive:
            if len(archive.infolist()) > 5000:
                raise UpdateError("The update archive contains too many files.")
            for info in archive.infolist():
                name = info.filename.rstrip("/")
                parts = name.split("/")
                mode = info.external_attr >> 16
                if parts[0] != prefix or (len(parts) < 2 and not info.is_dir()) or "\\" in name or ":" in name or any(p in {"", ".", ".."} or p.endswith((" ", ".")) for p in parts) or name.casefold() in seen or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise UpdateError("The update archive contains an unsafe or duplicate file path.")
                seen.add(name.casefold())
                total += info.file_size
                if total > MAX_EXPANDED_BYTES or info.file_size > MAX_DOWNLOAD_BYTES:
                    raise UpdateError("The expanded update exceeds its size limit.")
                if not info.is_dir():
                    files["/".join(parts[1:])] = info
            if not REQUIRED_FILES.issubset(files) or "package-manifest.json" not in files:
                raise UpdateError("The update package is missing required installer files.")
            manifest = json.loads(archive.read(files["package-manifest.json"]))
            if not isinstance(manifest, list):
                raise ValueError("Invalid manifest")
            listed = set()
            for entry in manifest:
                name = entry["path"]
                if name in listed or name not in files or name == "package-manifest.json":
                    raise ValueError("Invalid manifest entry")
                listed.add(name)
                data = archive.read(files[name])
                if entry["bytes"] != len(data) or entry["sha256"] != hashlib.sha256(data).hexdigest():
                    raise ValueError("Package hash mismatch")
            if listed != set(files) - {"package-manifest.json"}:
                raise ValueError("Unlisted package file")
            identity = json.loads(archive.read(files["release.json"]))
            if identity.get("tag") != release["tag"] or identity.get("version") != release["version"] or not re.fullmatch(r"[a-f0-9]{40}", identity.get("commit", "")):
                raise ValueError("Wrong release identity")
            package_root = destination / prefix
            for name, info in files.items():
                output = package_root / name
                output.parent.mkdir(parents=True, exist_ok=True)
                with output.open("xb") as handle:
                    handle.write(archive.read(info))
                if output.suffix in {".command", ".sh"}:
                    output.chmod(0o755)
            return package_root
    except (zipfile.BadZipFile, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
        if isinstance(error, UpdateError):
            raise
        raise UpdateError("The update package failed verification. Download it again by checking for updates.") from error


def install(root, current_version):
    global _installer_process
    if not _install_lock.acquire(blocking=False):
        raise UpdateError("An update is already being prepared. Wait for it to finish.", 409)
    stage, launched = None, False
    try:
        if _installer_process is not None and _installer_process.poll() is None:
            raise UpdateError("The update installer is already open. Finish or close it first.", 409)
        root, extensions = _owned(root)
        runtime = root / ".runtime"
        python = Path(getattr(sys, "_base_executable", "")).resolve()
        if runtime.is_symlink() or not python.is_file() or not any(_same_directory(str(parent), runtime) for parent in python.parents):
            raise UpdateError("CapForge's private setup runtime is unavailable. Run the CapForge installer once to repair it.")
        release = _latest()
        if not _status(root, current_version, release)["available"]:
            raise UpdateError("There is no newer CapForge update to install.")
        updates_root = root / ".updates"
        if updates_root.is_symlink():
            raise UpdateError("The update folder is a symbolic link. Run CapForge Setup to repair it.")
        updates_root.mkdir(exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix="release-", dir=updates_root))
        archive_name = release["archive"]["name"]
        checksum = _fetch(release["checksum"]["browser_download_url"], 4096).decode("ascii").strip().split()
        if len(checksum) not in (1, 2) or not re.fullmatch(r"[a-f0-9]{64}", checksum[0]) or (len(checksum) == 2 and checksum[1].lstrip("*") != archive_name):
            raise UpdateError("The update checksum file is invalid.")
        archive = _fetch(release["archive"]["browser_download_url"], MAX_DOWNLOAD_BYTES)
        if hashlib.sha256(archive).hexdigest() != checksum[0]:
            raise UpdateError("The update checksum did not match. Check for updates and try again.")
        archive_path = stage / archive_name
        archive_path.write_bytes(archive)
        package_root = _unpack(archive_path, stage, release)
        command = [str(python), str(package_root / "installer/install.py"), "--target", str(root), "--extension-root", str(extensions)]
        options = {"cwd": str(package_root), "stdin": subprocess.DEVNULL, "stderr": subprocess.STDOUT}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            options["start_new_session"] = True
        with (stage / "installer.log").open("wb") as log:
            _installer_process = subprocess.Popen(command, stdout=log, **options)
        launched = True
        return {"started": True, "version": release["version"], "tag": release["tag"], "message": "The update installer is opening. Save your work and close After Effects before installing. When setup finishes, start the service and reopen CapForge."}
    except (OSError, UnicodeError) as error:
        raise UpdateError("The update could not be prepared. Check available disk space and try again.") from error
    finally:
        if stage is not None and not launched:
            shutil.rmtree(stage, ignore_errors=True)
        _install_lock.release()
