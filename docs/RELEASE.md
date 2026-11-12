# CapForge v0.3.3 distribution

v0.3.3 introduces separate native downloads for editors:

| Computer | Public download | First action |
| --- | --- | --- |
| Intel or Apple Silicon Mac | `CapForge-0.3.3-macOS.dmg` | Drag CapForge.app to Applications and open it |
| Windows | `CapForge-0.3.3-Windows.exe` | Open the standalone installer |

The [download page](https://meticuloustransformer.github.io/Georgian-Kartuli-After-Effects-Transcribtion-Tool/)
links to [official GitHub release assets](https://github.com/MeticulousTransformer/Georgian-Kartuli-After-Effects-Transcribtion-Tool/releases/latest).
Editor instructions are in [Install on Mac](INSTALL_MAC.md),
[Install on Windows](INSTALL_WINDOWS.md), and [Your first captions](QUICK_START.md).
The version described here is published only after the release workflow succeeds;
local implementation and tests are not publication evidence.

The Mac app contains a universal native executable and its setup resources. The
Windows EXE embeds the verified setup payload and extracts it automatically.
First setup downloads a private runtime and transcription dependencies. It does
not require users to install Python, FFmpeg, or certificates, or alter PATH.

## Build and publish

Run `python scripts/check_release.py`, then create the allowlisted shared payload
with `python scripts/package_release.py --source-only`. Build the public downloads
with `scripts/build_macos.py` and `scripts/build_windows.py` on their respective
platforms. See [Updating CapForge](UPDATES.md) for commands.

The allowlist excludes `.env`, tokens, exports, models, `.venv`, Git history,
and local build artifacts. The payload includes the caption engine, panel,
backend, offline design demo, installer resources, fixtures, and documentation.
Each package records its version and source commit. Runtime updates preserve
keys, exports, saved looks, and owned installation locations.

Pushing to `kml` starts `.github/workflows/release.yml`. Both native builds use
the same source commit and version. Publishing requires packaged installation
checks on Windows, Apple Silicon Mac, and Intel Mac. Both public downloads are
published together after those gates pass. An older workflow cannot supersede
a newer `kml` commit. Check the workflow and release itself to establish that a
particular build passed; `VALIDATION.md` records separate historical evidence.

The release also contains OS-specific update ZIPs and SHA-256 companions. A
shared `CapForge-0.3.3.zip` exists only for migration from the v0.3.2 updater.
The download page directs new users to the DMG or EXE.

## Preview signing and remaining acceptance

This preview has no Apple Developer ID or Windows publisher certificate. The
Mac app uses an ad-hoc signature and is **not Apple notarized**. Windows may show
an unknown-publisher warning. Native packaging does not remove those warnings.
The editor guides explain the OS-specific prompts without installing certificates
or disabling protection globally.

The Adobe panel is also unsigned. Setup exposes an explicit unsigned-extension
option; enabling it permits all unsigned Adobe panels for that user. A production
Adobe-signed package should not depend on that preview option.

Before describing this as a commercial, fully validated release:

- Test the downloaded artifacts on clean systems, including first-launch trust
  prompts, failed downloads, retry, update, and repair. CI installation checks do
  not reproduce every desktop security prompt.
- Verify real AE installation, restart, and playback for every supported AE
  version. The CEP manifest range alone does not prove compatibility.
- Validate Georgian transcription and word timing on a 10–20 second clip,
  including styles, portraits, multiline captions, and font weights. Record actual
  demonstrations and screenshots; do not substitute mockups as test evidence.
- Arrange Apple signing/notarization, Windows publisher signing, and Adobe
  signing for a signed release, and verify the final downloaded artifacts again.
- Document shipped dependencies and licenses. The bootstrap uses pinned,
  SHA-256-verified uv archives and private Python; audio support comes from
  `imageio-ffmpeg`.
- Publish accurate provider and AE compatibility information, cloud-audio handling,
  and a support route. Provider accounts and paid transcription remain separate
  from installation. The existing MIT license remains.

Technical references: [Adobe CEP resources](https://github.com/Adobe-CEP/CEP-Resources)
and [Adobe CEP 12 cookbook](https://github.com/Adobe-CEP/CEP-Resources/blob/master/CEP%2012%20HTML%20Extension%20Cookbook.md).
