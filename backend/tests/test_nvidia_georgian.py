import json
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as service
from fastapi import HTTPException
from providers.base import ProviderError
from providers.nvidia_georgian import NVIDIA_GEORGIAN_MODELS, _align_streaming_words, _wav_sections
from services.normalize import WordTimingError
from services.provider_registry import get_provider, list_infos


def write_wav(path, pcm):
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        out.writeframes(pcm)


def hypothesis(text, words):
    return SimpleNamespace(text=text, timestamp={"word": words})


class TestNvidiaGeorgian(unittest.TestCase):
    def test_discovery_is_cheap_and_shows_both_choices_without_nemo(self):
        with patch("providers.nvidia_georgian.module_available", return_value=False), \
             patch("providers.nvidia_georgian._load_model") as load:
            infos = {p["id"]: p for p in list_infos()}
            for provider in NVIDIA_GEORGIAN_MODELS:
                self.assertIs(get_provider(provider.id), provider)
                info = infos[provider.id]
                self.assertFalse(info["available"])
                self.assertFalse(info["needsApiKey"])
                self.assertFalse(info["supportsEnglish"])
                self.assertTrue(info["supportsWordTimestamps"])
                self.assertEqual(info["supportedLanguages"], ["ka-GE"])
                self.assertEqual(info["model"], provider.checkpoint)
            load.assert_not_called()

    def test_both_checkpoints_normalize_native_seconds_and_georgian_punctuation(self):
        items = [{"word": "გამარჯობა", "start": 0, "end": 0.48},
                 {"word": "როგორ", "start": 0.56, "end": 0.72},
                 {"word": "ხარ?", "start": 0.8, "end": 0.96}]
        with tempfile.TemporaryDirectory() as folder:
            audio = str(Path(folder) / "ქართული.wav")
            write_wav(audio, bytes(32000))
            for provider in NVIDIA_GEORGIAN_MODELS:
                model = Mock()
                model.transcribe.return_value = [hypothesis("გამარჯობა როგორ ხარ?", items)]
                with self.subTest(model=provider.checkpoint), patch("providers.nvidia_georgian._load_model", return_value=model) as load, \
                     patch("providers.nvidia_georgian._align_streaming_words", return_value=items):
                    result = provider.transcribe(audio, "ka-GE", {})
                    load.assert_called_once_with(provider.checkpoint)
                    model.transcribe.assert_called_once_with(
                        [audio], batch_size=1, timestamps=True, return_hypotheses=True, num_workers=0, verbose=False,
                    )
                    self.assertEqual([(w.id, w.text, w.start, w.end) for w in result.words],
                                     [(0, "გამარჯობა", 0, 0.48), (1, "როგორ", 0.56, 0.72), (2, "ხარ", 0.8, 0.96)])
                    self.assertEqual(result.words[-1].punctuationAfter, "?")
                    self.assertEqual(result.timing_quality, "word")
                    self.assertEqual(json.loads(json.dumps(result.raw))["sections"][0]["words"], items)

    def test_streaming_aligns_the_rnnt_text_inside_the_pcm_and_restores_offline_decoder(self):
        offline, streaming = NVIDIA_GEORGIAN_MODELS
        native = [{"word": "კი", "start": 0.4, "end": 0.64}, {"word": "ეს", "start": 1.04, "end": 1.12}]
        acoustic_words = [{"word": "კი", "start": 0.08, "end": 0.32}, {"word": "ეს", "start": 0.88, "end": 1.04}]
        recognizer, aligner = Mock(), Mock()
        hyp = hypothesis("კი ეს", native)
        recognizer.transcribe.return_value = [hyp]
        evidence = SimpleNamespace(y_sequence=list(range(20)), text="a different CTC transcript")
        aligner.transcribe.return_value = [evidence]
        force_align = Mock(return_value=[hypothesis(hyp.text, acoustic_words)])
        module = SimpleNamespace(get_forced_aligned_timestamps_with_external_model=force_align)
        models = {offline.checkpoint: aligner, streaming.checkpoint: recognizer}
        with patch.dict(sys.modules, {"nemo.collections.asr.parts.utils.timestamp_utils": module}), \
             patch("providers.nvidia_georgian._load_model", side_effect=models.__getitem__), \
             patch("providers.nvidia_georgian._wav_sections", return_value=[("source.wav", 0, 1)]):
            result = streaming.transcribe("source.wav", "ka", {})
            self.assertEqual([(w.text, w.start, w.end) for w in result.words], [("კი", 0.08, 0.32), ("ეს", 0.88, 1)])
            self.assertEqual(result.raw["sections"][0]["words"], native)
            self.assertEqual(result.raw["sections"][0]["alignedWords"], acoustic_words)
            self.assertEqual(result.raw["alignmentModel"], offline.checkpoint)
            self.assertEqual(len(evidence.y_sequence), 13)  # 1 second at 80 ms per frame.
            force_align.assert_called_once_with([evidence], aligner, [hyp], batch_size=1, has_hypotheses=True, timestamp_type="word")
            switches = [call(decoder_type="ctc", verbose=False), call(decoder_type="rnnt", verbose=False)]
            self.assertEqual(aligner.change_decoding_strategy.call_args_list, switches)
            force_align.side_effect = ValueError("Unable to align")
            with self.assertRaises(WordTimingError):
                _align_streaming_words("source.wav", 1, hyp, result.raw)
            self.assertEqual(aligner.change_decoding_strategy.call_args_list, switches + switches)

    def test_english_auto_and_unlisted_models_are_rejected_before_loading(self):
        provider = NVIDIA_GEORGIAN_MODELS[0]
        with patch("providers.nvidia_georgian._load_model") as load:
            for lang, options in [("en-US", {}), ("auto", {}), ("ka", {"model": "some-user/checkpoint"})]:
                with self.subTest(lang=lang), self.assertRaises(ProviderError):
                    provider.transcribe("unused", lang, options)
            load.assert_not_called()

    def test_shared_encoder_frame_yields_valid_one_word_captions_and_preserves_raw(self):
        provider = NVIDIA_GEORGIAN_MODELS[0]
        items = [
            {"word": "ახლა", "start": 0.0, "end": 0.16},
            {"word": "კი", "start": 0.08, "end": 0.16},
            {"word": "ეს", "start": 0.08, "end": 0.16},
            {"word": "არის", "start": 0.08, "end": 0.4},
            {"word": "ტესტი.", "start": 0.48, "end": 0.8},
        ]
        with tempfile.TemporaryDirectory() as folder, patch.object(service, "EXPORTS_DIR", folder), \
             patch.object(provider, "availability", return_value=(True, None)), \
             patch("providers.nvidia_georgian._load_model") as load:
            audio = str(Path(folder) / "source.wav")
            write_wav(audio, bytes(32000))
            request = service.TranscribeRequest(mediaPath=audio, language="ka-GE", provider=provider.id,
                                                grouping={"minWords": 1, "maxWords": 1})
            load.return_value.transcribe.return_value = [hypothesis("ახლა კი ეს არის ტესტი.", items)]
            result = service.transcribe(request)
            doc = result["document"]
            self.assertEqual([c["wordIds"] for c in doc["captions"]], [[i] for i in range(5)])
            intervals = [(w["start"], w["end"]) for w in doc["words"]]
            self.assertEqual(intervals[0], (0.0, 0.08))
            for i in range(3):
                self.assertAlmostEqual(intervals[i + 1][0], 0.08 + i * 0.08 / 3)
                self.assertEqual(intervals[i][1], intervals[i + 1][0])
            self.assertEqual(intervals[3][1], 0.4)
            self.assertEqual(intervals[4], (0.48, 0.8))
            self.assertTrue(any("sub-frame boundaries were estimated" in w for w in result["warnings"]))
            raw = json.loads(Path(result["debugPaths"]["rawProviderJson"]).read_text(encoding="utf-8"))
            self.assertEqual(raw["sections"][0]["words"], items)

    def test_reversed_or_multi_frame_overlaps_keep_the_original_error(self):
        provider = NVIDIA_GEORGIAN_MODELS[0]
        with patch("providers.nvidia_georgian._wav_sections", return_value=[("sample.wav", 0, 2)]), \
             patch("providers.nvidia_georgian._load_model") as load:
            for a, b in [((0, 0.40), (0.16, 0.48)), ((0.16, 0.24), (0.08, 0.32)),
                         ((0, 0.24), (0.16, 0.20))]:
                items = [{"word": "აბა", "start": a[0], "end": a[1]}, {"word": "რა", "start": b[0], "end": b[1]}]
                load.return_value.transcribe.return_value = [hypothesis("აბა რა", items)]
                with self.subTest(times=(a, b)), self.assertRaises(WordTimingError) as error:
                    provider.transcribe("sample.wav", "ka", {})
                self.assertEqual(error.exception.raw_response["sections"][0]["words"], items)

    def test_missing_word_timing_is_preserved_for_raw_debug_export(self):
        provider = NVIDIA_GEORGIAN_MODELS[0]
        with patch("providers.nvidia_georgian._wav_sections", return_value=[("sample.wav", 0, 2)]), \
             patch("providers.nvidia_georgian._load_model") as load:
            for items in (None, [], [{"word": "გამარჯობა", "end": 1}],
                          [{"word": "გამარჯობა", "start": 0.5, "end": 0.5}],
                          [{"word": "მოკლე", "start": 0, "end": 1}]):
                load.return_value.transcribe.return_value = [hypothesis("გამარჯობა", items)]
                with self.subTest(items=items), self.assertRaises(WordTimingError) as error:
                    provider.transcribe("sample.wav", "ka", {})
                self.assertEqual(error.exception.raw_response["sections"][0]["words"], items)

    def test_long_recording_splits_in_pause_without_dropping_or_repeating_samples(self):
        rate = 16000
        speech = struct.pack("<h", 4000)
        # 21 seconds of speech, a 100 ms pause, then 8 seconds of speech.
        pcm = speech * (21 * rate) + bytes(2 * rate // 10) + speech * (8 * rate)
        provider = NVIDIA_GEORGIAN_MODELS[0]
        with tempfile.TemporaryDirectory() as folder:
            audio = str(Path(folder) / "long.wav")
            write_wav(audio, pcm)
            reconstructed = bytearray()
            offsets = []
            for path, offset, duration in _wav_sections(audio):
                with wave.open(path, "rb") as section:
                    reconstructed.extend(section.readframes(section.getnframes()))
                offsets.append((offset, duration))
            self.assertEqual(reconstructed, pcm)
            self.assertEqual(offsets, [(0, 21.05), (21.05, 8.05)])
            with patch("providers.nvidia_georgian._load_model") as load:
                load.return_value.transcribe.side_effect = [
                    [hypothesis("ჯერ", [{"word": "ჯერ", "start": 20.4, "end": 20.95}])],
                    [hypothesis("მერე", [{"word": "მერე", "start": 0.16, "end": 0.64}])],
                ]
                result = provider.transcribe(audio, "kat", {})
            self.assertEqual([w.id for w in result.words], [0, 1])
            self.assertAlmostEqual(result.words[1].start, 21.21)
            self.assertAlmostEqual(result.words[1].end, 21.69)

    def test_api_exports_normalized_words_and_keeps_raw_on_bad_timing(self):
        provider = NVIDIA_GEORGIAN_MODELS[0]
        with tempfile.TemporaryDirectory() as folder, patch.object(service, "EXPORTS_DIR", folder), \
             patch.object(provider, "availability", return_value=(True, None)), \
             patch("providers.nvidia_georgian._load_model") as load:
            audio = str(Path(folder) / "source.wav")
            write_wav(audio, bytes(32000))
            request = service.TranscribeRequest(mediaPath=audio, language="ka-GE", provider=provider.id)
            load.return_value.transcribe.return_value = [hypothesis("კი.", [{"word": "კი.", "start": 0.16, "end": 0.4}])]
            result = service.transcribe(request)
            doc = json.loads(Path(result["debugPaths"]["normalizedJson"]).read_text(encoding="utf-8"))
            self.assertEqual(doc["provider"], provider.id)
            self.assertEqual(doc["captions"][0]["text"], "კი.")
            self.assertEqual((doc["words"][0]["start"], doc["words"][0]["end"]), (0.16, 0.4))
            good_run = Path(result["debugPaths"]["rawProviderJson"]).parent
            items = [{"word": "კი."}]
            load.return_value.transcribe.return_value = [hypothesis("კი.", items)]
            with self.assertRaises(HTTPException) as error:
                service.transcribe(request)
            self.assertEqual(error.exception.status_code, 400)
            bad_run, = set((Path(folder) / "runs").iterdir()) - {good_run}
            raw = json.loads((bad_run / f"raw_{provider.id}.json").read_text(encoding="utf-8"))
            self.assertEqual(raw["sections"][0]["words"], items)
            self.assertFalse((bad_run / "normalized.json").exists())


if __name__ == "__main__":
    unittest.main()
