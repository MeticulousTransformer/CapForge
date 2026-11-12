"""Start once, reuse our authenticated service, and explain occupied ports."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from app import BACKEND_DIR, VERSION
from services.studio_settings import local_token

# A machine-wide proxy must not route the local panel token off this computer.
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


HTTP = build_opener(ProxyHandler({}), NoRedirect())


def ready(port: int, token: str) -> bool:
    try:
        base = f"http://127.0.0.1:{port}"
        with HTTP.open(base + "/health", timeout=1) as response:
            health = json.loads(response.read(1024 * 1024))
        if not isinstance(health, dict) or health.get("ok") is not True or "availableProviders" not in health or "ffmpeg" not in health:
            return False
        with HTTP.open(Request(base + "/providers", headers={"X-KCF-Token": token}), timeout=1) as response:
            providers = json.loads(response.read(1024 * 1024))
        if not isinstance(providers, dict) or not isinstance(providers.get("providers"), list):
            return False
        if health.get("version") != VERSION:
            raise RuntimeError("An older or different CapForge service is still running. Restart this computer, then start CapForge again to finish the update.")
        return True
    except (OSError, ValueError, TypeError):
        return False


def occupied(port: int) -> bool:
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
        return False
    except OSError:
        return True


def start(port: int, token: str) -> int:
    if ready(port, token):
        print("CapForge is already running. Open the panel and check connection.")
        return 0
    if occupied(port):
        # Another click may have launched our server a moment earlier.
        for _ in range(5):
            time.sleep(0.5)
            if ready(port, token):
                return 0
        raise RuntimeError(f"Port {port} is used by another service or CapForge installation. Close that service and try again. Your installation does not need repair.")
    result = subprocess.run([sys.executable, str(Path(BACKEND_DIR) / "app.py")])
    # Covers two launchers racing between the free-port check and server bind.
    if result.returncode and ready(port, token):
        return 0
    return result.returncode


if __name__ == "__main__":
    import os
    try:
        port = int(os.environ.get("KCF_PORT", "8765"))
        print(f"CapForge service v{VERSION}")
        raise SystemExit(start(port, local_token(BACKEND_DIR)))
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
