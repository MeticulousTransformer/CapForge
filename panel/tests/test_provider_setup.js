const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const guides = require('../js/provider_guide');
const root = path.resolve(__dirname, '../..');

test('onboarding covers the registry and exactly the supported credential fields', () => {
    const registry = fs.readFileSync(path.join(root, 'backend/services/provider_registry.py'), 'utf8');
    const adapters = [...registry.matchAll(/from providers\.(\w+) import/g)].map(m => m[1]).filter(name => name !== 'base');
    for (const adapter of adapters) {
        const code = fs.readFileSync(path.join(root, 'backend/providers', adapter + '.py'), 'utf8');
        const id = code.match(/    id = "([^"]+)"/)[1];
        assert.ok(guides.get(id), id);
    }
    const credentials = fs.readFileSync(path.join(root, 'backend/services/studio_settings.py'), 'utf8');
    const allowed = [...credentials.match(/ALLOWED_KEYS = \{([^}]+)\}/)[1].matchAll(/"([^"]+)"/g)].map(m => m[1]);
    assert.deepEqual(guides.list.filter(p => p.key).map(p => p.key).sort(), allowed.sort());
    for (const guide of guides.list) {
        assert.equal(guide.steps.length, 3);
        assert.equal(new URL(guide.url).protocol, 'https:');
        assert.equal(new URL(guide.url).search, '');
        assert.equal(guides.get(guide.key || guide.id), guide);
    }
    assert.equal(guides.get('unknown'), null);
});

function links(window) {
    window.KCF_ProviderGuide = guides;
    vm.runInNewContext(fs.readFileSync(path.join(root, 'panel/js/external_links.js'), 'utf8'), { window });
    return window.KCF_ExternalLinks;
}

test('CEP opens account links through the default browser and blocks injected URLs', () => {
    const calls = [];
    const api = links({ __adobe_cep__: {}, cep: {util: {openURLInDefaultBrowser: url => { calls.push(url); return {err: 0}; }}} });
    for (const guide of guides.list) api.open(guide.url);
    assert.deepEqual(calls, guides.urls);
    for (const bad of ['javascript:alert(1)', 'file:///secret', guides.urls[0] + '?key=secret', 'https://evil.example']) {
        assert.throws(() => api.open(bad), /not allowed/);
    }
    assert.equal(calls.length, guides.list.length);
});

test('demo account links isolate the new tab; missing CEP opener reports useful help', () => {
    const calls = [];
    const tab = {opener: {}};
    links({open: (...args) => {calls.push(args); return tab;}}).open(guides.urls[0]);
    assert.deepEqual(calls[0], [guides.urls[0], '_blank', 'noopener,noreferrer']);
    assert.equal(tab.opener, null);
    assert.throws(() => links({__adobe_cep__: {}}).open(guides.urls[0]), /Visit https:/);
    assert.throws(() => links({cep: {util: {openURLInDefaultBrowser: () => ({err: 1})}}}).open(guides.urls[0]), /could not open/);
});

async function studio(options = {}) {
    // Minimal DOM model: tests behavior only, without launching or rendering a browser.
    const elements = new Map();
    function element(id = '') {
        return {id, value: '', type: 'password', dataset: {}, children: [], events: {}, attributes: {},
            classList: {add() {}, remove() {}, toggle() {}},
            addEventListener(name, fn) { this.events[name] = fn; },
            setAttribute(name, value) { this.attributes[name] = value; },
            appendChild(child) { this.children.push(child); },
            focus() {}, querySelectorAll() {return [];},
            set textContent(value) {this.text = value; this.children = [];},
            get textContent() {return this.text || '';}
        };
    }
    const html = fs.readFileSync(path.join(root, 'panel/index.html'), 'utf8');
    for (const match of html.matchAll(/id="([^"]+)"/g)) elements.set(match[1], element(match[1]));
    const $ = id => {assert.ok(elements.has(id), id); return elements.get(id);};
    $('language').value = 'ka-GE'; $('key-provider').value = 'ELEVENLABS_API_KEY'; $('provider').value = 'elevenlabs';
    const panes = ['source', 'design', 'transcript', 'setup'].map(id => $('tab-' + id));
    const windowEvents = {}, calls = [], storage = new Map();
    const configured = new Set(options.configured || []);
    if (options.saved) storage.set("kcf.studio.v1", JSON.stringify(options.saved));
    const providers = () => guides.list.map(p => ({id: p.id, label: p.name, type: p.key ? 'cloud' : 'local', available: configured.has(p.id)}));
    const window = {
        addEventListener: (name, fn) => {windowEvents[name] = fn;},
        KCF_Settings: require('../js/settings'), KCF_Titles: require('../js/catalog'),
        KCF_Transcript: require('../js/transcript'), KCF_ProviderGuide: guides,
        KCF_DesignControls: {mountDial: () => ({sync() {}}), fontGroups: () => ({})},
        KCF_Preview: {create: () => ({set() {}, context() {}, pause() {}, destroy() {}})},
        KCF_Bridge: {available: true, call: async action => {
            if (options.host) await options.host(action);
            return action === 'context' ? {comp: null, fonts: []} : 'test-token';
        }},
        KCF_API: {setToken() {}, request: async (route, payload) => {
            calls.push({route, payload});
            if (route === '/health') {if (options.health) await options.health(); return {ffmpeg: true};}
            if (route === '/providers') return {providers: providers()};
            if (route === '/settings/provider-key') {if (options.save) await options.save(); configured.add(guides.get(payload.name).id); return {ok: true};}
        }}
    };
    const document = {getElementById: $, createElement: () => element(), body: element(), addEventListener() {},
        querySelector: () => element(), querySelectorAll: selector => selector === '.tab-pane' ? panes : []};
    vm.runInNewContext(fs.readFileSync(path.join(root, 'panel/js/updates.js'), 'utf8'), {window});
    vm.runInNewContext(fs.readFileSync(path.join(root, 'panel/js/app.js'), 'utf8'), {
        window, document, setTimeout: fn => {Promise.resolve().then(fn);}, localStorage: {getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value)}
    });
    const settle = async () => {for (let i = 0; i < 300; i++) await Promise.resolve();};
    await settle();
    return {$, windowEvents, calls, storage, settle};
}

test('setup flow clears switched keys, handles Azure region and selects the saved AI', async () => {
    const {$, windowEvents, calls, storage, settle} = await studio();
    assert.equal($('save-key').disabled, false);
    $('api-key').value = 'old-provider-secret';
    $('key-provider').value = 'AZURE_SPEECH_KEY'; $('key-provider').events.change.call($('key-provider'));
    assert.equal($('api-key').value, ''); assert.equal($('azure-region-field').hidden, false);
    assert.equal($('provider-guide-steps').children.length, 3);
    $('api-key').value = 'test-only-secret'; $('azure-region').value = 'westeurope';
    $('toggle-key').events.click.call($('toggle-key'));
    assert.equal($('api-key').type, 'text'); windowEvents.blur(); assert.equal($('api-key').type, 'password');
    $('model').value = 'model-from-another-provider';
    $('save-key').events.click(); await settle();
    const saved = calls.find(c => c.route === '/settings/provider-key');
    assert.equal(saved.payload.name, 'AZURE_SPEECH_KEY'); assert.equal(saved.payload.region, 'westeurope');
    assert.equal($('provider').value, 'azure_speech'); assert.equal($('model').value, '');
    assert.equal($('api-key').value, ''); assert.equal($('tab-source').hidden, false);
    assert.ok(![...storage.values()].some(value => value.includes('secret')));
    $('key-provider').value = 'google_chirp'; $('key-provider').events.change();
    assert.equal($('provider-key-fields').hidden, true);
    assert.equal($('azure-region-field').hidden, true);
    assert.ok($('provider-setup-status').textContent.includes('additional setup'));
});


test('changing provider clears an incompatible custom model; reconnect preserves it', async () => {
    const {$, settle} = await studio();
    $('model').value = 'scribe_v2';
    $('provider').value = 'openai'; $('provider').events.change();
    assert.equal($('model').value, '');
    $('model').value = 'whisper-1';
    $('reconnect').events.click(); await settle();
    assert.equal($('model').value, 'whisper-1');
});

test('starting the service waits for readiness without another user click', async () => {
    let started = false, checks = 0, launches = 0;
    const {$, settle} = await studio({
        host: action => {if (action === 'startService') {started = true; launches++;}},
        health: () => {if (!started || ++checks < 3) throw new Error('Local service is offline.');}
    });
    assert.equal($('save-key').disabled, false);
    assert.equal(launches, 1, 'opening the panel starts it automatically');
    $('start-service').events.click(); await settle();
    assert.equal(launches, 1);
    assert.equal($('save-key').disabled, false);
    assert.match($('service-status').textContent, /Connected/);
    $('start-service').events.click(); await settle();
    assert.equal(launches, 1, 'do not launch a second connected service');
});

test('a service that never starts unlocks controls and explains recovery', async () => {
    const {$, settle} = await studio({health: () => {throw new Error('Local service is offline.');}});
    $('start-service').events.click(); await settle();
    assert.equal($('start-service').disabled, false);
    assert.equal($('save-key').disabled, false);
    assert.equal($('setup-retry').hidden, false);
    assert.match($('provider-setup-status').textContent, /repair|Try again/);
});

test('failed startup retains the actionable connection error', async () => {
    const {$, settle} = await studio({health: () => {throw new Error('An older CapForge service is running. Restart this computer.');}});
    $('start-service').events.click(); await settle();
    assert.match($('notice-text').textContent, /Restart this computer/);
});


test('paste and save during cold startup shares one launch and performs no transcription', async () => {
    let release, launches = 0, started = false;
    const waiting = new Promise(resolve => {release = resolve;});
    const {$, calls, storage, settle} = await studio({
        host: async action => {if (action === 'startService') {launches++; await waiting; started = true;}},
        health: () => {if (!started) throw new Error('offline');}
    });
    assert.equal($('api-key').disabled, false);
    assert.equal($('save-key').disabled, false);
    $('api-key').value = 'fixture-secret';
    $('save-key').events.click(); await settle();
    assert.equal(launches, 1);
    release(); await settle();
    assert.equal(calls.filter(c => c.route === '/settings/provider-key').length, 1);
    assert.equal($('api-key').value, '');
    assert.equal($('tab-source').hidden, false);
    assert.ok(!calls.some(c => /transcribe|extract_audio/.test(c.route)));
    assert.ok(![...storage.values()].some(value => value.includes('fixture-secret')));
});

test('startup failure keeps pasted key and Save retries successfully', async () => {
    let broken = true;
    const {$, calls, settle} = await studio({health: () => {if (broken) throw new Error('offline');}});
    $('api-key').value = 'fixture-secret';
    $('save-key').events.click(); await settle();
    assert.equal($('api-key').value, 'fixture-secret');
    assert.equal($('save-key').disabled, false);
    assert.equal(calls.filter(c => c.route === '/settings/provider-key').length, 0);
    broken = false;
    $('save-key').events.click(); await settle();
    assert.equal($('api-key').value, '');
    assert.equal($('tab-source').hidden, false);
});

test('key write failure stays in onboarding with key intact and inline error', async () => {
    const {$, settle} = await studio({save: () => {throw new Error('Could not save your key.');}});
    $('api-key').value = 'fixture-secret';
    $('save-key').events.click(); await settle();
    assert.equal($('api-key').value, 'fixture-secret');
    assert.match($('provider-setup-status').textContent, /Could not save/);
    assert.equal($('tab-setup').hidden, false);
});

test('first use opens onboarding, returning configured provider opens footage', async () => {
    const first = await studio();
    assert.equal(first.$('tab-setup').hidden, false);
    const returning = await studio({configured: ['openai'], saved: {provider: 'openai'}});
    assert.equal(returning.$('tab-source').hidden, false);
    assert.equal(returning.$('provider').value, 'openai');
});


test('background readiness respects navigation and reconnects on focus', async () => {
    let release, online = false, starts = 0;
    const waiting = new Promise(resolve => {release = resolve;});
    const {$, windowEvents, settle} = await studio({
        host: async action => {if (action === 'startService') {starts++; await waiting; online = true;}},
        health: () => {if (!online) throw new Error('offline');}
    });
    $('use-provider').events.click();
    release(); await settle();
    assert.equal($('tab-source').hidden, false, 'do not pull the editor back to setup');
    online = false;
    windowEvents.focus(); await settle();
    assert.equal(starts, 2, 'reconnect automatically when returning to the panel');
});


test('Try again retries a failed save, not just the connection', async () => {
    let fail = true;
    const {$, calls, settle} = await studio({save: () => {if (fail) throw new Error('Could not save key');}});
    $('api-key').value = 'fixture-secret';
    $('save-key').events.click(); await settle();
    fail = false;
    $('setup-retry').events.click(); await settle();
    assert.equal(calls.filter(c => c.route === '/settings/provider-key').length, 2);
    assert.equal($('api-key').value, '');
    assert.equal($('tab-source').hidden, false);
});
