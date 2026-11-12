const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const vm = require('node:vm');
const repo = path.resolve(__dirname, '../..');

function host() {
    function File(name) {this.fsName = path.resolve(String(name)); this.name = path.basename(this.fsName); this.exists = fs.existsSync(this.fsName);}
    function Folder(name) {this.fsName = path.resolve(String(name)); this.exists = fs.existsSync(this.fsName);}
    Object.defineProperty(File.prototype, 'parent', {get() {return new Folder(path.dirname(this.fsName));}});
    Object.defineProperty(Folder.prototype, 'parent', {get() {return new Folder(path.dirname(this.fsName));}});
    File.prototype.open = function () {return this.exists;};
    File.prototype.read = function () {return fs.readFileSync(this.fsName, 'utf8');};
    File.prototype.close = function () {};
    Folder.prototype.getFiles = function () {return fs.readdirSync(this.fsName).filter(p => p.endsWith('.jsx')).map(p => new File(path.join(this.fsName, p)));};
    const context = {File, Folder, JSON: undefined, app: {project: null}};
    context.$ = {fileName: 'C:/unrelated/AnotherExtension.jsx', evalFile(file) {vm.runInContext(fs.readFileSync(file.fsName, 'utf8'), context);}};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(repo, 'panel/host.jsx'), 'utf8'), context);
    return context;
}

test('host loads source engine using the explicit CEP path, with no native JSON', () => {
    const context = host();
    assert.equal(JSON.parse(context.KCF_initialize(path.join(repo, 'panel'))).ok, true);
    assert.equal(context.KCF_runtimeRoot.fsName, repo);
    assert.equal(Object.keys(context.KCF_PRESETS).length, 13);
    assert.equal(JSON.parse(context.KCF_dispatch('{"action":"context"}')).ok, true);
});

test('installed bootstrap reads its separate runtime and tolerates a UTF-8 BOM', () => {
    const base = fs.mkdtempSync(path.join(os.tmpdir(), 'capforge-bootstrap-'));
    try {
        const extension = path.join(base, 'CEP with spaces ქართული'); fs.mkdirSync(extension);
        fs.copyFileSync(path.join(repo, 'ae/lib/json2.js'), path.join(extension, 'json2.js'));
        fs.writeFileSync(path.join(extension, 'install.json'), '\uFEFF' + JSON.stringify({tool: 'CapForge', runtimeRoot: repo}));
        const context = host();
        assert.equal(JSON.parse(context.KCF_initialize(extension)).ok, true);
        assert.equal(context.KCF_runtimeRoot.fsName, repo);
        fs.writeFileSync(path.join(extension, 'install.json'), JSON.stringify({tool: 'Other', runtimeRoot: repo}));
        assert.equal(JSON.parse(context.KCF_initialize(extension)).ok, false);
        assert.equal(JSON.parse(context.KCF_dispatch('{"action":"context"}')).ok, false);
    } finally {fs.rmSync(base, {recursive: true, force: true});}
});

test('bridge initializes once, normalizes platform URLs and safely passes paths as strings', async () => {
    for (const [raw, normalized] of [['file:///C:/CEP/My%20Panel', 'C:/CEP/My Panel'], ['file:///Users/editor/CEP', '/Users/editor/CEP'], ['C:\\CEP\\Quoted"Panel', 'C:/CEP/Quoted"Panel']]) {
        const codes = [];
        const window = {__adobe_cep__: {getSystemPath: type => {assert.equal(type, 'extension'); return raw;}, evalScript(code, callback) {codes.push(code); callback('{"ok":true,"data":true}');}}};
        vm.runInNewContext(fs.readFileSync(path.join(repo, 'panel/js/bridge.js'), 'utf8'), {window});
        await Promise.all([window.KCF_Bridge.call('context'), window.KCF_Bridge.call('token')]);
        assert.equal(codes.filter(code => code.startsWith('$.evalFile')).length, 1);
        assert.ok(codes[0].includes('KCF_initialize(' + JSON.stringify(normalized) + ')'));
        assert.equal(codes.length, 3);
    }
});

test('failed initialization can retry after the installation is repaired', async () => {
    let attempt = 0;
    const window = {__adobe_cep__: {getSystemPath: () => 'C:/CEP/CapForge', evalScript(code, callback) {callback(code.startsWith('$.evalFile') && attempt++ === 0 ? '{"ok":false,"error":"Missing engine"}' : '{"ok":true,"data":true}');}}};
    vm.runInNewContext(fs.readFileSync(path.join(repo, 'panel/js/bridge.js'), 'utf8'), {window});
    await assert.rejects(window.KCF_Bridge.call('context'), /Missing engine/);
    assert.equal(await window.KCF_Bridge.call('context'), true);
});

test('bridge preserves literal percent names and decodes reserved characters in file URLs', async () => {
    for (const [raw, normalized] of [
        ['C:\\Users\\100% editor\\CEP', 'C:/Users/100% editor/CEP'],
        ['/Users/editor%20name/CEP', '/Users/editor%20name/CEP'],
        ['file:///Users/editor%23one/100%25%20%E1%83%A5%E1%83%90%E1%83%A0%E1%83%97%E1%83%A3%E1%83%9A%E1%83%98/CEP', '/Users/editor#one/100% ქართული/CEP'],
        ['file:///C:/Users/editor%26studio/CEP', 'C:/Users/editor&studio/CEP']
    ]) {
        const codes = [];
        const window = {__adobe_cep__: {getSystemPath: () => raw, evalScript(code, callback) {codes.push(code); callback('{"ok":true,"data":true}');}}};
        vm.runInNewContext(fs.readFileSync(path.join(repo, 'panel/js/bridge.js'), 'utf8'), {window});
        await window.KCF_Bridge.call('context');
        assert.ok(codes[0].includes('KCF_initialize(' + JSON.stringify(normalized) + ')'), raw);
    }
});
