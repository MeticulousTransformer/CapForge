"""Owned, per-user installation. Never scan/copy arbitrary repository content."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from environment import data_root, extension_root
from service_control import stop_for_update

TOOL = "CapForge"
LEGACY_TOOL = "Kartuli Caption Forge"
VERSION = "0.3.3"
EXTENSION_ID = "com.kartuli.captionforge"
SOURCE = Path(__file__).resolve().parents[1]
RUNTIME_FILES = ("run_backend.bat", "run_backend.sh", "Install Windows.cmd", "Install macOS.command", "LICENSE", "README.md")


def _inside(path: Path, parent: Path) -> Path:
    resolved = path.resolve()
    if resolved == parent.resolve() or parent.resolve() not in resolved.parents:
        raise ValueError("Installation path escaped its destination.")
    # Keep the original path so callers can still reject a symlink, even when
    # its target happens to be inside the installation root.
    return path.absolute()


def _owned(root: Path, marker: str) -> bool:
    file = root / marker
    if not file.exists():
        return False
    try:
        return json.loads(file.read_text(encoding="utf-8-sig")).get("tool") in {TOOL, LEGACY_TOOL}
    except (ValueError, OSError):
        return False


def _uses_private_python(python: Path, runtime: Path) -> bool:
    if not python.is_absolute() or runtime.is_symlink() or not runtime.is_dir():
        return False
    executable = python.resolve()
    # samefile also recognizes differently capitalized paths on macOS. Resolve
    # the executable first so a link to an outside interpreter stays outside.
    return executable.is_file() and any(parent.samefile(runtime) for parent in executable.parents)


def enable_unsigned() -> None:
    """Explicit installer option for the unsigned development build only."""
    if sys.platform == "win32":
        import winreg
        for version in (9, 10, 11, 12):
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Adobe\CSXS.{version}") as key:
                winreg.SetValueEx(key, "PlayerDebugMode", 0, winreg.REG_SZ, "1")
    elif sys.platform == "darwin":
        for version in (9, 10, 11, 12):
            subprocess.run(["/usr/bin/defaults", "write", f"com.adobe.CSXS.{version}", "PlayerDebugMode", "1"], check=True, capture_output=True)


def install(target: Path | None = None, extensions: Path | None = None, *, dependencies: bool = True, unsigned: bool = False, progress=print) -> dict:
    if sys.version_info < (3, 10):
        raise RuntimeError("Open the CapForge setup launcher to prepare a compatible private runtime.")
    root_input = target or data_root()
    ext_input = extensions or extension_root()
    if root_input.is_symlink() or ext_input.is_symlink():
        raise ValueError("Choose an installation folder that is not a symbolic link.")
    root = root_input.resolve()
    ext_parent = ext_input.resolve()
    # Refuse to write into an unrelated non-empty destination or follow links.
    if root.is_symlink() or (root.exists() and any(root.iterdir()) and not _owned(root, ".kcf-install.json")):
        raise ValueError("This folder contains unrelated files. Choose an empty installation folder.")
    if (ext_parent / EXTENSION_ID).is_symlink():
        raise ValueError("The extension destination is a symbolic link.")
    extension = _inside(ext_parent / EXTENSION_ID, ext_parent)
    if extension.is_symlink() or (extension.exists() and not _owned(extension, "install.json")):
        raise ValueError("The extension destination is not owned by CapForge. Move it aside before installing.")
    if (root / ".runtime").is_symlink():
        raise ValueError("The private runtime is a symbolic link. Choose an installation folder without symbolic links.")
    stop_for_update(root, progress=progress)
    root.mkdir(parents=True, exist_ok=True)
    ext_parent.mkdir(parents=True, exist_ok=True)
    marker = {"tool": TOOL, "version": VERSION, "runtimeRoot": str(root), "extension": str(extension)}
    # Mark before dependency work: failed installs can be retried safely.
    marker_file = root / ".kcf-install.json"
    old_marker = marker_file.read_text(encoding="utf-8") if marker_file.exists() else None
    marker_file.write_text(json.dumps(marker, indent=2), encoding="utf-8")
    staging = Path(tempfile.mkdtemp(prefix=".kcf-stage-", dir=root))
    backups = root / "backups" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    replaced: list[tuple[Path, Path | None]] = []
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", "node_modules", "exports", "models", ".env", "config.env", ".local-token", ".env-*")
    try:
        progress("Preparing your caption studio…")
        for name in ("ae", "backend", "docs", "agents", "installer"):
            shutil.copytree(SOURCE / name, staging / name, ignore=ignore)
        # Credentials belong to the user's existing install, never to the source package.
        for name in (".env", "config.env", ".local-token"):
            existing = root / "backend" / name
            if existing.exists():
                shutil.copy2(existing, staging / "backend" / name)
        shutil.copytree(SOURCE / "panel", staging / "panel", ignore=shutil.ignore_patterns("install.json", "json2.js"))
        shutil.copy2(SOURCE / "ae/lib/json2.js", staging / "panel/json2.js")
        (staging / "panel/install.json").write_text(json.dumps(marker, indent=2), encoding="utf-8")
        runtime_files = RUNTIME_FILES + tuple(name for name in ("CapForge Setup.exe", "release.json") if (SOURCE / name).is_file())
        for name in runtime_files:
            shutil.copy2(SOURCE / name, staging / name)
        shutil.copy2(SOURCE / "run_backend.sh", staging / "run_backend.command")
        # Archives and cross-platform copies can discard POSIX permissions.
        # Repair launchers must still open from Finder after installation.
        for name in ("Install macOS.command", "installer/bootstrap_macos.sh", "run_backend.sh", "run_backend.command"):
            (staging / name).chmod(0o755)
        if dependencies:
            progress("Preparing your private transcription service…")
            environment = _inside(root / ".venv", root)
            if environment.is_symlink():
                raise ValueError("The service environment is a symbolic link. Refusing to replace it.")
            python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            if environment.exists():
                try:
                    # JSON keeps this pipe ASCII-safe on Windows even when the
                    # user's folder contains Georgian or other Unicode text.
                    health = subprocess.run([str(python), "-I", "-c", "import json, sys, pip; print(json.dumps(sys._base_executable))"], capture_output=True, text=True, timeout=20)
                    healthy = health.returncode == 0
                    base_executable = json.loads(health.stdout) if healthy else None
                    healthy = healthy and isinstance(base_executable, str) and bool(base_executable)
                    private_runtime = root / ".runtime"
                    if healthy and _uses_private_python(Path(sys.executable), private_runtime):
                        # Earlier installs may work with system Python but cannot
                        # launch the independent private updater until migrated.
                        base_python = Path(base_executable)
                        healthy = _uses_private_python(base_python, private_runtime)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    healthy = False
                # pip can replace packages before an install fails. Keep a
                # complete earlier environment so rollback restores packages
                # together with the code that used them.
                backup = _inside(backups / "environment", root)
                backup.parent.mkdir(parents=True, exist_ok=True)
                if healthy:
                    progress("Backing up the transcription service…")
                    shutil.copytree(environment, backup, symlinks=True)
                else:
                    progress("Repairing the transcription service…")
                    shutil.move(str(environment), str(backup))
                replaced.append((environment, backup))
            if not python.exists():
                subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True, capture_output=True, text=True)
            progress("Installing the transcription service (internet required)…")
            cache = _inside(root / ".runtime/pip-cache", root)
            requirements = staging / "backend/requirements-lock.txt"
            if not requirements.is_file():
                requirements = staging / "backend/requirements.txt"
            result = subprocess.run([str(python), "-m", "pip", "--isolated", "install", "--disable-pip-version-check", "--cache-dir", str(cache), "-r", str(requirements)], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError("Could not install the service packages. Check your internet connection and retry.\n" + (result.stderr or result.stdout)[-900:])
            progress("Checking transcription and audio support…")
            for command in (
                [str(python), "-m", "pip", "--isolated", "check"],
                [str(python), "-I", "-c", "import fastapi, uvicorn, pydantic, requests, imageio_ffmpeg; imageio_ffmpeg.get_ffmpeg_exe()"],
            ):
                result = subprocess.run(command, capture_output=True, text=True)
                if result.returncode:
                    raise RuntimeError("The transcription packages could not be verified. Run setup again.\n" + (result.stderr or result.stdout)[-900:])
        progress("Installing the After Effects panel…")
        for name in ("ae", "backend", "docs", "agents", "installer", "panel", "run_backend.command") + runtime_files:
            destination = _inside(root / name, root)
            backup = None
            if destination.is_symlink():
                raise ValueError("An installed file is a symbolic link. Refusing to replace it.")
            if destination.exists():
                backups.mkdir(parents=True, exist_ok=True)
                backup = backups / name
                shutil.move(str(destination), str(backup))
            replaced.append((destination, backup))
            shutil.move(str(staging / name), str(destination))
        # Stage the extension on the same filesystem before replacing it.
        ext_stage = Path(tempfile.mkdtemp(prefix=".kcf-stage-", dir=ext_parent))
        try:
            shutil.copytree(root / "panel", ext_stage / EXTENSION_ID)
            backup = None
            if extension.exists():
                backups.mkdir(parents=True, exist_ok=True)
                backup = backups / "extension"
                shutil.move(str(extension), str(backup))
            replaced.append((extension, backup))
            shutil.move(str(ext_stage / EXTENSION_ID), str(extension))
        finally:
            _inside(ext_stage, ext_parent)
            shutil.rmtree(ext_stage)
        if unsigned:
            progress("Enabling this unsigned development panel for your user account…")
            enable_unsigned()
        progress("Installed. Restart AE, then open Window → Extensions → CapForge.")
        return marker
    except Exception:
        # Restore the previous files if replacement fails; keep outputs and venv.
        for destination, backup in reversed(replaced):
            if destination.exists():
                if destination.is_dir():
                    _inside(destination, root if root in destination.parents else ext_parent)
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            if backup and backup.exists():
                shutil.move(str(backup), str(destination))
        if old_marker is not None:
            marker_file.write_text(old_marker, encoding="utf-8")
        raise
    finally:
        _inside(staging, root)
        shutil.rmtree(staging)
