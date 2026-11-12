/* Text styling + measurement helpers for AE word layers. */

// "#FFCC00" or "FFCC00" -> [1, 0.8, 0]
function KCF_hexToRgb(hex) {
    hex = String(hex).replace(/^#/, "");
    if (hex.length === 3) {
        hex = hex.charAt(0) + hex.charAt(0) +
              hex.charAt(1) + hex.charAt(1) +
              hex.charAt(2) + hex.charAt(2);
    }
    var n = parseInt(hex, 16);
    if (isNaN(n)) { return [1, 1, 1]; }
    return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

function KCF_pad3(n) {
    var s = String(n);
    while (s.length < 3) { s = "0" + s; }
    return s;
}

function KCF_timestamp() {
    var d = new Date();
    function p(x) { return (x < 10 ? "0" : "") + x; }
    return "" + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) +
        "_" + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds());
}

/* Apply typography settings to a text layer's TextDocument. */
function KCF_styleTextLayer(textLayer, style) {
    var prop = textLayer.property("Source Text");
    var doc = prop.value;
    // New AE text inherits the editor's Character panel state (including
    // All Caps and scaling). Start clean before applying this caption's style.
    doc.resetCharStyle();
    if (style.font) { doc.font = style.font; }
    doc.fontSize = style.fontSize;
    // The boundary fitter works with fractional estimates; AE's tracking
    // property accepts integers only. Keep that conversion at the AE boundary.
    doc.tracking = Math.round(style.tracking || 0);
    if (style.lineHeight && style.lineHeight > 0) {
        doc.autoLeading = false;
        doc.leading = style.lineHeight;
    }

    // fill off + stroke on gives hollow outlined text
    doc.applyFill = (style.fill !== false);
    if (doc.applyFill) { doc.fillColor = style.fillColor; }

    if (style.stroke) {
        doc.applyStroke = true;
        doc.strokeColor = style.strokeColor;
        doc.strokeWidth = style.strokeWidth;
        /* AE always centres the stroke on the glyph outline. Painting the
           fill on top hides its inner half, which reads as an outer
           stroke; a true inner stroke is not available on AE text. */
        doc.strokeOverFill = (style.strokePosition === "center");
    } else {
        doc.applyStroke = false;
    }
    if (!doc.applyFill && !doc.applyStroke) {
        doc.applyFill = true;               // otherwise nothing renders
        doc.fillColor = style.fillColor;
    }

    doc.justification = ParagraphJustification.LEFT_JUSTIFY;
    if (style.fauxBold !== undefined && doc.fauxBold !== undefined) {
        try { doc.fauxBold = style.fauxBold; } catch (e) { /* pre-CC2019 */ }
    }
    if (style.fauxItalic !== undefined && doc.fauxItalic !== undefined) {
        try { doc.fauxItalic = style.fauxItalic; } catch (e) { /* pre-CC2019 */ }
    }
    prop.setValue(doc);
}

/* A copy of a style set at a different size. The original is untouched,
   so the caller can re-derive from it as often as it likes. */
function KCF_withFontSize(style, fontSize) {
    var out = {};
    for (var key in style) {
        if (style.hasOwnProperty(key)) { out[key] = style[key]; }
    }
    out.fontSize = fontSize;
    return out;
}

/* Drop shadow with real controls behind it.
   AE's Drop Shadow opacity is not a percentage — it runs to whatever
   maximum the property reports (255 on current builds), so the panel's
   0-100 value gets scaled into that range rather than passed straight
   through. */
function KCF_addDropShadow(textLayer, style) {
    var fx;
    try {
        fx = textLayer.property("Effects").addProperty("ADBE Drop Shadow");
    } catch (e) {
        return null;                        // effect unavailable
    }
    function set(matchName, value) {
        try { fx.property(matchName).setValue(value); } catch (e) {}
    }
    function pick(value, fallback) {
        if (value === undefined || value === null) { return fallback; }
        if (typeof value === "number" && isNaN(value)) { return fallback; }
        return value;
    }

    set("ADBE Drop Shadow-0001", pick(style.shadowColor, [0, 0, 0]));

    try {
        var opacity = fx.property("ADBE Drop Shadow-0002");
        var pct = Math.max(0, Math.min(100, pick(style.shadowOpacity, 60)));
        var top = opacity.hasMax ? opacity.maxValue : 100;
        opacity.setValue(top * pct / 100);
    } catch (e) {}

    set("ADBE Drop Shadow-0003", pick(style.shadowAngle, 135));
    set("ADBE Drop Shadow-0004", pick(style.shadowDistance, 8));
    set("ADBE Drop Shadow-0005", pick(style.shadowSoftness, 12));
    return fx;
}

/* Measure a layer's source rect at a time where the layer exists. */
function KCF_measureLayer(layer, comp) {
    var t = Math.max(layer.inPoint, 0);
    return layer.sourceRectAtTime(t, false);
}
