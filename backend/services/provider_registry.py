"""Central provider registry. Add a provider = add one line here."""
from __future__ import annotations

from typing import List, Optional

from providers.base import ASRProvider
from providers.elevenlabs_scribe import ElevenLabsScribeProvider
from providers.google_chirp import GoogleChirpProvider
from providers.openai_asr import OpenAIASRProvider
from providers.azure_speech import AzureSpeechProvider
from providers.gladia import GladiaProvider
from providers.assemblyai import AssemblyAIProvider
from providers.whisper_cpp import WhisperCppProvider
from providers.faster_whisper_local import FasterWhisperProvider
from providers.mlx_whisper_local import MlxWhisperProvider
from providers.nvidia_georgian import NVIDIA_GEORGIAN_MODELS
from providers.omnilingual_ctc import OmnilingualCTCProvider

PROVIDERS: List[ASRProvider] = [
    ElevenLabsScribeProvider(),
    GoogleChirpProvider(),
    OpenAIASRProvider(),
    AzureSpeechProvider(),
    GladiaProvider(),
    AssemblyAIProvider(),
    WhisperCppProvider(),
    FasterWhisperProvider(),
    MlxWhisperProvider(),
    *NVIDIA_GEORGIAN_MODELS,
    OmnilingualCTCProvider(),
]


def get_provider(provider_id: str) -> Optional[ASRProvider]:
    for p in PROVIDERS:
        if p.id == provider_id:
            return p
    return None


def list_infos() -> List[dict]:
    return [p.info() for p in PROVIDERS]


def available_ids() -> List[str]:
    return [p.id for p in PROVIDERS if p.availability()[0]]
