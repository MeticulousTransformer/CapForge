# Install CapForge on Mac

Get the Mac download from the [CapForge download page](https://meticuloustransformer.github.io/Georgian-Kartuli-After-Effects-Transcribtion-Tool/)
or [official GitHub release](https://github.com/MeticulousTransformer/Georgian-Kartuli-After-Effects-Transcribtion-Tool/releases/latest).
For v0.3.3, choose **CapForge-0.3.3-macOS.dmg**. The app supports Intel and Apple
Silicon Macs. Keep an internet connection available for first setup.

1. Open the downloaded DMG and drag **CapForge.app** to **Applications**.
2. Open **CapForge** from Applications. You can eject the disk image after copying.
3. Save your project and close After Effects.
4. Select **Allow unsigned Adobe extensions for this account** for this preview.
   This setting allows all unsigned Adobe panels for your account; it is separate
   from macOS app security.
5. Click **Install CapForge**. Setup prepares its private runtime, audio support,
   and caption panel. Wait for **CapForge is installed**.
6. Click **Open After Effects**, then choose **Window → Extensions → CapForge**.
   Some AE versions call this menu **Extensions (Legacy)**. If AE was still open
   during installation, quit and reopen it first.
7. In CapForge's **Setup** section, click **Start service**. Once connected, add
   your AI account or try the built-in demo. Follow [Your first captions](QUICK_START.md).

No separate Python, FFmpeg, terminal commands, or certificate installation is
needed. After Effects itself must already be installed.

## If macOS blocks opening the app

This preview is not Apple notarized or signed with an identified developer's
certificate. Its local ad-hoc signature does not remove Gatekeeper warnings.

If you trust the official download, first try opening CapForge. Then go to
**System Settings → Privacy & Security → Open Anyway** for CapForge and confirm
**Open**. This creates an exception for that app. See
[Apple's instructions](https://support.apple.com/102445). Keep Gatekeeper enabled;
do not run commands that disable protection globally. A managed Mac may require
your administrator's approval.

## Updates and repair

In the AE panel, choose **Setup → Check for updates → Update**. CapForge selects
the Mac update automatically and opens Setup. Save your project, close AE, and
click **Update / Repair**. Your keys and exported transcripts remain in place.

The app in Applications also repairs your installation. If the installed release
is newer than that app, Repair uses the installed files and preserves the newer
release. Otherwise, it uses the app's bundled version. To update manually,
download the latest DMG and replace the app first. See [Updating CapForge](UPDATES.md).

If setup fails, use **Logs** to inspect the error and **Try Again** after resolving
it. If the panel is missing, close AE, enable the unsigned Adobe preview option
in CapForge, run **Update / Repair**, then restart AE.

Your runtime and exported files live in
`~/Library/Application Support/CapForge`, separately from the app in Applications.
An owned earlier installation keeps its original folder. Keep that runtime folder
in place; it contains the local service and your data.
