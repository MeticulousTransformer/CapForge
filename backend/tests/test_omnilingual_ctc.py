import hashlib
import importlib.util
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from providers import omnilingual_ctc as omni
from providers.base import ProviderError
from services.provider_registry import get_provider


def wav(path, samples, rate=16000):
    with wave.open(str(path), "wb") as source:
        source.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        source.writeframes(samples)


class TestOmnilingualCTC(unittest.TestCase):
    def setUp(self):
        self.provider = get_provider("omnilingual_ctc_1b")

    def test_discovery_and_selections_do_not_download(self):
        with patch.object(omni, "_load_model") as load, patch.object(omni, "module_available", return_value=False):
            info = self.provider.info()
            self.assertFalse(info["available"])
            self.assertFalse(info["needsApiKey"])
            self.assertEqual(info["supportedLanguages"], ["ka-GE", "en-US", "auto"])
            self.assertEqual(info["languageMode"], "auto")
            self.assertTrue(info["supportsWordTimestamps"])
            for language, options in [("fr", {}), ("ka-GE", {"model": "other/repo"})]:
                with self.assertRaises(ProviderError):
                    self.provider.transcribe("unused", language, options)
            load.assert_not_called()

    def test_verifies_checksum_for_exact_hub_revision(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tokens.txt"
            path.write_bytes(b"test")
            download = Mock(return_value=str(path))
            self.assertEqual(omni._verified_file(download, path.name, hashlib.sha256(b"test").hexdigest()), path)
            download.assert_called_once_with(repo_id=omni.MODEL_ID, filename=path.name, revision=omni.REVISION)
            path.write_bytes(b"changed")
            with self.assertRaisesRegex(ProviderError, "checksum"):
                omni._verified_file(download, path.name, hashlib.sha256(b"test").hexdigest())

    def test_caption_words_keep_emission_ends_before_silence_and_unicode(self):
        tokens = {4: " ", 5: "ა", 6: "რ", 7: "!"}
        emissions = [
            {"id": idx, "startFrame": start, "endFrame": end, "confidence": 0.8}
            for idx, start, end in [(5, 5, 7), (6, 8, 9), (4, 45, 46), (5, 46, 47), (7, 47, 48)]
        ]
        with tempfile.TemporaryDirectory() as folder, patch.object(omni, "_load_model", return_value=(None, tokens)), \
                patch.object(omni, "_emissions", return_value=emissions):
            path = Path(folder) / "sample.wav"
            wav(path, bytes(32000))
            for language in ("ka-GE", "en-US", "auto"):
                with self.subTest(language=language):
                    result = self.provider.transcribe(str(path), language, {})
                    self.assertEqual([(w.id, w.text, w.start, w.end, w.punctuationAfter) for w in result.words],
                                     [(0, "არ", 0.1, 0.18, ""), (1, "ა", 0.92, 0.96, "!")])
                    self.assertEqual(result.raw["emissions"], emissions)
                    self.assertEqual(result.duration, 1.0)

    def test_silence_and_malformed_wav(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(omni, "_load_model", return_value=(None, {})), \
                patch.object(omni, "_emissions", return_value=[]):
            path = Path(folder) / "sample.wav"
            wav(path, bytes(32000))
            with self.assertRaisesRegex(ProviderError, "no speech words"):
                self.provider.transcribe(str(path), "auto", {})
            wav(path, bytes(16000), rate=8000)
            with self.assertRaisesRegex(ProviderError, "16 kHz"):
                self.provider.transcribe(str(path), "auto", {})

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "requires optional NumPy")
    def test_global_ctc_collapse_across_overlapping_audio_windows(self):
        import numpy as np

        # Each simulated acoustic frame's input samples encode its winning logit.
        def infer(outputs, inputs):
            self.assertEqual(outputs, ["logits"])
            ids = (inputs["x"][0][::320] * 32768).astype(int)
            logits = np.zeros((1, len(ids), 8), dtype=np.float32)
            logits[0, np.arange(len(ids)), ids] = 10.0
            return [logits]

        session = Mock()
        session.run.side_effect = infer
        tokens = {4: " ", 5: "ა", 6: "ბ"}
        pcm = b"".join(struct.pack("<h", token) * 320 for token in [0, 5, 5, 5, 5, 0, 5, 4, 6, 6])
        with tempfile.TemporaryDirectory() as folder, patch.object(omni, "_load_model", return_value=(session, tokens)), \
                patch.object(omni, "CORE_SAMPLES", 4 * 320), patch.object(omni, "CONTEXT_SAMPLES", 2 * 320):
            path = Path(folder) / "sample.wav"
            wav(path, pcm)
            result = self.provider.transcribe(str(path), "ka", {})
        self.assertEqual([(w.text, w.start, w.end) for w in result.words], [("აა", 0.02, 0.14), ("ბ", 0.16, 0.20)])
        self.assertEqual([(r["id"], r["startFrame"], r["endFrame"]) for r in result.raw["emissions"]],
                         [(5, 1, 5), (5, 6, 7), (4, 7, 8), (6, 8, 10)])
        self.assertEqual(session.run.call_count, 3)
        self.assertTrue(all(0.99 < w.confidence <= 1.0 for w in result.words))
