/* Update discovery and setup handoff. Downloads stay in the local service. */
(function (root) {
    "use strict";
    function create(api, elements) {
        var available = false, enabled = false;
        function refresh() {
            elements.check.disabled = !enabled;
            elements.install.disabled = !enabled || !available;
            elements.install.hidden = !available;
        }
        function failed(error) {
            available = false;
            elements.status.textContent = error.message;
            refresh();
            throw error;
        }
        refresh();
        return {
            setEnabled: function (value) { enabled = value; refresh(); },
            check: function () {
                available = false;
                elements.status.textContent = "Checking for updates…";
                elements.notes.textContent = "";
                refresh();
                return api.request("/updates/check").then(function (result) {
                    available = result.available;
                    elements.status.textContent = result.message;
                    elements.notes.textContent = result.notes || "";
                    elements.install.textContent = "Update to " + result.version;
                    refresh();
                }).catch(failed);
            },
            install: function () {
                if (!available) { return Promise.reject(new Error("Check for updates first.")); }
                elements.status.textContent = "Downloading and checking your update…";
                return api.request("/updates/install", {}).then(function (result) {
                    available = false;
                    elements.status.textContent = result.message;
                    refresh();
                }).catch(failed);
            }
        };
    }
    root.KCF_Updates = { create: create };
}(window));
