"""Each real adapter must preserve missing timings and retain its raw response."""
import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as service
from fastapi import HTTPException
from providers.elevenlabs_scribe import ElevenLabsScribeProvider
from providers.openai_asr import OpenAIASRProvider
from providers.gladia import GladiaProvider
from providers.assemblyai import AssemblyAIProvider
from providers.azure_speech import AzureSpeechProvider
from providers.mlx_whisper_local import MlxWhisperProvider
from providers.faster_whisper_local import FasterWhisperProvider
from providers.whisper_cpp import WhisperCppProvider
from services.normalize import WordTimingError


def response(raw):
    return SimpleNamespace(ok=True, json=lambda: raw)


class TestAdapterTimingSafety(unittest.TestCase):
    def test_azure_rejects_missing_offsets_and_durations_but_accepts_real_zero(self):
        provider = AzureSpeechProvider()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"AZURE_SPEECH_KEY": "test", "AZURE_SPEECH_REGION": "westeurope"}):
            audio = Path(folder) / "clip.wav"
            audio.touch()
            for timing in ({"durationMilliseconds": 1000}, {"offsetMilliseconds": 0}, {"offsetMilliseconds": False, "durationMilliseconds": 1000}):
                raw = {"phrases": [{"words": [{"text": "hello", **timing}]}]}
                with self.subTest(timing=timing), patch("requests.post", return_value=response(raw)):
                    with self.assertRaises(WordTimingError):
                        provider.transcribe(str(audio), "en", {})
            raw = {"phrases": [{"words": [{"text": "hello", "offsetMilliseconds": 0, "durationMilliseconds": 1000}]}]}
            with patch("requests.post", return_value=response(raw)):
                result = provider.transcribe(str(audio), "en", {})
                self.assertEqual((result.words[0].start, result.words[0].end), (0, 1))

    def test_mlx_rejects_missing_start_but_accepts_real_zero(self):
        provider = MlxWhisperProvider()
        for timing in ({"end": 1}, {"start": 0, "end": 1}):
            raw = {"segments": [{"words": [{"word": "hello", **timing}]}]}
            module = SimpleNamespace(transcribe=lambda *args, **kwargs: raw)
            with self.subTest(timing=timing), patch.object(provider, "availability", return_value=(True, None)), patch.dict(sys.modules, {"mlx_whisper": module}):
                if "start" not in timing:
                    with self.assertRaises(WordTimingError):
                        provider.transcribe("unused.wav", "en", {})
                else:
                    result = provider.transcribe("unused.wav", "en", {})
                    self.assertEqual((result.words[0].start, result.words[0].end), (0, 1))

    def test_whisper_rejects_missing_offset_in_new_and_continuation_tokens(self):
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / "ggml-model.bin"
            model.touch()
            for text, previous in ((" hello", []), ("lo", [{"text": " hel", "offsets": {"from": 0, "to": 500}}])):
                raw = {"transcription": previous + [{"text": text, "offsets": {"to": 1000}}]}
                def encode(command, **kwargs):
                    Path(command[command.index("-of") + 1] + ".json").write_text(json.dumps(raw))
                    return SimpleNamespace(returncode=0, stderr="", stdout="")
                with self.subTest(text=text), patch("providers.whisper_cpp.find_whisper_cpp_binary", return_value="whisper-cli"), patch("providers.whisper_cpp.subprocess.run", side_effect=encode):
                    with self.assertRaises(WordTimingError):
                        WhisperCppProvider().transcribe("unused.wav", "en", {"model": str(model)})

    def test_whisper_combines_same_tick_pieces_and_ignores_untimed_punctuation(self):
        raw = {"transcription": [
            {"text": " hel", "offsets": {"from": 0, "to": 0}},
            {"text": "lo", "offsets": {"from": 0, "to": 1000}},
            {"text": "!"},
        ]}
        def encode(command, **kwargs):
            Path(command[command.index("-of") + 1] + ".json").write_text(json.dumps(raw))
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / "ggml-model.bin"
            model.touch()
            with patch("providers.whisper_cpp.find_whisper_cpp_binary", return_value="whisper-cli"), patch("providers.whisper_cpp.subprocess.run", side_effect=encode):
                result = WhisperCppProvider().transcribe("unused.wav", "en", {"model": str(model)})
                self.assertEqual(len(result.words), 1)
                self.assertEqual(result.words[0].display_text(), "hello!")
                self.assertEqual((result.words[0].start, result.words[0].end), (0, 1))
                raw["transcription"] = [{"text": " hello", "offsets": {"from": 0, "to": 0}}]
                with self.assertRaises(WordTimingError) as error:
                    WhisperCppProvider().transcribe("unused.wav", "en", {"model": str(model)})
                self.assertEqual(error.exception.raw_response, raw)

    def test_api_saves_successful_provider_response_when_adapter_rejects_timing(self):
        providers = [ElevenLabsScribeProvider(), OpenAIASRProvider(), GladiaProvider(), AssemblyAIProvider(), AzureSpeechProvider(), MlxWhisperProvider(), FasterWhisperProvider(), WhisperCppProvider()]
        for provider in providers:
            with self.subTest(provider=provider.id), tempfile.TemporaryDirectory() as folder, ExitStack() as mocks:
                source = Path(folder) / "clip.wav"
                source.touch()
                options = {}
                mocks.enter_context(patch.object(provider, "availability", return_value=(True, None)))
                mocks.enter_context(patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test", "OPENAI_API_KEY": "test", "GLADIA_API_KEY": "test", "ASSEMBLYAI_API_KEY": "test", "AZURE_SPEECH_KEY": "test", "AZURE_SPEECH_REGION": "westeurope"}))
                if provider.id == "elevenlabs":
                    raw = {"words": [{"text": "hello", "end": 1}]}
                    mocks.enter_context(patch.object(provider, "_request", return_value=response(raw)))
                elif provider.id == "openai":
                    raw = {"words": [{"word": "hello", "end": 1}]}
                    mocks.enter_context(patch("requests.post", return_value=response(raw)))
                elif provider.id == "gladia":
                    raw = {"status": "done", "result": {"transcription": {"utterances": [{"words": [{"word": "hello", "end": 1}]}]}}}
                    mocks.enter_context(patch("requests.post", side_effect=[response({"audio_url": "https://audio.example"}), response({"result_url": "https://api.gladia.io/result"})]))
                    mocks.enter_context(patch("requests.get", return_value=response(raw)))
                elif provider.id == "assemblyai":
                    raw = {"status": "completed", "words": [{"text": "hello", "end": 1000}]}
                    mocks.enter_context(patch("requests.post", side_effect=[response({"upload_url": "https://audio.example"}), response({"id": "test"})]))
                    mocks.enter_context(patch("requests.get", return_value=response(raw)))
                elif provider.id == "azure_speech":
                    raw = {"phrases": [{"words": [{"text": "hello", "durationMilliseconds": 1000}]}]}
                    mocks.enter_context(patch("requests.post", return_value=response(raw)))
                elif provider.id == "mlx_whisper":
                    raw = {"segments": [{"words": [{"word": "hello", "end": 1}]}]}
                    mocks.enter_context(patch.dict(sys.modules, {"mlx_whisper": SimpleNamespace(transcribe=lambda *args, **kwargs: raw)}))
                elif provider.id == "faster_whisper":
                    word = SimpleNamespace(word="hello", start=None, end=1, probability=1)
                    segment = SimpleNamespace(text="hello", start=0, end=1, words=[word])
                    model = SimpleNamespace(transcribe=lambda *args, **kwargs: ([segment], SimpleNamespace(language="en", duration=1)))
                    mocks.enter_context(patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=lambda *args, **kwargs: model)}))
                    mocks.enter_context(patch("providers.faster_whisper_local._MODEL_CACHE", {}))
                    raw = {"model": "large-v3", "computeType": "int8", "language": "en", "duration": 1, "segments": [{"text": "hello", "start": 0, "end": 1}], "words": [{"text": "hello", "start": None, "end": 1, "confidence": 1}]}
                else:
                    raw = {"transcription": [{"text": " hello", "offsets": {"to": 1000}}]}
                    model = Path(folder) / "ggml-model.bin"
                    model.touch()
                    options = {"model": str(model)}
                    def encode(command, **kwargs):
                        Path(command[command.index("-of") + 1] + ".json").write_text(json.dumps(raw))
                        return SimpleNamespace(returncode=0, stderr="", stdout="")
                    mocks.enter_context(patch("providers.whisper_cpp.find_whisper_cpp_binary", return_value="whisper-cli"))
                    mocks.enter_context(patch("providers.whisper_cpp.subprocess.run", side_effect=encode))
                mocks.enter_context(patch.object(service, "get_provider", return_value=provider))
                mocks.enter_context(patch.object(service, "extract_audio", return_value=str(source)))
                mocks.enter_context(patch.object(service, "wav_duration", return_value=1))
                mocks.enter_context(patch.object(service, "EXPORTS_DIR", folder))
                with self.assertRaises(HTTPException) as error:
                    service.transcribe(service.TranscribeRequest(mediaPath=str(source), language="en", providerOptions=options))
                self.assertEqual(error.exception.status_code, 400)
                raw_paths = list(Path(folder).glob("runs/*/raw_*.json"))
                self.assertEqual(len(raw_paths), 1)
                self.assertEqual(json.loads(raw_paths[0].read_text()), raw)
                self.assertEqual(list(Path(folder).glob("runs/*/normalized.json")), [])
                self.assertFalse(service._transcription_lock.locked())


if __name__ == "__main__":
    unittest.main()
