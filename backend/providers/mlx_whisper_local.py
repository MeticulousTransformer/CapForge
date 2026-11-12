"""Local mlx-whisper. Apple Silicon only. Fast on Mac, word timestamps.

pip install mlx-whisper
"""
from __future__ import annotations

from providers.base import ASRProvider, ProviderError, ProviderResult, lang_short
from services.local_scan import is_apple_silicon, module_available
from services.normalize import words_from_simple

DEFAULT_REPO = "mlx-community/whisper-large-v3-mlx"


class MlxWhisperProvider(ASRProvider):
    id = "mlx_whisper"
    label = "Local mlx-whisper (Apple Silicon)"
    type = "local"
    needs_api_key = False

    def availability(self):
        if not is_apple_silicon():
            return False, "requires Apple Silicon Mac"
        if not module_available("mlx_whisper"):
            return False, "pip install mlx-whisper"
        return True, None

    def transcribe(self, audio_path: str, language: str, options: dict) -> ProviderResult:
        ok, detail = self.availability()
        if not ok:
            raise ProviderError(f"Provider unavailable: {detail}.")
        import mlx_whisper

        options = options or {}
        repo = options.get("model", DEFAULT_REPO)
        lang = lang_short(language) or None
        raw = mlx_whisper.transcribe(
            audio_path, path_or_hf_repo=repo,
            language=lang, word_timestamps=True,
            condition_on_previous_text=False,  # stops error cascades / drift
        )
        raw_words = []
        for seg in raw.get("segments", []):
            for w in seg.get("words", []):
                raw_words.append({
                    "text": (w.get("word") or "").strip(),
                    "start": w.get("start"), "end": w.get("end"),
                    "confidence": w.get("probability", 1.0),
                })
        words = words_from_simple(raw_words, raw_response=raw)
        if not words:
            raise ProviderError("mlx-whisper produced no word timestamps.")
        return ProviderResult(raw=raw, words=words, timing_quality="word")
