"""Installer handoff only stops the authenticated, idle service."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as service
from backend.tests.test_studio import request
from services.studio_settings import local_token


class TestServiceControl(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.backend = Path(self.temp.name) / "backend"
        self.backend.mkdir()
        self.folder = patch.object(service, "BACKEND_DIR", str(self.backend))
        self.folder.start()
        self.headers = {"X-KCF-Token": local_token(str(self.backend))}

    async def asyncTearDown(self):
        self.folder.stop()
        self.temp.cleanup()

    async def test_info_is_authenticated_and_identifies_the_runtime_without_secrets(self):
        status, _ = await request("/service/info")
        self.assertEqual(status, 401)
        status, result = await request("/service/info", headers=self.headers)
        self.assertEqual(status, 200)
        self.assertEqual(result, {"runtimeRoot": os.path.realpath(self.temp.name), "version": service.VERSION})

    async def test_stop_requires_authentication_and_a_server_shutdown_callback(self):
        status, _ = await request("/service/stop", "POST")
        self.assertEqual(status, 401)
        status, result = await request("/service/stop", "POST", headers=self.headers)
        self.assertEqual(status, 409)
        self.assertIn("close", result["detail"].lower())

    async def test_stop_rejects_active_transcription(self):
        with service._transcription_lock:
            status, _ = await request("/service/stop", "POST", headers=self.headers)
        self.assertEqual(status, 409)

    async def test_idle_stop_responds_then_requests_shutdown_and_blocks_new_work(self):
        stopped = []
        with patch.object(service, "_shutdown_server", lambda: stopped.append(True), create=True), patch.object(service, "_service_stopping", False, create=True):
            status, result = await request("/service/stop", "POST", headers=self.headers)
            self.assertEqual(status, 200)
            self.assertTrue(result["stopping"])
            self.assertEqual(stopped, [True])
            status, _ = await request("/transcribe", "POST", {"mediaPath": "unused.mp4"}, headers=self.headers)
            self.assertEqual(status, 503)
            status, _ = await request("/service/info", headers=self.headers)
            self.assertEqual(status, 200)
