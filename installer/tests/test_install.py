import json
import sys
import tempfile
import unittest
import os
import subprocess
import shutil
import types
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deployment import EXTENSION_ID, install
import deployment


class TestInstaller(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "POSIX executable permissions")
    def test_installed_repair_launcher_works_when_source_lost_execute_permission(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            source = base / "source"
            source.mkdir()
            for name in ("ae", "backend", "docs", "agents", "installer", "panel"):
                shutil.copytree(deployment.SOURCE / name, source / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".env", ".env-*", "config.env", ".local-token", ".venv", "exports", "models"))
            for name in deployment.RUNTIME_FILES:
                shutil.copy2(deployment.SOURCE / name, source / name)
            (source / "release.json").write_text('{"version":"0.3.2"}\n')
            (source / "Install macOS.command").chmod(0o644)
            root, extensions = base / "runtime", base / "extensions"
            with patch("deployment.SOURCE", source):
                install(root, extensions, dependencies=False, progress=lambda _: None)
            (root / "installer/bootstrap_macos.sh").write_text('printf "repair opened\\n"\n')
            result = subprocess.run([str(root / "Install macOS.command")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "repair opened\n")
            self.assertEqual(json.loads((root / "release.json").read_text())["version"], "0.3.2")

    def test_unavailable_setup_window_reports_failure(self):
        import install as installer_ui
        tkinter = types.ModuleType("tkinter")
        tkinter.TclError = RuntimeError
        def unavailable_window():
            raise tkinter.TclError("display unavailable")
        tkinter.Tk = unavailable_window
        tkinter.messagebox = object()
        tkinter.ttk = object()
        with patch.dict(sys.modules, {"tkinter": tkinter}):
            with self.assertRaisesRegex(RuntimeError, "graphical installer could not open"):
                installer_ui.wizard()

    def test_dependency_install_uses_the_shipped_lock_file(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            root, extensions = base / "runtime", base / "extensions"
            requirement_files = []
            def run(arguments, **kwargs):
                if arguments[1:3] == ["-m", "pip"] and "install" in arguments:
                    file = Path(arguments[arguments.index("-r") + 1])
                    requirement_files.append((file.name, file.read_bytes()))
                return subprocess.CompletedProcess(arguments, 0, "", "")
            with patch("deployment.subprocess.run", side_effect=run):
                install(root, extensions, progress=lambda _: None)
            self.assertEqual(requirement_files, [("requirements-lock.txt", (deployment.SOURCE / "backend/requirements-lock.txt").read_bytes())])

    def test_private_setup_migrates_external_python_and_preserves_other_healthy_environments(self):
        for managed_setup, private_environment in ((True, False), (True, True), (False, False)):
            with self.subTest(managed_setup=managed_setup, private_environment=private_environment), tempfile.TemporaryDirectory() as folder:
                base = Path(folder).resolve()
                root, extensions = base / "runtime", base / "extensions"
                install(root, extensions, dependencies=False, progress=lambda _: None)
                interpreter = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
                interpreter.parent.mkdir(parents=True)
                interpreter.write_text("earlier environment")
                (root / ".venv/user-package.txt").write_text("preserve")
                private_python = root / ".runtime/python/python.exe"
                private_python.parent.mkdir(parents=True)
                private_python.touch()
                old_base = private_python if private_environment else base / "system-python"
                setup_python = private_python if managed_setup else base / "developer-python"
                def run(arguments, **kwargs):
                    if arguments[1:3] == ["-m", "venv"]:
                        interpreter.parent.mkdir(parents=True)
                        interpreter.write_text("managed environment")
                    output = json.dumps(str(old_base)) + "\n" if "sys._base_executable" in arguments[-1] else ""
                    return subprocess.CompletedProcess(arguments, 0, output, "")
                with patch("deployment.sys.executable", str(setup_python)), patch("deployment.subprocess.run", side_effect=run):
                    install(root, extensions, progress=lambda _: None)
                migrated = managed_setup and not private_environment
                self.assertEqual(interpreter.read_text(), "managed environment" if migrated else "earlier environment")
                saved = list((root / "backups").glob("*/environment/user-package.txt"))
                self.assertEqual(len(saved), 1 if migrated else 0)
                if migrated:
                    self.assertEqual(saved[0].read_text(), "preserve")

    def test_private_python_probe_preserves_georgian_paths_with_cp1252_stdout(self):
        real_python, real_run = sys.executable, subprocess.run
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            root, extensions = base / "runtime", base / "extensions"
            install(root, extensions, dependencies=False, progress=lambda _: None)
            private_python = root / ".runtime/ქართული/python.exe"
            private_python.parent.mkdir(parents=True)
            private_python.touch()
            interpreter = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text("healthy environment")
            probes = []
            def run(arguments, **kwargs):
                if "sys._base_executable" in arguments[-1]:
                    preamble = "import sys; sys.stdout.reconfigure(encoding='cp1252'); sys._base_executable = " + ascii(str(private_python)) + "; "
                    result = real_run([real_python, "-I", "-c", preamble + arguments[-1]], **kwargs)
                    probes.append(result)
                    return result
                if arguments[1:3] == ["-m", "venv"]:
                    interpreter.parent.mkdir(parents=True)
                    interpreter.write_text("rebuilt environment")
                return subprocess.CompletedProcess(arguments, 0, "", "")
            with patch("deployment.sys.executable", str(private_python)), patch("deployment.subprocess.run", side_effect=run):
                install(root, extensions, progress=lambda _: None)
            self.assertEqual(len(probes), 1)
            self.assertEqual(probes[0].returncode, 0, probes[0].stderr)
            self.assertEqual(interpreter.read_text(), "healthy environment")
            self.assertEqual(list((root / "backups").glob("*/environment")), [])

    def test_malformed_python_probe_is_repaired(self):
        for output in ("not JSON", "null", "{}"):
            with self.subTest(output=output), tempfile.TemporaryDirectory() as folder:
                base = Path(folder).resolve()
                root, extensions = base / "runtime", base / "extensions"
                install(root, extensions, dependencies=False, progress=lambda _: None)
                interpreter = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
                interpreter.parent.mkdir(parents=True)
                interpreter.write_text("invalid environment")
                def run(arguments, **kwargs):
                    if arguments[1:3] == ["-m", "venv"]:
                        interpreter.parent.mkdir(parents=True)
                        interpreter.write_text("repaired environment")
                    return subprocess.CompletedProcess(arguments, 0, output if "sys._base_executable" in arguments[-1] else "", "")
                with patch("deployment.subprocess.run", side_effect=run):
                    install(root, extensions, progress=lambda _: None)
                self.assertEqual(interpreter.read_text(), "repaired environment")

    def test_private_runtime_case_aliases_do_not_change_migration_decisions(self):
        for external_environment in (False, True):
            with self.subTest(external_environment=external_environment), tempfile.TemporaryDirectory() as folder:
                base = Path(folder).resolve()
                root, extensions = base / "Runtime", base / "extensions"
                install(root, extensions, dependencies=False, progress=lambda _: None)
                alias = root.with_name("runtime")
                if not alias.is_dir() or not alias.samefile(root):
                    self.skipTest("The test filesystem is case-sensitive")
                private_python = root / ".runtime/python/python.exe"
                private_python.parent.mkdir(parents=True)
                private_python.touch()
                interpreter = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
                interpreter.parent.mkdir(parents=True)
                interpreter.write_text("earlier environment")
                old_base = base / "outside-python" if external_environment else alias / ".runtime/python/python.exe"
                setup_python = alias / ".runtime/python/python.exe" if external_environment else private_python
                def run(arguments, **kwargs):
                    if arguments[1:3] == ["-m", "venv"]:
                        interpreter.parent.mkdir(parents=True)
                        interpreter.write_text("managed environment")
                    output = json.dumps(str(old_base)) + "\n" if "sys._base_executable" in arguments[-1] else ""
                    return subprocess.CompletedProcess(arguments, 0, output, "")
                with patch("deployment.sys.executable", str(setup_python)), patch("deployment.subprocess.run", side_effect=run):
                    install(root, extensions, progress=lambda _: None)
                self.assertEqual(interpreter.read_text(), "managed environment" if external_environment else "earlier environment")

    def test_symbolic_link_private_runtime_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            root, extensions = base / "runtime", base / "extensions"
            install(root, extensions, dependencies=False, progress=lambda _: None)
            outside = base / "outside-runtime"
            outside.mkdir()
            try:
                (root / ".runtime").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Creating symbolic links is unavailable")
            with self.assertRaisesRegex(ValueError, "private runtime.*symbolic link"):
                install(root, extensions, dependencies=False, progress=lambda _: None)

    def test_private_python_link_cannot_point_to_an_outside_interpreter(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            runtime = base / ".runtime"
            runtime.mkdir()
            outside = base / "outside-python"
            outside.touch()
            linked = runtime / "python"
            try:
                linked.symlink_to(outside)
            except OSError:
                self.skipTest("Creating symbolic links is unavailable")
            self.assertFalse(deployment._uses_private_python(linked, runtime))

    def test_invalid_dependencies_cannot_report_a_successful_installation(self):
        for failure in ("dependency conflict", "missing requests"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                base = Path(folder).resolve()
                root, extensions = base / "runtime", base / "extensions"
                install(root, extensions, dependencies=False, progress=lambda _: None)
                original = (root / "backend/app.py").read_bytes()
                def run(arguments, **kwargs):
                    failed = (failure == "dependency conflict" and arguments[-1] == "check") or (failure == "missing requests" and "requests" in arguments[-1])
                    if failed and kwargs.get("check"):
                        raise subprocess.CalledProcessError(1, arguments, stderr=failure)
                    return subprocess.CompletedProcess(arguments, 1 if failed else 0, "", failure if failed else "")
                with patch("deployment.subprocess.run", side_effect=run):
                    with self.assertRaises(RuntimeError):
                        install(root, extensions, progress=lambda _: None)
                self.assertEqual((root / "backend/app.py").read_bytes(), original)

    def test_install_and_update_preserve_user_keys_outputs_and_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); root, extensions = base/"runtime", base/"extensions"
            install(root, extensions, dependencies=False, progress=lambda _: None)
            self.assertFalse((root/"backend/.venv").exists())
            self.assertFalse((root/"backend/.env").exists())
            self.assertFalse((root/"backend/.local-token").exists())
            (root/"backend/.env").write_text("OPENAI_API_KEY=test-user-key\n",encoding="utf-8")
            (root/"exports").mkdir(); (root/"exports/user.json").write_text("keep")
            (root/".venv").mkdir(); (root/".venv/keep").write_text("keep")
            install(root, extensions, dependencies=False, progress=lambda _: None)
            self.assertIn("test-user-key", (root/"backend/.env").read_text())
            self.assertEqual((root/"exports/user.json").read_text(),"keep")
            self.assertTrue((root/".venv/keep").exists())
            self.assertTrue((root/"installer/bootstrap_windows.ps1").exists())
            self.assertTrue((root/"panel/index.html").exists())
            extension = extensions/EXTENSION_ID
            self.assertTrue((extension/"CSXS/manifest.xml").exists())
            self.assertTrue((extension/"json2.js").exists())
            self.assertEqual(json.loads((extension/"install.json").read_text())["runtimeRoot"],str(root.resolve()))
            self.assertEqual([p.name for p in extensions.iterdir()],[EXTENSION_ID])
            self.assertTrue(list((root/"backups").glob("*/extension")))

    def test_refuses_unrelated_runtime_or_extension_destinations(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); root, extensions = base/"runtime", base/"extensions"
            root.mkdir(); (root/"user.txt").write_text("keep")
            with self.assertRaises(ValueError): install(root, extensions, dependencies=False)
            self.assertEqual((root/"user.txt").read_text(),"keep")
            unrelated = extensions/EXTENSION_ID; unrelated.mkdir(parents=True)
            (unrelated/"user.txt").write_text("keep")
            with self.assertRaises(ValueError): install(base/"new-runtime", extensions, dependencies=False)
            self.assertEqual((unrelated/"user.txt").read_text(),"keep")

    def test_failure_restores_previous_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); root, extensions = base/"runtime", base/"extensions"
            install(root, extensions, dependencies=False, progress=lambda _:None)
            original = (root/"ae/KartuliCaptionForge.jsx").read_bytes()
            (root/"backend/.env").write_text("OPENAI_API_KEY=preserve\n")
            with patch("deployment.enable_unsigned", side_effect=RuntimeError("injected failure")):
                with self.assertRaises(RuntimeError): install(root, extensions, dependencies=False, unsigned=True, progress=lambda _:None)
            self.assertEqual((root/"ae/KartuliCaptionForge.jsx").read_bytes(),original)
            self.assertIn("preserve", (root/"backend/.env").read_text())
            self.assertTrue((extensions/EXTENSION_ID/"CSXS/manifest.xml").exists())

    def test_rename_updates_owned_legacy_install_without_losing_user_data(self):
        from environment import data_root
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); root = base/"Kartuli Caption Forge"; extensions = base/"extensions"
            install(root,extensions,dependencies=False,progress=lambda _:None)
            for marker in (root/".kcf-install.json",extensions/EXTENSION_ID/"install.json"):
                data=json.loads(marker.read_text()); data["tool"]="Kartuli Caption Forge"
                marker.write_text(json.dumps(data),encoding="utf-8")
            (root/"backend/.env").write_text("OPENAI_API_KEY=legacy-user-key\n")
            (root/".runtime").mkdir(); (root/".runtime/keep").write_text("private-runtime")
            with patch("environment.sys.platform","win32"), patch.dict(os.environ,{"LOCALAPPDATA":str(base)}):
                self.assertEqual(data_root(),root)
            install(root,extensions,dependencies=False,progress=lambda _:None)
            self.assertEqual(json.loads((root/".kcf-install.json").read_text())["tool"],"CapForge")
            self.assertIn("legacy-user-key",(root/"backend/.env").read_text())
            self.assertEqual((root/".runtime/keep").read_text(),"private-runtime")

    def test_broken_earlier_python_is_backed_up_and_restored_if_repair_fails(self):
        for fail in (False,True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as folder:
                base=Path(folder); root=base/"runtime"; extensions=base/"extensions"
                install(root,extensions,dependencies=False,progress=lambda _:None)
                interpreter=root/".venv"/("Scripts/python.exe" if sys.platform=="win32" else "bin/python")
                interpreter.parent.mkdir(parents=True); interpreter.write_text("broken base interpreter")
                (root/".venv/user-package.txt").write_text("preserve")
                def run(arguments,**kwargs):
                    if arguments[1:3]==["-m","venv"]:
                        interpreter.parent.mkdir(parents=True); interpreter.write_text("private runtime")
                    broken = Path(arguments[0]).resolve() == interpreter.resolve() and interpreter.read_text() == "broken base interpreter"
                    failed = fail and arguments[1:3]==["-m","pip"]
                    return subprocess.CompletedProcess(arguments,1 if broken or failed else 0,"","injected package failure" if failed else "")
                with patch("deployment.subprocess.run",side_effect=run):
                    if fail:
                        with self.assertRaises(RuntimeError): install(root,extensions,progress=lambda _:None)
                        self.assertEqual(interpreter.read_text(),"broken base interpreter")
                        self.assertEqual((root/".venv/user-package.txt").read_text(),"preserve")
                    else:
                        install(root,extensions,progress=lambda _:None)
                        self.assertEqual(interpreter.read_text(),"private runtime")
                        backups=list((root/"backups").glob("*/environment/user-package.txt"))
                        self.assertEqual(len(backups),1); self.assertEqual(backups[0].read_text(),"preserve")

    @unittest.skipIf(sys.platform == "win32", "POSIX venv interpreter symlinks")
    def test_dangling_interpreter_is_repaired_without_losing_old_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            root, extensions = base / "runtime", base / "extensions"
            install(root, extensions, dependencies=False, progress=lambda _: None)
            interpreter = root / ".venv/bin/python"
            interpreter.parent.mkdir(parents=True)
            interpreter.symlink_to(base / "removed-python")
            (root / ".venv/user-package.txt").write_text("preserve")
            real_run = subprocess.run
            def run(arguments, **kwargs):
                if arguments[1:3] == ["-m", "pip"] or "imageio_ffmpeg" in arguments[-1]:
                    return subprocess.CompletedProcess(arguments, 0, "", "")
                return real_run(arguments, **kwargs)
            with patch("deployment.subprocess.run", side_effect=run):
                install(root, extensions, progress=lambda _: None)
            self.assertTrue(interpreter.exists())
            backups = list((root / "backups").glob("*/environment/user-package.txt"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), "preserve")


if __name__ == "__main__": unittest.main()
