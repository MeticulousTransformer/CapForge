"""AssemblyAI. Georgian ('ka') supported via nano speech model.

Env: ASSEMBLYAI_API_KEY
Flow: upload -> create transcript -> poll.
"""
from __future__ import annotations

import time

import requests

from providers.base import ASRProvider, ProviderError, ProviderResult, http_error, lang_short
from services.normalize import words_from_simple

BASE = "https://api.assemblyai.com/v2"
POLL_INTERVAL = 2.0
POLL_TIMEOUT = 900


class AssemblyAIProvider(ASRProvider):
    id = "assemblyai"
    label = "AssemblyAI"
    type = "cloud"
    api_key_env = "ASSEMBLYAI_API_KEY"

    def transcribe(self, audio_path: str, language: str, options: dict) -> ProviderResult:
        key = self.require_key()
        options = options or {}
        headers = {"authorization": key}

        with open(audio_path, "rb") as f:
            up = requests.post(f"{BASE}/upload", headers=headers, data=f, timeout=900)
        if not up.ok:
            raise http_error(self.label, up.status_code)
        upload_url = up.json().get("upload_url")

        lang = lang_short(language)
        payload = {"audio_url": upload_url, "punctuate": True}
        if lang:
            payload["language_code"] = lang
            # Georgian is served by the nano model tier
            payload["speech_model"] = options.get("model") or ("nano" if lang == "ka" else "best")
        elif options.get("model"):
            payload["speech_model"] = options["model"]

        job = requests.post(f"{BASE}/transcript", headers=headers, json=payload, timeout=60)
        if not job.ok:
            raise http_error(self.label, job.status_code)
        tid = job.json().get("id")

        deadline = time.time() + POLL_TIMEOUT
        raw = None
        while time.time() < deadline:
            poll = requests.get(f"{BASE}/transcript/{tid}", headers=headers, timeout=60)
            if not poll.ok:
                raise http_error(self.label, poll.status_code)
            raw = poll.json()
            status = raw.get("status")
            if status == "completed":
                break
            if status == "error":
                raise ProviderError(f"AssemblyAI failed: {raw.get('error')}")
            time.sleep(POLL_INTERVAL)
        else:
            raise ProviderError("AssemblyAI transcription timed out.")

        words = words_from_simple(raw.get("words", []), time_scale=0.001, raw_response=raw)
        if not words:
            raise ProviderError("AssemblyAI returned no words.")
        duration = raw.get("audio_duration")
        return ProviderResult(raw=raw, words=words, duration=duration, timing_quality="word")
