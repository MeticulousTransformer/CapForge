/* The preview and AE share this word timeline. Text edits never change timing. */
(function (root) {
    "use strict";
    function finite(value) { return typeof value === "number" && isFinite(value); }
    function validate(input) {
        var doc = JSON.parse(JSON.stringify(input && input.document ? input.document : input));
        if (!doc || !Array.isArray(doc.words) || !doc.words.length || !Array.isArray(doc.captions) || !doc.captions.length) {
            throw new Error("Choose a word-timed transcript with words and captions.");
        }
        if (doc.words.length > 20000 || doc.captions.length > 10000) { throw new Error("This transcript is too large. Split the source into shorter clips."); }
        var byId = Object.create(null), previous = -1;
        doc.words.forEach(function (word) {
            if (!Number.isInteger(word.id) || word.id < 0 || byId[word.id]) { throw new Error("Every word needs a unique, non-negative integer ID."); }
            if (typeof word.text !== "string" || !word.text.trim() || word.text.length > 200 || /[\r\n]/.test(word.text)) { throw new Error("Each word needs non-empty text, without line breaks (up to 200 characters)."); }
            if (!finite(word.start) || !finite(word.end) || word.start < 0 || word.end <= word.start || word.start < previous) { throw new Error("Word timings must be ordered, positive intervals in seconds."); }
            if (word.punctuationAfter !== undefined && (typeof word.punctuationAfter !== "string" || word.punctuationAfter.length > 16)) { throw new Error("Word punctuation must be a short string."); }
            previous = word.start;
            word.punctuationAfter = word.punctuationAfter || "";
            byId[word.id] = word;
        });
        previous = -1;
        var captionIds = Object.create(null), used = Object.create(null);
        doc.captions.forEach(function (caption) {
            if (!Number.isInteger(caption.id) || caption.id < 0 || captionIds[caption.id]) { throw new Error("Each caption needs a unique integer ID."); }
            captionIds[caption.id] = true;
            if (!finite(caption.start) || !finite(caption.end) || caption.start < 0 || caption.end <= caption.start || caption.start < previous) { throw new Error("Caption timings must be ordered and must not overlap."); }
            previous = caption.end;
            if (!Array.isArray(caption.wordIds) || !caption.wordIds.length || caption.wordIds.length > 100) { throw new Error("Each caption needs between 1 and 100 word IDs."); }
            var last = -1;
            caption.wordIds.forEach(function (id) {
                var word = byId[id];
                if (!Number.isInteger(id) || id < 0 || !word || used[id] || word.start < last || word.start < caption.start - 0.001 || word.end > caption.end + 0.001) { throw new Error("Caption word references must be unique, ordered and inside the caption timing."); }
                used[id] = true;
                last = word.start;
            });
            caption.text = caption.wordIds.map(function (id) { return byId[id].text + byId[id].punctuationAfter; }).join(" ");
        });
        if (Object.keys(used).length !== doc.words.length) { throw new Error("Every timed word must belong to one caption."); }
        var end = Math.max(doc.words[doc.words.length - 1].end, doc.captions[doc.captions.length - 1].end);
        doc.duration = finite(doc.duration) && doc.duration >= end ? doc.duration : end;
        if (doc.duration > 86400) { throw new Error("Clips must be shorter than 24 hours."); }
        return doc;
    }
    function demo(language) {
        var phrases = language === "ka-GE" ? ["ყველა სიტყვას მნიშვნელობა აქვს", "შენი ამბავი მოძრაობაში ცოცხლდება", "შექმენი რაღაც განსაკუთრებული"] : ["Make every word matter", "Your story deserves captions", "Create something worth watching"];
        var words = [], captions = [], cursor = 0.2;
        phrases.forEach(function (phrase, ci) {
            var ids = [], start = cursor;
            phrase.split(" ").forEach(function (text) {
                var id = words.length, length = 0.48;
                words.push({ id: id, text: text, start: cursor, end: cursor + length, confidence: 1, speaker: null, punctuationAfter: "", isEdited: false });
                ids.push(id); cursor += length + 0.08;
            });
            captions.push({ id: ci, text: phrase, start: start, end: cursor - 0.08, wordIds: ids, lineIndex: 0 });
            cursor += 0.5;
        });
        return { id: "built-in-demo", sourceMediaPath: "", language: language, provider: "demo", duration: cursor, words: words, captions: captions };
    }
    function editWord(doc, id, text) {
        text = text.trim();
        if (!text || /\s/.test(text) || text.length > 200) { throw new Error("Edit one word at a time. Keep its timing; use JSON import to add or remove words."); }
        var word = doc.words.filter(function (w) { return w.id === id; })[0];
        if (!word) { throw new Error("Word not found."); }
        word.text = text; word.isEdited = true;
        doc.captions.forEach(function (caption) {
            var map = Object.create(null); doc.words.forEach(function (w) { map[w.id] = w; });
            caption.text = caption.wordIds.map(function (wid) { return map[wid].text + (map[wid].punctuationAfter || ""); }).join(" ");
        });
    }
    var api = { validate: validate, demo: demo, editWord: editWord };
    if (typeof module !== "undefined" && module.exports) { module.exports = api; } else { root.KCF_Transcript = api; }
}(this));
