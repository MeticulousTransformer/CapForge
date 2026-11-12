# Your first captions

1. Download your platform's installer from the
   [CapForge download page](https://meticuloustransformer.github.io/CapForge/)
   or [official release](https://github.com/MeticulousTransformer/CapForge/releases/latest).
   On Mac, open **CapForge-0.3.3-macOS.dmg**, drag **CapForge.app** to Applications,
   and open it there. On Windows, open **CapForge-0.3.3-Windows.exe** directly.
   See the [Mac guide](INSTALL_MAC.md) or [Windows guide](INSTALL_WINDOWS.md).
2. Close AE and click **Install CapForge**. Keep internet available while Setup
   prepares the private runtime, audio support, and caption panel. No Python
   download or PATH setup is needed. For this preview, enable the explicit
   **Allow unsigned Adobe extensions for this account** option. It applies to
   all unsigned Adobe panels for your account.
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
CapForge downloads and checks the package for your OS and opens Setup for you.
Save your AE project, close AE, and click **Update / Repair** on Mac or
**Install CapForge** on Windows. Reopen AE afterward. Setup closes the old
local service automatically and preserves your keys and exports. An older
service from before v0.3.2 may need its window closed once before updating.

**App security prompts:** This preview has no trusted publisher certificate and
is not Apple notarized. A native installer does not remove OS security warnings.
Use the platform guide above for the official per-app opening instructions.
No certificate installation or global security changes are needed.

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
