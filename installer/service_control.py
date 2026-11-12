"""Stop only this installation's authenticated service before replacing its files."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import time
import urllib.error
import urllib.request

STOP_TIMEOUT = 10.0
# Windows can take several seconds to report a refused localhost connection.
CONNECT_TIMEOUT = 5.0


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, url):
        return None


def stop_for_update(root: Path, *, progress=print) -> bool:
    token_file = root / "backend/.local-token"
    if not token_file.is_file():
        return False
    token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        return False
    port = int(os.environ.get("KCF_PORT", "8765"))
    if not 1 <= port <= 65535:
        raise RuntimeError("CapForge's service port is invalid. Close its service and retry setup.")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirects())

    def request(path: str, method: str = "GET") -> dict:
        message = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}", method=method,
            headers={"X-KCF-Token": token},
        )
        with opener.open(message, timeout=CONNECT_TIMEOUT) as response:
            body = response.read(16385)
        if len(body) > 16384:
            raise ValueError("Unexpected service response")
        result = json.loads(body)
        if not isinstance(result, dict):
            raise ValueError("Unexpected service response")
        return result

    try:
        info = request("/service/info")
        service_root = info.get("runtimeRoot")
        if not isinstance(service_root, str) or not service_root:
            raise ValueError("Service identity is missing")
        service_path = Path(service_root)
        if not service_path.is_absolute():
            raise ValueError("Service identity is not an absolute folder")
        if not service_path.is_dir() or not service_path.samefile(root):
            return False
        progress("Closing the local caption service for this update…")
        if request("/service/stop", "POST").get("stopping") is not True:
            raise ValueError("Service did not accept shutdown")
    except urllib.error.HTTPError as error:
        error.close()
        if error.code == 409:
            raise RuntimeError("CapForge is busy or cannot close automatically. Finish transcription or close its service window, then try installation again.") from error
        if error.code == 404:
            raise RuntimeError("This older CapForge service needs to close before updating. Close its service window or restart this computer once, then run setup again.") from error
        raise RuntimeError("The running service could not be verified. Close its window, then try installation again.") from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, ConnectionRefusedError):
            return False
        raise RuntimeError("The local service is not responding. Close its window, then try installation again.") from error
    except (ValueError, OSError) as error:
        raise RuntimeError("The local service could not be checked safely. Close its window, then try installation again.") from error

    # Wait for the listener to close; never terminate a process by PID or name.
    deadline = time.monotonic() + STOP_TIMEOUT
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=min(CONNECT_TIMEOUT, remaining)):
                pass
        except ConnectionRefusedError:
            return True
        except OSError:
            pass
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(0.1, remaining))
    raise RuntimeError("The CapForge service did not stop in time. Close its window, then try installation again.")
