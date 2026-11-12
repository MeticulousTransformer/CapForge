/* CapForge — dockable After Effects panel.
   Georgian/English word-timed caption animator.

   Install: copy KartuliCaptionForge.jsx AND the lib/ folder into
   Scripts/ScriptUI Panels/ (see README), then Window > KartuliCaptionForge.jsx.
   Requires: local backend running (python backend/app.py). */

#include "lib/json2.js"
#include "lib/http_client.jsx"
#include "lib/text_measure.jsx"
#include "lib/style_shuffle.jsx"
#include "lib/presets.jsx"
#include "lib/title_registry.jsx"
#include "lib/layer_builder.jsx"

var KCF_BACKEND_ROOT = new File($.fileName).parent.parent.fsName + "/backend";
KCF_loadTitles(new Folder(new File($.fileName).parent.fsName + "/titles"));

(function KartuliCaptionForge(thisObj) {

    var SETTINGS_SECTION = "KartuliCaptionForge";

    // ---- persisted state helpers ----
    function loadSetting(key, fallback) {
        try {
            if (app.settings.haveSetting(SETTINGS_SECTION, key)) {
                return app.settings.getSetting(SETTINGS_SECTION, key);
            }
        } catch (e) {}
        return fallback;
    }
    function saveSetting(key, value) {
        try { app.settings.saveSetting(SETTINGS_SECTION, key, String(value)); } catch (e) {}
    }

    // ---- runtime state ----
    var state = {
        mediaPath: "",
        doc: null,                       // last normalized TranscriptDocument
        providerIds: ["elevenlabs", "google_chirp", "openai", "azure_speech",
                      "gladia", "assemblyai", "whisper_cpp", "faster_whisper",
                      "mlx_whisper"],
        providerLabels: ["ElevenLabs Scribe v2", "Google Chirp", "OpenAI whisper-1",
                         "Azure AI Speech", "Gladia (Whisper cloud)", "AssemblyAI",
                         "Local whisper.cpp", "Local faster-whisper",
                         "Local mlx-whisper"]
    };

    function buildUI(thisObj) {
        var win = (thisObj instanceof Panel) ? thisObj
            : new Window("palette", "CapForge", undefined,
                         { resizeable: true });
        win.orientation = "column";
        win.alignChildren = ["fill", "fill"];
        win.spacing = 0;
        win.margins = 0;

        // scroll viewport: content column + scrollbar (ScriptUI has no
        // native scrolling; the scrollbar shifts content.location.y)
        var scroller = win.add("group");
        scroller.orientation = "row";
        scroller.alignChildren = ["fill", "top"];
        scroller.alignment = ["fill", "fill"];
        scroller.spacing = 2;
        var content = scroller.add("group");
        content.orientation = "column";
        content.alignChildren = ["fill", "top"];
        content.spacing = 6;
        content.margins = 8;
        var sbScroll = scroller.add("scrollbar");
        sbScroll.preferredSize.width = 16;
        sbScroll.alignment = ["right", "fill"];

        /* No fixed height here. A tabbedpanel pinned to one clips whatever
           its tabs hold past that point, and the scrollbar below measures
           `content`, so it never sees the trapped overflow. Sizing to the
           tallest tab puts the overflow where the scrollbar can reach it,
           and keeps working as tabs gain controls. */
        var tabs = content.add("tabbedpanel");
        tabs.alignChildren = ["fill", "top"];

        // ================= SOURCE TAB =================
        var tSrc = tabs.add("tab", undefined, "Source");
        tSrc.orientation = "column";
        tSrc.alignChildren = ["fill", "top"];

        var gFile = tSrc.add("group");
        gFile.add("statictext", undefined, "Media:");
        var etMedia = gFile.add("edittext", undefined, "");
        etMedia.preferredSize.width = 160;
        var btnBrowse = gFile.add("button", undefined, "Browse…");
        var btnFromComp = gFile.add("button", undefined, "From Comp");

        var gLang = tSrc.add("group");
        gLang.add("statictext", undefined, "Language:");
        var ddLang = gLang.add("dropdownlist", undefined,
            ["Georgian (ka-GE)", "English (en-US)", "Auto-detect"]);
        ddLang.selection = 0;

        var gProv = tSrc.add("group");
        gProv.add("statictext", undefined, "Provider:");
        var ddProv = gProv.add("dropdownlist", undefined, state.providerLabels);
        ddProv.selection = 0;
        ddProv.preferredSize.width = 200;
        var btnScan = gProv.add("button", undefined, "Scan");

        var gBackend = tSrc.add("group");
        gBackend.add("statictext", undefined, "Backend:");
        var etHost = gBackend.add("edittext", undefined, loadSetting("host", "127.0.0.1"));
        etHost.preferredSize.width = 100;
        var etPort = gBackend.add("edittext", undefined, loadSetting("port", "8765"));
        etPort.preferredSize.width = 55;
        var btnHealth = gBackend.add("button", undefined, "Test");

        var gAsr = tSrc.add("panel", undefined, "ASR Options");
        gAsr.orientation = "column";
        gAsr.alignChildren = ["fill", "top"];
        var gModel = gAsr.add("group");
        gModel.add("statictext", undefined, "Model override:");
        var etModel = gModel.add("edittext", undefined, "");
        etModel.preferredSize.width = 160;
        var gKey = gAsr.add("group");
        gKey.add("statictext", undefined, "Keyterms (comma):");
        var etKeyterms = gKey.add("edittext", undefined, "");
        etKeyterms.preferredSize.width = 160;
        var cbDiarize = gAsr.add("checkbox", undefined, "Diarization");

        // ================= GROUPING TAB =================
        var tGrp = tabs.add("tab", undefined, "Grouping");
        tGrp.orientation = "column";
        tGrp.alignChildren = ["left", "top"];

        function numField(parent, label, value, width) {
            var g = parent.add("group");
            g.add("statictext", undefined, label);
            var et = g.add("edittext", undefined, String(value));
            et.preferredSize.width = width || 55;
            return et;
        }
        /* Circular direction dial. ScriptUI ships no dial control, so this
           is a button we draw ourselves and drive from mouse drags. The
           needle points at the side the word travels in FROM, and uses the
           same maths as the preset so the dial cannot disagree with the
           motion it produces. */
        function angleDial(parent, initialDeg) {
            var angle = initialDeg;

            var row = parent.add("group");
            row.orientation = "row";
            row.alignChildren = ["left", "center"];
            row.spacing = 10;

            var dial = row.add("iconbutton", undefined, undefined,
                { style: "toolbutton" });
            dial.preferredSize = [66, 66];

            var col = row.add("group");
            col.orientation = "column";
            col.alignChildren = ["left", "top"];
            col.spacing = 4;
            col.add("statictext", undefined, "Angle (0 = from bottom)");
            var et = col.add("edittext", undefined, String(initialDeg));
            et.preferredSize.width = 60;
            var hint = col.add("statictext", undefined, "drag dial, shift snaps 15°");
            hint.enabled = false;

            function redraw() {
                // ScriptUI has no invalidate(); re-assigning size repaints
                try { dial.size = dial.size; } catch (e) {}
                try { win.update(); } catch (e) {}
            }
            function setAngle(deg) {
                deg = deg % 360;
                if (deg < 0) { deg += 360; }
                angle = deg;
                et.text = String(Math.round(deg * 10) / 10);
                redraw();
            }

            dial.onDraw = function () {
                var g = this.graphics;
                var w = this.size.width, h = this.size.height;
                var cx = w / 2, cy = h / 2;
                var r = Math.min(w, h) / 2 - 3;
                var accent = [0.29, 0.56, 0.90, 1];

                g.newPath();
                g.ellipsePath(cx - r, cy - r, r * 2, r * 2);
                g.fillPath(g.newBrush(g.BrushType.SOLID_COLOR, [0.16, 0.16, 0.16, 1]));
                g.newPath();
                g.ellipsePath(cx - r, cy - r, r * 2, r * 2);
                g.strokePath(g.newPen(g.PenType.SOLID_COLOR, [0.45, 0.45, 0.45, 1], 1));

                var v = KCF_slideOffset(angle, r);
                g.newPath();
                g.moveTo(cx, cy);
                g.lineTo(cx + v[0], cy + v[1]);
                g.strokePath(g.newPen(g.PenType.SOLID_COLOR, accent, 2));
                g.newPath();
                g.ellipsePath(cx + v[0] - 3, cy + v[1] - 3, 6, 6);
                g.fillPath(g.newBrush(g.BrushType.SOLID_COLOR, accent));
            };

            var dragging = false;
            function fromMouse(ev) {
                var dx = ev.clientX - dial.size.width / 2;
                var dy = ev.clientY - dial.size.height / 2;
                if (dx === 0 && dy === 0) { return; }
                var deg = KCF_slideAngleFromPoint(dx, dy);
                if (ev.shiftKey) { deg = Math.round(deg / 15) * 15; }
                setAngle(deg);
            }
            dial.addEventListener("mousedown", function (ev) {
                dragging = true;
                fromMouse(ev);
            });
            dial.addEventListener("mousemove", function (ev) {
                if (dragging) { fromMouse(ev); }
            });
            dial.addEventListener("mouseup", function () { dragging = false; });
            dial.addEventListener("mouseout", function () { dragging = false; });

            et.onChange = function () {
                var v = parseFloat(et.text);
                setAngle(isNaN(v) ? 0 : v);
            };

            return { value: function () { return angle; } };
        }

        var etMinWords = numField(tGrp, "Min words per caption (1-6):", loadSetting("minWords", "2"));
        var etMaxWords = numField(tGrp, "Max words per caption (1-6):", loadSetting("maxWords", "4"));
        var etMaxChars = numField(tGrp, "Max characters:", loadSetting("maxChars", "42"));
        var etPause = numField(tGrp, "Pause break (s):", loadSetting("pauseBreakSeconds", "0.55"));
        var etMinDur = numField(tGrp, "Min real caption duration (s):", loadSetting("minCaptionDuration", "0.5"));
        var etMaxDur = numField(tGrp, "Max real caption duration (s):", loadSetting("maxCaptionDuration", "3.5"));
        var cbRemoveCommasPeriods = tGrp.add("checkbox", undefined, "Remove commas and periods");
        cbRemoveCommasPeriods.value = loadSetting("removeCommasAndPeriods", "false") === "true";

        // ================= TYPOGRAPHY TAB =================
        var tType = tabs.add("tab", undefined, "Type");
        tType.orientation = "column";
        tType.alignChildren = ["left", "top"];

        // font pickers: AE 24+ exposes app.fonts; fall back to a text field
        var fontGroups = [];
        try {
            fontGroups = app.fonts.allFonts || [];
        } catch (eFonts) {
            fontGroups = [];
        }
        var etFont = null, ddFamily = null, ddStyle = null;
        function fillStyles(styleIndex) {
            if (!ddFamily || !ddFamily.selection) { return; }
            var fam = fontGroups[ddFamily.selection.index];
            ddStyle.removeAll();
            for (var s = 0; s < fam.length; s++) {
                ddStyle.add("item", fam[s].styleName);
            }
            ddStyle.selection = Math.min(styleIndex || 0, fam.length - 1);
        }
        if (fontGroups.length > 0) {
            var gFam = tType.add("group");
            gFam.add("statictext", undefined, "Font:");
            ddFamily = gFam.add("dropdownlist", undefined, []);
            ddFamily.preferredSize.width = 210;
            var gSty = tType.add("group");
            gSty.add("statictext", undefined, "Style:");
            ddStyle = gSty.add("dropdownlist", undefined, []);
            ddStyle.preferredSize.width = 170;
            for (var fgi = 0; fgi < fontGroups.length; fgi++) {
                ddFamily.add("item", fontGroups[fgi][0].familyName);
            }
            ddFamily.onChange = function () { fillStyles(0); };
            // restore previously used font
            var savedPs = loadSetting("font", "NotoSansGeorgian-Bold");
            var selFam = 0, selSty = 0;
            for (var a = 0; a < fontGroups.length; a++) {
                for (var b = 0; b < fontGroups[a].length; b++) {
                    if (fontGroups[a][b].postScriptName === savedPs) {
                        selFam = a; selSty = b; a = fontGroups.length; break;
                    }
                }
            }
            ddFamily.selection = selFam;   // triggers onChange -> fillStyles(0)
            fillStyles(selSty);
        } else {
            etFont = numField(tType, "Font (PostScript name):",
                loadSetting("font", "NotoSansGeorgian-Bold"), 180);
        }
        function currentFontPS() {
            if (ddFamily && ddFamily.selection && ddStyle && ddStyle.selection) {
                return fontGroups[ddFamily.selection.index]
                    [ddStyle.selection.index].postScriptName;
            }
            return etFont ? etFont.text : "";
        }
        var etFontSize = numField(tType, "Font size:", loadSetting("fontSize", "72"));
        var etTracking = numField(tType, "Tracking:", "0");
        var etLineHeight = numField(tType, "Line height (0 = auto):", "0");
        var gFaux = tType.add("group");
        var cbFauxBold = gFaux.add("checkbox", undefined, "Faux bold");
        var cbFauxItalic = gFaux.add("checkbox", undefined, "Faux italic");
        cbFauxBold.value = loadSetting("fauxBold", "false") === "true";
        cbFauxItalic.value = loadSetting("fauxItalic", "false") === "true";

        function colorField(parent, label, defaultHex) {
            var g = parent.add("group");
            g.add("statictext", undefined, label);
            var et = g.add("edittext", undefined, defaultHex);
            et.preferredSize.width = 70;
            var btn = g.add("button", undefined, "Pick");
            btn.preferredSize.width = 45;
            btn.onClick = function () {
                var c = $.colorPicker();
                if (c !== -1) {
                    var hex = c.toString(16);
                    while (hex.length < 6) { hex = "0" + hex; }
                    et.text = "#" + hex.toUpperCase();
                }
            };
            return et;
        }
        function section(parent, title) {
            var p = parent.add("panel", undefined, title);
            p.orientation = "column";
            p.alignChildren = ["left", "top"];
            p.margins = [10, 14, 10, 10];
            p.spacing = 4;
            return p;
        }

        // ================= STYLE TAB =================
        var tStyle = tabs.add("tab", undefined, "Style");
        tStyle.orientation = "column";
        tStyle.alignChildren = ["left", "top"];

        // ---- Fill ----
        var pFill = section(tStyle, "Fill");
        var cbFill = pFill.add("checkbox", undefined, "Fill text");
        cbFill.value = loadSetting("fill", "true") !== "false";
        var etFill = colorField(pFill, "Color:", loadSetting("fillColor", "#FFFFFF"));
        var etHighlight = colorField(pFill, "Highlight:", loadSetting("highlightColor", "#FFD400"));
        var stFillNote = pFill.add("statictext", undefined,
            "uncheck, with stroke on, for hollow outlined text");
        stFillNote.enabled = false;

        // ---- Stroke ----
        var pStroke = section(tStyle, "Stroke");
        var gStroke = pStroke.add("group");
        var cbStroke = gStroke.add("checkbox", undefined, "Stroke");
        cbStroke.value = loadSetting("stroke", "false") === "true";
        gStroke.add("statictext", undefined, "Weight:");
        var etStrokeW = gStroke.add("edittext", undefined, loadSetting("strokeWidth", "7"));
        etStrokeW.preferredSize.width = 45;
        gStroke.add("statictext", undefined, "px");
        var etStrokeColor = colorField(pStroke, "Color:", loadSetting("strokeColor", "#000000"));
        var gStrokePos = pStroke.add("group");
        gStrokePos.add("statictext", undefined, "Position:");
        var ddStrokePos = gStrokePos.add("dropdownlist", undefined, ["Outer", "Center"]);
        ddStrokePos.selection =
            (loadSetting("strokePosition", "outer") === "center") ? 1 : 0;
        var stStrokeNote = pStroke.add("statictext", undefined,
            "AE text strokes cannot be inner");
        stStrokeNote.enabled = false;

        // ================= EFFECTS TAB =================
        var tFx = tabs.add("tab", undefined, "Effects");
        tFx.orientation = "column";
        tFx.alignChildren = ["left", "top"];

        // ---- Background ----
        var pBg = section(tFx, "Background");
        var cbBox = pBg.add("checkbox", undefined, "Background box");
        cbBox.value = loadSetting("backgroundBox", "false") === "true";
        var etBoxColor = colorField(pBg, "Color:", loadSetting("boxColor", "#000000"));
        var etBoxOpacity = numField(pBg, "Opacity (%):", loadSetting("boxOpacity", "100"));
        var etActiveBox = colorField(pBg, "Active word box:",
            loadSetting("activeBoxColor", "#FF3B30"));
        var etBoxRadius = numField(pBg, "Corner radius (px):",
            loadSetting("boxRadius", "18"));

        // ---- Shadow ----
        var pShadow = section(tFx, "Shadow");
        var cbShadow = pShadow.add("checkbox", undefined, "Drop shadow");
        cbShadow.value = loadSetting("shadow", "false") === "true";
        var etShadowColor = colorField(pShadow, "Color:", loadSetting("shadowColor", "#000000"));
        var etShadowOpacity = numField(pShadow, "Opacity (%):", loadSetting("shadowOpacity", "60"));
        var etShadowDistance = numField(pShadow, "Distance (px):", loadSetting("shadowDistance", "8"));
        var etShadowAngle = numField(pShadow, "Angle (deg):", loadSetting("shadowAngle", "135"));
        var etShadowSoftness = numField(pShadow, "Softness:", loadSetting("shadowSoftness", "12"));

        // ---- Style shuffle ----
        // back on the Style tab; a tab takes children whenever they are added
        var pShuffle = section(tStyle, "Style shuffle");
        var cbShuffle = pShuffle.add("checkbox", undefined,
            "Give each word a different look");
        cbShuffle.value = loadSetting("styleShuffle", "false") === "true";
        var gLooks = pShuffle.add("group");
        gLooks.add("statictext", undefined, "Looks:");
        var cbLookSolid = gLooks.add("checkbox", undefined, "Solid");
        var cbLookHighlight = gLooks.add("checkbox", undefined, "Highlight");
        var cbLookOutline = gLooks.add("checkbox", undefined, "Outline");
        cbLookSolid.value = loadSetting("shuffleSolid", "true") !== "false";
        cbLookHighlight.value = loadSetting("shuffleHighlight", "true") !== "false";
        cbLookOutline.value = loadSetting("shuffleOutline", "true") !== "false";
        var gShuffleFonts = pShuffle.add("group");
        gShuffleFonts.add("statictext", undefined, "Fonts:");
        var etShuffleFonts = gShuffleFonts.add("edittext", undefined,
            loadSetting("shuffleFonts", ""));
        etShuffleFonts.preferredSize.width = 190;
        var btnAddFont = gShuffleFonts.add("button", undefined, "Add current");
        btnAddFont.preferredSize.width = 80;
        btnAddFont.onClick = function () {
            var ps = currentFontPS();
            if (!ps) { return; }
            var list = etShuffleFonts.text.replace(/^\s+/, "").replace(/\s+$/, "");
            etShuffleFonts.text = list ? (list + ", " + ps) : ps;
        };
        var stFontNote = pShuffle.add("statictext", undefined,
            "PostScript names, comma separated. Empty = the Type tab font");
        stFontNote.enabled = false;
        var etShuffleSeed = numField(pShuffle, "Seed (0 = new mix each run):",
            loadSetting("shuffleSeed", "0"));
        var stShuffleNote = pShuffle.add("statictext", undefined,
            "outline borrows the Stroke weight, and its colour when Stroke is on");
        stShuffleNote.enabled = false;

        // ================= POSITION TAB =================
        var tPos = tabs.add("tab", undefined, "Position");
        tPos.orientation = "column";
        tPos.alignChildren = ["left", "top"];

        var gAnchor = tPos.add("group");
        gAnchor.add("statictext", undefined, "Anchor:");
        var ddAnchor = gAnchor.add("dropdownlist", undefined,
            ["Bottom center", "Center", "Top center", "Custom X/Y"]);
        ddAnchor.selection = 0;
        var etX = numField(tPos, "Custom X (px):", "960");
        var etY = numField(tPos, "Custom Y (px):", "1600");
        var etVOffset = numField(tPos, "Vertical offset (px):", "0");
        var etSafe = numField(tPos, "Safe margin (px):", "160");
        var gAlign = tPos.add("group");
        gAlign.add("statictext", undefined, "Alignment:");
        var ddAlign = gAlign.add("dropdownlist", undefined, ["Center", "Left", "Right"]);
        ddAlign.selection = 0;

        var pLines = section(tPos, "Line breaking");
        var etWordSpacing = numField(pLines, "Word spacing (px):",
            loadSetting("wordSpacing", "24"));
        var etWordsPerLine = numField(pLines, "Max words per line (0 = one line):",
            loadSetting("wordsPerLine", "0"));
        var etMinWordsPerLine = numField(pLines, "Min words per line:",
            loadSetting("minWordsPerLine", "2"));
        var etCharsPerLine = numField(pLines, "Chars per line (0 = off):",
            loadSetting("charsPerLine", "0"));

        var pFit = section(tPos, "Fit to boundary");
        var cbFit = pFit.add("checkbox", undefined,
            "Scale every line to fill the boundary");
        cbFit.value = loadSetting("fitBoundary", "false") === "true";
        var etFitWidth = numField(pFit, "Boundary width (0 = comp less safe margin):",
            loadSetting("fitWidth", "0"), 70);
        var etFitMax = numField(pFit, "Max font size (px):",
            loadSetting("fitMaxFontSize", "260"));
        var etFitTracking = numField(pFit, "Max tracking (0 = size only):",
            loadSetting("fitMaxTracking", "120"));
        var stFitNote = pFit.add("statictext", undefined,
            "line spacing follows the fitted sizes, so Line height is ignored");
        stFitNote.enabled = false;

        // ================= ANIMATE TAB =================
        var tAnim = tabs.add("tab", undefined, "Animate");
        tAnim.orientation = "column";
        tAnim.alignChildren = ["left", "top"];
        tAnim.add("statictext", undefined, "Preset:");
        var presetNames = [];
        for (var pi = 0; pi < KCF_PRESET_LABELS.length; pi++) {
            presetNames.push(KCF_PRESET_LABELS[pi][1]);
        }
        var lbPreset = tAnim.add("listbox", undefined, presetNames);
        lbPreset.preferredSize.height = 180;
        lbPreset.selection = 0;
        var stAnimNote = tAnim.add("statictext", undefined,
            "colours, stroke and boxes live in the Type tab");
        stAnimNote.enabled = false;
        var etPopScale = numField(tAnim, "Pop scale % (100 = no pop):",
            loadSetting("popScale", "112"));

        // ---- Slide In preset controls ----
        var gSlide = section(tAnim, "Slide In");
        var slideDial = angleDial(gSlide,
            parseFloat(loadSetting("slideAngle", "0")) || 0);
        var etSlideDistance = numField(gSlide, "Distance (px):",
            loadSetting("slideDistance", "140"));
        var etSlideDuration = numField(gSlide, "Duration (s):",
            loadSetting("slideDuration", "0.35"));
        var etSlideDolly = numField(gSlide, "Dolly (start scale offset %):",
            loadSetting("slideDolly", "0"));
        var etSlideEaseIn = numField(gSlide, "Ease in (0-100):",
            loadSetting("slideEaseIn", "100"));
        var etSlideEaseOut = numField(gSlide, "Ease out (0-100):",
            loadSetting("slideEaseOut", "98"));
        var cbSlideBlur = gSlide.add("checkbox", undefined, "Motion blur");
        cbSlideBlur.value = loadSetting("slideMotionBlur", "true") === "true";

        tabs.selection = 0;

        // ================= ACTIONS + PREVIEW =================
        var gActions = content.add("group");
        gActions.alignment = "fill";
        var btnTranscribe = gActions.add("button", undefined, "Transcribe");
        var btnLoadJson = gActions.add("button", undefined, "Load JSON");
        var btnGenerate = gActions.add("button", undefined, "Generate Captions");
        var btnClear = gActions.add("button", undefined, "Clear Generated");

        var stStatus = content.add("statictext", undefined, "Ready.");
        stStatus.alignment = "fill";

        var etPreview = content.add("edittext", undefined, "", {
            multiline: true, readonly: true, scrolling: true
        });
        etPreview.alignment = ["fill", "top"];
        etPreview.preferredSize.height = 90;

        // ---- helpers ----
        function status(msg) {
            stStatus.text = msg;
            win.update && win.update();
        }
        function host() { return etHost.text || "127.0.0.1"; }
        function port() { return parseInt(etPort.text, 10) || 8765; }
        function langCode() {
            var i = ddLang.selection ? ddLang.selection.index : 0;
            return ["ka-GE", "en-US", "auto"][i];
        }
        function providerId() {
            var i = ddProv.selection ? ddProv.selection.index : 0;
            return state.providerIds[i];
        }
        /* parseFloat with a fallback that survives a legitimate 0, which
           the "or default" idiom would swallow. */
        function num(text, fallback) {
            var v = parseFloat(text);
            return isNaN(v) ? fallback : v;
        }
        function shuffleVariants() {
            var picked = [];
            if (cbLookSolid.value) { picked.push("solid"); }
            if (cbLookHighlight.value) { picked.push("highlight"); }
            if (cbLookOutline.value) { picked.push("outline"); }
            return picked;
        }
        function gatherSettings() {
            var anchorIdx = ddAnchor.selection ? ddAnchor.selection.index : 0;
            var alignIdx = ddAlign.selection ? ddAlign.selection.index : 0;
            var presetIdx = lbPreset.selection ? lbPreset.selection.index : 0;
            return {
                font: currentFontPS(),
                fontSize: parseFloat(etFontSize.text) || 72,
                tracking: parseFloat(etTracking.text) || 0,
                lineHeight: parseFloat(etLineHeight.text) || 0,
                wordSpacing: num(etWordSpacing.text, 24),
                wordsPerLine: parseInt(etWordsPerLine.text, 10) || 0,
                minWordsPerLine: Math.max(1, parseInt(etMinWordsPerLine.text, 10) || 2),
                charsPerLine: parseInt(etCharsPerLine.text, 10) || 0,
                fauxBold: cbFauxBold.value,
                fauxItalic: cbFauxItalic.value,
                styleShuffle: cbShuffle.value,
                shuffleVariants: shuffleVariants(),
                shuffleFonts: KCF_splitList(etShuffleFonts.text),
                shuffleSeed: num(etShuffleSeed.text, 0),
                fill: cbFill.value,
                fillColor: KCF_hexToRgb(etFill.text),
                highlightColor: KCF_hexToRgb(etHighlight.text),
                shadow: cbShadow.value,
                stroke: cbStroke.value,
                strokeColor: KCF_hexToRgb(etStrokeColor.text),
                strokeWidth: num(etStrokeW.text, 7),
                strokePosition:
                    (ddStrokePos.selection && ddStrokePos.selection.index === 1)
                        ? "center" : "outer",
                shadowColor: KCF_hexToRgb(etShadowColor.text),
                shadowOpacity: num(etShadowOpacity.text, 60),
                shadowDistance: num(etShadowDistance.text, 8),
                shadowAngle: num(etShadowAngle.text, 135),
                shadowSoftness: num(etShadowSoftness.text, 12),
                backgroundBox: cbBox.value,
                boxColor: KCF_hexToRgb(etBoxColor.text),
                boxOpacity: Math.max(0, Math.min(100, num(etBoxOpacity.text, 100))),
                popScale: parseFloat(etPopScale.text) || 112,
                activeBoxColor: KCF_hexToRgb(etActiveBox.text),
                boxRadius: parseFloat(etBoxRadius.text) || 0,
                anchorPreset: ["bottom_center", "center", "top_center", "custom"][anchorIdx],
                alignment: ["center", "left", "right"][alignIdx],
                fitBoundary: cbFit.value,
                fitWidth: num(etFitWidth.text, 0),
                fitMaxFontSize: num(etFitMax.text, 260),
                fitMaxTracking: num(etFitTracking.text, 120),
                x: num(etX.text, 960),
                y: num(etY.text, 1600),
                verticalOffset: parseFloat(etVOffset.text) || 0,
                safeMargin: num(etSafe.text, 160),
                slideAngle: slideDial.value(),
                slideDistance: parseFloat(etSlideDistance.text) || 0,
                slideDuration: parseFloat(etSlideDuration.text) || 0.35,
                slideDolly: parseFloat(etSlideDolly.text) || 0,
                slideEaseIn: parseFloat(etSlideEaseIn.text),
                slideEaseOut: parseFloat(etSlideEaseOut.text),
                slideMotionBlur: cbSlideBlur.value,
                preset: KCF_PRESET_LABELS[presetIdx][0]
            };
        }
        function showPreview(doc, warnings) {
            var lines = [];
            if (warnings && warnings.length) {
                lines.push("WARNINGS: " + warnings.join(" | "), "");
            }
            for (var i = 0; i < doc.captions.length; i++) {
                var c = doc.captions[i];
                lines.push("[" + c.start.toFixed(2) + "-" + c.end.toFixed(2) + "] " + c.text);
            }
            etPreview.text = lines.join("\n");
        }
        function persistSettings() {
            saveSetting("host", etHost.text);
            saveSetting("port", etPort.text);
            saveSetting("font", currentFontPS());
            saveSetting("fontSize", etFontSize.text);
            saveSetting("wordSpacing", etWordSpacing.text);
            saveSetting("wordsPerLine", etWordsPerLine.text);
            saveSetting("minWordsPerLine", etMinWordsPerLine.text);
            saveSetting("charsPerLine", etCharsPerLine.text);
            saveSetting("fillColor", etFill.text);
            saveSetting("highlightColor", etHighlight.text);
            saveSetting("minWords", etMinWords.text);
            saveSetting("maxWords", etMaxWords.text);
            saveSetting("maxChars", etMaxChars.text);
            saveSetting("pauseBreakSeconds", etPause.text);
            saveSetting("minCaptionDuration", etMinDur.text);
            saveSetting("maxCaptionDuration", etMaxDur.text);
            saveSetting("removeCommasAndPeriods", cbRemoveCommasPeriods.value);
            saveSetting("popScale", etPopScale.text);
            saveSetting("activeBoxColor", etActiveBox.text);
            saveSetting("boxRadius", etBoxRadius.text);
            saveSetting("slideAngle", slideDial.value());
            saveSetting("slideDistance", etSlideDistance.text);
            saveSetting("slideDuration", etSlideDuration.text);
            saveSetting("slideDolly", etSlideDolly.text);
            saveSetting("slideEaseIn", etSlideEaseIn.text);
            saveSetting("slideEaseOut", etSlideEaseOut.text);
            saveSetting("slideMotionBlur", cbSlideBlur.value);
            saveSetting("fauxBold", cbFauxBold.value);
            saveSetting("fauxItalic", cbFauxItalic.value);
            saveSetting("fill", cbFill.value);
            saveSetting("stroke", cbStroke.value);
            saveSetting("strokeWidth", etStrokeW.text);
            saveSetting("strokeColor", etStrokeColor.text);
            saveSetting("strokePosition",
                (ddStrokePos.selection && ddStrokePos.selection.index === 1)
                    ? "center" : "outer");
            saveSetting("backgroundBox", cbBox.value);
            saveSetting("boxColor", etBoxColor.text);
            saveSetting("boxOpacity", etBoxOpacity.text);
            saveSetting("shadow", cbShadow.value);
            saveSetting("shadowColor", etShadowColor.text);
            saveSetting("shadowOpacity", etShadowOpacity.text);
            saveSetting("shadowDistance", etShadowDistance.text);
            saveSetting("shadowAngle", etShadowAngle.text);
            saveSetting("shadowSoftness", etShadowSoftness.text);
            saveSetting("styleShuffle", cbShuffle.value);
            saveSetting("shuffleSolid", cbLookSolid.value);
            saveSetting("shuffleHighlight", cbLookHighlight.value);
            saveSetting("shuffleOutline", cbLookOutline.value);
            saveSetting("shuffleSeed", etShuffleSeed.text);
            saveSetting("shuffleFonts", etShuffleFonts.text);
            saveSetting("fitBoundary", cbFit.value);
            saveSetting("fitWidth", etFitWidth.text);
            saveSetting("fitMaxFontSize", etFitMax.text);
            saveSetting("fitMaxTracking", etFitTracking.text);
        }

        // ---- handlers ----
        btnBrowse.onClick = function () {
            var f = File.openDialog("Select audio/video file");
            if (f) {
                state.mediaPath = f.fsName;
                etMedia.text = f.fsName;
            }
        };
        etMedia.onChange = function () { state.mediaPath = etMedia.text; };

        /* Footage file behind a layer, or null. Follows one precomp level. */
        function footageFileOfLayer(layer, depth) {
            if (!layer || !layer.source) { return null; }
            var src = layer.source;
            if (src instanceof FootageItem && src.file &&
                    !(src.mainSource instanceof SolidSource)) {
                return src.file;
            }
            if (src instanceof CompItem && depth > 0) {
                return firstFootageFileInComp(src, depth - 1);
            }
            return null;
        }
        function firstFootageFileInComp(comp, depth) {
            var fallback = null;
            for (var i = 1; i <= comp.numLayers; i++) {
                var f = footageFileOfLayer(comp.layer(i), depth);
                if (!f) { continue; }
                var hasAudio = false;
                try { hasAudio = comp.layer(i).hasAudio; } catch (e) {}
                if (hasAudio) { return f; }       // prefer layers with audio
                if (!fallback) { fallback = f; }
            }
            return fallback;
        }
        btnFromComp.onClick = function () {
            var comp = app.project ? app.project.activeItem : null;
            if (!(comp && comp instanceof CompItem)) {
                alert("No active composition selected.");
                return;
            }
            // selected layer wins, else first audio footage layer in comp
            var file = null;
            for (var s = 0; s < comp.selectedLayers.length && !file; s++) {
                file = footageFileOfLayer(comp.selectedLayers[s], 1);
            }
            if (!file) { file = firstFootageFileInComp(comp, 1); }
            if (!file) {
                alert("No footage file found in this comp. Select the video " +
                      "layer or use Browse.");
                return;
            }
            state.mediaPath = file.fsName;
            etMedia.text = file.fsName;
            status("Media from comp: " + file.displayName);
        };

        btnHealth.onClick = function () {
            status("Testing backend at " + host() + ":" + port() + "…");
            try {
                var h = KCF_httpJSON("GET", host(), port(), "/health", null);
                status("Backend OK v" + h.version + ". Providers ready: " +
                    (h.availableProviders.join(", ") || "none (add API keys)"));
            } catch (e) {
                alert(e.message);
                status("Backend not reachable.");
            }
        };

        btnScan.onClick = function () {
            try {
                status("Scanning providers…");
                var resp = KCF_httpJSON("GET", host(), port(), "/providers", null);
                var ids = [], labels = [];
                for (var i = 0; i < resp.providers.length; i++) {
                    var p = resp.providers[i];
                    ids.push(p.id);
                    labels.push((p.available ? "✓ " : "✗ ") + p.label +
                        (p.available ? "" : "  (" + (p.detail || "unavailable") + ")"));
                }
                state.providerIds = ids;
                var keep = ddProv.selection ? ddProv.selection.index : 0;
                ddProv.removeAll();
                for (var j = 0; j < labels.length; j++) { ddProv.add("item", labels[j]); }
                ddProv.selection = Math.min(keep, labels.length - 1);
                status("Provider scan done.");
            } catch (e) {
                alert(e.message);
                status("Scan failed.");
            }
        };

        btnTranscribe.onClick = function () {
            if (!state.mediaPath) {
                btnFromComp.onClick();           // try the active comp's footage
            }
            if (!state.mediaPath) {
                alert("Select a media file first.");
                return;
            }
            persistSettings();
            var providerOptions = { diarize: cbDiarize.value };
            if (etModel.text) { providerOptions.model = etModel.text; }
            if (etKeyterms.text) {
                var terms = etKeyterms.text.split(",");
                var clean = [];
                for (var t = 0; t < terms.length; t++) {
                    var term = terms[t].replace(/^\s+|\s+$/g, "");
                    if (term) { clean.push(term); }
                }
                if (clean.length) { providerOptions.keyterms = clean; }
            }
            var payload = {
                mediaPath: state.mediaPath,
                language: langCode(),
                provider: providerId(),
                providerOptions: providerOptions,
                grouping: {
                    minWords: Math.min(parseInt(etMinWords.text, 10) || 2,
                        Math.max(1, parseInt(etMaxWords.text, 10) || 4)),
                    maxWords: parseInt(etMaxWords.text, 10) || 4,
                    maxChars: parseInt(etMaxChars.text, 10) || 42,
                    pauseBreakSeconds: parseFloat(etPause.text) || 0.55,
                    minCaptionDuration: parseFloat(etMinDur.text) || 0.5,
                    maxCaptionDuration: parseFloat(etMaxDur.text) || 3.5,
                    removeCommasAndPeriods: cbRemoveCommasPeriods.value
                }
            };
            try {
                status("Transcribing (" + providerId() + ")… this can take a while.");
                var resp = KCF_httpJSON("POST", host(), port(), "/transcribe", payload);
                state.doc = resp.document;
                showPreview(state.doc, resp.warnings);
                status("Transcribed: " + state.doc.words.length + " words, " +
                    state.doc.captions.length + " captions. Debug: " +
                    resp.debugPaths.normalizedJson);
            } catch (e) {
                alert(e.message);
                status("Transcription failed.");
            }
        };

        btnLoadJson.onClick = function () {
            var f = File.openDialog("Select normalized.json");
            if (!f) { return; }
            try {
                f.encoding = "UTF-8";
                f.open("r");
                var text = f.read();
                f.close();
                var doc = JSON.parse(text);
                if (!doc.captions) { throw new Error("Not a normalized transcript JSON."); }
                state.doc = doc;
                showPreview(doc, []);
                status("Loaded " + doc.captions.length + " captions from JSON.");
            } catch (e) {
                alert("Could not load JSON: " + e.message);
            }
        };

        btnGenerate.onClick = function () {
            if (!state.doc) {
                alert("No transcript. Transcribe or load a JSON first.");
                return;
            }
            persistSettings();
            try {
                var name = KCF_generate(state.doc, gatherSettings());
                status("Generated precomp: " + name);
            } catch (e) {
                alert(e.message);
                status("Generation failed.");
            }
        };

        btnClear.onClick = function () {
            if (!confirm("Delete all CapForge-owned caption precomps from this project? " +
                    "Older unmarked precomps will be kept.")) {
                return;
            }
            var n = KCF_clearGenerated();
            status("Removed " + n + " generated precomp(s).");
        };

        /* ---- scrolling ----
           ScriptUI has no scrollable container, so the scrollbar shifts
           content.location.y and the window clips what hangs out.

           The catch: layout.resize() clamps content.size down to the
           viewport, so measuring content.size reports zero overflow while
           the controls below it are quietly cut off — the scrollbar then
           hides itself exactly when it is needed. preferredSize is the
           height the content actually asked for, so measure that and pin
           the group to it. */
        function updateScroll() {
            if (!scroller.size) { return; }
            var wanted = content.preferredSize.height;
            var viewport = scroller.size.height;
            if (wanted <= 0 || viewport <= 0) { return; }
            if (content.size.height < wanted) {
                content.size.height = wanted;      // undo the clamp
            }
            var overflow = wanted - viewport;
            if (overflow > 0) {
                sbScroll.visible = true;
                sbScroll.minvalue = 0;
                sbScroll.maxvalue = overflow;
                sbScroll.jumpdelta = Math.max(20, viewport - 40);
                if (sbScroll.value > overflow) { sbScroll.value = overflow; }
            } else {
                sbScroll.visible = false;
                sbScroll.value = 0;
            }
            content.location.y = -Math.round(sbScroll.value);
        }
        sbScroll.onChanging = sbScroll.onChange = function () {
            content.location.y = -Math.round(sbScroll.value);
        };
        tabs.onChange = function () { updateScroll(); };

        win.onResizing = win.onResize = function () {
            this.layout.resize();
            updateScroll();
        };
        // sizes are only real once AE has shown the panel
        win.onShow = function () { updateScroll(); };
        win.layout.layout(true);
        win.layout.resize();
        if (win instanceof Window) {
            /* Sizing to content would now open a window taller than the
               display; cap it and let the scrollbar reach the rest. */
            var roomy = 900;
            try {
                roomy = Math.max(420, $.screens[0].bottom - $.screens[0].top - 140);
            } catch (eScreen) { /* no screen metrics available */ }
            if (win.size.height > roomy) {
                win.size.height = roomy;
                win.layout.resize();
            }
            win.center();
            win.show();
        }
        updateScroll();
        return win;
    }

    buildUI(thisObj);

})(this);
