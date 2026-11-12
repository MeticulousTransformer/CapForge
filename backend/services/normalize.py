"""Provider output -> normalized Word list.

Rules (AGENTS.md):
- Keep Georgian Unicode intact. Never transliterate.
- Skip spacing / audio-event tokens; never assign them word IDs.
- Punctuation returned as separate tokens is merged into the
  previous word's `punctuationAfter`.
- Trailing punctuation attached to a word is split off into
  `punctuationAfter` so grouping can detect sentence ends.
"""
from __future__ import annotations

import math
from typing import List, Optional

from services.models import Word

SENTENCE_END = ".?!…"
PUNCT_CHARS = ".,!?;:…\"'«»“”‘’()[]"


class WordTimingError(ValueError):
    """A speech word is missing a usable provider timing interval."""

    def __init__(self, raw_response=None):
        super().__init__(
            "The provider returned a word without valid start and end times. "
            "Choose a model with word timestamps or try another provider."
        )
        # Keep an already-received response available for debugging even when
        # its timeline cannot become a normalized document.
        self.raw_response = raw_response


def word_times(item: dict, start_key="start", end_key="end", time_scale=1.0,
               raw_response=None, allow_zero_duration=False):
    """Read real times; absent timestamps must never turn into time zero."""
    try:
        if not isinstance(item, dict):
            raise ValueError
        start, end = item.get(start_key), item.get(end_key)
        if isinstance(start, bool) or isinstance(end, bool):
            raise ValueError
        start, end = float(start) * time_scale, float(end) * time_scale
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start or (end == start and not allow_zero_duration):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise WordTimingError(raw_response) from None
    return start, end


def split_trailing_punctuation(text: str):
    """'ხარ?' -> ('ხარ', '?'). A punctuation-only token -> ('', token)."""
    core = text
    punct = ""
    while core and core[-1] in PUNCT_CHARS:
        punct = core[-1] + punct
        core = core[:-1]
    if not core:
        return "", punct
    return core, punct


def words_from_tokens(tokens: List[dict], raw_response=None) -> List[Word]:
    """Token stream (ElevenLabs style) -> Words.

    Token: {text, start, end, type?, speaker?, confidence?}
    type "spacing" / "audio_event" tokens are skipped.
    """
    words: List[Word] = []
    for t in tokens:
        ttype = t.get("type", "word")
        if ttype in ("spacing", "audio_event"):
            continue
        text = (t.get("text") or "").strip()
        if not text:
            continue
        core, punct = split_trailing_punctuation(text)
        if not core:
            # punctuation-only token: merge into previous word
            if words:
                words[-1].punctuationAfter += punct
            continue
        start, end = word_times(t, raw_response=raw_response)
        confidence = t.get("confidence")
        words.append(
            Word(
                id=len(words),
                text=core,
                start=start,
                end=end,
                confidence=float(confidence) if confidence is not None else 1.0,
                speaker=t.get("speaker"),
                punctuationAfter=punct,
            )
        )
    return words


def words_from_simple(
    items: List[dict],
    text_key: str = "text",
    start_key: str = "start",
    end_key: str = "end",
    confidence_key: str = "confidence",
    speaker_key: Optional[str] = None,
    time_scale: float = 1.0,
    raw_response=None,
) -> List[Word]:
    """Flat word list (OpenAI, Gladia, AssemblyAI, Azure...) -> Words.

    time_scale converts provider units to seconds (0.001 for ms).
    """
    words: List[Word] = []
    for it in items:
        text = (it.get(text_key) or "").strip()
        if not text:
            continue
        core, punct = split_trailing_punctuation(text)
        if not core:
            if words:
                words[-1].punctuationAfter += punct
            continue
        conf = it.get(confidence_key)
        start, end = word_times(it, start_key, end_key, time_scale, raw_response=raw_response)
        words.append(
            Word(
                id=len(words),
                text=core,
                start=start,
                end=end,
                confidence=float(conf) if conf is not None else 1.0,
                speaker=it.get(speaker_key) if speaker_key else None,
                punctuationAfter=punct,
            )
        )
    return words


def normalize_elevenlabs(raw: dict) -> List[Word]:
    tokens = [
        {
            "text": w.get("text", ""),
            "start": w.get("start"),
            "end": w.get("end"),
            "type": w.get("type", "word"),
            "speaker": w.get("speaker_id"),
            "confidence": w.get("confidence"),
        }
        for w in raw.get("words", [])
    ]
    return words_from_tokens(tokens, raw_response=raw)


def normalize_openai_verbose(raw: dict) -> List[Word]:
    return words_from_simple(raw.get("words", []), text_key="word", raw_response=raw)


def estimate_words_from_text(text: str, start: float, end: float, confidence: float = 0.3) -> List[Word]:
    """Fallback when a provider returns text without word timings.

    Distributes time proportionally to character length. Marked low
    confidence so the UI can warn that timings are estimated.
    """
    parts = [p for p in text.split() if p]
    if not parts:
        return []
    total_chars = sum(len(p) + 1 for p in parts)
    span = max(end - start, 0.01)
    words: List[Word] = []
    cursor = start
    for p in parts:
        w_dur = span * (len(p) + 1) / total_chars
        core, punct = split_trailing_punctuation(p)
        if not core:
            if words:
                words[-1].punctuationAfter += punct
                words[-1].end = round(cursor + w_dur, 4)
            cursor += w_dur
            continue
        words.append(
            Word(
                id=len(words),
                text=core,
                start=round(cursor, 4),
                end=round(cursor + w_dur, 4),
                confidence=confidence,
                punctuationAfter=punct,
            )
        )
        cursor += w_dur
    return words
