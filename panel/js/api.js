/* Local service only. The install-specific token stays in memory, never storage. */
(function (root) {
    "use strict";
    var serviceVersion = "0.3.2";
    var token = "", base = "http://127.0.0.1:8765";
    function request(path, payload) {
        var headers = { "Content-Type": "application/json" };
        if (token) { headers["X-KCF-Token"] = token; }
        return fetch(base + path, { method: payload ? "POST" : "GET", headers: headers, body: payload ? JSON.stringify(payload) : undefined, credentials: "omit" }).then(function (response) {
            return response.json().then(function (result) {
                if (!response.ok) { throw new Error(typeof result.detail === "string" ? result.detail : "The local service rejected this request. Check your settings."); }
                if (path === "/health" && result.version !== serviceVersion) { throw new Error("An older or different CapForge service is still running. Restart this computer, then start CapForge again to finish the update."); }
                return result;
            });
        }).catch(function (error) {
            if (error instanceof TypeError) { throw new Error("Local service is offline. Open Setup and start the service, then check the connection."); }
            throw error;
        });
    }
    root.KCF_API = { request: request, setToken: function (value) { token = value; } };
}(window));
