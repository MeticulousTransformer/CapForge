# Small parts, clear boundaries

```text
panel/index.html                 semantic UI, no inline scripts
panel/styles/tokens.css          colors and visual identity
panel/styles/panel.css           layout, components, narrow panel rules
panel/js/catalog.js             style names, categories, descriptions
panel/js/transcript.js          demos, validation, word-only editing
panel/js/settings.js            defaults, validation, conversion to AE RGB
panel/js/design_controls.js     form values, font grouping, direction dial
panel/js/word_styles.js         generated adapter of the AE shuffle engine
panel/js/preview.js             approximate canvas rendering + motion
panel/js/bridge.js              JSON calls to the CEP host
panel/js/api.js                 authenticated loopback service requests
panel/js/updates.js             release check/status and verified Setup handoff
panel/js/provider_guide.js      editable AI setup content and trusted account URLs
panel/js/external_links.js      opens allowlisted setup URLs in the regular browser
panel/js/app.js                 connects the above, no rendering engine
panel/host.jsx                  allowlisted host actions, no dynamic user eval
panel/CSXS/manifest.xml         Adobe CEP panel metadata

ae/lib/presets.jsx              original animation presets
ae/lib/title_registry.jsx       additive registration + loading
ae/titles/*.jsx                 independently removable new titles
ae/lib/layer_builder.jsx        measured positioning + precomp generation
ae/lib/text_measure.jsx         typography, font metrics, effects
ae/KartuliCaptionForge.jsx      original ScriptUI panel

backend/app.py                  API boundary, validation, serialized transcription
backend/start_service.py        authenticated reuse of an already-running local service
backend/providers/*.py          interchangeable ASR adapters
backend/services/grouping.py    real word timings → caption groups
backend/services/studio_settings.py  local token + provider credential persistence
backend/services/transcript_validation.py  imported timeline validation
backend/services/updates.py     official release download, verification, Setup launch

installer/environment.py        prerequisite checks + platform paths
installer/theme.py              installer colors and fixed window dimensions
installer/runtime_assets.json   pinned uv archives and SHA-256 checksums
installer/runtime_windows.ps1   private runtime download and path validation
installer/bootstrap_windows.ps1 native loading UI before Python exists
installer/bootstrap_macos.sh    private runtime bootstrap using macOS tools
installer/deployment.py         owned installation, backups, rollback
installer/service_control.py    authenticated idle service shutdown before updates
installer/install.py            native wizard + command-line entry
scripts/package_release.py      explicit release file allowlist
scripts/check_release.py        complete tests, version and archive checks
.github/workflows/release.yml   tested kml pushes become in-app updates
```

The modern panel uses **CEP**, because ScriptUI cannot host a modern animated
canvas. The original ScriptUI panel remains in the runtime and shares the same
renderer and new title registry. Nothing routes transcription through AE.

The studio exposes every original visual setting, checked against ScriptUI's
`gatherSettings()` in the panel tests. Keep new controls in that parity check.
`word_styles.js` is generated from `ae/lib/style_shuffle.jsx`; edit the AE source
and run `python scripts/sync_preview_styles.py`. Release packaging regenerates
it automatically. Preview and AE use the same seeded shuffle algorithm.

Data flow:

1. AE chooses a source media path. The panel posts it to the loopback service.
2. The service extracts audio into `exports/runs/<uuid>/`, runs the selected
   adapter, normalizes words, and groups captions. Raw and normalized JSON are saved.
3. The panel validates the result. The preview and editor use that document.
4. Text edits change `text/isEdited` and caption text; timings stay intact.
5. Generate passes validated JSON and normalized settings to `KCF_dispatch`.
6. The existing layer builder measures text, creates a fresh precomp, and calls
   the registered preset's hooks. The original composition receives one precomp layer.

Installed location:

- Windows runtime: `%LOCALAPPDATA%/CapForge`.
- macOS runtime: `~/Library/Application Support/CapForge`.
- An owned earlier `Kartuli Caption Forge` runtime stays in its original path.
  Marker and saved-look readers accept both product names. Public branding is CapForge.
- `.runtime/` contains CapForge's private uv tools and managed Python. The
  bootstrap never modifies system PATH or registers Python globally. The venv
  gets a bundled audio binary through `imageio-ffmpeg`; no ffmpeg setup is required.
- CEP panel: the user's Adobe CEP `extensions/com.kartuli.captionforge` folder.
- `install.json` contains a runtime path, **never** an API key or auth token.
- `.venv/`, `exports/`, backend key files and `.local-token` survive updates.
- A runtime copy of `installer/` and `panel/` lets users repair from the app folder.
- Older code/panel copies are backed up under the runtime's `backups/` folder.
- The preview package is unsigned; the optional debug-mode setting applies to
  all unsigned Adobe extensions for that user. Sign the production package.

Security boundaries:

- Service binds to `127.0.0.1`. Only loopback Host headers are accepted.
- Readiness is public; other endpoints require a random installation token.
- CEP file origins `null` and `file://` are accepted with token authentication. Web origins are denied.
- API keys stay in the service's local `.env`; saved looks allowlist visual settings.
- Strings cross into AE as JSON, not source code. User text is DOM `textContent`
  or Canvas text, never `innerHTML`.
- Title files are trusted installed code. Do not build a UI that executes uploaded JSX.
- Local `.env` files are plaintext; owner-only permissions are used on POSIX.
  OS credential-vault storage remains a release improvement, not a claimed feature.
