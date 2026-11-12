# Your first captions

1. Extract the entire CapForge package. Connect to the internet for first setup.
2. Close AE. Double-click **CapForge Setup.exe** (Windows; **Install Windows.cmd**
   is the fallback) or **Install macOS.command** (Mac).
   The launcher prepares CapForge's private runtime automatically. Click
   **Install CapForge** in the wizard; audio and transcription support are
   installed for you. No Python download or PATH setup is needed. This preview build needs
   Adobe's unsigned-extension mode; the wizard has an explicit checkbox.
3. Restart AE. Open **Window → Extensions → CapForge** (Adobe may
   label this menu **Extensions (Legacy)**).
4. Play the built-in preview and choose a style. Open **Design** to change the
   font, colors, layout or animation controls. Use a Georgian-supporting font.
5. In **Setup**, click **Start service** and wait for **Studio connected**. Connection checks happen automatically. Use **Check connection** to refresh after other setup changes. Select a
   service and follow its three-step guide. Open its account page, paste your own
   key and choose **Save key & use this AI**. Start with ElevenLabs for Georgian.
   See [AI setup](AI_SETUP.md) for account links and optional Google/local setup.
6. In **Source**, choose a clip, language and words per caption. Click
   **Transcribe clip**, then review and edit individual words in **Words**.
7. Open the destination composition in AE. Click **Generate captions**. A fresh
   caption precomp is added to your composition. Play the timeline to check it.

The built-in demo and importing JSON do not require a cloud API account.
The panel can generate demo captions in AE. Cloud transcription may incur
provider charges. The canvas shows a design approximation, not an AE render.

**Save your work:** Export JSON saves your edited wording and original timings.
Save look exports reusable visual settings. Keep your AE project saved as usual.
Generated keyframes remain editable even without the panel.

**Updates:** In Setup, choose **Check for updates**, then **Update** when offered.
CapForge downloads and checks the package and opens Setup for you. Save your AE
project, close AE, and click Install. Reopen AE afterward. Setup closes the old
local service automatically and preserves your keys and exports. An older
service from before v0.3.2 may need its window closed once before updating.

**Mac access-privileges error:** use the ZIP attached to the latest release and
extract the entire package. The v0.3.2 launcher includes the correct permissions;
the old download needs replacing. Avoid sharing the installer file by itself.

**Source alignment:** Transcription starts at the source file's beginning.
Selecting a trimmed or offset footage layer does not change that. Move the
generated precomp layer to align it with that footage, or supply appropriately
offset word-timed JSON.

**Changing chunk sizes:** Adjust grouping in Source, then open Words and click
**Apply Source grouping**. Word timestamps stay intact. Words per line in
Design changes visual wrapping separately from caption grouping.

**Finding effects:** Design's **Animation effect** menu and the collection use
the original effect names, including **Slide In**, **Bounce In** and
**Pop Karaoke**. Choosing Slide In opens its motion controls. Drag the direction
dial, choose Left/Right/Above/Below, or enter an angle. Set travel, duration,
dolly, easing and AE motion blur there. Other effects show the controls they use.

**Fine tuning:** Typography includes installed font families/styles when AE
supports enumeration. Layout controls wrapping, spacing and boundary fitting;
0 words/characters per line removes that limit. Finish contains complete outline,
background and shadow controls. Background opacity sets transparency from
0–100% without fading the caption text. Style shuffle mixes solid, accent,
outline and chosen fonts. A fixed seed repeats the same pattern; 0 generates a fresh mix.
The canvas approximates typography and motion; motion blur renders in AE.

**More transcription control:** Source's Transcription options includes model,
speaker identification, caption minimums/durations and a manual media location.
Prepare audio only saves a WAV without sending it to a transcription provider.

**No connection:** Click **Start service** and wait for CapForge to connect.
If it cannot connect, it shows the error and lets you retry. If another copy of the service uses port 8765, close that
copy before starting the installed service. The installed panel uses its own token.

**No panel in AE:** Restart AE after installation. Confirm the unsigned-build
checkbox was enabled, or use a signed release. Check Adobe's CEP support for your
AE version. The original ScriptUI panel remains available in the runtime `ae/`.

**Files:** Intermediate audio and JSON are in the installation's
`exports/runs/<run-id>/` folder. Updates preserve your keys and exports.
The installation folder contains the service and must stay in place.
Its `.runtime/` folder is managed by CapForge; keep it alongside the app.
Earlier owned installations keep their existing folder, API keys and exports.

**Removing the panel:** Close AE and remove only the user CEP folder named
`com.kartuli.captionforge`. Keep the runtime folder until you have backed up
exports, keys and any models you want. The installer does not alter AE projects.
