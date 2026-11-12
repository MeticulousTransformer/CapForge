const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function api(result) {
    const window = {};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../js/api.js'), 'utf8'), {
        window, fetch: async () => ({ok: true, json: async () => result})
    });
    return window.KCF_API;
}

test('panel requires a restart before connecting to an older running service', async () => {
    await assert.rejects(api({ok: true, version: '0.2.0', ffmpeg: true}).request('/health'), /[Rr]estart/);
});

test('panel accepts current service health and leaves other API payloads intact', async () => {
    const health = {ok: true, version: '0.3.2', ffmpeg: true};
    assert.deepEqual(await api(health).request('/health'), health);
    const result = {providers: []};
    assert.deepEqual(await api(result).request('/providers'), result);
});
