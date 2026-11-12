/* UI orchestration. Each feature has a small boundary: host, service, data, preview. */
(function () {
    "use strict";
    var $ = function (id) { return document.getElementById(id); };
    var bridge = window.KCF_Bridge, api = window.KCF_API, transcript = window.KCF_Transcript;
    var settings = window.KCF_Settings, titles = window.KCF_Titles, controls = window.KCF_DesignControls;
    var fontGroups = Object.create(null);
    var providerGuide = window.KCF_ProviderGuide;
    var updates = window.KCF_Updates.create(api, {status: $("update-status"), notes: $("update-notes"), check: $("check-updates"), install: $("install-update")});
    var state = { doc: transcript.demo("ka-GE"), look: settings.normalize({}), media: null, providers: [], connected: false, ffmpeg: false, busy: false, category: "All", comp: null, renderedCaption: null, wordLimit: 80 };
    var guideFocus = null;
    try {
        var stored = JSON.parse(localStorage.getItem("kcf.studio.v1") || "null");
        if (stored) { state.look = settings.normalize(stored.look); $("language").value = stored.language || "ka-GE"; }
    } catch (error) { /* A corrupt/stale saved look should not block the panel. */ }
    if (!titles.get(state.look.preset)) { state.look.preset = "highlight_word"; }
    state.doc = transcript.demo($("language").value);
    function persist() { try { localStorage.setItem("kcf.studio.v1", JSON.stringify({ look: state.look, language: $("language").value })); } catch (error) { /* Storage can be disabled by the host. */ } }
    function notice(message) { $("notice-text").textContent = message; $("notice").hidden = false; }
    function status(message) { $("status").textContent = message; }
    function tab(name) {
        document.querySelectorAll("[data-tab]").forEach(function (button) { button.setAttribute("aria-selected", String(button.dataset.tab === name)); button.tabIndex = button.dataset.tab === name ? 0 : -1; });
        document.querySelectorAll(".tab-pane").forEach(function (pane) { pane.hidden = pane.id !== "tab-" + name; });
    }
    function setDot(id, ready) { $(id).className = "status-dot" + (ready ? " ready" : ""); }
    function currentProvider() { return state.providers.filter(function (p) { return p.id === $("provider").value; })[0]; }
    function readiness() {
        var provider = currentProvider(), live = bridge.available;
        updates.setEnabled(live && state.connected && !state.busy);
        $("generate").disabled = !live || state.busy || !state.doc || !state.comp;
        $("transcribe").disabled = !live || state.busy || !state.media || !state.connected || !state.ffmpeg || !provider || !provider.available;
        $("prepare-audio").disabled = !live || state.busy || !state.media || !state.connected || !state.ffmpeg;
        $("scan-providers").disabled = !live || state.busy;
        $("save-key").disabled = !live || state.busy || !state.connected;
        $("use-provider").disabled = state.busy;
        $("setup-ai").disabled = state.busy;
        $("key-provider").disabled = state.busy;
        $("api-key").disabled = state.busy;
        $("azure-region").disabled = state.busy;
        $("regroup").disabled = !live || !state.connected || state.busy;
        ["choose-media", "selected-media", "start-service"].forEach(function (id) { $(id).disabled = !live || state.busy; });
        ["import-json", "demo", "reset-design", "save-look", "load-look", "reconnect"].forEach(function (id) { $(id).disabled = state.busy; });
        // Keep the generation snapshot stable while an AE operation is in flight.
        document.querySelectorAll("[data-setting], [data-slide-angle], #direction-dial, #font-family, #font-style, #language, #provider, #max-words, #min-words, #pause-break, #max-chars, #min-duration, #max-duration, #model, #diarize, #media-path, #keyterms, #remove-punctuation, .word-field input, .style-card").forEach(function (control) { control.disabled = state.busy; });
        $("comp-status").textContent = state.comp ? state.comp.name + " · " + state.comp.width + " × " + state.comp.height + " · new precomp" : live ? "Select a composition in After Effects to generate." : "Browser demo · open in After Effects to generate.";
    }
    function operation(message, task) {
        if (state.busy) { return Promise.resolve(); }
        state.busy = true; document.body.classList.add("busy"); status(message); readiness();
        return Promise.resolve().then(task).catch(function (error) { status("Needs attention"); notice(error.message); }).then(function () { state.busy = false; document.body.classList.remove("busy"); readiness(); });
    }
    function tc(time, decimals) { var minutes = Math.floor(time / 60), seconds = time % 60; return String(minutes).padStart(2, "0") + ":" + seconds.toFixed(decimals ? 2 : 0).padStart(decimals ? 5 : 2, "0"); }
    var preview = window.KCF_Preview.create($("preview"), function (time, duration, playing, caption) {
        $("timecode").textContent = tc(time, true); $("duration").textContent = tc(duration, false);
        $("scrubber").max = duration; $("scrubber").value = time;
        $("play").textContent = playing ? "Ⅱ" : "▶"; $("play").setAttribute("aria-label", playing ? "Pause preview" : "Play preview");
        if (state.renderedCaption !== (caption ? caption.id : null)) {
            state.renderedCaption = caption ? caption.id : null;
            $("preview-text").textContent = caption ? caption.text : "";
            $("preview").setAttribute("aria-label", "Caption preview: " + (caption ? caption.text : "Between captions"));
            document.querySelectorAll(".caption-row").forEach(function (row) { row.classList.toggle("active", !!caption && Number(row.dataset.caption) === caption.id); });
        }
    });
    function syncLook() {
        document.querySelectorAll("[data-setting]").forEach(function (input) { controls.write(input, state.look[input.dataset.setting]); });
        $("custom-position").hidden = state.look.anchorPreset !== "custom";
        $("fit-controls").hidden = !state.look.fitBoundary;
        $("slide-controls").hidden = state.look.preset !== "slide_in";
        $("pop-controls").hidden = ["highlight_word", "pop_karaoke", "active_word_box"].indexOf(state.look.preset) < 0;
        $("motion-hint").textContent = state.look.preset === "slide_in" ? "Each word slides into its place as it is spoken. Distance 0 gives a fade with optional dolly." : titles.get(state.look.preset).description;
        var title = titles.get(state.look.preset);
        $("selected-title").textContent = title.name; $("selected-description").textContent = title.description;
        $("preview-style-name").textContent = title.name;
        dial.sync(); syncFont();
        preview.set(state.doc, state.look); persist();
    }
    function gallery() {
        var query = $("style-search").value.toLowerCase(), grid = $("style-grid"); grid.textContent = "";
        var filtered = titles.all.filter(function (title) { return (state.category === "All" || title.category === state.category) && (title.name + " " + title.engineName + " " + title.description).toLowerCase().indexOf(query) >= 0; });
        $("style-count").textContent = filtered.length + " styles"; $("no-styles").hidden = !!filtered.length;
        filtered.forEach(function (title) {
            var button = document.createElement("button"); button.className = "style-card"; button.dataset.style = title.id;
            button.setAttribute("aria-pressed", String(state.look.preset === title.id)); button.setAttribute("aria-label", title.name + ": " + title.description);
            var sample = document.createElement("span"); sample.className = "style-sample";
            var text = document.createElement("span");
            var phrases = title.sample.split(" "); phrases.forEach(function (word, index) { var piece = document.createElement(index === 1 ? "em" : "span"); piece.textContent = word + (index < phrases.length - 1 ? " " : ""); text.appendChild(piece); }); sample.appendChild(text);
            var info = document.createElement("span"); info.className = "style-info";
            var name = document.createElement("span"); name.className = "style-name"; name.textContent = title.name;
            var category = document.createElement("span"); category.className = "style-category"; category.textContent = title.category;
            info.appendChild(name); info.appendChild(category); button.appendChild(sample); button.appendChild(info);
            if (title.tag) { var tag = document.createElement("span"); tag.className = "style-tag"; tag.textContent = title.tag; button.appendChild(tag); }
            if (state.look.preset === title.id) { var check = document.createElement("span"); check.className = "style-selected"; check.textContent = "✓"; check.setAttribute("aria-hidden", "true"); button.appendChild(check); }
            button.addEventListener("click", function () {
                if (state.busy) { return; } state.look.preset = title.id; $("motion-section").open = true; syncLook(); gallery(); tab("design"); status(title.name + " selected");
                // Restore keyboard focus after rebuilding the gallery.
                var selected = grid.querySelector('[data-style="' + title.id + '"]'); if (selected) { selected.focus({ preventScroll: true }); }
            });
            grid.appendChild(button);
        });
    }
    function renderWords() {
        var editor = $("word-editor"), byId = Object.create(null); editor.textContent = "";
        state.doc.words.forEach(function (word) { byId[word.id] = word; });
        var shown = 0;
        state.doc.captions.forEach(function (caption, index) {
            if (shown >= state.wordLimit) { return; } shown += caption.wordIds.length;
            var row = document.createElement("div"); row.className = "caption-row"; row.dataset.caption = caption.id;
            var top = document.createElement("div"); top.className = "caption-top";
            var counter = document.createElement("span"); counter.textContent = "CAPTION " + String(index + 1).padStart(2, "0");
            var seek = document.createElement("button"); seek.className = "text-button"; seek.textContent = tc(caption.start, true) + " → " + tc(caption.end, true); seek.setAttribute("aria-label", "Preview caption " + (index + 1));
            seek.addEventListener("click", function () { preview.seek(caption.start + 0.02); preview.pause(); }); top.appendChild(counter); top.appendChild(seek);
            var fields = document.createElement("div"); fields.className = "word-fields";
            caption.wordIds.forEach(function (id) {
                var word = byId[id], label = document.createElement("label"); label.className = "word-field";
                var input = document.createElement("input"); input.value = word.text; input.setAttribute("aria-label", "Edit word " + (id + 1) + ": " + word.text); input.maxLength = 200;
                input.addEventListener("change", function () { try { transcript.editWord(state.doc, id, input.value); input.value = word.text; preview.set(state.doc, state.look); status("Word updated · timing preserved"); } catch (error) { input.value = word.text; notice(error.message); } });
                var timing = document.createElement("small"); timing.textContent = word.start.toFixed(2) + " — " + word.end.toFixed(2) + "s";
                label.appendChild(input); label.appendChild(timing); fields.appendChild(label);
            }); row.appendChild(top); row.appendChild(fields); editor.appendChild(row);
        });
        if (shown < state.doc.words.length) { var more = document.createElement("button"); more.className = "secondary-button full"; more.textContent = "Show more words"; more.addEventListener("click", function () { state.wordLimit += 80; renderWords(); }); editor.appendChild(more); }
        $("word-count").textContent = state.doc.words.length + " words"; $("caption-count").textContent = state.doc.captions.length + " captions";
        state.renderedCaption = null; preview.set(state.doc, state.look);
    }
    function setDocument(doc, note) {
        state.doc = transcript.validate(doc); state.wordLimit = 80; renderWords();
        var demo = state.doc.provider === "demo";
        $("demo-badge").textContent = demo ? "Built-in demo" : "Your transcript";
        $("preview-source").textContent = state.doc.language === "ka-GE" ? "ქართული / Georgian" : state.doc.language === "en-US" ? "English" : state.doc.language || "Imported transcript";
        $("transcript-note").textContent = note; readiness();
    }
    function grouping() {
        var maxWords = Math.round(Number($("max-words").value)), pause = Number($("pause-break").value), maxChars = Math.round(Number($("max-chars").value));
        if (!isFinite(maxWords) || maxWords < 1 || maxWords > 6 || !isFinite(pause) || pause < 0.1 || pause > 5 || !isFinite(maxChars) || maxChars < 4 || maxChars > 200) { throw new Error("Check Source grouping: 1–6 words, 0.1–5 second pauses, and 4–200 characters."); }
        var minWords = Math.round(Number($("min-words").value)), minDuration = Number($("min-duration").value), maxDuration = Number($("max-duration").value);
        if (!isFinite(minWords) || minWords < 1 || minWords > 6 || !isFinite(minDuration) || minDuration < 0 || minDuration > 30 || !isFinite(maxDuration) || maxDuration < 0.1 || maxDuration > 30 || minDuration > maxDuration) { throw new Error("Check minimum words and caption durations. Minimum duration must not exceed maximum duration."); }
        return { minWords: Math.min(minWords, maxWords), maxWords: maxWords, maxChars: maxChars, pauseBreakSeconds: pause, minCaptionDuration: minDuration, maxCaptionDuration: maxDuration, removeCommasAndPeriods: $("remove-punctuation").checked };
    }
    function updateProvider() {
        var provider = currentProvider();
        $("provider-detail").textContent = provider ? (provider.available ? "Ready · " + (provider.type === "local" ? "runs on this computer" : "cloud transcription") : "Setup needed · " + (provider.detail || "configure this provider")) : "Connect the local service in Setup to check providers.";
        if (provider && $("language").value === "ka-GE" && provider.id !== "elevenlabs") { $("provider-detail").textContent += ". Georgian quality varies; start with ElevenLabs."; }
        $("key-status").textContent = provider && provider.available ? "Selected provider is configured" : "Selected provider needs configuration";
        setDot("key-dot", provider && provider.available); readiness();
        updateGuideStatus();
    }
    function updateGuideStatus() {
        var guide = providerGuide.get($("key-provider").value);
        var configured = state.providers.some(function (p) { return p.id === guide.id && p.available; });
        $("provider-setup-status").textContent = !bridge.available ? "Demo mode · save your key when this panel is open inside After Effects." : !state.connected ? "Start the local service above, then check connection to save a key." : configured ? "Configured on this computer. Your first transcription checks the account and timing." : guide.key ? "Ready for your key. Saving it does not transcribe audio or check billing." : "Complete the additional setup, then check connection above.";
    }
    function renderProviderGuide() {
        var guide = providerGuide.get($("key-provider").value);
        $("provider-guide-badge").textContent = guide.badge;
        $("provider-guide-name").textContent = guide.name;
        $("provider-guide-description").textContent = guide.description;
        $("provider-account").textContent = guide.link + " ↗";
        $("provider-guide-note").textContent = guide.note;
        $("provider-guide-steps").textContent = "";
        guide.steps.forEach(function (step) { var item = document.createElement("li"); item.textContent = step; $("provider-guide-steps").appendChild(item); });
        $("provider-key-fields").hidden = !guide.key;
        $("azure-region-field").hidden = guide.id !== "azure_speech";
        // Switching accounts must never leave a different provider's key in the form.
        $("api-key").value = ""; hideKey(); updateGuideStatus();
    }
    function hideKey() { $("api-key").type = "password"; $("toggle-key").textContent = "Show"; $("toggle-key").setAttribute("aria-label", "Show API key"); $("toggle-key").setAttribute("aria-pressed", "false"); }
    function chooseGuideProvider() {
        var guide = providerGuide.get($("key-provider").value);
        if (state.providers.some(function (p) { return p.id === guide.id; })) { $("provider").value = guide.id; $("model").value = ""; updateProvider(); }
        tab("source"); $("provider").focus();
    }
    function context() {
        if (!bridge.available) { return Promise.resolve(); }
        return bridge.call("context").then(function (data) {
            state.comp = data.comp; preview.context(state.comp, data.fonts);
            setDot("host-dot", true); $("host-status").textContent = state.comp ? state.comp.name : "Connected · select a composition";
            var list = $("font-list"); list.textContent = "";
            data.fonts.forEach(function (font) { var option = document.createElement("option"); option.value = font.name; option.label = font.family; list.appendChild(option); });
            fontGroups = controls.fontGroups(data.fonts);
            $("font-family").textContent = "";
            Object.keys(fontGroups).sort().forEach(function (family) { var option = document.createElement("option"); option.value = family; option.textContent = family; $("font-family").appendChild(option); });
            $("installed-fonts").hidden = !data.fonts.length; syncFont();
            readiness();
        });
    }
    function connect(quiet) {
        if (!bridge.available) { $("service-status").textContent = "Open in After Effects to connect"; $("ffmpeg-status").textContent = "Not needed for the demo"; status("Browser demonstration mode"); readiness(); return Promise.resolve(); }
        return context().then(function () { return bridge.call("token"); }).then(function (token) {
            api.setToken(token); return api.request("/health");
        }).then(function (health) {
            state.ffmpeg = !!health.ffmpeg;
            return api.request("/providers");
        }).then(function (result) {
            state.connected = true; state.providers = result.providers;
            var value = $("provider").value; $("provider").textContent = "";
            result.providers.forEach(function (provider) { var option = document.createElement("option"); option.value = provider.id; option.textContent = provider.label + (provider.available ? " · ready" : " · setup needed"); $("provider").appendChild(option); });
            if (state.providers.some(function (p) { return p.id === value; })) { $("provider").value = value; }
            setDot("service-dot", true); setDot("connection-dot", true); setDot("ffmpeg-dot", state.ffmpeg);
            $("service-status").textContent = "Connected · running on this computer"; $("ffmpeg-status").textContent = state.ffmpeg ? "Ready to prepare your audio" : "Audio support missing · run the installer to repair";
            updateProvider(); status("Studio connected");
        }).catch(function (error) {
            state.connected = false; state.ffmpeg = false; ["service-dot", "connection-dot", "ffmpeg-dot"].forEach(function (id) { setDot(id, false); });
            $("service-status").textContent = "Offline · start the service below"; $("ffmpeg-status").textContent = "Waiting for service"; status("Preview ready · service offline"); readiness();
            updateGuideStatus();
            if (!quiet && error.message.indexOf("offline") < 0) {
                if (error.message.indexOf("engine") >= 0 || error.message.indexOf("bridge") >= 0) { $("host-status").textContent = "Caption engine needs attention · see message"; }
                notice(error.message);
            }
            return error;
        });
    }
    function waitForService(attempts) {
        return connect(true).then(function (error) {
            if (state.connected) { status("Studio connected · ready to transcribe"); return; }
            if (attempts <= 1) { throw new Error((error ? error.message + " " : "") + "The local service did not become ready. Check its startup window for an error, then retry. If it keeps failing, close After Effects and run the CapForge installer to repair Setup."); }
            status("Waiting for the local service…");
            return new Promise(function (resolve) { setTimeout(resolve, 1000); }).then(function () { return waitForService(attempts - 1); });
        });
    }
    function exportFile(name, data, kind) {
        if (bridge.available) { return bridge.call("saveJSON", { kind: kind, data: data }).then(function (saved) { if (saved) { status(kind === "look" ? "Look saved" : "Transcript exported"); } }); }
        var url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })), anchor = document.createElement("a");
        anchor.href = url; anchor.download = name; document.body.appendChild(anchor); anchor.click(); anchor.remove(); setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        return Promise.resolve();
    }
    function readJSON(input, handler) {
        var file = input.files[0]; input.value = ""; if (!file) { return; }
        if (file.size > 12 * 1024 * 1024) { notice("JSON files must be smaller than 12 MB."); return; }
        var reader = new FileReader(); reader.onload = function () { try { handler(JSON.parse(reader.result)); } catch (error) { notice(error.message); } }; reader.onerror = function () { notice("Could not read this JSON file."); }; reader.readAsText(file, "UTF-8");
    }
    function guide(open) {
        $("guide-overlay").hidden = !open;
        if (open) { guideFocus = document.activeElement; $("close-guide").focus(); } else { if (guideFocus) { guideFocus.focus(); } try { localStorage.setItem("kcf.guide.seen", "yes"); } catch (error) {} }
    }
    document.querySelectorAll("[data-tab]").forEach(function (button) { button.addEventListener("click", function () { tab(button.dataset.tab); }); });
    document.querySelector(".tabs").addEventListener("keydown", function (event) {
        if (["ArrowLeft", "ArrowRight", "Home", "End"].indexOf(event.key) < 0) { return; }
        var buttons = Array.from(this.querySelectorAll("[data-tab]")), index = buttons.indexOf(document.activeElement);
        if (index < 0) { return; }
        index = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
        tab(buttons[index].dataset.tab); buttons[index].focus(); event.preventDefault();
    });
    document.querySelectorAll("[data-ratio]").forEach(function (button) { button.addEventListener("click", function () { preview.ratio(button.dataset.ratio); document.querySelectorAll("[data-ratio]").forEach(function (b) { b.setAttribute("aria-pressed", String(b === button)); }); }); });
    document.querySelectorAll("[data-category]").forEach(function (button) { button.addEventListener("click", function () { state.category = button.dataset.category; document.querySelectorAll("[data-category]").forEach(function (b) { b.setAttribute("aria-pressed", String(b === button)); }); gallery(); }); });
    $("style-search").addEventListener("input", gallery);
    $("back-preview").addEventListener("click", function () { document.querySelector(".preview-section").scrollIntoView({ behavior: "auto", block: "start" }); });
    $("browse-collection").addEventListener("click", function () { document.querySelector(".library").scrollIntoView({ behavior: "auto", block: "start" }); });
    titles.all.forEach(function (title) { var option = document.createElement("option"); option.value = title.id; option.textContent = title.name; $("preset-select").appendChild(option); });
    var dial = controls.mountDial($("direction-dial"), $("slide-angle"));
    document.querySelectorAll("[data-setting]").forEach(function (input) {
        function update() {
            if (state.busy) { return; }
            try {
                var draft = Object.assign({}, state.look); draft[input.dataset.setting] = controls.read(input);
                state.look = settings.normalize(draft); syncLook();
                if (input.dataset.setting === "preset") { $("motion-section").open = true; gallery(); status(titles.get(state.look.preset).name + " selected"); }
            } catch (error) { notice(error.message); syncLook(); }
        }
        input.addEventListener("change", update);
        if (input.type === "range" || input.type === "color") { input.addEventListener("input", update); }
    });
    function populateFontStyles() {
        $("font-style").textContent = "";
        (fontGroups[$("font-family").value] || []).forEach(function (font) { var option = document.createElement("option"); option.value = font.name; option.textContent = font.style; $("font-style").appendChild(option); });
    }
    function syncFont() {
        var family = Object.keys(fontGroups).filter(function (name) { return fontGroups[name].some(function (font) { return font.name === state.look.font; }); })[0];
        if (!family) { $("font-family").selectedIndex = -1; $("font-style").textContent = ""; return; }
        $("font-family").value = family; populateFontStyles(); $("font-style").value = state.look.font;
    }
    $("font-family").addEventListener("change", function () { populateFontStyles(); state.look.font = $("font-style").value; syncLook(); });
    $("font-style").addEventListener("change", function () { state.look.font = this.value; syncLook(); });
    $("play").addEventListener("click", preview.toggle); $("restart").addEventListener("click", preview.restart);
    $("scrubber").addEventListener("input", function () { preview.seek(Number(this.value)); preview.pause(); });
    $("dismiss-notice").addEventListener("click", function () { $("notice").hidden = true; });
    ["help-button", "open-guide"].forEach(function (id) { $(id).addEventListener("click", function () { guide(true); }); });
    ["close-guide", "begin"].forEach(function (id) { $(id).addEventListener("click", function () { guide(false); }); });
    document.addEventListener("keydown", function (event) {
        if ($("guide-overlay").hidden) { return; }
        if (event.key === "Escape") { guide(false); }
        if (event.key === "Tab") { var first = $("close-guide"), last = $("begin"); if (event.shiftKey && document.activeElement === first) { last.focus(); event.preventDefault(); } else if (!event.shiftKey && document.activeElement === last) { first.focus(); event.preventDefault(); } }
    });
    $("choose-media").addEventListener("click", function () { choose("chooseMedia"); }); $("selected-media").addEventListener("click", function () { choose("selectedMedia"); });
    function selectMedia(media) { state.media = media; $("media-path").value = media ? media.path : ""; $("media-name").textContent = media ? media.name : "Choose your media"; $("media-detail").textContent = media ? "Transcription starts at the source file’s beginning." : "Video or audio, with speech."; readiness(); }
    function choose(action) { operation("Choosing media…", function () { return bridge.call(action).then(function (media) { if (media) { selectMedia(media); status("Media selected"); } else { status("Ready"); } }); }); }
    $("media-path").addEventListener("change", function () { var path = this.value.trim(); selectMedia(path ? {path: path, name: path.split(/[\\/]/).pop()} : null); });
    $("language").addEventListener("change", function () { persist(); updateProvider(); if (state.doc.provider === "demo") { setDocument(transcript.demo(this.value), "Built-in sample. Import JSON or transcribe your own clip."); } });
    $("provider").addEventListener("change", function () { $("model").value = ""; updateProvider(); });
    $("transcribe").addEventListener("click", function () { operation("Transcribing your clip…", function () {
        var options = {keyterms: $("keyterms").value.split(",").map(function (word) { return word.trim(); }).filter(Boolean), diarize: $("diarize").checked};
        if ($("model").value.trim()) { options.model = $("model").value.trim(); }
        return api.request("/transcribe", { mediaPath: state.media.path, language: $("language").value, provider: $("provider").value, grouping: grouping(), providerOptions: options }).then(function (result) {
            setDocument(result.document, "Your transcript · " + (result.timingQuality || "word") + " timing. Export JSON to save edits."); tab("transcript"); status("Transcript ready · review your words");
            if (result.warnings && result.warnings.length) { notice(result.warnings.join(" ")); }
        });
    }); });
    $("regroup").addEventListener("click", function () { operation("Applying grouping…", function () { return api.request("/regroup", { document: state.doc, grouping: grouping() }).then(function (result) { setDocument(result.document, "Grouping updated · word timings preserved. Export JSON to save."); status("Grouping applied"); }); }); });
    $("import-json").addEventListener("click", function () { $("json-file").click(); }); $("json-file").addEventListener("change", function () { readJSON(this, function (data) { setDocument(data, "Imported transcript. Text edits keep original timings."); tab("transcript"); status("Transcript imported"); }); });
    $("export-json").addEventListener("click", function () { operation("Exporting transcript…", function () { return exportFile("capforge-transcript.json", state.doc, "transcript"); }); });
    $("demo").addEventListener("click", function () { setDocument(transcript.demo($("language").value), "Built-in sample. Import JSON or transcribe your own clip."); preview.restart(); status("Built-in demo loaded"); });
    $("reset-design").addEventListener("click", function () { state.look = settings.normalize({}); syncLook(); gallery(); status("Design reset"); });
    $("save-look").addEventListener("click", function () { operation("Saving look…", function () { return exportFile("capforge-look.json", { tool: "CapForge", version: 1, settings: state.look }, "look"); }); });
    $("load-look").addEventListener("click", function () { $("look-file").click(); }); $("look-file").addEventListener("change", function () { readJSON(this, function (data) { if (!settings.isSavedLook(data) || !titles.get(data.settings.preset)) { throw new Error("Choose a CapForge look exported by this panel."); } state.look = settings.normalize(data.settings); syncLook(); gallery(); status("Look loaded"); }); });
    $("reconnect").addEventListener("click", function () { operation("Checking connection…", connect); });
    $("check-updates").addEventListener("click", function () { operation("Checking for updates…", function () { return updates.check().then(function () { status("Update check finished"); }); }); });
    $("install-update").addEventListener("click", function () { operation("Preparing update…", function () { return updates.install().then(function () { status("Update setup is opening"); }); }); });
    $("scan-providers").addEventListener("click", function () { operation("Refreshing providers…", connect); });
    $("prepare-audio").addEventListener("click", function () { operation("Preparing audio…", function () { return api.request("/extract_audio", {mediaPath: state.media.path}).then(function (result) { status("Audio prepared · " + result.duration.toFixed(1) + "s"); notice("WAV saved: " + result.audio); }); }); });
    $("start-service").addEventListener("click", function () { operation("Checking local service…", function () {
        return connect().then(function () {
            if (state.connected) { status("Service is already running · ready to transcribe"); return; }
            return bridge.call("startService").then(function () { return waitForService(10); });
        });
    }); });
    $("key-provider").addEventListener("change", renderProviderGuide);
    $("setup-ai").addEventListener("click", function () { var guide = providerGuide.get($("provider").value); if (guide) { $("key-provider").value = guide.key || guide.id; renderProviderGuide(); } tab("setup"); $("key-provider").focus(); });
    $("provider-account").addEventListener("click", function () { try { window.KCF_ExternalLinks.open(providerGuide.get($("key-provider").value).url); } catch (error) { notice(error.message); } });
    $("toggle-key").addEventListener("click", function () { var show = $("api-key").type === "password"; $("api-key").type = show ? "text" : "password"; this.textContent = show ? "Hide" : "Show"; this.setAttribute("aria-label", show ? "Hide API key" : "Show API key"); this.setAttribute("aria-pressed", String(show)); });
    $("use-provider").addEventListener("click", chooseGuideProvider);
    $("save-key").addEventListener("click", function () { operation("Saving provider key…", function () {
        var key = $("api-key").value.trim(); if (!key) { throw new Error("Paste your provider API key first."); }
        var payload = { name: $("key-provider").value, value: key }; if (payload.name === "AZURE_SPEECH_KEY") { payload.region = $("azure-region").value.trim(); }
        return api.request("/settings/provider-key", payload).then(function () { $("api-key").value = ""; hideKey(); return connect(); }).then(function () { chooseGuideProvider(); status("Key saved · choose a clip to try your AI"); });
    }); });
    $("generate").addEventListener("click", function () { operation("Generating editable caption layers…", function () { var doc = transcript.validate(state.doc), look = settings.forAE(state.look); return bridge.call("generate", { document: doc, settings: look }).then(function (result) { status("Created " + result.name); notice("Your captions are ready in a fresh precomp. Play the AE timeline to check the final result."); return context(); }); }); });
    // Check the selected composition when returning from the AE timeline.
    window.addEventListener("focus", function () { if (bridge.available && !state.busy) { context().catch(function (error) { notice(error.message); }); } });
    window.addEventListener("beforeunload", preview.destroy);
    window.addEventListener("blur", hideKey);
    syncLook(); gallery(); renderWords(); renderProviderGuide(); readiness(); connect();
}());
