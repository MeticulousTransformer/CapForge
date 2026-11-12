"""A local test server exercises authenticated, non-destructive update shutdown."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deployment import install
import service_control


class ServiceControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "runtime"
        self.extensions = Path(self.temp.name).resolve() / "extensions"
        install(self.root, self.extensions, dependencies=False, progress=lambda _: None)
        (self.root / "backend/.local-token").write_text("test-token", encoding="utf-8")
        self.mode = "stop"
        self.requests = []
        case = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def respond(self, status, value, **headers):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                for name, value_ in headers.items():
                    self.send_header(name, value_)
                self.end_headers()
                self.wfile.write(json.dumps(value).encode())

            def do_GET(self):
                case.requests.append(("GET", self.path))
                if self.headers.get("X-KCF-Token") != "test-token" or case.mode == "unauthorized":
                    self.respond(401, {"detail": "Unauthorized"})
                elif case.mode == "old":
                    self.respond(404, {"detail": "Not found"})
                elif case.mode == "redirect":
                    self.respond(302, {}, Location="/stolen-token")
                else:
                    root = case.root / "other" if case.mode == "other" else case.root
                    self.respond(200, {"runtimeRoot": str(root), "version": "0.3.2"})

            def do_POST(self):
                case.requests.append(("POST", self.path))
                if self.headers.get("X-KCF-Token") != "test-token":
                    self.respond(401, {"detail": "Unauthorized"})
                elif case.mode == "busy":
                    self.respond(409, {"detail": "Transcription is running"})
                else:
                    self.respond(200, {"stopping": True})
                    if case.mode == "stop":
                        threading.Thread(target=case.close_server, daemon=True).start()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.worker.start()
        self.addCleanup(self.close_server)
        self.port = patch.dict(os.environ, {"KCF_PORT": str(self.server.server_port)})
        self.port.start()
        self.addCleanup(self.port.stop)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()

    def test_matching_service_stops_gracefully_before_installation(self):
        self.assertTrue(service_control.stop_for_update(self.root, progress=lambda _: None))
        self.assertEqual(self.requests, [("GET", "/service/info"), ("POST", "/service/stop")])

    def test_same_folder_with_different_capitalization_still_stops_its_service(self):
        alias = self.root.with_name(self.root.name.upper())
        if not alias.is_dir() or not alias.samefile(self.root):
            self.skipTest("The test filesystem is case-sensitive")
        self.assertTrue(service_control.stop_for_update(alias, progress=lambda _: None))
        self.assertEqual(self.requests, [("GET", "/service/info"), ("POST", "/service/stop")])

    def test_no_listener_requires_no_shutdown(self):
        self.close_server()
        self.assertFalse(service_control.stop_for_update(self.root))

    def test_another_installation_is_never_stopped(self):
        self.mode = "other"
        self.assertFalse(service_control.stop_for_update(self.root))
        self.assertEqual(self.requests, [("GET", "/service/info")])

    def test_missing_target_token_never_sends_a_request(self):
        (self.root / "backend/.local-token").unlink()
        self.assertFalse(service_control.stop_for_update(self.root))
        self.assertEqual(self.requests, [])

    def test_unauthenticated_and_redirecting_services_are_not_stopped(self):
        for mode in ("unauthorized", "redirect"):
            with self.subTest(mode=mode):
                self.mode = mode
                self.requests.clear()
                with self.assertRaises(RuntimeError):
                    service_control.stop_for_update(self.root)
                self.assertEqual(self.requests, [("GET", "/service/info")])

    def test_old_service_explains_the_one_time_restart(self):
        self.mode = "old"
        with self.assertRaisesRegex(RuntimeError, "restart"):
            service_control.stop_for_update(self.root)
        self.assertEqual(self.requests, [("GET", "/service/info")])

    def test_service_that_never_exits_has_a_bounded_wait(self):
        self.mode = "hung"
        with patch("service_control.STOP_TIMEOUT", 0.1):
            with self.assertRaisesRegex(RuntimeError, "did not stop"):
                service_control.stop_for_update(self.root, progress=lambda _: None)

    def test_busy_service_blocks_installation_before_mutating_files(self):
        self.mode = "busy"
        marker = (self.root / ".kcf-install.json").read_bytes()
        engine = (self.root / "ae/KartuliCaptionForge.jsx").read_bytes()
        with self.assertRaisesRegex(RuntimeError, "busy"):
            install(self.root, self.extensions, dependencies=False, progress=lambda _: None)
        self.assertEqual((self.root / ".kcf-install.json").read_bytes(), marker)
        self.assertEqual((self.root / "ae/KartuliCaptionForge.jsx").read_bytes(), engine)
        self.assertFalse((self.root / "backups").exists())
        self.assertEqual(list(self.root.glob(".kcf-stage-*")), [])


if __name__ == "__main__":
    unittest.main()
