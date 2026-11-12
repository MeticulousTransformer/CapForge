import json
import sys
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import start_service as service


class TestServiceStart(unittest.TestCase):
    def test_reuses_authenticated_service_without_starting_a_process(self):
        with patch.object(service, "ready", return_value=True), patch.object(service.subprocess, "run") as run:
            self.assertEqual(service.start(8765, "test-token"), 0)
            run.assert_not_called()

    def test_foreign_port_is_not_killed_or_reported_as_broken_installation(self):
        with patch.object(service, "ready", return_value=False), patch.object(service, "occupied", return_value=True), patch.object(service.time, "sleep"), patch.object(service.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "does not need repair"):
                service.start(8765, "test-token")
            run.assert_not_called()

    def test_concurrent_launch_recovers_if_our_service_won_the_race(self):
        with patch.object(service, "ready", side_effect=[False, True]), patch.object(service, "occupied", return_value=False), patch.object(service.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
            self.assertEqual(service.start(8765, "test-token"), 0)

    def test_health_and_authenticated_providers_are_both_required(self):
        health = {"ok": True, "version": service.VERSION, "availableProviders": [], "ffmpeg": True}
        responses = [BytesIO(json.dumps(health).encode()), BytesIO(b'{"providers":[]}')]
        with patch.object(service.HTTP, "open", side_effect=responses) as http:
            self.assertTrue(service.ready(8765, "test-token"))
            self.assertEqual(http.call_args.args[0].get_header("X-kcf-token"), "test-token")
        for invalid in [[], {"ok": True}, {"ok": False, "ffmpeg": True, "availableProviders": []}]:
            with patch.object(service.HTTP, "open", return_value=BytesIO(json.dumps(invalid).encode())):
                self.assertFalse(service.ready(8765, "test-token"))
        with patch.object(service.HTTP, "open", side_effect=OSError("unauthorized")):
            self.assertFalse(service.ready(8765, "test-token"))

    def test_authenticated_older_service_requires_restart_instead_of_silent_reuse(self):
        health = {"ok": True, "version": "0.2.0", "availableProviders": [], "ffmpeg": True}
        responses = [BytesIO(json.dumps(health).encode()), BytesIO(b'{"providers":[]}')]
        with patch.object(service.HTTP, "open", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "[Rr]estart"):
                service.start(8765, "test-token")

    def test_local_token_cannot_follow_a_redirect_to_another_host(self):
        self.assertIsNone(service.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example"))
