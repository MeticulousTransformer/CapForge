"""Offline regressions for provider output and the transcription API boundary."""
import os
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as service
from fastapi import HTTPException
from providers.base import ProviderError, ProviderResult
from providers.elevenlabs_scribe import ElevenLabsScribeProvider
from providers.openai_asr import OpenAIASRProvider
from providers.gladia import GladiaProvider
from providers.assemblyai import AssemblyAIProvider
from providers.azure_speech import AzureSpeechProvider
from providers.whisper_cpp import WhisperCppProvider
from services.models import Word, build_document
from services.normalize import normalize_elevenlabs, words_from_simple, words_from_tokens
from requests.exceptions import ConnectionError, Timeout


class TestProviderTiming(unittest.TestCase):
    def test_missing_word_timestamps_are_rejected_instead_of_becoming_zero(self):
        for normalize, raw in [
            (words_from_simple, [{"text": "გამარჯობა", "end": 1}]),
            (words_from_tokens, [{"text": "გამარჯობა", "end": 1}]),
            (normalize_elevenlabs, {"words": [{"text": "გამარჯობა", "end": 1}]}),
        ]:
            with self.subTest(normalize=normalize.__name__), self.assertRaisesRegex(ValueError, "tim"):
                normalize(raw)

    def test_invalid_word_times_are_rejected_without_repairing_real_timing(self):
        for start, end in [(0, 0), (-1, 1), (2, 1), (float("nan"), 1), (0, float("inf")), (False, 1), (None, 1)]:
            for normalize in (words_from_simple, words_from_tokens):
                with self.subTest(start=start, end=end, normalize=normalize.__name__), self.assertRaises(ValueError):
                    normalize([{"text": "hello", "start": start, "end": end}])

    def test_zero_confidence_stays_zero(self):
        words = words_from_tokens([{"text": "maybe", "start": 0, "end": 1, "confidence": 0}])
        self.assertEqual(words[0].confidence, 0)

    def test_document_duration_covers_every_word_even_if_provider_duration_is_short(self):
        word = Word(4, "ხარ", 0.5, 1.2345)
        doc = build_document("clip.wav", "ka-GE", "test", 1, [word], [])
        self.assertGreaterEqual(doc["duration"], word.end)
        self.assertEqual(doc["words"][0], word.to_dict())


class TestElevenLabsRequests(unittest.TestCase):
    def test_http_failures_do_not_repeat_upload_or_silently_change_models(self):
        for status in (400, 401, 403, 429, 500):
            provider = ElevenLabsScribeProvider()
            response = SimpleNamespace(ok=False, status_code=status, text="test failure")
            with self.subTest(status=status), patch.object(provider, "require_key", return_value="test-key"), patch.object(provider, "_request", return_value=response) as request:
                with self.assertRaises(ProviderError):
                    provider.transcribe("unused.wav", "ka-GE", {"model": "scribe_v2", "keyterms": ["თბილისი"]})
                self.assertEqual(request.call_count, 1)
                self.assertEqual(request.call_args.args[2]["model_id"], "scribe_v2")

    def test_http_auth_errors_explain_setup_without_echoing_provider_response(self):
        response = SimpleNamespace(ok=False, status_code=401, text='{"error":"invalid key: private-test-key"}')
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "clip.wav"
            audio.touch()
            for provider in (ElevenLabsScribeProvider(), OpenAIASRProvider(), GladiaProvider(), AssemblyAIProvider(), AzureSpeechProvider()):
                with self.subTest(provider=provider.id), patch.dict(os.environ, {provider.api_key_env: "private-test-key", "AZURE_SPEECH_REGION": "westeurope"}), patch("requests.post", return_value=response):
                    with self.assertRaises(ProviderError) as error:
                        provider.transcribe(str(audio), "ka-GE", {})
                    self.assertNotIn("private-test-key", str(error.exception))
                    self.assertIn("Setup", str(error.exception))


class TestWhisperOutput(unittest.TestCase):
    def test_success_reads_its_own_output_and_removes_only_its_temporary_directory(self):
        output_paths = []
        def write_output(command, **kwargs):
            output = Path(command[command.index("-of") + 1] + ".json")
            output_paths.append(output)
            output.write_text('{"transcription":[{"text":" გამარჯობა", "offsets":{"from":125,"to":900}}]}', encoding="utf-8")
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / "ggml-test.bin"
            model.touch()
            with patch("providers.whisper_cpp.find_whisper_cpp_binary", return_value="whisper-cli"), patch("providers.whisper_cpp.subprocess.run", side_effect=write_output):
                for _ in range(2):
                    result = WhisperCppProvider().transcribe("unused.wav", "ka-GE", {"model": str(model)})
                    self.assertEqual((result.words[0].text, result.words[0].start, result.words[0].end), ("გამარჯობა", 0.125, 0.9))
            self.assertNotEqual(output_paths[0], output_paths[1])
            self.assertTrue(all(not path.parent.exists() for path in output_paths))
            self.assertTrue(model.exists())

    def test_old_output_is_never_returned_when_next_run_writes_no_json(self):
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / "ggml-test.bin"
            model.touch()
            stale = Path(folder) / "kcf_whisper_out.json"
            stale.write_text('{"transcription":[{"text":" old", "offsets":{"from":0,"to":1000}}]}')
            provider = WhisperCppProvider()
            with patch("providers.whisper_cpp.find_whisper_cpp_binary", return_value="whisper-cli"), patch("providers.whisper_cpp.tempfile.gettempdir", return_value=folder), patch("providers.whisper_cpp.subprocess.run", return_value=SimpleNamespace(returncode=0, stderr="", stdout="")):
                with self.assertRaisesRegex(ProviderError, "output|JSON|json"):
                    provider.transcribe("unused.wav", "ka-GE", {"model": str(model)})
            self.assertTrue(stale.exists(), "Unrelated prior output must not be deleted.")


class TestTranscriptionBoundary(unittest.TestCase):
    def test_valid_transcription_preserves_word_ids_text_and_precise_timing(self):
        words = [Word(7, "გამარჯობა", 0.123456, 0.7), Word(9, "ხარ", 0.8, 1.234567)]
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "clip.wav"
            source.touch()
            provider = Mock(id="test", label="Test provider")
            provider.availability.return_value = (True, None)
            provider.transcribe.return_value = ProviderResult(raw={"test": True}, words=words, duration=1)
            with patch.object(service, "get_provider", return_value=provider), patch.object(service, "extract_audio", return_value=str(source)), patch.object(service, "EXPORTS_DIR", folder):
                result = service.transcribe(service.TranscribeRequest(mediaPath=str(source)))
            self.assertEqual(result["document"]["words"], [word.to_dict() for word in words])
            self.assertEqual(result["document"]["captions"][0]["wordIds"], [7, 9])
            self.assertEqual(result["document"]["duration"], 1.234567)
            self.assertEqual(json.loads(Path(result["debugPaths"]["normalizedJson"]).read_text()), result["document"])

    def test_stop_started_after_middleware_check_still_blocks_work(self):
        with patch.object(service, "_service_stopping", True), patch.object(service, "_transcribe") as transcribe:
            with self.assertRaises(HTTPException) as error:
                service.transcribe(service.TranscribeRequest(mediaPath="unused.wav"))
            self.assertEqual(error.exception.status_code, 503)
            transcribe.assert_not_called()

    def test_stopping_cannot_interrupt_audio_extraction(self):
        from fastapi import BackgroundTasks
        def during_extraction(*args):
            with self.assertRaises(HTTPException) as error:
                service.stop_service(BackgroundTasks())
            self.assertEqual(error.exception.status_code, 409)
            return "prepared.wav"
        with patch.object(service, "extract_audio", side_effect=during_extraction), patch.object(service, "wav_duration", return_value=1), patch.object(service, "_shutdown_server", lambda: None), patch.object(service, "_service_stopping", False):
            self.assertEqual(service.extract(service.ExtractRequest(mediaPath="clip.wav"))["duration"], 1)

    def test_provider_network_failures_offer_an_editor_action_without_exception_text(self):
        for failure in (ConnectionError("secret-provider-detail"), Timeout("secret-provider-detail")):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / "clip.wav"
                source.touch()
                provider = Mock(id="test", label="Test provider")
                provider.availability.return_value = (True, None)
                provider.transcribe.side_effect = failure
                with patch.object(service, "get_provider", return_value=provider), patch.object(service, "extract_audio", return_value=str(source)):
                    with self.assertRaises(HTTPException) as error:
                        service.transcribe(service.TranscribeRequest(mediaPath=str(source)))
                    self.assertEqual(error.exception.status_code, 400)
                    self.assertNotIn("secret-provider-detail", error.exception.detail)
                    self.assertRegex(error.exception.detail.lower(), "connection|timed out")

    def test_provider_timeline_is_rejected_before_saving_normalized_document(self):
        for words in ([Word(0, "bad", 1, 0)], [Word(0, "bad", 0, float("nan"))], [Word(0, "a", 1, 2), Word(1, "b", 0, 1)]):
            with self.subTest(words=words), tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / "clip.wav"
                source.touch()
                provider = Mock(id="test", label="Test provider")
                provider.availability.return_value = (True, None)
                provider.transcribe.return_value = ProviderResult(raw={"test": True}, words=words, duration=2)
                with patch.object(service, "get_provider", return_value=provider), patch.object(service, "extract_audio", return_value=str(source)), patch.object(service, "EXPORTS_DIR", folder):
                    with self.assertRaises(HTTPException) as error:
                        service.transcribe(service.TranscribeRequest(mediaPath=str(source)))
                    self.assertEqual(error.exception.status_code, 400)
                    self.assertIn("tim", error.exception.detail.lower())
                self.assertEqual(len(list(Path(folder).glob("runs/*/raw_test.json"))), 1)
                self.assertEqual(list(Path(folder).glob("runs/*/normalized.json")), [])
                self.assertFalse(service._transcription_lock.locked())


if __name__ == "__main__":
    unittest.main()
