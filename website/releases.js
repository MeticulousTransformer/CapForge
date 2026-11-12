/* Only official, fully published platform pairs become download buttons. */
(function (root) {
    'use strict';
    var repo = 'MeticulousTransformer/Georgian-Kartuli-After-Effects-Transcribtion-Tool';
    function select(release) {
        if (!release || release.draft || release.prerelease || !/^build-[a-f0-9]{40}$/.test(release.tag_name) || !Array.isArray(release.assets)) return null;
        var mac = release.assets.filter(function (a) { return /^CapForge-\d+\.\d+\.\d+-macOS\.dmg$/.test(a.name); });
        var win = release.assets.filter(function (a) { return /^CapForge-\d+\.\d+\.\d+-Windows\.exe$/.test(a.name); });
        if (mac.length !== 1 || win.length !== 1) return null;
        var version = mac[0].name.match(/CapForge-(\d+\.\d+\.\d+)/)[1];
        if (win[0].name !== 'CapForge-' + version + '-Windows.exe') return null;
        for (var i = 0; i < 2; i++) {
            var asset = i ? win[0] : mac[0];
            if (asset.browser_download_url !== 'https://github.com/' + repo + '/releases/download/' + release.tag_name + '/' + asset.name) return null;
        }
        return {version: version, mac: mac[0].browser_download_url, windows: win[0].browser_download_url, commit: release.tag_name.slice(6,13)};
    }
    if (typeof module !== 'undefined' && module.exports) { module.exports = select; return; }
    var status = document.getElementById('release-status');
    if (!status) return;
    var timeout = new Promise(function (_, reject) { setTimeout(function () { reject(new Error('timeout')); }, 8000); });
    Promise.race([fetch('https://api.github.com/repos/' + repo + '/releases/latest').then(function (r) {if (!r.ok) throw new Error('release'); return r.json();}), timeout]).then(function (release) {
        var pair = select(release);
        if (!pair) throw new Error('incomplete');
        status.textContent = 'Latest: ' + pair.version + ' · build ' + pair.commit;
        ['mac', 'windows'].forEach(function (os) {
            var link = document.getElementById(os + '-download');
            if (link) { link.href = pair[os]; link.textContent = os === 'mac' ? 'Download for Mac' : 'Download for Windows'; }
        });
    }).catch(function () {status.textContent = 'See the latest GitHub release for available downloads.';});
}(this));
