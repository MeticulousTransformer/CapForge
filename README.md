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
key. CapForge checks the connection automatically after you start the service. Select an AE composition before generating captions.

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
- [Fresh review: bugs, causes and programming lessons](docs/BUGS_AND_LESSONS.md)
- [Current review evidence and remaining acceptance work](docs/REVIEW_2026-11-12.md)

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

## For editors

Choose one transcription provider. Start with ElevenLabs for Georgian; review
its output on your own recording. Leave **Model** blank for the adapter default
unless you know which model you need. Switching provider clears the previous
custom model. Configured means the local settings exist, not that billing or
provider access has been tested.

Cloud transcription needs an account and may incur charges. Demo captions and
imported word-timed JSON work without a paid transcription request. Google and
local Whisper require extra setup; see [AI setup](docs/AI_SETUP.md).

**Save your words:** use **Export JSON** after editing. CapForge saves visual
settings locally, but does not yet restore an edited transcript after closing
the panel. Save your After Effects project separately.

**Align with footage:** transcription uses the whole source file. Selecting a
trimmed or moved footage layer does not apply its trim, speed or timeline offset.
Align the generated precomp with the footage and check playback.

## For developers and the original ScriptUI panel

These commands are for development; customers use the installer above.
The backend requires Python 3.10 or later. Create a virtual environment and
install `backend/requirements-lock.txt`, then run `backend/app.py`. The original
`run_backend.sh` / `run_backend.bat` launchers are also available. Linux is a
manual backend option; the AE panel requires Windows or macOS and connects to
the service on the same computer.

Run the complete checks using that environment's Python:

```sh
python scripts/check_release.py
python scripts/check_release.py --package
```

The original ScriptUI panel requires `ae/lib/` and `ae/titles/` alongside its
JSX and access to the installed backend token. In AE, enable **Allow Scripts
to Write Files and Access Network**. Prefer the guided CEP installation for
normal use. In ScriptUI, **Clear Generated** only removes caption compositions
marked by current CapForge builds; older unmarked outputs can be removed by hand.

Transcription adapters produce the shared word-timeline format. Caption styles
consume it independently. Read [the architecture](agents/ARCHITECTURE.md) before
changing either. The project uses the MIT license; see [LICENSE](LICENSE).
