/* CEP's only host entry. Strings cross as JSON; never as executable user code. */
var KCF_hostRoot = null;
var KCF_runtimeRoot = null;
var KCF_hostError = "The caption engine has not been initialized.";
var KCF_engine = null;

// CEP provides this path explicitly. $.fileName can refer to another AE script.
function KCF_initialize(extensionPath) {
    KCF_engine = null;
    try {
        KCF_hostRoot = new Folder(extensionPath);
        KCF_runtimeRoot = KCF_hostRoot.parent;
        var shim = new File(KCF_hostRoot.fsName + "/json2.js");
        if (!shim.exists) { shim = new File(KCF_runtimeRoot.fsName + "/ae/lib/json2.js"); }
        if (!shim.exists) { throw new Error("The JSON support file is missing from " + KCF_hostRoot.fsName + ". Run CapForge Setup to repair it."); }
        $.evalFile(shim);
        var config = new File(KCF_hostRoot.fsName + "/install.json");
        if (config.exists) {
            var marker = JSON.parse(KCF_hostRead(config).replace(/^\uFEFF/, ""));
            if ((marker.tool !== "CapForge" && marker.tool !== "Kartuli Caption Forge") || typeof marker.runtimeRoot !== "string" || !marker.runtimeRoot) {
                throw new Error("The CapForge installation configuration is invalid.");
            }
            KCF_runtimeRoot = new Folder(marker.runtimeRoot);
        }
        var libraries = ["json2.js", "text_measure.jsx", "style_shuffle.jsx", "presets.jsx", "title_registry.jsx", "layer_builder.jsx"];
        for (var i = 0; i < libraries.length; i++) {
            var library = new File(KCF_runtimeRoot.fsName + "/ae/lib/" + libraries[i]);
            if (!library.exists) { throw new Error("Missing caption engine file: " + library.fsName + ". Run CapForge Setup to repair it."); }
            $.evalFile(library);
        }
        KCF_loadTitles(new Folder(KCF_runtimeRoot.fsName + "/ae/titles"));
        // ExtendScript evaluates these files in this function's scope. Keep
        // the engine and its closure available to later CEP dispatch calls.
        KCF_engine = { generate: KCF_generate, presets: KCF_PRESETS, labels: KCF_PRESET_LABELS };
        KCF_hostError = null;
        return JSON.stringify({ ok: true, data: true });
    } catch (error) {
        KCF_hostError = "Caption engine could not load: " + error.toString();
        // JSON may be unavailable when even the local shim is missing.
        if (typeof JSON !== "undefined" && JSON.stringify) { return JSON.stringify({ ok: false, error: KCF_hostError }); }
        return "EvalScript error.";
    }
}

function KCF_hostRead(file) {
    file.encoding = "UTF-8";
    if (!file.open("r")) { throw new Error("Could not read the file."); }
    try { return file.read(); } finally { file.close(); }
}
function KCF_hostComp() {
    var comp = app.project && app.project.activeItem;
    if (!(comp && comp instanceof CompItem)) { return null; }
    return { name: comp.name, width: comp.width, height: comp.height, duration: comp.duration, frameRate: comp.frameRate };
}
function KCF_hostFonts() {
    var found = [], seen = {};
    try {
        var groups = app.fonts.allFonts;
        for (var i = 0; i < groups.length; i++) {
            for (var j = 0; j < groups[i].length; j++) {
                var font = groups[i][j];
                if (!seen[font.postScriptName]) { found.push({ name: font.postScriptName, family: font.familyName, style: font.styleName }); seen[font.postScriptName] = true; }
            }
        }
    } catch (error) { /* Font enumeration is unavailable in older AE releases. */ }
    return found;
}
function KCF_hostValidate(doc, settings) {
    function number(value) { return typeof value === "number" && isFinite(value); }
    function integer(value) { return number(value) && value >= 0 && value % 1 === 0; }
    function array(value) { return Object.prototype.toString.call(value) === "[object Array]"; }
    if (!doc || !array(doc.words) || !array(doc.captions) || !doc.words.length || !doc.captions.length || doc.words.length > 20000 || doc.captions.length > 10000) { throw new Error("A valid word-timed transcript is required."); }
    if (!settings || !KCF_engine.presets.hasOwnProperty(settings.preset) || !number(settings.fontSize) || !(settings.fontSize >= 8 && settings.fontSize <= 600)) { throw new Error("Choose a registered style and a valid font size."); }
    var seen = {}, used = {}, captionIds = {}, previous = -1;
    for (var i = 0; i < doc.words.length; i++) {
        var w = doc.words[i];
        if (!w || !integer(w.id) || seen[w.id] || typeof w.text !== "string" || !/\S/.test(w.text) || /[\r\n]/.test(w.text) || w.text.length > 200 || !(number(w.start) && number(w.end) && w.start >= 0 && w.end > w.start && w.start >= previous)) { throw new Error("Invalid word or timing in transcript."); }
        if (w.punctuationAfter !== undefined && (typeof w.punctuationAfter !== "string" || w.punctuationAfter.length > 16 || /[\r\n]/.test(w.punctuationAfter))) { throw new Error("Word punctuation must be a short string without line breaks."); }
        seen[w.id] = w; previous = w.start;
    }
    previous = -1;
    for (var ci = 0; ci < doc.captions.length; ci++) {
        var c = doc.captions[ci], last = -1;
        if (!c || !integer(c.id) || captionIds[c.id] || !(number(c.start) && number(c.end) && c.start >= 0 && c.end > c.start && c.start >= previous) || !array(c.wordIds) || !c.wordIds.length || c.wordIds.length > 100) { throw new Error("Invalid caption interval."); }
        captionIds[c.id] = true;
        previous = c.end;
        for (var wi = 0; wi < c.wordIds.length; wi++) {
            var word = seen[c.wordIds[wi]];
            if (!integer(c.wordIds[wi]) || !word || used[word.id] || word.start < last || word.start < c.start - 0.001 || word.end > c.end + 0.001) { throw new Error("Invalid caption word reference."); }
            used[word.id] = true; last = word.start;
        }
    }
    for (var id in seen) { if (seen.hasOwnProperty(id) && !used[id]) { throw new Error("Every word must belong to a caption."); } }
}
function KCF_dispatch(json) {
    try {
        if (KCF_hostError) { throw new Error(KCF_hostError); }
        var request = JSON.parse(json), data = null, payload = request.payload || {};
        switch (request.action) {
        case "context": data = { comp: KCF_hostComp(), fonts: KCF_hostFonts(), presets: KCF_engine.labels }; break;
        case "token":
            var tokenFile = new File(KCF_runtimeRoot.fsName + "/backend/.local-token");
            data = tokenFile.exists ? KCF_hostRead(tokenFile).replace(/\s/g, "") : "";
            break;
        case "chooseMedia":
            var media = File.openDialog("Choose video or audio with speech");
            data = media ? { path: media.fsName, name: decodeURIComponent(media.name) } : null;
            break;
        case "selectedMedia":
            var comp = app.project && app.project.activeItem;
            if (!(comp && comp instanceof CompItem)) { throw new Error("Open a composition and select a footage layer."); }
            var layers = comp.selectedLayers;
            for (var i = 0; i < layers.length; i++) {
                var source = layers[i].source;
                if (source && source.file) { data = { path: source.file.fsName, name: decodeURIComponent(source.file.name) }; break; }
            }
            if (!data) { throw new Error("Select a video or audio footage layer in the active composition."); }
            break;
        case "startService":
            var isWindows = $.os.indexOf("Windows") === 0;
            var launcher = new File(KCF_runtimeRoot.fsName + (isWindows ? "/run_backend.bat" : "/run_backend.command"));
            if (!launcher.exists || !launcher.execute()) { throw new Error("Could not launch the service. Run the Start service shortcut from your installation folder."); }
            data = true; break;
        case "saveJSON":
            var destination = File.saveDialog("Save " + (payload.kind === "look" ? "caption look" : "word-timed transcript"), "*.json");
            if (destination) {
                if (!/\.json$/i.test(destination.name)) { destination = new File(destination.fsName + ".json"); }
                destination.encoding = "UTF-8";
                if (!destination.open("w")) { throw new Error("Could not write the selected file."); }
                try { destination.write(JSON.stringify(payload.data, null, 2)); } finally { destination.close(); }
                data = true;
            }
            break;
        case "generate":
            KCF_hostValidate(payload.document, payload.settings);
            data = { name: KCF_engine.generate(payload.document, payload.settings) }; break;
        default: throw new Error("Unknown CapForge action.");
        }
        return JSON.stringify({ ok: true, data: data });
    } catch (error) {
        return JSON.stringify({ ok: false, error: error.toString() });
    }
}
