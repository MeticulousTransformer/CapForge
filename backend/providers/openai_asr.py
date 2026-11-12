"""OpenAI ASR.

whisper-1 + verbose_json + word granularity = real word timestamps.
gpt-4o-transcribe = better text, NO word timestamps -> timings are
estimated and marked low confidence with a warning.
"""
from __future__ import annotations

import os

import requests

from providers.base import ASRProvider, ProviderError, ProviderResult, http_error, lang_short
from services.audio_extract import wav_duration
from services.normalize import estimate_words_from_text, normalize_openai_verbose

API_URL = "https://api.openai.com/v1/audio/transcriptions"


class OpenAIASRProvider(ASRProvider):
    id = "openai"
    label = "OpenAI whisper-1"
    type = "cloud"
    api_key_env = "OPENAI_API_KEY"

    def transcribe(self, audio_path: str, language: str, options: dict) -> ProviderResult:
        api_key = self.require_key()
        options = options or {}
        model = options.get("model", "whisper-1")
        lang = lang_short(language)

        data = {"model": model}
        if lang:
            data["language"] = lang
        if model == "whisper-1":
            data["response_format"] = "verbose_json"
            data["timestamp_granularities[]"] = "word"
        else:
            # gpt-4o-transcribe / gpt-4o-mini-transcribe support json only
            data["response_format"] = "json"

        with open(audio_path, "rb") as f:
            resp = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                files={"file": (os.path.basename(audio_path), f, "audio/wav")},
                timeout=900,
            )
        if not resp.ok:
            raise http_error(self.label, resp.status_code)
        raw = resp.json()

        if raw.get("words"):
            words = normalize_openai_verbose(raw)
            return ProviderResult(
                raw=raw, words=words,
                duration=raw.get("duration"), timing_quality="word",
            )

        # No word timestamps (gpt-4o-transcribe): estimate over audio length.
        text = raw.get("text", "")
        if not text:
            raise ProviderError("OpenAI returned no transcript text.")
        duration = raw.get("duration") or wav_duration(audio_path)
        words = estimate_words_from_text(text, 0.0, duration, confidence=0.25)
        return ProviderResult(
            raw=raw, words=words, duration=duration, timing_quality="estimated",
            warnings=[
                f"{model} returns no word timestamps; timings are rough estimates. "
                "Use whisper-1 or ElevenLabs for real word timing."
            ],
        )
