"""Meta's Omnilingual CTC 1B v2, decoded from its 20 ms acoustic emissions."""
from __future__ import annotations

import hashlib
import wave
from functools import lru_cache
from itertools import groupby
from pathlib import Path

from providers.base import ASRProvider, ProviderError, ProviderResult, lang_short
from services.local_scan import module_available
from services.normalize import words_from_simple


MODEL_ID = "OpenVoiceOS/omnilingual-asr-ctc-1b-onnx"
REVISION = "54aff519eb8feb79962d5f45f1aad8f4fafd44f2"
MODEL_SHA256 = "8af72da192fc2c8567c328d4f8059bdf47f182a0369077893c295ef39740c637"
TOKENS_SHA256 = "7d99997ef207ff14c2cfe825f2aa037528ea250113cc3c6392bfe49326884ba6"
SAMPLE_RATE = 16000
FRAME_SAMPLES = 320
CORE_SAMPLES = 24 * SAMPLE_RATE
CONTEXT_SAMPLES = 2 * SAMPLE_RATE
INSTALL_HINT = "Install the optional Omnilingual dependencies in CapForge's Python environment."


def _verified_file(download, filename, expected_digest):
    path = Path(download(repo_id=MODEL_ID, filename=filename, revision=REVISION))
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected_digest:
        raise ProviderError(f"The cached Omnilingual {filename} failed its checksum. Remove that cached file and retry.")
    return path


@lru_cache(maxsize=1)
def _load_model():
    try:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
    except (ImportError, OSError) as error:
        raise ProviderError(INSTALL_HINT) from error
    try:
        model = _verified_file(hf_hub_download, "model.int8.onnx", MODEL_SHA256)
        vocabulary = _verified_file(hf_hub_download, "tokens.txt", TOKENS_SHA256)
        # The vocabulary uses a literal space character. Only the final space
        # on each line separates the character from its numeric ID.
        tokens = {}
        with vocabulary.open(encoding="utf-8") as file:
            for line in file:
                text, index = line.rstrip("\n").rsplit(" ", 1)
                tokens[int(index)] = text
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        return ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"]), tokens
    except ProviderError:
        raise
    except Exception as error:
        raise ProviderError(
            "Could not load Meta Omnilingual CTC. First use needs internet access and about 1 GB of disk space."
        ) from error


def _emissions(source, session):
    """Decode bounded overlapping windows, keeping each absolute frame exactly once."""
    import numpy as np

    total = source.getnframes()
    emitted = []
    # Both window and context sizes are multiples of the model's 320-sample stride.
    for start in range(0, total, CORE_SAMPLES):
        stop = min(total, start + CORE_SAMPLES)
        left = max(0, start - CONTEXT_SAMPLES)
        right = min(total, stop + CONTEXT_SAMPLES)
        source.setpos(left)
        audio = np.frombuffer(source.readframes(right - left), dtype="<i2").astype(np.float32) / 32768
        if len(audio) < 400:  # The convolutional frontend needs one full receptive field.
            audio = np.pad(audio, (0, 400 - len(audio)))
        logits = session.run(["logits"], {"x": audio[None, :]})[0][0]
        first = (start - left) // FRAME_SAMPLES
        last = (stop - left + FRAME_SAMPLES - 1) // FRAME_SAMPLES
        logits = logits[first:last]
        if len(logits) == 0:
            continue
        ids = np.argmax(logits, axis=1)
        boundaries = np.r_[0, np.flatnonzero(ids[1:] != ids[:-1]) + 1, len(ids)]
        for i, j in zip(boundaries[:-1], boundaries[1:]):
            token = int(ids[i])
            if token == 0:
                continue
            frame = start // FRAME_SAMPLES + int(i)
            end = start // FRAME_SAMPLES + int(j)
            # Posterior of this emission's first frame, calculated from its logits.
            confidence = 1.0 / float(np.exp(logits[i] - logits[i, token]).sum())
            if emitted and emitted[-1]["id"] == token and emitted[-1]["endFrame"] == frame:
                emitted[-1]["endFrame"] = end
            else:
                emitted.append({"id": token, "startFrame": frame, "endFrame": end, "confidence": confidence})
    return emitted


def _words(emissions, tokens, duration):
    words = []
    letters = (emission for emission in emissions if emission["id"] >= 4)
    for is_space, run in groupby(letters, key=lambda emission: tokens[emission["id"]] == " "):
        if is_space:
            continue
        parts = list(run)
        words.append({
            "text": "".join(tokens[part["id"]] for part in parts),
            "start": parts[0]["startFrame"] * FRAME_SAMPLES / SAMPLE_RATE,
            "end": min(duration, parts[-1]["endFrame"] * FRAME_SAMPLES / SAMPLE_RATE),
            "confidence": sum(part["confidence"] for part in parts) / len(parts),
        })
    return words


class OmnilingualCTCProvider(ASRProvider):
    id = "omnilingual_ctc_1b"
    label = "Meta Omnilingual CTC 1B v2"
    type = "local"
    needs_api_key = False

    def info(self):
        return dict(super().info(), supportedLanguages=["ka-GE", "en-US", "auto"], model=MODEL_ID,
                    languageMode="auto", languageNote="This model detects the spoken language automatically.")

    def availability(self):
        if not all(module_available(name) for name in ("onnxruntime", "huggingface_hub", "numpy")):
            return False, INSTALL_HINT
        return True, None

    def transcribe(self, audio_path, language, options):
        if lang_short(language) not in ("ka", "kat", "en", ""):
            raise ProviderError(f"Choose Georgian, English or Auto for {self.label}.")
        if options and options.get("model") not in (None, "", MODEL_ID):
            raise ProviderError("Choose Meta Omnilingual CTC 1B v2 from CapForge's provider list.")
        with wave.open(audio_path, "rb") as source:
            if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (SAMPLE_RATE, 1, 2):
                raise ProviderError("Meta Omnilingual CTC requires a 16 kHz mono PCM WAV.")
            duration = source.getnframes() / SAMPLE_RATE
            session, tokens = _load_model()
            emissions = _emissions(source, session)
        items = _words(emissions, tokens, duration)
        raw = {"model": MODEL_ID, "revision": REVISION, "frameSeconds": FRAME_SAMPLES / SAMPLE_RATE,
               "emissions": emissions, "words": items}
        words = words_from_simple(items, raw_response=raw)
        if not words:
            raise ProviderError("Meta Omnilingual CTC found no speech words in this audio.")
        return ProviderResult(raw=raw, words=words, duration=duration)
