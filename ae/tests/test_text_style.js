/* Text styling: fill, stroke, faux styles and the drop shadow, which is
   what the Type tab's controls actually drive. */

const assert = require("node:assert/strict");
const test = require("node:test");

const { loadLib, makeTextLayer, build } = require("./ae_stub.js");

const BASE = {
    font: "NotoSansGeorgian-Bold",
    fontSize: 72,
    tracking: 0,
    lineHeight: 0,
    fillColor: [1, 1, 1],
    strokeColor: [0, 0, 0],
    strokeWidth: 7
};

function style(overrides) {
    const context = loadLib();
    const layer = makeTextLayer();
    context.KCF_styleTextLayer(layer, Object.assign({}, BASE, overrides || {}));
    return layer.textDocument;
}

test("generated text ignores inherited AE caps and character scaling", () => {
    const context = loadLib();
    const layer = makeTextLayer();
    Object.assign(layer.textDocument, {
        allCaps: true, horizontalScale: 160, verticalScale: 70, baselineShift: 25,
        fauxItalic: true
    });
    context.KCF_styleTextLayer(layer, Object.assign({}, BASE, { fauxBold: true }));
    const applied = layer.sourceText.applied;

    assert.equal(applied.allCaps, false, "lowercase transcript words must stay lowercase on screen");
    assert.equal(applied.smallCaps, false);
    assert.equal(applied.text, "word");
    assert.equal(applied.horizontalScale, 100);
    assert.equal(applied.verticalScale, 100);
    assert.equal(applied.baselineShift, 0);
    assert.equal(applied.fauxItalic, false);
    assert.equal(applied.fauxBold, true, "requested styling still applies after the reset");
    assert.equal(applied.font, "NotoSansGeorgian-Bold");
    assert.equal(applied.fontSize, 72);
});

test("fractional tracking is rounded only when assigning the AE text property", () => {
    for (const [requested, expected] of [[27.0171171834326, 27], [-12.75, -13]]) {
        const context = loadLib();
        const layer = makeTextLayer();
        const settings = Object.assign({}, BASE, { tracking: requested });
        context.KCF_styleTextLayer(layer, settings);
        assert.equal(layer.textDocument.tracking, expected);
        assert.equal(settings.tracking, requested, "the supplied style must stay unchanged");
    }
});

// --- fill and stroke --------------------------------------------------

test("text is filled by default", () => {
    const doc = style();

    assert.equal(doc.applyFill, true);
    assert.deepEqual(Array.from(doc.fillColor), [1, 1, 1]);
});

test("turning the fill off leaves hollow outlined text", () => {
    const doc = style({ fill: false, stroke: true });

    assert.equal(doc.applyFill, false, "no fill");
    assert.equal(doc.applyStroke, true, "stroke still drawn");
    assert.equal(doc.strokeWidth, 7);
});

test("text with neither fill nor stroke falls back to a fill so it stays visible", () => {
    const doc = style({ fill: false, stroke: false });

    assert.equal(doc.applyFill, true);
    assert.deepEqual(Array.from(doc.fillColor), [1, 1, 1]);
});

test("stroke position outer draws the fill over the stroke", () => {
    const doc = style({ stroke: true, strokePosition: "outer" });

    assert.equal(doc.strokeOverFill, false);
});

test("stroke position centre draws the stroke over the fill", () => {
    const doc = style({ stroke: true, strokePosition: "center" });

    assert.equal(doc.strokeOverFill, true);
});

test("stroke colour and weight come straight from the settings", () => {
    const doc = style({ stroke: true, strokeColor: [1, 0, 0], strokeWidth: 12 });

    assert.deepEqual(Array.from(doc.strokeColor), [1, 0, 0]);
    assert.equal(doc.strokeWidth, 12);
});

// --- faux styles ------------------------------------------------------

test("faux bold and faux italic are both applied", () => {
    const doc = style({ fauxBold: true, fauxItalic: true });

    assert.equal(doc.fauxBold, true);
    assert.equal(doc.fauxItalic, true);
});

test("faux styles stay off unless asked for", () => {
    const doc = style({ fauxBold: false, fauxItalic: false });

    assert.equal(doc.fauxBold, false);
    assert.equal(doc.fauxItalic, false);
});

// --- drop shadow ------------------------------------------------------

function shadow(overrides) {
    const context = loadLib();
    const layer = makeTextLayer();
    context.KCF_addDropShadow(layer, Object.assign({}, BASE, overrides || {}));
    return layer.effects["ADBE Drop Shadow"];
}

test("shadow opacity is scaled into the range AE actually reports", () => {
    // AE's Drop Shadow opacity tops out at 255, not 100
    const fx = shadow({ shadowOpacity: 100 });

    assert.equal(fx.property("ADBE Drop Shadow-0002").value, 255);
});

test("a half-strength shadow lands halfway up that range", () => {
    const fx = shadow({ shadowOpacity: 50 });

    assert.equal(fx.property("ADBE Drop Shadow-0002").value, 127.5);
});

test("shadow colour, angle, distance and softness are all set", () => {
    const fx = shadow({
        shadowColor: [0.1, 0.2, 0.3],
        shadowAngle: 45,
        shadowDistance: 20,
        shadowSoftness: 30
    });

    assert.deepEqual(Array.from(fx.property("ADBE Drop Shadow-0001").value),
        [0.1, 0.2, 0.3]);
    assert.equal(fx.property("ADBE Drop Shadow-0003").value, 45);
    assert.equal(fx.property("ADBE Drop Shadow-0004").value, 20);
    assert.equal(fx.property("ADBE Drop Shadow-0005").value, 30);
});

test("a build without the drop shadow effect degrades quietly", () => {
    const context = loadLib();
    const { makePrecomp } = require("./ae_stub.js");
    const comp = makePrecomp({ noEffects: true });
    const layer = comp.layers.addText("word");

    assert.doesNotThrow(() => context.KCF_addDropShadow(layer, BASE));
});

// --- wired through the builder ---------------------------------------

test("the builder gives every word the shadow settings from the panel", () => {
    const { precomp } = build(2, {
        shadow: true,
        shadowOpacity: 80,
        shadowAngle: 90,
        shadowDistance: 14,
        shadowSoftness: 6,
        shadowColor: [0, 0, 0]
    });

    for (const layer of precomp.created) {
        const fx = layer.effects["ADBE Drop Shadow"];
        assert.ok(fx, `word ${layer.index} should have a shadow`);
        assert.equal(fx.property("ADBE Drop Shadow-0004").value, 14);
        assert.equal(fx.property("ADBE Drop Shadow-0002").value, 204);
    }
});

test("outlined text survives the full build", () => {
    const { precomp } = build(2, { fill: false, stroke: true, strokeWidth: 9 });

    for (const layer of precomp.created) {
        assert.equal(layer.textDocument.applyFill, false);
        assert.equal(layer.textDocument.strokeWidth, 9);
    }
});
