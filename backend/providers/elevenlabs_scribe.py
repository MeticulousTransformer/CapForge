"""ElevenLabs Scribe — primary Georgian provider. Word-level timestamps."""
from __future__ import annotations

import json
import os

import requests

from providers.base import ASRProvider, ProviderError, ProviderResult, http_error, lang_short
from services.normalize import normalize_elevenlabs

API_URL = "https://api.elevenlabs.io/v1/speech-to-text"


class ElevenLabsScribeProvider(ASRProvider):
    id = "elevenlabs"
    label = "ElevenLabs Scribe v2"
    type = "cloud"
    api_key_env = "ELEVENLABS_API_KEY"

    def _request(self, api_key: str, audio_path: str, data: dict) -> requests.Response:
        with open(audio_path, "rb") as f:
            return requests.post(
                API_URL,
                headers={"xi-api-key": api_key},
                data=data,
                files={"file": (os.path.basename(audio_path), f, "audio/wav")},
                timeout=900,
            )

    def transcribe(self, audio_path: str, language: str, options: dict) -> ProviderResult:
        api_key = self.require_key()
        options = options or {}
        model = options.get("model", "scribe_v2")
        data = {
            "model_id": model,
            "timestamps_granularity": "word",
            "diarize": "true" if options.get("diarize") else "false",
            "tag_audio_events": "false",
        }
        lang = lang_short(language)
        if lang:
            data["language_code"] = lang
        keyterms = options.get("keyterms")
        if keyterms:
            data["keyterms"] = json.dumps(list(keyterms), ensure_ascii=False)

        resp = self._request(api_key, audio_path, data)
        # One click makes one upload. A failed request does not authorize a
        # second paid attempt or a silent change to the selected model.
        if not resp.ok:
            raise http_error(self.label, resp.status_code)

        raw = resp.json()
        words = normalize_elevenlabs(raw)
        if not words:
            raise ProviderError("ElevenLabs returned no words. Check audio content.")
        return ProviderResult(raw=raw, words=words, timing_quality="word")
