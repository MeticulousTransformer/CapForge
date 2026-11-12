/* Local service only. The install-specific token stays in memory, never storage. */
(function (root) {
    "use strict";
    var serviceVersion = "0.3.3";
    var token = "", base = "http://127.0.0.1:8765";
    function request(path, payload) {
        var headers = { "Content-Type": "application/json" };
        // A stalled health check must not leave every panel control locked.
        // Long-running transcription keeps its provider's own timeout.
        var controller = path === "/health" && typeof AbortController !== "undefined" ? new AbortController() : null;
        var timer = null;
        if (token) { headers["X-KCF-Token"] = token; }
        var responsePromise = fetch(base + path, { method: payload ? "POST" : "GET", headers: headers, body: payload ? JSON.stringify(payload) : undefined, credentials: "omit", signal: controller ? controller.signal : undefined }).then(function (response) {
            return response.json().then(function (result) {
                if (!response.ok) { throw new Error(typeof result.detail === "string" ? result.detail : "The local service rejected this request. Check your settings."); }
                if (path === "/health" && result.version !== serviceVersion) { throw new Error("An older or different CapForge service is still running. Restart this computer, then start CapForge again to finish the update."); }
                return result;
            });
        });
        // Older CEP browsers cannot cancel fetch. Still release the UI when
        // their health request stalls; its late response is ignored.
        var pending = path !== "/health" ? responsePromise : new Promise(function (resolve, reject) {
            timer = setTimeout(function () {
                reject(new Error("The local service is not responding. Close its startup window and start it again from Setup."));
                if (controller) { controller.abort(); }
            }, 5000);
            responsePromise.then(resolve, reject);
        });
        return pending.catch(function (error) {
            if (error.name === "AbortError") { throw new Error("The local service is not responding. Close its startup window and start it again from Setup."); }
            if (error instanceof TypeError) { throw new Error("Local service is offline. Open Setup and start the service, then check the connection."); }
            throw error;
        }).then(function (result) {
            if (timer !== null) { clearTimeout(timer); }
            return result;
        }, function (error) {
            if (timer !== null) { clearTimeout(timer); }
            throw error;
        });
    }
    root.KCF_API = { request: request, setToken: function (value) { token = value; } };
}(window));
