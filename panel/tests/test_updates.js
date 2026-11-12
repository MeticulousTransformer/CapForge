const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup(request) {
    const window = {};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../js/updates.js'), 'utf8'), {window});
    const elements = {status: {}, notes: {}, check: {}, install: {}};
    return {elements, updates: window.KCF_Updates.create({request}, elements)};
}

test('updates are opt-in and available only after a successful release check', async () => {
    const calls = [];
    const {updates, elements} = setup(async (route) => {
        calls.push(route);
        return {available: true, version: '0.3.3', tag: 'build-new', notes: '<script>literal text</script>', message: 'Update available'};
    });
    assert.equal(calls.length, 0);
    updates.setEnabled(true);
    assert.equal(elements.install.hidden, true);
    await updates.check();
    assert.deepEqual(calls, ['/updates/check']);
    assert.equal(elements.install.hidden, false);
    assert.equal(elements.notes.textContent, '<script>literal text</script>');
    updates.setEnabled(false);
    assert.equal(elements.install.disabled, true);
});

test('offline release check clears stale install action and shows retry guidance', async () => {
    const {updates, elements} = setup(async () => { throw new Error('Check your internet connection and try again.'); });
    updates.setEnabled(true);
    await assert.rejects(updates.check(), /internet/);
    assert.equal(elements.install.hidden, true);
    assert.match(elements.status.textContent, /internet/);
});

test('install request contains no paths or remote URLs and explains the setup handoff', async () => {
    const calls = [];
    const {updates, elements} = setup(async (route, payload) => {
        calls.push({route, payload});
        return route === '/updates/check'
            ? {available: true, version: '0.3.3', message: 'Ready'}
            : {started: true, message: 'Setup is open. Save your project and close After Effects before installing.'};
    });
    updates.setEnabled(true);
    await updates.check();
    await updates.install();
    assert.equal(calls[1].route, '/updates/install');
    assert.deepEqual(Object.keys(calls[1].payload), []);
    assert.match(elements.status.textContent, /Save your project/);
    assert.equal(elements.install.hidden, true);
});
