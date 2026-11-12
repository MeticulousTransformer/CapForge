"""Local smoke check: installed dependencies and audio extraction, no AE or cloud calls."""
from pathlib import Path
import sys
import tempfile
import wave
from unittest.mock import patch

runtime = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(runtime / "backend"))
import fastapi, uvicorn, pydantic, requests, imageio_ffmpeg
from services.audio_extract import extract_audio
from services.updates import _owned

owned_root, _ = _owned(runtime)
assert owned_root.samefile(runtime), "The updater should recognize this installation."
private_runtime = runtime / ".runtime"
assert not private_runtime.is_symlink(), "The private runtime must belong to this installation."
base_python = Path(sys._base_executable).resolve()
assert any(parent.samefile(private_runtime) for parent in base_python.parents), "Python should come from the private installation."

# Force the bundled binary for this check, even on a developer machine that
# also has Homebrew/system ffmpeg. The real extraction still runs end to end.
binary = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
assert any(parent.samefile(runtime) for parent in binary.parents), "Audio binary should come from the private installation."
with tempfile.TemporaryDirectory(prefix="audio-check-", dir=runtime) as folder:
    source = Path(folder) / "sample.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(44100)
        audio.writeframes(b"\0" * (11025 * 2 * 2))
    with patch("services.audio_extract.find_ffmpeg", return_value=str(binary)):
        result = extract_audio(str(source), str(Path(folder) / "output"))
    with wave.open(result, "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getframerate() == 16000
        assert audio.getnframes() > 0
print("Installed update ownership, private Python, service imports and bundled audio extraction passed (16 kHz mono WAV).")
