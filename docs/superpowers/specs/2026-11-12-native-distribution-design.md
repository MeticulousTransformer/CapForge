# One CapForge, native installation on each OS

Editors should never have to select a script from a source folder. The Mac
entry is a universal native app in a DMG; Windows receives one self-contained
EXE. Both embed the same allowlisted payload, release version and commit.
The existing provider adapters, normalized timeline and AE engine stay shared.

The Mac app uses Swift/AppKit from the installed Xcode toolchain, shows setup
progress/errors itself and runs the existing deployment headlessly. The Windows
launcher embeds the source ZIP and keeps the existing native bootstrap/wizard.
First setup still downloads private runtime dependencies; neither changes PATH.
Existing credentials, exports, ownership checks and rollback remain intact.

Public downloads: `CapForge-0.3.3-macOS.dmg` and
`CapForge-0.3.3-Windows.exe`. Internal OS update ZIPs carry the native launchers,
checksums, manifest and OS identity. A legacy ZIP is retained for migration from
0.3.2; it is not the website's recommended download. The updater verifies the
current OS package before launching its native setup. Old Mac updaters entering
the new Python installer hand off to the bundled native app.

GitHub Actions builds both platforms from one commit, verifies packaged installs
on Windows, Intel Mac and Apple Silicon, then publishes one release. GitHub
Releases stores binaries; a small static GitHub Pages site introduces the tool,
provides separate download buttons and guides, and reads only published assets.

Implementation choices: no Electron, no second backend, no unrelated framework.
The site uses the existing muted violet palette, readable system typography,
a caption/timeline example and direct install steps. No signup or tracking.

No Developer ID signing identity is installed on this Mac. Ad-hoc signing can
make the universal app internally valid; it does not replace Developer ID and
notarization. Guides must state that limitation and never suggest globally
disabling Gatekeeper. Adobe unsigned CEP mode remains an explicit preview option.

Acceptance: packaged native launchers install into isolated Unicode destinations;
shared tests pass; both archive platforms validate; Mac GUI is visually checked;
website is keyboard-accessible and fits narrow screens; both platform artifacts
are published from the same SHA. Live OS trust prompts and paid ASR quality are
separate from automated installation evidence.
