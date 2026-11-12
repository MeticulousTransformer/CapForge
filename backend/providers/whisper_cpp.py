"""Local whisper.cpp. Free, offline, cross-platform.

Runs whisper-cli with -oj -ml 1 -sow for word-ish timestamps.
Timing quality marked "experimental" per AGENTS.md.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

from providers.base import ASRProvider, ProviderError, ProviderResult, lang_short
from services.local_scan import find_whisper_cpp_binary, find_whisper_model
from services.models import Word
from services.normalize import split_trailing_punctuation, word_times


class WhisperCppProvider(ASRProvider):
    id = "whisper_cpp"
    label = "Local whisper.cpp"
    type = "local"
    needs_api_key = False
    supports_word_timestamps = "experimental"

    def availability(self):
        binary = find_whisper_cpp_binary()
        if not binary:
            return False, "whisper-cli binary not found"
        model = find_whisper_model()
        if not model:
            return False, f"binary at {binary}, but no ggml model found"
        return True, f"{binary} + {os.path.basename(model)}"

    def info(self) -> dict:
        d = super().info()
        binary = find_whisper_cpp_binary()
        if binary:
            d["path"] = binary
        model = find_whisper_model()
        if model:
            d["model"] = model
        return d

    def transcribe(self, audio_path: str, language: str, options: dict) -> ProviderResult:
        options = options or {}
        binary = find_whisper_cpp_binary()
        if not binary:
            raise ProviderError(
                "Local whisper.cpp not found. Install: 'brew install whisper-cpp' "
                "(macOS) or build from github.com/ggml-org/whisper.cpp."
            )
        lang = lang_short(language) or "auto"
        model = options.get("model") or find_whisper_model(lang)
        if not model or not os.path.isfile(model):
            raise ProviderError(
                "Local whisper.cpp found, but no model found. Download e.g. "
                "ggml-large-v3-turbo.bin into ~/models/whisper/."
            )

        # A private directory prevents another install, or an earlier run,
        # from supplying this request's output by accident.
        with tempfile.TemporaryDirectory(prefix="kcf-whisper-") as out_dir:
            out_prefix = os.path.join(out_dir, "transcript")
            cmd = [
                binary, "-m", model, "-f", audio_path,
                "-l", lang, "-oj", "-ml", "1", "-sow",
                "-of", out_prefix,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=3600)
            json_path = out_prefix + ".json"
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout or "")[-800:]
                raise ProviderError(f"whisper.cpp failed (code {proc.returncode}): {tail}")
            if not os.path.isfile(json_path):
                raise ProviderError("whisper.cpp finished without transcript output. Check the model and try again.")

            with open(json_path, encoding="utf-8") as f:
                raw = json.load(f)

        # With -ml 1 -sow each transcription entry is ~one word; entries whose
        # text does NOT start with a space continue the previous word.
        words = []
        for seg in raw.get("transcription", []):
            text = seg.get("text", "")
            starts_new = text.startswith(" ")
            piece = text.strip()
            if not piece:
                continue
            core, punct = split_trailing_punctuation(piece)
            if not core:
                if words:
                    words[-1].punctuationAfter += punct
                continue
            # Sub-word pieces can share a clock tick. Check their offsets now,
            # then require a positive interval for every assembled word below.
            start, end = word_times(seg.get("offsets"), "from", "to", 0.001,
                                    raw_response=raw, allow_zero_duration=True)
            if words and not starts_new and not words[-1].punctuationAfter:
                # continuation of previous token (sub-word piece)
                words[-1].text += core
                words[-1].punctuationAfter = punct
                words[-1].end = end
            else:
                words.append(Word(
                    id=len(words), text=core, start=start, end=end,
                    confidence=0.6, punctuationAfter=punct,
                ))
        if not words:
            raise ProviderError("whisper.cpp produced no words. Check audio/model.")
        for word in words:
            word_times({"start": word.start, "end": word.end}, raw_response=raw)
        return ProviderResult(
            raw=raw, words=words, timing_quality="experimental",
            warnings=["whisper.cpp word timings are experimental (-ml 1 -sow). "
                      "Verify in exports/normalized.json."],
        )
