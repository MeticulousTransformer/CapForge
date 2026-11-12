import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services import audio_extract


class TestBundledAudio(unittest.TestCase):
    def test_bundled_binary_is_used_when_ffmpeg_is_not_on_path(self):
        bundled=SimpleNamespace(get_ffmpeg_exe=lambda: "/private/capforge/ffmpeg")
        with patch.object(audio_extract.shutil,"which",return_value=None), patch.object(audio_extract,"FFMPEG_CANDIDATES",[]), patch.dict(sys.modules,{"imageio_ffmpeg":bundled}):
            self.assertEqual(audio_extract.find_ffmpeg(),"/private/capforge/ffmpeg")

    def test_missing_binary_offers_installer_repair(self):
        with patch.object(audio_extract.shutil,"which",return_value=None), patch.object(audio_extract,"FFMPEG_CANDIDATES",[]), patch.dict(sys.modules,{"imageio_ffmpeg":None}):
            self.assertIsNone(audio_extract.find_ffmpeg())
            with self.assertRaisesRegex(RuntimeError,"CapForge installer"):
                audio_extract.extract_audio("missing.mp4","exports")

    def test_audio_preparation_survives_georgian_logs_on_windows_code_pages(self):
        # The external encoder can emit UTF-8 filenames and non-UTF-8 diagnostic
        # bytes. Emulate that child output with Python, keeping real pipe decoding.
        run = subprocess.run
        def encoder(command, **kwargs):
            script = "import sys, wave; w = wave.open(sys.argv[1], 'wb'); w.setparams((1, 2, 16000, 0, 'NONE', 'not compressed')); w.writeframes(b'\\0' * 16000); w.close(); sys.stderr.buffer.write('ქართული'.encode('utf-8') + b'\\xff')"
            return run([sys.executable, "-c", script, command[-1]], **kwargs)

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "ქართული.mp4"
            source.touch()
            with patch.object(audio_extract, "find_ffmpeg", return_value="ffmpeg"), patch.object(audio_extract.subprocess, "run", side_effect=encoder), patch.object(subprocess, "_text_encoding", return_value="cp1252"):
                result = audio_extract.extract_audio(str(source), folder)
            self.assertEqual(Path(result).name, "ქართული_16k.wav")
            self.assertEqual(audio_extract.wav_duration(result), 0.5)
