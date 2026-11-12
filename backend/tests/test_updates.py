"""Release updates use verified packages and the existing owned install only."""
import hashlib
import io
import json
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import updates

REPO = "https://github.com/MeticulousTransformer/CapForge"
API = "https://api.github.com/repos/MeticulousTransformer/CapForge/releases/latest"
TAG = "kml-1234567"
VERSION = "0.3.3"
NAME = "CapForge-0.3.3-macOS.zip"


def package(extra=None, manifest_change=None, release_tag=TAG, missing=None,
            platform="macos", version=VERSION, identity_platform="same"):
    files = {name: b"# release component\n" for name in (
        "installer/install.py", "installer/deployment.py", "installer/environment.py", "installer/theme.py",
        "installer/runtime_assets.json", "installer/service_control.py", "backend/app.py", "backend/requirements.txt",
        "panel/CSXS/manifest.xml", "panel/host.jsx", "ae/lib/json2.js", "run_backend.sh", "run_backend.bat"
    )}
    if platform:
        files[updates.NATIVE_SETUP[platform]] = b"native setup binary"
    if missing:
        del files[missing]
    identity = {"version": version, "tag": release_tag, "commit": "a" * 40}
    if identity_platform == "same":
        identity_platform = platform
    if identity_platform is not None:
        identity["platform"] = identity_platform
    files["release.json"] = json.dumps(identity).encode()
    manifest = [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in files.items()]
    if manifest_change:
        manifest_change(manifest)
    files["package-manifest.json"] = json.dumps(manifest).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr("CapForge-" + version + "/" + name, data)
        if extra:
            name, data, mode = extra
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            archive.writestr(info, data)
    return output.getvalue()


class ReleaseNetwork:
    """Only the network boundary is replaced; Response parsing stays real."""
    def __init__(self, archive, platform="macos", version=VERSION):
        prefix = REPO + "/releases/download/" + TAG + "/"
        name = "CapForge-" + version + ({"macos": "-macOS", "windows": "-Windows"}.get(platform, "")) + ".zip"
        self.release = {"tag_name": TAG, "draft": False, "prerelease": False, "body": "Startup improvements.", "assets": [
            {"name": name, "browser_download_url": prefix + name, "size": len(archive)},
            {"name": name + ".sha256", "browser_download_url": prefix + name + ".sha256", "size": 100}
        ]}
        self.data = {prefix + name: archive, prefix + name + ".sha256": (hashlib.sha256(archive).hexdigest() + "  " + name + "\n").encode()}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        response = requests.Response()
        response.status_code = 200
        response.url = url
        response._content = json.dumps(self.release).encode() if url == API else self.data[url]
        response._content_consumed = True
        response.headers["Content-Length"] = str(len(response._content))
        return response


class TestUpdates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve() / "CapForge ქართული"
        self.root.mkdir()
        self.extension = Path(self.temp.name).resolve() / "CEP" / "com.kartuli.captionforge"
        self.extension.mkdir(parents=True)
        marker = {"tool": "CapForge", "version": "0.3.2", "runtimeRoot": str(self.root), "extension": str(self.extension)}
        (self.root / ".kcf-install.json").write_text(json.dumps(marker), encoding="utf-8")
        (self.extension / "install.json").write_text(json.dumps(marker), encoding="utf-8")
        self.base_python = self.root / ".runtime/python/bin/python"
        self.base_python.parent.mkdir(parents=True)
        self.base_python.touch()
        self.base_override = patch.object(sys, "_base_executable", str(self.base_python))
        self.base_override.start()
        self.network = ReleaseNetwork(package())
        self.http = patch.object(updates.requests, "get", side_effect=lambda url, **kwargs: self.network.get(url, **kwargs))
        self.http.start()
        self.process = patch.object(updates, "_installer_process", None)
        self.process.start()
        self.platform = patch.object(updates, "_platform", return_value="macos")
        self.platform.start()

    def tearDown(self):
        self.platform.stop()
        self.base_override.stop()
        self.process.stop()
        self.http.stop()
        self.temp.cleanup()

    def test_check_reports_latest_release_without_downloading_or_changing_installation(self):
        result = updates.check(self.root, "0.3.2")
        self.assertTrue(result["available"])
        self.assertEqual(result["currentVersion"], "0.3.2")
        self.assertEqual(result["currentTag"], "")
        self.assertEqual((result["version"], result["tag"]), (VERSION, TAG))
        self.assertEqual(result["notes"], "Startup improvements.")
        self.assertEqual(self.network.calls, [API])
        self.assertFalse((self.root / ".updates").exists())

    def test_no_published_release_returns_a_normal_empty_update_status(self):
        response = requests.Response()
        response.status_code = 404
        response._content = b'{"message":"Not Found"}'
        response._content_consumed = True
        with patch.object(updates.requests, "get", return_value=response):
            result = updates.check(self.root, "0.3.2")
        self.assertFalse(result["available"])
        self.assertEqual(result["tag"], "")
        self.assertIn("No published update", result["message"])

    def test_untrusted_redirect_is_blocked_before_following_it(self):
        response = requests.Response()
        response.status_code = 302
        response.headers["Location"] = "https://evil.example/capforge.zip"
        response._content = b""
        response._content_consumed = True
        with patch.object(updates.requests, "get", return_value=response) as http:
            with self.assertRaisesRegex(updates.UpdateError, "trusted"):
                updates.check(self.root, "0.3.2")
            self.assertEqual(http.call_count, 1)

    def test_actual_stream_size_is_bounded_when_response_has_no_content_length(self):
        response = requests.Response()
        response.status_code = 200
        response._content = b"0123456789"
        response._content_consumed = True
        with patch.object(updates.requests, "get", return_value=response):
            with self.assertRaisesRegex(updates.UpdateError, "size"):
                updates._fetch(API, 9)

    def test_network_failure_reports_retry_without_exposing_low_level_error(self):
        with patch.object(updates.requests, "get", side_effect=requests.ConnectionError("private proxy details")):
            with self.assertRaises(updates.UpdateError) as failure:
                updates.check(self.root, "0.3.2")
        self.assertEqual(failure.exception.status_code, 502)
        self.assertNotIn("private proxy details", str(failure.exception))

    def test_same_version_new_commit_is_an_update_but_same_tag_is_current(self):
        (self.root / "release.json").write_text(json.dumps({"version": VERSION, "tag": "earlier-commit", "commit": "b" * 40}))
        self.assertTrue(updates.check(self.root, VERSION)["available"])
        (self.root / "release.json").write_text(json.dumps({"version": VERSION, "tag": TAG, "commit": "a" * 40}))
        self.assertFalse(updates.check(self.root, VERSION)["available"])

    def test_runtime_markers_accept_capitalization_aliases_of_the_same_directory(self):
        alias = self.root.with_name(self.root.name.swapcase())
        if not alias.exists():
            self.skipTest("This filesystem distinguishes filename capitalization")
        for marker_path in [self.root / ".kcf-install.json", self.extension / "install.json"]:
            with self.subTest(marker=marker_path.name):
                original = marker_path.read_text(encoding="utf-8")
                marker = json.loads(original)
                marker["runtimeRoot"] = str(alias)
                marker_path.write_text(json.dumps(marker), encoding="utf-8")
                try:
                    self.assertTrue(updates.check(self.root, "0.3.2")["available"])
                finally:
                    marker_path.write_text(original, encoding="utf-8")

    def test_newer_installed_version_is_not_downgraded(self):
        (self.root / "release.json").write_text(json.dumps({"version": "0.4.0", "tag": "newer", "commit": "b" * 40}))
        self.assertFalse(updates.check(self.root, "0.4.0")["available"])

    def test_source_checkout_cannot_install_or_make_network_requests(self):
        (self.root / ".kcf-install.json").unlink()
        with self.assertRaisesRegex(updates.UpdateError, "install"):
            updates.install(self.root, "0.3.2")
        self.assertEqual(self.network.calls, [])

    def test_install_verifies_package_and_launches_wizard_for_existing_destinations(self):
        with patch.object(updates.subprocess, "Popen", return_value=SimpleNamespace(poll=lambda: None)) as launch:
            result = updates.install(self.root, "0.3.2")
        self.assertTrue(result["started"])
        self.assertEqual(result["tag"], TAG)
        command = launch.call_args.args[0]
        self.assertEqual(command[1:], ["--target", str(self.root), "--extension-root", str(self.extension.parent)])
        executable = Path(command[0])
        self.assertTrue(executable.is_file())
        self.assertEqual(executable.relative_to(Path(launch.call_args.kwargs["cwd"])).as_posix(), updates.NATIVE_SETUP["macos"])
        self.assertIn(self.root / ".updates", executable.parents)
        self.assertEqual(json.loads((Path(launch.call_args.kwargs["cwd"]) / "release.json").read_text())["tag"], TAG)
        self.assertNotIn("--headless", command)
        if sys.platform != "win32":
            self.assertEqual(stat.S_IMODE(executable.stat().st_mode), 0o755)
        self.assertFalse((self.root / "backend").exists(), "Only the installer may replace runtime files")

    def use_legacy_release(self):
        self.network = ReleaseNetwork(package(platform=None, version="0.3.2"), platform=None, version="0.3.2")

    def test_native_setup_repairs_a_missing_private_python(self):
        self.base_python.unlink()
        with patch.object(updates.subprocess, "Popen", return_value=SimpleNamespace(poll=lambda: None)) as launch:
            self.assertTrue(updates.install(self.root, "0.3.2")["started"])
        executable = Path(launch.call_args.args[0][0])
        package_root = Path(launch.call_args.kwargs["cwd"])
        self.assertEqual(executable.relative_to(package_root).as_posix(), updates.NATIVE_SETUP["macos"])

    def test_native_setup_launch_keeps_installed_keys_and_exports_untouched(self):
        for name in ("backend/.env", "backend/.local-token", "exports/normalized.json"):
            file = self.root / name
            file.parent.mkdir(exist_ok=True)
            file.write_text("keep " + name)
        with patch.object(updates.subprocess, "Popen", return_value=SimpleNamespace(poll=lambda: None)):
            updates.install(self.root, "0.3.2")
        for name in ("backend/.env", "backend/.local-token", "exports/normalized.json"):
            self.assertEqual((self.root / name).read_text(), "keep " + name)

    def test_current_os_is_selected_from_both_native_assets_and_migration_archive(self):
        windows = ReleaseNetwork(package(platform="windows"), platform="windows")
        compatibility = ReleaseNetwork(package(platform=None), platform=None)
        self.network.release["assets"].extend(windows.release["assets"] + compatibility.release["assets"])
        self.assertEqual(updates._latest()["archive"]["name"], NAME)
        with patch.object(updates, "_platform", return_value="windows"):
            release = updates._latest()
        self.assertEqual(release["archive"]["name"], "CapForge-0.3.3-Windows.zip")
        self.assertEqual(release["platform"], "windows")

    def test_wrong_os_or_new_legacy_only_release_cannot_be_selected(self):
        for platform in ("windows", None):
            with self.subTest(platform=platform):
                self.network = ReleaseNetwork(package(platform=platform), platform=platform)
                with self.assertRaises(updates.UpdateError):
                    updates.check(self.root, "0.3.2")
                self.assertEqual(self.network.calls, [API])

    def test_native_asset_without_its_checksum_does_not_fall_back(self):
        self.network.release["assets"].pop()
        legacy = ReleaseNetwork(package(platform=None, version="0.3.2"), platform=None, version="0.3.2")
        self.network.release["assets"].extend(legacy.release["assets"])
        with self.assertRaises(updates.UpdateError):
            updates.check(self.root, "0.3.2")

    def test_windows_setup_launches_exe_with_existing_destinations(self):
        self.network = ReleaseNetwork(package(platform="windows"), platform="windows")
        with patch.object(updates, "_platform", return_value="windows"), patch.object(updates.subprocess, "Popen", return_value=SimpleNamespace(poll=lambda: None)) as launch:
            self.assertTrue(updates.install(self.root, "0.3.2")["started"])
        command = launch.call_args.args[0]
        self.assertTrue(command[0].endswith("CapForge Setup.exe"))
        self.assertEqual(command[1:], ["--target", str(self.root), "--extension-root", str(self.extension.parent)])
        self.assertNotIn("shell", launch.call_args.kwargs)

    def test_native_package_requires_matching_platform_identity_and_executable(self):
        cases = [package(identity_platform="windows"), package(identity_platform=None),
                 package(missing=updates.NATIVE_SETUP["macos"])]
        for archive in cases:
            self.network = ReleaseNetwork(archive)
            with patch.object(updates.subprocess, "Popen") as launch:
                with self.assertRaises(updates.UpdateError):
                    updates.install(self.root, "0.3.2")
                launch.assert_not_called()

    def test_unpack_rejects_a_release_for_a_different_os(self):
        with self.assertRaisesRegex(updates.UpdateError, "different operating system"):
            updates._unpack(None, self.root, {"version": VERSION, "platform": "windows"})

    def test_legacy_release_uses_its_private_python(self):
        self.use_legacy_release()
        with patch.object(updates.subprocess, "Popen", return_value=SimpleNamespace(poll=lambda: None)) as launch:
            self.assertTrue(updates.install(self.root, "0.3.2")["started"])
        command = launch.call_args.args[0]
        self.assertEqual(command[0], str(self.base_python))
        self.assertEqual(Path(command[1]), Path(launch.call_args.kwargs["cwd"]) / "installer/install.py")
        self.assertEqual(command[2:], ["--target", str(self.root), "--extension-root", str(self.extension.parent)])

    def test_legacy_wizard_never_uses_a_missing_or_external_python(self):
        self.use_legacy_release()
        (Path(self.temp.name) / "outside-python").touch()
        for python in [self.root / ".runtime/missing-python", Path(self.temp.name) / "outside-python"]:
            with self.subTest(python=python), patch.object(sys, "_base_executable", str(python)), patch.object(updates.subprocess, "Popen") as launch:
                with self.assertRaisesRegex(updates.UpdateError, "runtime"):
                    updates.install(self.root, "0.3.2")
                launch.assert_not_called()

    def test_private_python_accepts_a_capitalization_alias_inside_the_owned_runtime(self):
        self.use_legacy_release()
        alias = self.root.with_name(self.root.name.swapcase())
        if not alias.exists():
            self.skipTest("This filesystem distinguishes filename capitalization")
        base_alias = alias / self.base_python.relative_to(self.root)
        with patch.object(sys, "_base_executable", str(base_alias)), patch.object(updates.subprocess, "Popen", return_value=SimpleNamespace(poll=lambda: None)) as launch:
            self.assertTrue(updates.install(self.root, "0.3.2")["started"])
        self.assertTrue(Path(launch.call_args.args[0][0]).samefile(self.base_python))

    def test_private_runtime_symlink_cannot_allow_an_external_interpreter(self):
        outside = Path(self.temp.name).resolve() / "outside-runtime"
        (self.root / ".runtime").rename(outside)
        try:
            (self.root / ".runtime").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks is unavailable on this test system")
        with patch.object(sys, "_base_executable", str(outside / "python/bin/python")), patch.object(updates.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(updates.UpdateError, "runtime"):
                updates.install(self.root, "0.3.2")
            launch.assert_not_called()

    def test_invalid_extension_marker_path_reports_an_update_error(self):
        marker_path = self.root / ".kcf-install.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        for invalid in [None, 42, {}, "relative/extension"]:
            marker["extension"] = invalid
            marker_path.write_text(json.dumps(marker), encoding="utf-8")
            with self.subTest(extension=invalid), self.assertRaises(updates.UpdateError):
                updates.check(self.root, "0.3.2")

    def test_package_must_include_the_installer_service_handoff(self):
        self.network = ReleaseNetwork(package(missing="installer/service_control.py"))
        with patch.object(updates.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(updates.UpdateError, "installer files"):
                updates.install(self.root, "0.3.2")
            launch.assert_not_called()

    def test_bad_checksum_never_opens_installer(self):
        checksum = next(url for url in self.network.data if url.endswith(".sha256"))
        self.network.data[checksum] = ("0" * 64).encode()
        with patch.object(updates.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(updates.UpdateError, "checksum"):
                updates.install(self.root, "0.3.2")
            launch.assert_not_called()

    def test_untrusted_asset_url_is_rejected_before_requesting_it(self):
        self.network.release["assets"][0]["browser_download_url"] = "https://evil.example/package.zip"
        with self.assertRaises(updates.UpdateError):
            updates.install(self.root, "0.3.2")
        self.assertEqual(self.network.calls, [API])

    def test_unsafe_or_unlisted_archive_members_never_escape_staging(self):
        cases = [
            ("../escaped.py", b"bad", stat.S_IFREG | 0o644),
            ("CapForge-0.3.3/../../escaped.py", b"bad", stat.S_IFREG | 0o644),
            ("CapForge-0.3.3/link", b"../../escaped", stat.S_IFLNK | 0o777),
            ("CapForge-0.3.3/BACKEND/app.py", b"duplicate", stat.S_IFREG | 0o644),
            ("CapForge-0.3.3/unlisted.py", b"extra code", stat.S_IFREG | 0o644),
            ("CapForge-0.3.3/installer/evil.py:stream", b"bad", stat.S_IFREG | 0o644)
        ]
        for extra in cases:
            with self.subTest(member=extra[0]), patch.object(updates.subprocess, "Popen") as launch:
                self.network = ReleaseNetwork(package(extra=extra))
                with self.assertRaises(updates.UpdateError):
                    updates.install(self.root, "0.3.2")
                launch.assert_not_called()
        self.assertFalse((self.root / "escaped.py").exists())

    def test_archive_rejects_a_normalized_alias_of_a_verified_file(self):
        self.network = ReleaseNetwork(package(extra=("CapForge-0.3.3/backend/./app.py", b"# release component\n", stat.S_IFREG | 0o644)))
        with patch.object(updates.subprocess, "Popen") as launch:
            with self.assertRaises(updates.UpdateError):
                updates.install(self.root, "0.3.2")
            launch.assert_not_called()

    def test_failed_installer_launch_removes_its_staged_download(self):
        with patch.object(updates.subprocess, "Popen", side_effect=OSError("Cannot launch")):
            with self.assertRaises(updates.UpdateError):
                updates.install(self.root, "0.3.2")
        self.assertEqual(list((self.root / ".updates").iterdir()), [])

    def test_manifest_tampering_and_wrong_release_identity_are_rejected(self):
        for archive in [package(manifest_change=lambda rows: rows[0].update(sha256="0" * 64)), package(release_tag="other-tag")]:
            self.network = ReleaseNetwork(archive)
            with patch.object(updates.subprocess, "Popen") as launch:
                with self.assertRaises(updates.UpdateError):
                    updates.install(self.root, "0.3.2")
                launch.assert_not_called()

    def test_declared_download_and_expanded_archive_limits_are_enforced(self):
        self.network.release["assets"][0]["size"] = 10 ** 10
        with self.assertRaises(updates.UpdateError):
            updates.install(self.root, "0.3.2")
        self.network = ReleaseNetwork(package())
        with patch.object(updates, "MAX_EXPANDED_BYTES", 10), self.assertRaises(updates.UpdateError):
            updates.install(self.root, "0.3.2")

    def test_second_update_is_rejected_while_installer_is_open(self):
        with patch.object(updates.subprocess, "Popen", return_value=SimpleNamespace(poll=lambda: None)):
            updates.install(self.root, "0.3.2")
            with self.assertRaisesRegex(updates.UpdateError, "already"):
                updates.install(self.root, "0.3.2")

    def test_symlinked_update_directory_is_not_followed(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        try:
            (self.root / ".updates").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks is unavailable on this test system")
        with self.assertRaises(updates.UpdateError):
            updates.install(self.root, "0.3.2")
        self.assertEqual(list(outside.iterdir()), [])


class TestUpdateAPI(unittest.IsolatedAsyncioTestCase):
    async def test_update_routes_require_token_and_preserve_friendly_error_status(self):
        from backend.tests.test_studio import request
        with tempfile.TemporaryDirectory() as folder, patch("app.BACKEND_DIR", folder):
            for route, method in [("/updates/check", "GET"), ("/updates/install", "POST")]:
                status, _ = await request(route, method)
                self.assertEqual(status, 401)
            from services.studio_settings import local_token
            headers = {"X-KCF-Token": local_token(folder)}
            with patch.object(updates, "check", side_effect=updates.UpdateError("Check the connection.", 502)):
                status, body = await request("/updates/check", headers=headers)
            self.assertEqual((status, body), (502, {"detail": "Check the connection."}))

    async def test_install_route_blocks_updates_during_transcription(self):
        from backend.tests.test_studio import request
        from app import _transcription_lock
        from services.studio_settings import local_token
        with tempfile.TemporaryDirectory() as folder, patch("app.BACKEND_DIR", folder):
            headers = {"X-KCF-Token": local_token(folder)}
            _transcription_lock.acquire()
            try:
                status, _ = await request("/updates/install", "POST", headers=headers)
            finally:
                _transcription_lock.release()
            self.assertEqual(status, 409)
