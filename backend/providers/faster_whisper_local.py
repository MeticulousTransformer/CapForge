"""Local faster-whisper (Python). Real word timestamps, offline.

pip install faster-whisper
Best on NVIDIA GPU; on CPU use compute type int8 (default here).
"""
from __future__ import annotations

from providers.base import ASRProvider, ProviderError, ProviderResult, lang_short
from services.local_scan import module_available
from services.normalize import words_from_simple

_MODEL_CACHE = {}


class FasterWhisperProvider(ASRProvider):
    id = "faster_whisper"
    label = "Local faster-whisper"
    type = "local"
    needs_api_key = False

    def availability(self):
        if not module_available("faster_whisper"):
            return False, "pip install faster-whisper"
        return True, None

    def transcribe(self, audio_path: str, language: str, options: dict) -> ProviderResult:
        ok, detail = self.availability()
        if not ok:
            raise ProviderError(f"Provider unavailable: {detail}.")
        from faster_whisper import WhisperModel

        options = options or {}
        model_name = options.get("model", "large-v3")
        compute_type = options.get("computeType", "int8")
        cache_key = (model_name, compute_type)
        if cache_key not in _MODEL_CACHE:
            _MODEL_CACHE[cache_key] = WhisperModel(model_name, compute_type=compute_type)
        model = _MODEL_CACHE[cache_key]

        lang = lang_short(language) or None
        # vad off by default: on speech with music beds VAD drops real words
        segments, info = model.transcribe(
            audio_path,
            language=lang,
            word_timestamps=True,
            vad_filter=bool(options.get("vad", False)),
            beam_size=int(options.get("beamSize", 5)),
            temperature=0.0,
            condition_on_previous_text=False,  # stops error cascades / drift
        )
        raw_words = []
        raw_segments = []
        for seg in segments:
            raw_segments.append({"text": seg.text, "start": seg.start, "end": seg.end})
            for w in seg.words or []:
                raw_words.append({
                    "text": w.word.strip(), "start": w.start, "end": w.end,
                    "confidence": getattr(w, "probability", 1.0),
                })
        raw = {
            "model": model_name, "computeType": compute_type,
            "language": getattr(info, "language", lang),
            "duration": getattr(info, "duration", None),
            "segments": raw_segments, "words": raw_words,
        }
        words = words_from_simple(raw_words, raw_response=raw)
        if not words:
            raise ProviderError("faster-whisper produced no words. Check audio.")
        return ProviderResult(
            raw=raw, words=words,
            duration=getattr(info, "duration", None), timing_quality="word",
        )
