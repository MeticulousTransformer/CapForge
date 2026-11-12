# Install CapForge on Windows

Get the Windows download from the [CapForge download page](https://meticuloustransformer.github.io/CapForge/)
or [official GitHub release](https://github.com/MeticulousTransformer/CapForge/releases/latest).
For v0.3.3, choose **CapForge-0.3.3-Windows.exe**. It is a standalone installer;
you do not need to download or extract a ZIP.

1. Save your project and close After Effects. Connect to the internet.
2. Double-click **CapForge-0.3.3-Windows.exe**. Keep the file intact; its setup
   files are included inside it.
3. Wait while CapForge prepares its private runtime. The guided installer opens
   automatically.
4. Review **Allow unsigned Adobe extensions for this account (preview build)**.
   Enable it for this preview panel to appear in AE. The option applies to all
   unsigned Adobe panels for your account.
5. Click **Install CapForge** and wait for the installed message.
6. Open After Effects and choose **Window → Extensions → CapForge**. Some AE
   versions call this menu **Extensions (Legacy)**.
7. In CapForge's **Setup** section, click **Start service**. Once connected, add
   your AI account or try the built-in demo. Follow [Your first captions](QUICK_START.md).

Setup installs for your account. You do not need to install Python, FFmpeg,
certificates, or configure PATH. After Effects itself must already be installed.
First setup needs internet to prepare the runtime and transcription packages.

## If Windows shows a publisher warning

This preview EXE has no trusted publisher certificate. Windows may show an
unknown-publisher or SmartScreen warning. Verify that you downloaded the file
from the official release before deciding to run it. Where Windows offers it,
**More info → Run anyway** applies to this file. Keep Windows protection enabled;
a work computer's policy may require administrator approval. Microsoft explains
[SmartScreen and app reputation](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation).

## Updates and repair

In the AE panel, choose **Setup → Check for updates → Update**. CapForge selects
the Windows update automatically and opens Setup. Save your project, close AE,
and click **Install CapForge**. Reopen AE after setup finishes. Your keys and
exported transcripts remain in place.

To repair manually, run the downloaded EXE again. It reinstalls the version
bundled in that EXE; download the latest release first when you want a newer
version. See [Updating CapForge](UPDATES.md).

If setup fails, read the error and retry after resolving it. If the panel is
missing, close AE, rerun the installer with the unsigned Adobe preview option
enabled, and restart AE.

Your runtime and exported files live in `%LOCALAPPDATA%\CapForge`. An owned
earlier installation keeps its original folder. Keep that runtime folder in
place; it contains the local service and your data.
