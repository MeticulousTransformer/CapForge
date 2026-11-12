"""ffmpeg audio extraction -> 16 kHz mono WAV. Cross-platform."""
from __future__ import annotations

import os
import shutil
import subprocess
import wave
from typing import Optional

FFMPEG_CANDIDATES = [
    "/opt/homebrew/bin/ffmpeg",          # macOS Apple Silicon (Homebrew)
    "/usr/local/bin/ffmpeg",             # macOS Intel (Homebrew)
    "/usr/bin/ffmpeg",                   # Linux
    "C:\\ffmpeg\\bin\\ffmpeg.exe",       # Windows common
    "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
]


def find_ffmpeg() -> Optional[str]:
    path = shutil.which("ffmpeg")
    if path:
        return path
    for cand in FFMPEG_CANDIDATES:
        if os.path.isfile(cand):
            return cand
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        pass
    return None


def extract_audio(media_path: str, out_dir: str) -> str:
    """Extract audio track to <stem>_16k.wav (16 kHz mono PCM)."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "Audio preparation is unavailable. Run the CapForge installer again to repair the local service."
        )
    if not os.path.isfile(media_path):
        raise RuntimeError(f"Media file not found: {media_path}")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(media_path))[0]
    out_path = os.path.join(out_dir, f"{stem}_16k.wav")
    cmd = [
        ffmpeg, "-y", "-i", media_path,
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        out_path,
    ]
    # ffmpeg diagnostics include media filenames, independent of Windows' ANSI
    # code page. Undecodable log bytes must not reject a successfully made WAV.
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError:
        raise RuntimeError("Audio preparation could not start. Run the CapForge installer again to repair the audio tool.") from None
    if proc.returncode != 0 or not os.path.isfile(out_path):
        tail = (proc.stderr or "")[-800:]
        if "does not contain any stream" in tail.lower() or "matches no streams" in tail.lower():
            raise RuntimeError("This media file has no usable audio track. Choose a video with sound or an audio file.")
        raise RuntimeError("CapForge could not prepare this file's audio. Check that it plays with sound, or export a WAV file from your editor and choose that instead.")
    return out_path


def wav_duration(path: str) -> float:
    with wave.open(path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / float(rate) if rate else 0.0
