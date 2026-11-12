# CapForge: a small book of bugs and lessons

This guide explains the bugs found in CapForge and the ideas behind their
repairs. You do not need to understand every line of Python or JavaScript.
Follow one example at a time. The purpose is to make the growing code easier to
reason about, while keeping each change small.

For using the app, start with [Your first captions](QUICK_START.md). This guide
is about how it works and why seemingly small mistakes matter. The earlier
checks below come from [VALIDATION.md](VALIDATION.md). Later chapters describe
the changes in the 12 November 2026 review. They do not mean that these changes
have been published or that commercial acceptance work is complete.

## 1. Three parts, one shared timeline

CapForge has three main jobs. The panel collects choices. The Python service
prepares audio and asks a transcription provider for words. The After Effects
engine measures text and creates layers.

The connection between them is a document containing words, IDs, start times,
end times and caption groups. Think of each word as an edit with a stable label.
Changing “helo” to “hello” should change the spelling while keeping its place
in time. Regrouping four words into two captions should keep those same word
IDs and timings.

This boundary makes the project easier to extend. A new provider translates
its response into the existing document. A new animation reads that document.
Neither needs to rewrite the other. The [architecture map](../agents/ARCHITECTURE.md)
shows where each responsibility lives.

## 2. Earlier lesson: being loaded is different from being available

The earlier validation recorded a real AE error:
`KCF_PRESET_LABELS is undefined`. The engine files had been loaded, but the
declarations were inside an initialization scope. A later panel call could not
reach them.

A scope is the part of a program where a name can be used. Imagine putting a
tool inside a closed drawer: the tool exists, but someone outside that drawer
cannot simply use its name to retrieve it. The repair kept the engine available
through the intended connection between initialization and later calls.

The useful test was therefore more than “does this file load?” It initialized
the engine and generated captions in separate calls. Earlier real AE checks
also exercised all 13 presets. See the [engine bootstrap tests](../ae/tests/test_bootstrap.js).

## 3. Earlier lesson: paths and waiting are real inputs

Earlier installation checks used folders containing spaces and Georgian text.
That exposed assumptions which ordinary English paths can hide.

On a case-insensitive Mac disk, differently capitalized paths can refer to the
same folder. Comparing their spelling can incorrectly reject a valid install.
The installer and updater instead compare the physical directory. On Windows,
a child process using cp1252 output could not safely print a Georgian Python
path. Encoding the value as ASCII-safe JSON preserved it across that boundary.

Another earlier false alarm came from AE image exports. The script returned
before the PNG finished appearing. Checking immediately reported failure even
though the export completed. The lesson is to wait for the actual result, with
a limit, rather than treating “the command returned” as proof of completion.

These are documented historical findings, not new discoveries in this review.

## 4. An update needs a complete way back

An app depends on both its own files and installed Python packages. Previously,
the installer backed up the app files but reused a healthy package environment
without backing it up.

That left a failure path: a package update could replace some files, then fail.
Or the packages could update successfully and a later installation step fail.
Restoring only the old app would leave it using changed packages.

The repair in [deployment.py](../installer/deployment.py) makes a recovery copy
of the existing environment before changing packages. The existing rollback
then restores packages and app files together. Broken environments still follow
the repair path.

The regression test changes real temporary files to represent a partial package
update, then triggers each failure. It checks that the old package returns and
the newly added file disappears. The cost is extra disk space for the backup;
the code does not introduce a new package-management system.

## 5. A failed paid request should remain one request

The ElevenLabs adapter previously retried failed requests by removing keyterms,
and could retry again using an older model. This could turn one click into
several uploads and silently change the user's model choice.

The repair in [elevenlabs_scribe.py](../backend/providers/elevenlabs_scribe.py)
makes one upload attempt for that transcription request. An error is shown to
the editor, who can decide what to change before trying again. This rule is
especially useful for paid services: a timeout does not prove the provider
never received the audio.

Shared [provider errors](../backend/providers/base.py) now turn HTTP failures
into useful actions, such as checking the saved key or account credits. They
avoid copying an arbitrary remote error body into the panel. The tests replace
the network boundary, so this verification makes no paid calls.

## 6. Missing, zero and false mean different things

A start time of `0` is valid: the word begins at the start of the file. A missing
start time means the provider did not supply that information. Substituting
zero for a missing value invents timing.

The shared [normalizer](../backend/services/normalize.py) now rejects missing,
negative, reversed and non-finite word intervals. Adapter checks also preserve
missing values until validation, including Azure offsets and MLX timestamps.
Boolean values need a separate check: Python can convert `False` to `0` and
`True` to `1`, but neither is a timestamp supplied as a number.

The same distinction matters in settings. JavaScript's `value || fallback`
replaces a legitimate zero. ScriptUI now preserves zero for affected controls,
including custom X/Y position, spacing and safe margin. Token confidence zero
also stays zero instead of turning into full confidence.

The teaching rule is simple: choose a default for missing data deliberately;
do not use a test that also discards valid values.

## 7. Preserve precision and preserve the evidence

Provider duration metadata can end slightly before the final word. Rounding
the document duration can also lose a fraction of a millisecond. The document
builder now covers the word and caption endpoints without shortening them.
The API validates the completed document before saving normalized output.

Strict validation exposed another problem during review. If an adapter rejected
timing before returning its result, the API never reached the code that saved
the raw provider response. The most useful debugging evidence was lost.

Timing errors can now carry the raw response back to
[app.py](../backend/app.py), which saves it before reporting failure. The invalid
normalized document is not saved as a usable transcript. Tests exercise this
through eight real adapter implementations with controlled provider responses.

Keep the distinction clear: raw JSON records what arrived; normalized JSON is
the validated timeline the rest of CapForge can use.

## 8. Temporary files must belong to one run

The whisper.cpp adapter previously used one fixed output filename in the
temporary directory. If a later process finished without writing its JSON,
an older file could still exist and be mistaken for the new result.

[whisper_cpp.py](../backend/providers/whisper_cpp.py) now creates a separate
temporary directory for each run. It requires output from that directory,
reads it, and cleans up only that directory. A test deliberately leaves an old
transcript nearby and verifies it is neither returned nor deleted.

Whisper can also return word fragments. Two fragments may share a clock tick,
so the adapter allows that while assembling the word. The completed word must
still have a positive interval. Punctuation can attach to the previous word
without inventing a new spoken interval.

This is why validation belongs at the correct level: a fragment and a completed
word do not have identical requirements.

## 9. Starting and stopping need an agreed order

The service uses a lock to keep incompatible operations from running together.
Think of it as a sign saying “this work area is occupied.” Audio preparation
now uses that same protection, so an update cannot stop the service halfway
through extracting audio.

There was also a small timing window between admitting a request and starting
its worker. Shutdown could begin in between. The worker now checks the stopping
state again after acquiring the lock. The check and protected work therefore
agree on whether new work is allowed.

At the panel, clicking Start service now waits for readiness checks instead of
leaving the editor to guess when to click again. Health checks have a bounded
wait. Older CEP browsers may lack `AbortController`, so
[api.js](../panel/js/api.js) detects it first and still releases the interface
when a health request stalls. That short timer does not cut off transcription.

## 10. A composition name is not permission to delete it

An editor can name a composition `KCF_Captions_Client Animation`. Previously,
the cleanup code treated the name prefix as proof that CapForge owned it.
That was too broad.

New generated precomps receive explicit metadata. Cleanup checks this marker
instead of guessing from the name. Older unmarked precomps remain for manual
removal. This protects an editor's similarly named work, though changing or
copying ownership metadata still deserves care.

Generation also has a failure boundary. If a preset or effect fails while
building a new precomp, the engine removes that unfinished precomp and closes
the Undo group. It does not attempt to “repair” unrelated project contents.

The [generation safety tests](../ae/tests/test_generation_safety.js) verify both
behaviors. The guiding idea is to remember exactly what this operation created,
so cleanup can stay narrow.

## 11. Text layout needs the actual shape of the letters

Two words can have different shapes around their baseline. One reaches high;
another extends lower. Taking only the largest individual height does not
necessarily cover the combined line.

The [layer builder](../ae/lib/layer_builder.jsx) now measures the highest top
and lowest bottom across the line. Automatic line spacing uses those extents,
and caption backgrounds use the actual positioned glyph bounds. This matters
when fitted lines have different sizes or words use different fonts.

Layer order matters too. A caption background placed behind ordinary text can
still cover a preset's active-word box. Moving that background to the bottom
of the generated precomp keeps preset extras above it.

Real AE testing exposed another assumption: boundary fitting produced tracking
`27.0171171834326`, but AE requires an integer. The test double had accepted
fractions, so it missed the failure. Tightening that double and adding a
regression reproduced the problem. [text_measure.jsx](../ae/lib/text_measure.jsx)
now rounds only when assigning `TextDocument.tracking`. Word times remain
precise: a typography constraint is no reason to round the timeline. This is
why simulated layout checks still need real host checks, rendered frames and
playback.

## 12. A small panel choice can send a wrong request

A custom model name belongs to a provider. Switching from ElevenLabs to OpenAI
while retaining `scribe_v2` could send an incompatible model to the new service.
An explicit provider switch now clears that field. Reconnecting to the same
service preserves the editor's model choice.

The panel and AE host also check caption references more strictly. The number
`0`, the text `"0"`, and `false` should not become interchangeable IDs just
because JavaScript can convert between types. References must identify real
words, once each, inside the right caption interval.

The relevant boundaries are [panel validation](../panel/js/transcript.js) and
[host validation](../panel/host.jsx). Checking both is useful because imported
JSON and host calls can arrive through different paths.

## 13. What a passing test tells us

A regression test reproduces a particular mistake, then checks the repaired
behavior. For example, installer rollback tests proved that changed packages
survived a failed update before the repair, and were restored afterward.

Some tests run real file operations or a local HTTP server. Others substitute
a cloud response, browser document or AE object. Those substitutions keep
checks repeatable and avoid paid uploads or damage to a working project.
They also set a limit on the conclusion.

A simulated AE test cannot prove a Georgian font looks correct. A Mac test
cannot establish Windows installation behavior. A successful provider fixture
cannot establish current cloud accuracy or account eligibility. Earlier
recorded test totals describe their own runs; final review totals belong with
their actual execution evidence. Signing, clean-machine setup and first-user
acceptance remain separate work.

## Four small exercises

1. **Read one word.** Open a fixture from `backend/tests/fixtures/`. Identify its
   text, ID, start and end. In a copy, correct the spelling without changing
   timing. Explain why the ID should stay the same.

2. **Compare missing with zero.** On paper, write one word with `start: 0` and
   another without `start`. Describe what information the second example lacks.
   Then explain why `false` cannot fill that gap.

3. **Follow a failure.** Read the healthy-environment rollback regression in
   [test_install.py](../installer/tests/test_install.py). Find the three moments:
   the old file, the simulated update, and the restored file.

4. **Inspect a safe demo.** In a disposable AE project, generate built-in demo
   captions, then inspect a word layer's timing and the precomp comment. Compare
   the canvas preview with the AE frame. Save any useful project before cleanup.

## Product ideas for later — not implemented by this review

These suggestions are ordered for practical editor value. Each can be a small
separate task with its own acceptance check.

1. **One-button readiness.** Combine engine, service, audio-tool and provider
   status into one clear result. Show the next useful action when something
   fails. Check account configuration without silently buying a transcription.

2. **Signed distribution.** Sign the extension and installer, complete the
   applicable platform distribution checks, and test the exact downloaded
   artifact on clean machines. This should reduce setup friction and replace
   reliance on the preview's unsigned-extension setting.

3. **Captions aligned to trimmed footage.** Capture the selected layer's source
   trim and timeline offset, then show the intended placement before generation.
   Current behavior starts transcription at the source file's beginning; follow
   the alignment instructions in [QUICK_START](QUICK_START.md) until this exists.

4. **Autosaved transcript sessions.** Recover edited wording, source selection,
   grouping and look after a panel restart. Preserve original timings and let
   the editor choose whether to restore a session. Keep API keys out of it.

5. **A support bundle without secrets.** Export versions, selected settings and
   useful diagnostics, with a review screen. Exclude credentials and tokens;
   make media, transcript text and personal paths explicit choices.

6. **Actual first-user trials.** Ask editors unfamiliar with the code to install,
   transcribe a short Georgian clip, correct a word and generate captions.
   Record where they stop or misunderstand a message. Use those observations
   to choose the next small improvement rather than adding controls blindly.

## 14. The download is part of the program

A Mac editor expects an app they can drag to Applications. A Windows editor
expects an EXE they can open. CapForge now gives each system its own entry point:
the Mac app owns its setup window, while the Windows EXE carries and unpacks its
setup files. Both reach the same installation code for ownership checks, backups,
and preserving keys. The caption engine and normalized word timeline stay shared.
This is a useful boundary: separate the parts that the operating system needs,
and keep the common work in one place.

That separation also applies to updates. A Mac must select the Mac package;
Windows must select the Windows package. Each verified package carries its
version, source commit, file hashes, and native setup executable. These checks
help catch a wrong or incomplete download before Setup opens. An older Mac app
also checks whether the installed release is newer before repairing it, so an
old copy in Applications does not quietly undo an update.

A source-folder test can miss a file that was left out of the download. The
[packaged installation check](../scripts/check_native_install.py) therefore starts
the shipped executable, uses a fresh destination, and checks the installed
runtime and release identity. The workflow requires the Windows EXE and the Mac
DMG to work on their respective systems, including both Mac architectures.
Passing local tests does not establish that this remote release gate has passed.

The fresh-folder test exposed a small Mac path trap. A temporary folder can be
named under `/var`, while that system path points to `/private/var`. The installer
deliberately rejects symbolic links in destination paths. It therefore rejected
the test's own temporary path before installation began. The narrow repair was
to resolve the temporary folder created by the test:

```python
test_root = Path(folder).resolve()
```

`resolve()` finds the physical path. Here the test controls the folder it just
created, so using that path is appropriate. The installer's checks for arbitrary
user-supplied links remain in place. A failing test can reveal a mistake in its
setup as well as in the application.

The first Windows run then caught two tests comparing paths as plain text.
They expected `installer/install.py`, but Windows correctly returned
`installer\\install.py`. The command was valid; the assertion assumed Mac's
separator. Compare path components with `Path(...).parts`, or normalize a path
with `Path(...).as_posix()` before comparing it with a slash-based fixture.
Likewise, Unix executable permission bits belong in Unix tests; Windows uses a
different permission model. Keep the behavior checks on both systems, and test
OS-specific details on the system that implements them.
Windows can also expose a short folder alias such as `RUNNER~1` and expand it
to `runneradmin`. Both can identify the same directory. The native launcher test
now compares resolved destinations, while still checking that Georgian text and
literal characters survive the handoff.

Finally, a working installer and a trusted publisher are separate requirements.
Executable permissions allow a file to run. Signing with a trusted publisher
certificate identifies its publisher; Apple notarization adds Apple's checking
process. Building an app or adding an
execute bit does not supply a developer certificate. This preview can therefore
install correctly and still show an OS trust prompt. The
[Mac](INSTALL_MAC.md) and [Windows](INSTALL_WINDOWS.md) guides explain that status
and the available per-app choices. Keep evidence equally specific: package tests
show installation behavior; desktop checks show the actual opening experience.
