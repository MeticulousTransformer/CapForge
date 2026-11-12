# CapForge installation

Open **CapForge Setup.exe** or **Install macOS.command** from the extracted
package. Setup prepares everything needed for transcription and audio. Users do
not need to install Python, ffmpeg, Homebrew, or edit PATH.
`Install Windows.cmd` is included as a fallback. The native Windows entry is a
small .NET launcher, built from `installer/Launcher.cs`, and opens the loading
window without a terminal. Keep it with the other extracted package files.

On Windows, a native loading window shows progress before Python exists. Work
runs in a background worker so the window stays responsive. The setup wizard
then offers a compact Install button in a fixed-size window with a separate
Close button. Colors and dimensions live in `installer/theme.py`; the native
loading window uses the matching palette in `bootstrap_windows.ps1`.
On macOS, the `.command` launcher prepares the
runtime using built-in tools and opens the same wizard.

After installation, open the panel’s Setup tab for account links, plain-language
instructions and your own API key fields. See [AI setup](AI_SETUP.md).

**v0.3.1 repair:** the panel locates its engine using Adobe’s extension path,
rather than the last script filename in AE. If updating while AE is open, save
your project and restart AE to load the updated bridge. Starting an already
running authenticated service reconnects; another app using its port gets a
connection message and is not stopped automatically.

First setup needs internet. Runtime tools are pinned in
`installer/runtime_assets.json` and archives are checked against SHA-256 hashes
before extraction. Everything is kept in the app's `.runtime/` folder. uv is
invoked with `--no-bin --no-registry --managed-python --no-config`; no global
Python registration or PATH configuration is performed.

The transcription service gets its own virtual environment. Its pinned requirements
live in `backend/requirements-lock.txt`, including transitive dependencies, so
fresh installations use the versions checked for this release. Its requirements
include `imageio-ffmpeg`, whose platform wheels include an audio-processing
binary. A manually installed ffmpeg is still supported, but is optional.

Existing installations are recognized by their ownership marker. The older
product folder remains in place to preserve virtual-environment paths, API keys,
tokens and exports. New installations use CapForge. Saved looks exported under
either name are accepted. Internal CEP IDs and the KCF layer prefix remain
stable for compatibility.

For repair, reopen the setup launcher in the installation folder. Downloads can
be retried. The installer never replaces unrelated nonempty destinations and
backs up existing code and the panel before replacing them.
If an earlier Python installation was removed and left a broken service
environment, setup keeps that environment in backups and builds a replacement.

**v0.3.2:** Mac launchers are executable in both the checkout and ZIP, and release
packaging enforces Unix line endings even when built on Windows. Fresh Mac setup
creates a valid ownership record before downloading. Setup failures return a
failure status, allowing retry. Updates stop only the authenticated service that
belongs to this installation; active transcription blocks replacement. The
in-app updater uses the separate private Python to open Setup, avoiding locked
service dependencies on Windows. See [updates](UPDATES.md).

The preview build still uses Adobe's unsigned-extension option. Its checkbox is
explicit in the wizard. A signed commercial installer and clean-machine Mac/AE
validation remain release work.

Implementation references: [uv managed Python](https://docs.astral.sh/uv/concepts/python-versions/),
[uv installation options](https://docs.astral.sh/uv/reference/cli/#uv-python-install),
and [imageio-ffmpeg's bundled binaries](https://github.com/imageio/imageio-ffmpeg).
