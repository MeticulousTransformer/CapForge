"""Provider interface. Every ASR adapter implements ASRProvider."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Union

from services.models import Word


class ProviderError(RuntimeError):
    """User-facing provider failure (missing key, API error...)."""


def http_error(label: str, status: int) -> ProviderError:
    """Translate a failed provider request without echoing its private body."""
    if status in (401, 403):
        action = "Check the saved API key in Setup and confirm that your provider account allows transcription."
    elif status == 429:
        action = "Check your provider's credits or usage limit, then try again later."
    elif status == 413:
        action = "Export a shorter audio clip and try that file."
    elif status >= 500:
        action = "The provider is having trouble. Check its status and try again later."
    else:
        action = "Check the chosen model, language and transcription options, then try again."
    return ProviderError(f"{label} could not accept the request (HTTP {status}). {action}")


@dataclass
class ProviderResult:
    raw: object                      # raw provider JSON, saved for debugging
    words: List[Word]                # normalized words
    duration: Optional[float] = None
    # "word" | "experimental" | "segment-estimated" | "estimated"
    timing_quality: str = "word"
    warnings: List[str] = field(default_factory=list)


class ASRProvider:
    id = "base"
    label = "Base"
    type = "cloud"                   # "cloud" | "local"
    needs_api_key = True
    api_key_env: Optional[str] = None
    supports_word_timestamps: Union[bool, str] = True
    supports_georgian = True
    supports_english = True

    def availability(self):
        """-> (available: bool, detail: Optional[str])"""
        if self.api_key_env:
            if os.environ.get(self.api_key_env):
                return True, None
            return False, f"missing {self.api_key_env}"
        return True, None

    def info(self) -> dict:
        available, detail = self.availability()
        d = {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "available": available,
            "needsApiKey": self.needs_api_key,
            "supportsWordTimestamps": self.supports_word_timestamps,
            "supportsGeorgian": self.supports_georgian,
            "supportsEnglish": self.supports_english,
        }
        if detail:
            d["detail"] = detail
        return d

    def require_key(self) -> str:
        key = os.environ.get(self.api_key_env or "")
        if not key:
            raise ProviderError(f"Provider unavailable: missing {self.api_key_env}.")
        return key

    def transcribe(self, audio_path: str, language: str, options: dict) -> ProviderResult:
        raise NotImplementedError


def lang_short(language: str) -> str:
    """'ka-GE' -> 'ka', 'en-US' -> 'en', auto -> ''."""
    if not language or language.lower() in ("auto", "auto-detect", ""):
        return ""
    return language.split("-")[0].lower()


_DEFAULT_REGIONS = {"ka": "ka-GE", "en": "en-US"}


def lang_bcp47(language: str) -> str:
    """'ka' -> 'ka-GE', 'en' -> 'en-US', passthrough for full codes."""
    if not language or language.lower() in ("auto", "auto-detect", ""):
        return ""
    if "-" in language:
        return language
    return _DEFAULT_REGIONS.get(language.lower(), language)
