# CapForge

## Studio v0.3.2

A new dockable **CEP panel** wraps the existing caption engine in a focused
studio interface. It has a built-in animated caption screen, thirteen searchable
styles, Georgian and English demonstrations, a timed-word editor, reusable saved
looks, and guided provider setup. The canvas uses your imported or transcribed
words and their actual timestamps; final text metrics/effects render in AE.

Design preserves the original engine's full visual controls: recognizable
effect names, a draggable Slide In direction dial, dolly/easing, font families
and styles, flexible wrapping, boundary fitting, full shadows/outlines/boxes and
seeded word-style shuffle. Controls are grouped into Motion, Typography, Layout,
Finish and Style shuffle. Saved looks include every setting.

**Start here:** double-click `CapForge Setup.exe` on Windows (`Install Windows.cmd`
if the EXE is absent) or `Install macOS.command` on Mac
from the extracted package. The guided installer checks prerequisites, installs
for your user and preserves existing keys/exports when updating. The launcher
automatically prepares a private runtime; the wizard installs audio preparation
and transcription support. **No separate Python installation, PATH edits or
package manager required.** Internet is needed for first setup.

Open **Window → Extensions → CapForge** after restarting AE.
Explore the demo, or open **Setup** to start the local service and add a provider
key. Select an AE composition before generating captions.

v0.3.2 fixes the `KCF_PRESET_LABELS is undefined` error, Finder launch permissions,
fresh Mac setup, inherited All Caps formatting, and media paths containing
Georgian or special characters. Setup installs a private Python runtime and the
same pinned dependencies on each device, including bundled audio tools.

**Updates:** open **Setup → Check for updates → Update**. CapForge downloads and
verifies the official release, then opens Setup. Save your project and close AE
before clicking Install; reopen AE after setup. Saved keys, exports and looks
are preserved. See [updates and publishing](docs/UPDATES.md).

The service accepts both local origins used by Adobe CEP (`file://` and `null`),
so the installed panel can connect without the erroneous “This service only
accepts the installed CapForge panel” rejection. Private API requests still
require the installation token; web origins remain blocked.

- [First captions and troubleshooting](docs/QUICK_START.md)
- [AI accounts, API keys and optional local setup](docs/AI_SETUP.md)
- [Agent workspace and codebase map](agents/README.md)
- [Add a removable title style](agents/ADD_TITLE.md)
- [Commercial release checklist](docs/RELEASE.md)
- Browser design demo: open `panel/index.html` locally; no install or API key needed.
- Check and build a distribution: `python scripts/check_release.py --package`.
- [Checks passed and remaining validation](docs/VALIDATION.md)

**Release status:** this package is unsigned. The installer offers Adobe's
per-user unsigned-extension mode. Local validation covers Apple Silicon Mac
installation and AE 26.5 generation; the automated release workflow also requires
Windows and Intel Mac installation checks. Signing and broader AE-version
validation remain separate release work. The manifest's host range is not a
tested compatibility claim.

**Local service:** API calls now require an installation token in
`backend/.local-token` (generated on service startup). The panel reads it locally;
it is never stored in browser settings. Transcription outputs are saved separately
in `exports/runs/<run-id>/`, so later runs do not overwrite earlier transcripts.

**Original ScriptUI panel:** remains in `ae/KartuliCaptionForge.jsx`, sharing the
same renderer. Run it from the installed runtime or this checkout's `ae/` folder
so it can read its sibling `backend/.local-token`. If you copy the panel elsewhere,
set `KCF_BACKEND_ROOT` to your backend folder; moving the JSX alone no longer
provides service authorization. Include the `lib/` and `titles/` folders.

## Provider reference and original panel instructions

**Word-timed animated captions for After Effects — built for Georgian (ქართული), works for English too.**

Select a video in AE → transcribe with the AI provider of your choice → get animated
word-by-word caption layers (TikTok/CapCut style) at exact timestamps. What took hours
of manual keyframing takes minutes.

<!-- DEMO GIF: record ~20s of panel → Transcribe → Generate → playback, save as docs/demo.gif -->
<!-- ![demo](docs/demo.gif) -->

- 🎙️ **9 swappable ASR providers** — **ElevenLabs Scribe is the only one that handles
  Georgian well** (tested on real conversational audio). The others (Gladia, Azure,
  AssemblyAI, OpenAI, Google Chirp, local whisper variants) are wired in but poor or
  untested for Georgian — treat them as experimental / English-only
- ⏱️ **True word-level timestamps** — each word animates when it's spoken
- 🎨 **12 animation presets** — Highlight Word, Active Word Box (CapCut style), Slide In,
  Bounce In, Pop Karaoke, Typewriter, Brutalist Georgian, and more
- 🧭 **Slide In with a direction dial** — drag the dial to choose the angle words fly in
  from (0° = from below), with distance, duration, ease, dolly and real AE motion blur
- 📐 Full typography control: any installed font, faux bold/italic, multi-line wrapping,
  rounded background boxes, safe-area anchors for 9:16 / 1:1 / 16:9
- 🖍️ **Fill, Stroke, Background and Shadow sections** — stroke colour, weight and
  position; turn the fill off for hollow outlined captions; drop shadow with colour,
  opacity, distance, angle and softness
- 📏 **Fit to boundary** — scale every line until it spans a set width, so a one-word
  line and a four-word line read at the same size, the stretched-to-the-margins look
  used by social captions. Size is solved per line and capped; once it caps, tracking
  opens up to close the rest
- 🎲 **Style shuffle** — hand each word a different look (solid / highlight / hollow
  outline) and a different font from a set you choose, so captions read as designed,
  not uniform. Pick a single look to pin every word to it. Draws from a bag rather than
  rolling dice, so no look repeats back to back and no caption reuses the pattern of
  the previous three. Seeded, so a re-generate reproduces the same mix
- 🛡️ **Non-destructive** — everything generates into a fresh precomp; your work is never touched
- 🔍 Every intermediate JSON saved to `exports/` for debugging and hand-editing

Works on **macOS, Windows, Linux** (backend). After Effects panel: macOS + Windows
(Adobe doesn't ship AE for Linux — run the backend on Linux and AE elsewhere if needed).

License: MIT. Contributions welcome — especially new animation presets
(`ae/lib/presets.jsx`, ~10 lines each) and ASR adapters (`backend/providers/`, one file each).

---

## 1. What to download

### Required for the desktop plugin

Install After Effects, extract the full package, then open **CapForge Setup.exe**
or **Install macOS.command**. CapForge prepares its own runtime and audio tool.
The launchers support 64-bit Windows and Intel/Apple Silicon Macs (macOS 11+).
AE installation/display compatibility still needs validation before a commercial
release. Linux is supported for a manually configured backend only.
`Install Windows.cmd` is a fallback launcher if the native entry is unavailable.

For source development or a Linux backend, use Python 3.10+ and install
`backend/requirements.txt` in a virtual environment. Manual development commands
below are optional and are not part of customer installation.

### Optional — free local transcription (no API key, offline)

Pick ONE if you don't want to pay for cloud APIs:

**A. whisper.cpp** (fastest to set up on Mac)
```bash
# macOS
brew install whisper-cpp
# Windows: download release from github.com/ggml-org/whisper.cpp/releases
# Linux: build from source (cmake)
```
Then download a model into `~/models/whisper/` (create the folder):
- Best Georgian quality: [ggml-large-v3.bin](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin) (~3 GB)
- Faster: [ggml-large-v3-turbo.bin](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin) (~1.6 GB)
- If slow: [ggml-medium.bin](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin) (~1.5 GB)
- **Never** `.en` models for Georgian.
- Note: whisper.cpp word timings are marked *experimental*.

**B. faster-whisper** (real word timestamps, Python, all platforms)
```bash
./.venv/bin/pip install faster-whisper        # mac/linux
.venv\Scripts\pip install faster-whisper      # windows
```
Model (`large-v3`) downloads automatically on first run (~3 GB).

**C. mlx-whisper** (Apple Silicon Macs only, fast)
```bash
./.venv/bin/pip install mlx-whisper
```
Model downloads automatically on first run.

### Cloud providers (best Georgian quality — recommended: ElevenLabs)

Nothing to download — just API keys (next section).

---

## 2. Where to put your API keys

1. Copy `backend/config.example.env` → rename the copy to `backend/.env`
2. Paste keys after the `=` signs. **In `backend/.env` the lines are:**

| Line | Key | Where to get it |
|---|---|---|
| **8** | `ELEVENLABS_API_KEY=` | elevenlabs.io → Profile → API Keys ← **START HERE, best for Georgian** |
| **12** | `OPENAI_API_KEY=` | platform.openai.com/api-keys |
| **16** | `GOOGLE_APPLICATION_CREDENTIALS=` | path to Google service-account .json file |
| **17** | `GOOGLE_CLOUD_PROJECT=` | your GCP project id |
| **22** | `AZURE_SPEECH_KEY=` | portal.azure.com → Speech resource → Keys |
| **23** | `AZURE_SPEECH_REGION=` | e.g. `westeurope` |
| **27** | `GLADIA_API_KEY=` | app.gladia.io |
| **31** | `ASSEMBLYAI_API_KEY=` | assemblyai.com/app |

You only need ONE provider to work. Fill only what you have.

### Georgian support per provider (real-world tested)

**Short version: use ElevenLabs for Georgian. Everything else disappointed or is untested.**

| Provider | Georgian (tested on conversational audio) | Word timestamps | Cost |
|---|---|---|---|
| **ElevenLabs Scribe v2** | ✅ **excellent — the only recommended option** | ✅ real | paid API (free tier to test, ~$0.22/audio-hour after), Basically free or negligable |
| faster-whisper (local) | ❌ bad (~20-30% right, skips words) | ✅ real | free |
| mlx-whisper (local) | ❌ bad (same whisper model) | ✅ real | free |
| whisper.cpp (local) | ❌ bad + experimental timings | ⚠️ experimental | free |
| Gladia (Whisper cloud) | ⚠️ untested, whisper-based so expect similar | ✅ real | free tier |
| Azure AI Speech | ⚠️ untested for Georgian | ✅ real | free tier 5h/month |
| AssemblyAI (nano) | ⚠️ untested for Georgian | ✅ real | paid, cheap |
| OpenAI whisper-1 | ⚠️ untested, whisper-based | ✅ real | paid, cheap |
| Google Chirp 2/3 | ⚠️ untested for Georgian | ✅ (Chirp 2/3) | paid |

For **English**, the local whisper providers work fine and cost nothing.

---

## 3. Start the backend

```bash
# macOS / Linux — first run creates venv + installs deps automatically
./run_backend.sh

# Windows
run_backend.bat
```
Backend runs at `http://127.0.0.1:8765`. Leave the terminal open.

Manual alternative:
```bash
python3 -m venv .venv
./.venv/bin/pip install -r backend/requirements.txt
./.venv/bin/python backend/app.py
```
For Google Chirp also: `pip install google-cloud-speech`

---

## 4. Install the AE panel

Copy **both** `ae/KartuliCaptionForge.jsx` **and** the `ae/lib/` folder into:

- **macOS:** `/Applications/Adobe After Effects <version>/Scripts/ScriptUI Panels/`
- **Windows:** `C:\Program Files\Adobe\Adobe After Effects <version>\Scripts\ScriptUI Panels\`

Then in AE:
1. `Preferences → Scripting & Expressions → Allow Scripts to Write Files and Access Network` ✅ (required!)
2. Restart AE → `Window → KartuliCaptionForge.jsx`

---

## 5. Usage

1. Open your comp with the Georgian video.
2. Panel → **Source**: Browse media file, Language = Georgian, Provider = ElevenLabs (press **Scan** to see which providers are ready).
3. **Transcribe** — captions preview appears.
4. **Type/Position/Animate** tabs: pick font (Georgian-supporting, e.g. `NotoSansGeorgian-Bold`), colors, anchor = Bottom center, preset = Highlight Word.
5. **Generate Captions** — a new `KCF_Captions_…` precomp lands in your comp. Your existing layers are never touched.
6. Bad timestamps? Inspect `exports/normalized.json` first, edit it, then **Load JSON** → **Generate Captions**.

Georgian fonts: **Noto Sans Georgian** (free, fonts.google.com/noto), Helvetica Neue LT GEO, BPG fonts.

## Troubleshooting

- *"Backend not running"* → start `./run_backend.sh`; check port matches panel (8765).
- *"Provider unavailable: missing …"* → key missing in `backend/.env`; restart backend after editing.
- Georgian shows as boxes → font doesn't include Georgian glyphs; use Noto Sans Georgian.
- Words mistimed → check `exports/raw_<provider>.json` vs `exports/normalized.json`; try another provider.

## Tests

```bash
cd backend && python3 -m unittest discover -s tests
```
