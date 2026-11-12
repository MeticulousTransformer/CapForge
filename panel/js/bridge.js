/* Small CEP adapter. Browser mode can explore designs without pretending to be AE. */
(function (root) {
    "use strict";
    var available = !!root.__adobe_cep__;
    var initialization = null;
    function literal(value) { return JSON.stringify(value).replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029"); }
    function evaluate(code) {
        return new Promise(function (resolve, reject) {
            root.__adobe_cep__.evalScript(code, function (response) {
                try {
                    var result = JSON.parse(response);
                    if (!result.ok) { throw new Error(result.error || "After Effects could not complete the action."); }
                    resolve(result.data);
                } catch (error) { reject(new Error(response === "EvalScript error." ? "The AE bridge did not load. Reopen CapForge after running Setup, and allow AE scripts to write files and access the network." : error.message)); }
            });
        });
    }
    function initialize() {
        if (!initialization) {
            initialization = Promise.resolve().then(function () {
                var path = root.__adobe_cep__.getSystemPath("extension");
                if (!path) { throw new Error("Adobe did not provide the CapForge extension path. Reopen the panel inside After Effects."); }
                // CEP normally returns a file URL; a native path can contain a
                // literal percent sign, which must not be URI-decoded.
                if (/^file:\/\//i.test(path)) { path = decodeURIComponent(path); }
                path = path.replace(/^file:\/\/\/([a-z]:)/i, "$1").replace(/^file:\/\//i, "").replace(/\\/g, "/").replace(/\/$/, "");
                return evaluate("$.evalFile(new File(" + literal(path + "/host.jsx") + ")); KCF_initialize(" + literal(path) + ")");
            }).catch(function (error) { initialization = null; throw error; });
        }
        return initialization;
    }
    function call(action, payload) {
        if (!available) { return Promise.reject(new Error("Open CapForge in After Effects to use this action.")); }
        return initialize().then(function () {
            var data = JSON.stringify({ action: action, payload: payload || {} });
            return evaluate("KCF_dispatch(" + literal(data) + ")");
        });
    }
    root.KCF_Bridge = { available: available, call: call };
}(window));
