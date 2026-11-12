"""Normalized transcript data model.

All ASR providers convert their raw output into these types.
The normalized word timeline is sacred: the AE animation engine
must never care which provider produced it.
"""
from __future__ import annotations

import uuid
import math
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class Word:
    id: int
    text: str
    start: float
    end: float
    confidence: float = 1.0
    speaker: Optional[str] = None
    punctuationAfter: str = ""
    isEdited: bool = False

    def display_text(self) -> str:
        return self.text + self.punctuationAfter

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Caption:
    id: int
    text: str
    start: float
    end: float
    wordIds: List[int] = field(default_factory=list)
    lineIndex: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def build_document(
    source_media_path: str,
    language: str,
    provider: str,
    duration: Optional[float],
    words: List[Word],
    captions: List[Caption],
    doc_id: Optional[str] = None,
) -> dict:
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        duration = 0.0
    # Provider metadata can stop slightly before the final word. Keep the
    # timeline intact, including sub-millisecond endpoints.
    duration = max(duration, max((w.end for w in words), default=0.0),
                   max((c.end for c in captions), default=0.0))
    return {
        "id": doc_id or str(uuid.uuid4()),
        "sourceMediaPath": source_media_path,
        "language": language,
        "provider": provider,
        "duration": float(duration),
        "words": [w.to_dict() for w in words],
        "captions": [c.to_dict() for c in captions],
    }
