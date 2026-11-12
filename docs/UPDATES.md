# Updating CapForge

For users: open **Setup → Check for updates**. If an update is available, click
**Update**. CapForge downloads and verifies it, then opens Setup automatically.
Save your project, close After Effects, and click Install. Reopen After Effects
after setup. Your keys, exports and saved looks remain in place.

First setup and update downloads need internet. The app does not require users
to visit GitHub, install Python, manage dependencies, or use a terminal. Existing
copies older than v0.3.2 need this installer once to gain the update controls.

## Publishing changes

The workflow in `.github/workflows/release.yml` runs for pushes to `kml` and
manual runs. A local commit reaches users after it is pushed and all checks pass.
The workflow tests Windows and Intel Mac, builds the native Windows launcher,
then extracts and installs that exact ZIP on Apple Silicon Mac before publishing.
An older run cannot supersede a newer commit on `kml`.

Each release uses `build-<full commit SHA>`, so a commit can be offered as an
update even when the public version number stays unchanged. The updater reads
only this project's public GitHub Releases feed. No GitHub account is needed
for users. The workflow must first be pushed to GitHub; local tests do not create
a live update feed or publish a release.

The release includes `CapForge-<version>.zip`, its `.sha256` checksum,
`release.json`, and an internal file manifest. Downloads and redirects are
restricted to GitHub's release hosts. Before opening Setup, the app checks the
ZIP checksum, every file hash, release identity, path safety and size limits.
Interrupted or invalid downloads leave the installed code alone.

Installation uses the existing owned-directory deployment and backup mechanism.
It refuses unrelated destinations and stops only its authenticated idle local
service. It never terminates a process by name or PID. Close an older service
window once if it predates the graceful update support.

## Maintainer checks

Run `python scripts/check_release.py --package` with the test dependencies
installed. To inspect an existing archive, add `--archive dist/CapForge-0.3.2.zip`.
The Windows release job builds `CapForge Setup.exe`; locally built Mac packages
include the working `Install Windows.cmd` fallback.

To update dependency pins deliberately:

```sh
uv pip compile backend/requirements.txt --universal --python-version 3.12 --output-file backend/requirements-lock.txt --upgrade
```

Run the checks against the new lock before pushing. Core API providers are
included; Google and local Whisper adapters retain their documented optional
SDK/model setup. Provider accounts and API credit remain the user's choice.

The distribution is unsigned. Apple/Adobe signing and real AE playback across
the supported version range are separate from automated code/install checks.
