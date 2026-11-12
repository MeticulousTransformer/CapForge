/* Exercise the real CEP host with ExtendScript's caller-scoped evalFile.
   Node's ordinary vm.runInContext always uses global scope and masks this bug. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vm = require("node:vm");
const { makePrecomp, SETTINGS } = require("./ae_stub.js");
const repo = path.resolve(__dirname, "../..");

function host() {
    function File(name) {
        this.fsName = String(name);
        this.name = encodeURIComponent(path.basename(this.fsName));
        this.exists = fs.existsSync(this.fsName);
    }
    function Folder(name) {
        this.fsName = path.resolve(String(name));
        this.exists = fs.existsSync(this.fsName);
    }
    Object.defineProperty(File.prototype, "parent", { get() { return new Folder(path.dirname(this.fsName)); } });
    Object.defineProperty(Folder.prototype, "parent", { get() { return new Folder(path.dirname(this.fsName)); } });
    File.prototype.open = function () { return this.exists; };
    File.prototype.read = function () { return fs.readFileSync(this.fsName, "utf8"); };
    File.prototype.close = function () {};
    Folder.prototype.getFiles = function () {
        return fs.readdirSync(this.fsName).filter(p => p.endsWith(".jsx")).map(p => new File(path.join(this.fsName, p)));
    };
    // Direct eval is deliberately inserted at the call site so variables and
    // functions live in the caller, as $.evalFile does in ExtendScript.
    function source(file) {
        return fs.readFileSync(file.fsName, "utf8").replace(/\$\.evalFile\(([^;\n]+)\)/g, "eval(__readScript($1))");
    }
    const context = {
        File, Folder, JSON: undefined, __readScript: source,
        $: { fileName: "/unrelated/Other Extension.jsx" },
        CompItem: function () {}, FolderItem: function () {},
        ParagraphJustification: { LEFT_JUSTIFY: 1 },
        KeyframeInterpolationType: { HOLD: 2 },
        KeyframeEase: function (speed, influence) { this.speed = speed; this.influence = influence; },
        app: { project: null, beginUndoGroup() {}, endUndoGroup() {} }
    };
    vm.createContext(context);
    vm.runInContext(source(new File(path.join(repo, "panel/host.jsx"))), context);
    return context;
}

function dispatch(context, action, payload) {
    return JSON.parse(context.KCF_dispatch(JSON.stringify({ action, payload })));
}

const document = {
    words: [{ id: 0, text: "გამარჯობა", start: 0.2, end: 0.6, punctuationAfter: "" }],
    captions: [{ id: 0, text: "გამარჯობა", start: 0.2, end: 0.8, wordIds: [0] }],
    duration: 1
};

test("fresh host can list presets after caller-scoped initialization has returned", () => {
    const context = host();
    const initialized = JSON.parse(context.KCF_initialize(path.join(repo, "panel")));
    assert.equal(initialized.ok, true, initialized.error);
    const response = dispatch(context, "context");
    assert.equal(response.ok, true, response.error);
    assert.ok(response.data.presets.some(entry => entry[0] === "highlight_word"));
    assert.ok(response.data.presets.some(entry => entry[0] === "soft_rise"));
});

test("loaded engine keeps its helpers alive to generate Georgian captions in later calls", () => {
    const context = host();
    const precomps = [], inserted = [];
    const active = new context.CompItem();
    Object.assign(active, { width: 1080, height: 1920, duration: 5, pixelAspect: 1, frameRate: 25,
        layers: { add(comp) { inserted.push(comp); return { moveToBeginning() {} }; } } });
    context.app.project = { activeItem: active, numItems: 0, items: {
        addFolder(name) { return { name }; },
        addComp(name, width, height) {
            const comp = Object.assign(makePrecomp({ width, height }), { name });
            precomps.push(comp);
            return comp;
        }
    } };
    const original = JSON.stringify(document);
    const initialized = JSON.parse(context.KCF_initialize(path.join(repo, "panel")));
    assert.equal(initialized.ok, true, initialized.error);
    for (const preset of ["minimal", "soft_rise"]) {
        const response = dispatch(context, "generate", { document, settings: { ...SETTINGS, preset } });
        assert.equal(response.ok, true, response.error);
        assert.match(response.data.name, /^KCF_Captions_/);
    }
    assert.equal(precomps.length, 2);
    assert.equal(inserted.length, 2);
    assert.equal(precomps[0].created.length, 1);
    assert.equal(precomps[1].created[0].transform("Position").keys.length, 2);
    assert.equal(JSON.stringify(document), original);
});

test("reinitialization refreshes titles and blocks calls after a failed repair", () => {
    const context = host();
    for (let attempt = 0; attempt < 2; attempt++) {
        const initialized = JSON.parse(context.KCF_initialize(path.join(repo, "panel")));
        assert.equal(initialized.ok, true, initialized.error);
        const response = dispatch(context, "context");
        assert.equal(response.ok, true, response.error);
        assert.equal(response.data.presets.filter(entry => entry[0] === "soft_rise").length, 1);
    }
    const initialized = JSON.parse(context.KCF_initialize(path.join(repo, "missing-runtime", "panel")));
    assert.equal(initialized.ok, false);
    assert.equal(dispatch(context, "context").ok, false);
});

test("installed host loads from a separate runtime with spaces and Georgian characters", () => {
    const base = fs.mkdtempSync(path.join(os.tmpdir(), "capforge-host-"));
    try {
        const extension = path.join(base, "CEP ქართული"), runtime = path.join(base, "Runtime ქართული");
        fs.mkdirSync(extension);
        fs.cpSync(path.join(repo, "ae"), path.join(runtime, "ae"), { recursive: true });
        fs.copyFileSync(path.join(repo, "ae/lib/json2.js"), path.join(extension, "json2.js"));
        fs.writeFileSync(path.join(extension, "install.json"), "\uFEFF" + JSON.stringify({ tool: "CapForge", runtimeRoot: runtime }));
        const context = host();
        const initialized = JSON.parse(context.KCF_initialize(extension));
        assert.equal(initialized.ok, true, initialized.error);
        const response = dispatch(context, "context");
        assert.equal(response.ok, true, response.error);
        assert.ok(response.data.presets.some(entry => entry[0] === "soft_rise"));
    } finally { fs.rmSync(base, { recursive: true, force: true }); }
});

test("media selection displays encoded punctuation and Georgian names exactly", () => {
    const context = host();
    const initialized = JSON.parse(context.KCF_initialize(path.join(repo, "panel")));
    assert.equal(initialized.ok, true, initialized.error);
    const media = new context.File("/Footage/50% ქართული #1.mp4");
    context.File.openDialog = () => media;
    const chosen = dispatch(context, "chooseMedia");
    assert.equal(chosen.ok, true, chosen.error);
    assert.deepEqual(chosen.data, { path: media.fsName, name: "50% ქართული #1.mp4" });
    const comp = new context.CompItem();
    comp.selectedLayers = [{ source: { file: media } }];
    context.app.project = { activeItem: comp };
    const selected = dispatch(context, "selectedMedia");
    assert.equal(selected.ok, true, selected.error);
    assert.deepEqual(selected.data, chosen.data);
});
