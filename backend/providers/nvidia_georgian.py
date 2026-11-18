"""NVIDIA's two Georgian FastConformer checkpoints, using NeMo's word timestamps."""
from __future__ import annotations

import math
import os
import struct
import tempfile
import wave
from functools import lru_cache

from providers.base import ASRProvider, ProviderError, ProviderResult, lang_short
from services.local_scan import module_available
from services.normalize import WordTimingError, words_from_simple


# Both checkpoints have a 10 ms feature stride and 8x encoder subsampling.
FRAME_SECONDS = 0.08
TIME_TOLERANCE = 1e-8
OFFLINE_CHECKPOINT = "nvidia/stt_ka_fastconformer_hybrid_large_pc"
STREAMING_CHECKPOINT = "nvidia/stt_ka_fastconformer_hybrid_transducer_ctc_large_streaming_80ms_pc"


@lru_cache(maxsize=2)
def _load_model(checkpoint):
    try:
        import torch
        from nemo.collections.asr.models import ASRModel
    except (ImportError, OSError) as error:
        raise ProviderError("Install the optional NVIDIA NeMo ASR dependencies in CapForge's Python environment.") from error
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        return ASRModel.from_pretrained(model_name=checkpoint, map_location=device).eval()
    except Exception as error:
        raise ProviderError(
            f"Could not load {checkpoint}. The first use needs an internet connection and space to cache the model."
        ) from error


def _wav_sections(audio_path):
    """Bound inference memory and split long files at a quiet point near 25 s."""
    with wave.open(audio_path, "rb") as source:
        rate = source.getframerate()
        if (rate, source.getnchannels(), source.getsampwidth()) != (16000, 1, 2):
            raise ProviderError("NVIDIA FastConformer requires a 16 kHz mono PCM WAV.")
        total = source.getnframes()
        if total <= 25 * rate:
            yield audio_path, 0.0, total / rate
            return

        with tempfile.TemporaryDirectory(prefix="capforge-nvidia-") as folder:
            path = os.path.join(folder, "section.wav")
            while source.tell() < total:
                start = source.tell()
                count = min(25 * rate, total - start)
                data = source.readframes(count)
                if start + count < total:
                    # Compare 100 ms windows between 20 and 24 seconds. The
                    # midpoint of the quietest window is shared by both sections.
                    window = rate // 10
                    def energy(frame):
                        block = data[2 * frame:2 * (frame + window)]
                        return sum(v * v for (v,) in struct.iter_unpack("<h", block))
                    quietest = min(range(20 * rate, 24 * rate, window), key=energy)
                    count = quietest + window // 2
                    data = data[:2 * count]
                    source.setpos(start + count)
                with wave.open(path, "wb") as part:
                    part.setparams(source.getparams())
                    part.writeframes(data)
                yield path, start / rate, count / rate


def _separate_frame_overlaps(words, raw, warnings):
    """Keep the decode order when RNN-T emits multiple words on one acoustic frame."""
    for previous, current in zip(words, words[1:]):
        if (current.start < previous.start or current.end < previous.end
                or previous.end - current.start > FRAME_SECONDS + TIME_TOLERANCE):
            raise WordTimingError(raw)

    first = 0
    while first < len(words):
        start = words[first].start
        after = first + 1
        while after < len(words) and words[after].start == start:
            after += 1
        next_start = words[after].start if after < len(words) else None
        count = after - first
        if count > 1:
            # Only subdivide the shared part. The final word may continue for
            # several more frames and keeps that later endpoint.
            shared_end = words[first].end
            if next_start is not None:
                shared_end = min(shared_end, next_start)
            for i in range(1, count):
                boundary = start + (shared_end - start) * i / count
                words[first + i - 1].end = boundary
                words[first + i].start = boundary
            warnings.add("NVIDIA emitted multiple words at the same instant. Their sub-frame boundaries were estimated within the shared 80 ms frame.")
        last = words[after - 1]
        if next_start is not None and last.end > next_start:
            last.end = next_start
            warnings.add("Overlapping NVIDIA word endings were trimmed to the next word's start on a shared encoder frame.")
        first = after


def _align_streaming_words(path, duration, hypothesis, raw):
    """Align the streaming model's exact transcript to acoustic frames instead of emission times."""
    from nemo.collections.asr.parts.utils.timestamp_utils import get_forced_aligned_timestamps_with_external_model

    aligner = _load_model(OFFLINE_CHECKPOINT)
    aligner.change_decoding_strategy(decoder_type="ctc", verbose=False)
    try:
        acoustic = aligner.transcribe([path], batch_size=1, num_workers=0, return_hypotheses=True, verbose=False)
        # The encoder can pad a final analysis window. Search only frames
        # whose beginning falls inside this original section of the recording.
        acoustic[0].y_sequence = acoustic[0].y_sequence[:math.ceil(duration / FRAME_SECONDS)]
        aligned = get_forced_aligned_timestamps_with_external_model(
            acoustic, aligner, [hypothesis], batch_size=1, has_hypotheses=True, timestamp_type="word",
        )
        return aligned[0].timestamp["word"]
    except (ValueError, IndexError, KeyError) as error:
        raise WordTimingError(raw) from error
    finally:
        # This same cached checkpoint provides RNN-T recognition when the user
        # selects the offline model again.
        aligner.change_decoding_strategy(decoder_type="rnnt", verbose=False)


class NvidiaGeorgianProvider(ASRProvider):
    type = "local"
    needs_api_key = False
    supports_english = False

    def __init__(self, provider_id, label, checkpoint):
        self.id = provider_id
        self.label = label
        self.checkpoint = checkpoint

    def info(self):
        return dict(super().info(), supportedLanguages=["ka-GE"], model=self.checkpoint)

    def availability(self):
        if not module_available("nemo") or not module_available("torch"):
            return False, "Install the optional NVIDIA NeMo ASR dependencies in CapForge's Python environment."
        return True, None

    def transcribe(self, audio_path, language, options):
        if lang_short(language) not in ("ka", "kat"):
            raise ProviderError(f"{self.label} transcribes Georgian only. Choose Georgian as the language.")
        if options and options.get("model") not in (None, "", self.checkpoint):
            raise ProviderError("Choose the NVIDIA model from CapForge's provider list.")
        model = _load_model(self.checkpoint)
        raw = {"model": self.checkpoint, "sections": []}
        words = []
        warnings = set()
        for path, offset, duration in _wav_sections(audio_path):
            results = model.transcribe(
                [path], batch_size=1, timestamps=True, return_hypotheses=True, num_workers=0, verbose=False,
            )
            if not isinstance(results, list) or len(results) != 1:
                raise ProviderError("NVIDIA NeMo returned no transcription for this audio section.")
            hyp = results[0]
            stamps = getattr(hyp, "timestamp", None)
            items = stamps.get("word") if isinstance(stamps, dict) else None
            text = getattr(hyp, "text", hyp if isinstance(hyp, str) else "")
            section = {"offset": offset, "duration": duration, "text": text, "words": items}
            raw["sections"].append(section)
            if isinstance(text, str) and not text.strip() and not items:
                continue  # Silent sections can occur between speakers.
            if self.checkpoint == STREAMING_CHECKPOINT and isinstance(text, str) and text.strip():
                raw["alignmentModel"] = OFFLINE_CHECKPOINT
                items = _align_streaming_words(path, duration, hyp, raw)
                section["alignedWords"] = items
            if not isinstance(items, list) or not items:
                raise WordTimingError(raw)
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("word"), str) or not item["word"].strip():
                    raise WordTimingError(raw)
            timed_text = "".join(item["word"].strip() for item in items)
            if not isinstance(text, str) or timed_text != "".join(text.split()):
                raise WordTimingError(raw)
            section_words = words_from_simple(items, text_key="word", raw_response=raw)
            for word in section_words:
                # The last encoder frame can extend beyond the PCM section.
                if word.start >= duration or word.end - duration > FRAME_SECONDS + TIME_TOLERANCE:
                    raise WordTimingError(raw)
                word.end = min(word.end, duration)
            _separate_frame_overlaps(section_words, raw, warnings)
            for word in section_words:
                word.id = len(words)
                word.start += offset
                word.end += offset
                words.append(word)
        if not words:
            raise ProviderError("NVIDIA FastConformer found no Georgian speech in this audio.")
        return ProviderResult(raw=raw, words=words, warnings=sorted(warnings))


NVIDIA_GEORGIAN_MODELS = [
    NvidiaGeorgianProvider(
        "nvidia_fastconformer_ka", "NVIDIA Georgian FastConformer",
        OFFLINE_CHECKPOINT,
    ),
    NvidiaGeorgianProvider(
        "nvidia_fastconformer_ka_80ms", "NVIDIA Georgian FastConformer 80 ms",
        STREAMING_CHECKPOINT,
    ),
]
