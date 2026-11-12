const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function api(result) {
    const window = {};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../js/api.js'), 'utf8'), {
        window, AbortController, setTimeout, clearTimeout, fetch: async () => ({ok: true, json: async () => result})
    });
    return window.KCF_API;
}

test('panel requires a restart before connecting to an older running service', async () => {
    await assert.rejects(api({ok: true, version: '0.2.0', ffmpeg: true}).request('/health'), /[Rr]estart/);
});

test('panel accepts current service health and leaves other API payloads intact', async () => {
    const health = {ok: true, version: '0.3.3', ffmpeg: true};
    assert.deepEqual(await api(health).request('/health'), health);
    const result = {providers: []};
    assert.deepEqual(await api(result).request('/providers'), result);
});

test('an unresponsive health check times out and releases the connection operation', async () => {
    const window = {};
    let timer, cleared = false, signal;
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../js/api.js'), 'utf8'), {
        window, AbortController,
        setTimeout: fn => {timer = fn; return 1;}, clearTimeout: () => {cleared = true;},
        fetch: (url, options) => new Promise((resolve, reject) => {
            signal = options.signal;
            if (signal) signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), {name: 'AbortError'})));
        })
    });
    const pending = window.KCF_API.request('/health');
    assert.equal(typeof timer, 'function', 'health checks need a bounded wait');
    timer();
    await assert.rejects(pending, /not responding|timed out/i);
    assert.equal(signal.aborted, true); assert.equal(cleared, true);
});

test('health timeout is cleared on success; transcription is not cut off by the health timer', async () => {
    const window = {};
    let scheduled = 0, cleared = 0;
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../js/api.js'), 'utf8'), {
        window, AbortController,
        setTimeout: () => ++scheduled, clearTimeout: () => ++cleared,
        fetch: async () => ({ok: true, json: async () => ({version: '0.3.3'})})
    });
    await window.KCF_API.request('/health');
    assert.equal(scheduled, 1); assert.equal(cleared, 1);
    await window.KCF_API.request('/transcribe', {mediaPath: '/qa/clip.mov'});
    assert.equal(scheduled, 1);
});

test('older browser hosts without AbortController can connect and still time out', async () => {
    const window = {};
    let timer, stalled = false;
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../js/api.js'), 'utf8'), {
        window, setTimeout: fn => {timer = fn; return 1;}, clearTimeout() {},
        fetch: () => stalled ? new Promise(() => {}) : Promise.resolve({ok: true, json: async () => ({version: '0.3.3'})})
    });
    await window.KCF_API.request('/health');
    stalled = true;
    const pending = window.KCF_API.request('/health'); timer();
    await assert.rejects(pending, /not responding|timed out/i);
});
