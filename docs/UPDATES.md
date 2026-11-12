# Updating CapForge

Open **Setup → Check for updates** in the AE panel. When an update is offered,
click **Update**. CapForge downloads and verifies the package for your operating
system, then opens Setup. Save your project, close After Effects, and click
**Update / Repair** on Mac or **Install CapForge** on Windows. Reopen After Effects
after setup finishes. Your keys, exports and saved looks remain in place.

Update downloads need internet. You do not need to find a ZIP, install Python,
manage dependencies, or use a terminal. For a first installation or manual repair,
use the [Mac DMG](INSTALL_MAC.md) or [Windows EXE](INSTALL_WINDOWS.md) from the
[download page](https://meticuloustransformer.github.io/CapForge/)
or [latest official release](https://github.com/MeticulousTransformer/CapForge/releases/latest).
Saved installers do not fetch a newer application release by themselves. The Mac
app repairs the installed files when that release is newer than its bundled
version, preserving the newer installation. The Windows EXE reinstalls its bundled
version, so download the latest EXE before a manual update.

## Copies downloaded before the GitHub rename

The repository is now **MeticulousTransformer/CapForge**. If you installed a
build downloaded before this rename, download the current DMG or EXE once from
the links above and run Setup. The earlier updater checks the old repository
address exactly and cannot accept the renamed release assets. Your keys and
exports are preserved. After this installation, in-app updates use the new address.

## Moving from v0.3.2

Use the manual update above if your installed copy still uses the old GitHub
address. The release retains `CapForge-0.3.3.zip` and its checksum for compatibility
with the older installer entry point.
On Mac, that migration package hands the old Python entry point to the bundled
native app. On Windows, the earlier guided installer handles this one update.
Afterward, CapForge selects the OS-specific update package automatically.
Installations older than the update controls can use the latest DMG or EXE once.
An older local service may need its window closed once before updating.

## Verified packages

Native updates use `CapForge-<version>-macOS.zip` or
`CapForge-<version>-Windows.zip`, with a `.sha256` companion. These are internal
update assets; editors normally download the public DMG or EXE instead.

The updater selects only the current operating system's asset. Shared ZIP
fallback is limited to releases before v0.3.3. It checks the archive checksum,
every file hash, release version and tag, platform identity, required native
installer, path safety, and size limits before opening Setup. Downloads and
redirects stay on the allowlisted GitHub release hosts. Invalid or interrupted
downloads leave the installed code alone.

Native Setup can prepare or repair its own private runtime. It receives the
existing runtime and Adobe extension locations from the updater. Installation
uses owned destinations, backups, and rollback, and stops only its authenticated
idle local service. It never terminates a process by name or PID.

## Publishing changes

`.github/workflows/release.yml` runs for pushes to `kml` and manual runs. Both
platforms are built from the same commit SHA and version. The release gate requires
code checks and installation of the packaged EXE on Windows and the packaged app
from the DMG on both Apple Silicon and Intel Mac. Only then can the workflow
publish both public downloads and update assets together. A newer `kml` commit
prevents an older build from becoming the latest release.

Each release tag is `build-<full commit SHA>`, so a new commit can be offered even
when the public version remains unchanged. The updater reads this project's
public GitHub Releases feed; users do not need a GitHub account. Local builds and
passing local tests do not publish a release or prove that the three-platform
gate has passed. Check the actual workflow run and published assets for that.

## Maintainer checks

Run the component checks and create the shared source payload:

```sh
python scripts/check_release.py
python scripts/package_release.py --source-only
```

Build the native download on its platform:

```sh
# On Mac
python scripts/build_macos.py --archive dist/CapForge-0.3.3.zip

# On Windows
python scripts/build_windows.py --archive dist/CapForge-0.3.3.zip
```

The workflow uses `scripts/package_update.py` to wrap the same payload and native
installer into the verified OS update ZIP. `scripts/check_native_install.py`
exercises packaged installation into a fresh destination. For the complete
publication order, follow the workflow rather than uploading a single platform
early.

To update dependency pins deliberately:

```sh
uv pip compile backend/requirements.txt --universal --python-version 3.12 --output-file backend/requirements-lock.txt --upgrade
```

Run the checks against the new lock before pushing. Core API providers are
included; Google and local Whisper adapters retain their documented optional
SDK/model setup. Provider accounts and API credit remain the user's choice.

This preview is not Apple notarized, Windows publisher-signed, or Adobe-signed.
OS trust warnings and real AE playback acceptance are separate from automated
package and installation checks.
