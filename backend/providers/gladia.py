"""Gladia v2 (Whisper-large based). Georgian + word timestamps.

Env: GLADIA_API_KEY
Flow: upload -> start pre-recorded job -> poll result.
"""
from __future__ import annotations

import os
import time

import requests

from providers.base import ASRProvider, ProviderError, ProviderResult, http_error, lang_short
from services.normalize import words_from_simple

UPLOAD_URL = "https://api.gladia.io/v2/upload"
TRANSCRIBE_URL = "https://api.gladia.io/v2/pre-recorded"
POLL_INTERVAL = 2.0
POLL_TIMEOUT = 900


class GladiaProvider(ASRProvider):
    id = "gladia"
    label = "Gladia (Whisper cloud)"
    type = "cloud"
    api_key_env = "GLADIA_API_KEY"

    def transcribe(self, audio_path: str, language: str, options: dict) -> ProviderResult:
        key = self.require_key()
        options = options or {}
        headers = {"x-gladia-key": key}

        with open(audio_path, "rb") as f:
            up = requests.post(
                UPLOAD_URL, headers=headers,
                files={"audio": (os.path.basename(audio_path), f, "audio/wav")},
                timeout=900,
            )
        if not up.ok:
            raise http_error(self.label, up.status_code)
        audio_url = up.json().get("audio_url")

        payload = {"audio_url": audio_url}
        lang = lang_short(language)
        if lang:
            payload["language"] = lang
        job = requests.post(TRANSCRIBE_URL, headers=headers, json=payload, timeout=60)
        if not job.ok:
            raise http_error(self.label, job.status_code)
        result_url = job.json().get("result_url")

        deadline = time.time() + POLL_TIMEOUT
        raw = None
        while time.time() < deadline:
            poll = requests.get(result_url, headers=headers, timeout=60)
            if not poll.ok:
                raise http_error(self.label, poll.status_code)
            raw = poll.json()
            status = raw.get("status")
            if status == "done":
                break
            if status == "error":
                raise ProviderError(f"Gladia transcription failed: {raw.get('error_code')}")
            time.sleep(POLL_INTERVAL)
        else:
            raise ProviderError("Gladia transcription timed out.")

        transcription = (raw.get("result") or {}).get("transcription") or {}
        raw_words = []
        for utt in transcription.get("utterances", []):
            for w in utt.get("words", []):
                raw_words.append({
                    "text": (w.get("word") or "").strip(),
                    "start": w.get("start"), "end": w.get("end"),
                    "confidence": w.get("confidence", 1.0),
                })
        words = words_from_simple(raw_words, raw_response=raw)
        if not words:
            raise ProviderError("Gladia returned no words.")
        duration = ((raw.get("result") or {}).get("metadata") or {}).get("audio_duration")
        return ProviderResult(raw=raw, words=words, duration=duration, timing_quality="word")
