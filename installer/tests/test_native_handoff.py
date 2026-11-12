"""An installed pre-native updater can open the native macOS Setup window."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install as installer_ui


class TestNativeHandoff(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.source = Path(self.temp.name).resolve() / "CapForge ქართული"
        self.executable = self.source / "CapForge.app/Contents/MacOS/CapForge"
        self.executable.parent.mkdir(parents=True)
        self.executable.write_bytes(b"native setup")
        self.executable.chmod(0o644)
        self.file = patch.object(installer_ui, "__file__", str(self.source / "installer/install.py"))
        self.file.start()
        self.platform = patch.object(installer_ui.sys, "platform", "darwin")
        self.platform.start()

    def tearDown(self):
        self.platform.stop()
        self.file.stop()
        self.temp.cleanup()

    def test_old_updater_handoff_preserves_destinations_and_tracks_native_process(self):
        arguments = ["--target", str(self.source / "runtime ქართული"), "--extension-root", str(self.source / "CEP extensions")]
        with patch.object(sys, "argv", ["install.py", *arguments]), patch.object(installer_ui.subprocess, "call", return_value=7) as launch, patch.object(installer_ui, "wizard") as wizard:
            self.assertEqual(installer_ui.main(), 7)
        launch.assert_called_once_with([str(self.executable), *arguments], cwd=str(self.source))
        wizard.assert_not_called()
        if os.name != "nt":
            self.assertTrue(self.executable.stat().st_mode & 0o100)

    def test_headless_setup_keeps_the_python_deployment_path(self):
        target, extensions = self.source / "runtime", self.source / "extensions"
        arguments = ["install.py", "--headless", "--target", str(target), "--extension-root", str(extensions), "--skip-dependencies", "--enable-unsigned"]
        with patch.object(sys, "argv", arguments), patch.object(installer_ui, "install") as deploy, patch.object(installer_ui.subprocess, "call") as launch:
            self.assertEqual(installer_ui.main(), 0)
        deploy.assert_called_once_with(target, extensions, dependencies=False, unsigned=True)
        launch.assert_not_called()

    def test_missing_native_binary_does_not_silently_open_tk(self):
        self.executable.unlink()
        with patch.object(sys, "argv", ["install.py"]), patch.object(installer_ui, "wizard") as wizard:
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                installer_ui.main()
        wizard.assert_not_called()

    def test_source_only_and_windows_legacy_wizard_remain_available(self):
        with patch.object(installer_ui.sys, "platform", "win32"), patch.object(sys, "argv", ["install.py"]), patch.object(installer_ui, "wizard") as wizard, patch.object(installer_ui.subprocess, "call") as launch:
            self.assertEqual(installer_ui.main(), 0)
        wizard.assert_called_once_with(None, None)
        launch.assert_not_called()
        with patch.object(installer_ui, "__file__", str(self.source / "without-app/installer/install.py")):
            self.assertIsNone(installer_ui.native_macos_setup([]))

    def test_linked_binary_is_rejected_before_chmod_or_launch(self):
        self.executable.unlink()
        outside = self.source / "outside"
        outside.write_bytes(b"unrelated")
        outside.chmod(0o600)
        try:
            self.executable.symlink_to(outside)
        except OSError:
            self.skipTest("Creating symlinks is unavailable on this test system")
        with patch.object(installer_ui.subprocess, "call") as launch:
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                installer_ui.native_macos_setup([])
        launch.assert_not_called()
        self.assertFalse(outside.stat().st_mode & 0o111)


if __name__ == "__main__":
    unittest.main()
