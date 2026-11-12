"""Exercise launchers without downloading tools or touching the user's install."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform == "darwin", "macOS launchers")
class TestMacBootstrap(unittest.TestCase):
    def test_fresh_headless_install_leaves_retryable_marker_after_download_failure(self):
        with tempfile.TemporaryDirectory(prefix="CapForge ქართული ") as folder:
            base = Path(folder).resolve()
            root = base / 'first "runtime"'
            guard = base / "download-failure.sh"
            guard.write_text('''function mkdir {
  case "$2" in
    "$CAPFORGE_TEST_ROOT"|"$CAPFORGE_TEST_ROOT/"*) command mkdir "$@" ;;
    *) echo 'Blocked installation outside the test destination.' >&2; return 1 ;;
  esac
}
function /usr/bin/curl { echo 'Simulated network failure.' >&2; return 29; }
function /usr/bin/osascript { echo 'Unexpected GUI alert.' >&2; return 0; }
''')
            result = subprocess.run(
                ["/bin/bash", str(REPO / "installer/bootstrap_macos.sh"), "--target", str(root), "--headless"],
                env=dict(os.environ, BASH_ENV=str(guard), CAPFORGE_TEST_ROOT=str(root)),
                capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(result.returncode, 29, result.stdout + result.stderr)
            marker = json.loads((root / ".kcf-install.json").read_text())
            self.assertEqual(marker["tool"], "CapForge")
            self.assertEqual(marker["runtimeRoot"], str(root))
            self.assertIn("Simulated network failure.", result.stderr)
            self.assertNotIn("Unexpected GUI alert.", result.stderr)

    def test_finder_launcher_is_executable_and_passes_arguments(self):
        with tempfile.TemporaryDirectory(prefix="CapForge ქართული ") as folder:
            root = Path(folder).resolve()
            launcher = root / "Install macOS.command"
            shutil.copy2(REPO / launcher.name, launcher)
            (root / "installer").mkdir()
            (root / "installer/bootstrap_macos.sh").write_text(
                'printf "%s\\n" "$PWD" "$@"\n', encoding="utf-8"
            )
            result = subprocess.run(
                [str(launcher), "--headless", "--target", str(root / "custom runtime")],
                cwd="/", capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), [str(root), "--headless", "--target", str(root / "custom runtime")])

    def test_bootstrap_honors_custom_destination_and_forwards_installer_options(self):
        with tempfile.TemporaryDirectory(prefix="CapForge ქართული ") as folder:
            base = Path(folder).resolve()
            root = base / "custom runtime"
            root.mkdir()
            (root / ".kcf-install.json").write_text(json.dumps({"tool": "CapForge"}))
            manifest = json.loads((REPO / "installer/runtime_assets.json").read_text())
            uv = root / ".runtime/uv" / manifest["version"] / "uv"
            uv.parent.mkdir(parents=True)
            python = root / ".runtime/test-python"
            uv.write_text('#!/bin/bash\nif [ "$2" = find ]; then printf "%s\\n" "$CAPFORGE_TEST_PYTHON"; fi\n')
            python.write_text('#!/bin/bash\nif [ "$1" = -I ]; then exit 0; fi\nprintf "%s\\n" "$@"\n')
            uv.chmod(0o755)
            python.chmod(0o755)
            # Prevent even a regression from writing to the real app folder or
            # opening an alert. Only external side effects are replaced.
            guard = base / "shell-guard.sh"
            guard.write_text('''function mkdir {
  if [ "$1" != -p ] || [ "$2" != "$CAPFORGE_TEST_ROOT" ]; then
    echo 'Blocked installation outside the test destination.' >&2
    return 1
  fi
  command mkdir "$@"
}
function /usr/bin/osascript { return 0; }
''')
            env = dict(os.environ, BASH_ENV=str(guard), CAPFORGE_TEST_ROOT=str(root), CAPFORGE_TEST_PYTHON=str(python))
            extension = base / "custom extensions"
            for options in ([], ["--headless", "--extension-root", str(extension), "--skip-dependencies"]):
                with self.subTest(options=options):
                    result = subprocess.run(
                        ["/bin/bash", str(REPO / "installer/bootstrap_macos.sh"), "--target", str(root)] + options,
                        env=env, capture_output=True, text=True, timeout=20,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    expected = [str(REPO / "installer/install.py"), "--target", str(root)] + options
                    self.assertEqual(result.stdout.splitlines()[-len(expected):], expected)


if __name__ == "__main__":
    unittest.main()
