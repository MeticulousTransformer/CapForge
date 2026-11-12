const assert = require("node:assert/strict");
const test = require("node:test");
const {build} = require("./ae_stub");

test("caption box opacity accepts 0, partial and solid values without fading words", () => {
    const baseline = build(3,{backgroundBox:false}).precomp;
    for (const opacity of [0, 35, 100]) {
        const {precomp, caption} = build(3, {backgroundBox:true, boxColor:[0,0,0], boxOpacity:opacity});
        assert.equal(precomp.shapes.length,1);
        const box = precomp.shapes[0];
        assert.equal(box.transform("Opacity").value,opacity);
        assert.equal(box.inPoint,caption.start); assert.equal(box.outPoint,caption.end);
        precomp.created.forEach((word,index) => {
            const expected = baseline.created[index].transform("Opacity");
            assert.equal(word.transform("Opacity").value,expected.value);
            assert.deepEqual(word.transform("Opacity").keys,expected.keys);
        });
    }
});

test("old looks default to a solid box and out-of-range values stay within 0–100", () => {
    for (const [value, expected] of [[undefined,100],[NaN,100],[-10,0],[200,100]]) {
        const {precomp} = build(2, {backgroundBox:true,boxColor:[0,0,0],boxOpacity:value});
        assert.equal(precomp.shapes[0].transform("Opacity").value,expected);
    }
    assert.equal(build(2,{backgroundBox:false,boxOpacity:35}).precomp.shapes.length,0);
});

test("caption backgrounds cover the measured glyph bounds with equal vertical padding", () => {
    for (const fitBoundary of [false, true]) {
        const { precomp, settings } = build(3, {
            backgroundBox: true, boxColor: [0, 0, 0], wordsPerLine: 2,
            fitBoundary, fitWidth: 800, fitMaxFontSize: 400
        });
        const bounds = precomp.created.map(layer => {
            const rect = layer.sourceRectAtTime(0, false);
            const baseline = layer.transform("Position").value[1] -
                layer.transform("Anchor Point").value[1];
            return { top: baseline + rect.top, bottom: baseline + rect.top + rect.height };
        });
        const top = Math.min(...bounds.map(rect => rect.top));
        const bottom = Math.max(...bounds.map(rect => rect.bottom));
        const box = precomp.shapes[0];
        const pad = Math.round(settings.fontSize * 0.35);
        assert.ok(Math.abs((box.position[1] - box.size[1] / 2) - (top - pad)) <= 0.5);
        assert.ok(Math.abs((box.position[1] + box.size[1] / 2) - (bottom + pad)) <= 0.5);
    }
});

test("a solid caption background stays below the active word's colored box", () => {
    const { precomp } = build(3, {
        preset: "active_word_box", backgroundBox: true,
        boxColor: [0, 0, 0], boxOpacity: 100
    });
    const background = precomp.shapes.find(layer => layer.name === "KCF_C000_BOX");
    const textBottom = Math.max(...precomp.created.map(layer => precomp.layerStack.indexOf(layer)));
    const backgroundIndex = precomp.layerStack.indexOf(background);
    for (const box of precomp.shapes.filter(layer => layer !== background)) {
        const index = precomp.layerStack.indexOf(box);
        assert.ok(index > textBottom, "active box must be behind caption text");
        assert.ok(index < backgroundIndex, "active box must remain visible above caption background");
    }
});
