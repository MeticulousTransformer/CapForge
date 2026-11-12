# Start here

This is the agent workspace for **CapForge**. Read the root
`AGENTS.md`, then the relevant guide below. No agent-only runtime or framework.

| Task | Read | Own these files |
| --- | --- | --- |
| Add a caption/title style | [ADD_TITLE.md](ADD_TITLE.md) | One `ae/titles/*.jsx`, one catalog entry, one preview branch |
| Change UI or theme | [ARCHITECTURE.md](ARCHITECTURE.md) | `panel/index.html`, `panel/styles/`, relevant `panel/js/` module |
| Add transcription provider | Root `AGENTS.md` | One adapter in `backend/providers/`, registry entry, normalization test |
| Change installation | [ARCHITECTURE.md](ARCHITECTURE.md), `docs/RELEASE.md` | `installer/` and its tests |

Rules that matter:

- Preserve `words[].id/start/end` when editing wording or regrouping captions.
- Provider adapters never import AE or preview code.
- Animation hooks change keyframes/effects only; the layer builder owns layout.
- Never clear, rename, or overwrite user compositions as part of generation.
- All generated content goes into a fresh caption precomp, inside the KCF folder.
- Do not send real clips to paid APIs to test unrelated UI changes.
- Never put keys/tokens in frontend storage, examples, screenshots or release ZIPs.
- AE code is ExtendScript (ES3): `var`, regular functions, no arrow functions/classes.
- The browser UI is dependency-free and must work offline as a demonstration.
- Keep documentation truthful: canvas preview is approximate; only real AE playback
  verifies font metrics, effects and final timing.

Run the existing checks plus the checks for your change:

```text
python -m unittest discover -s backend/tests -v
python -m unittest discover -s installer/tests -v
node panel/tests/test_studio.js
node panel/tests/test_provider_setup.js
node panel/tests/test_bootstrap.js
node ae/tests/test_layer_builder.js
node ae/tests/test_word_anchor.js
node ae/tests/test_text_style.js
node ae/tests/test_background_opacity.js
node ae/tests/test_style_shuffle.js
node ae/tests/test_slide_in.js
node ae/tests/test_fit_boundary.js
node ae/tests/test_bootstrap.js
node panel/tests/test_api.js
node panel/tests/test_updates.js
python scripts/check_release.py
```

On Windows, `.venv\Scripts\python.exe` can replace `python`. If a sandbox blocks
Windows' event-loop socket, run API integration tests with local-network access.
If it blocks temporary folders, point `TEMP` and `TMP` to a writable test folder.

Check the **current** checkout and user edits first. Do not infer that a successful
test suite means the CEP panel was installed or visually tested inside AE.
