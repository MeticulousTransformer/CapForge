/* Fitting each caption line to a boundary width by scaling its type,
   the way stretched-to-the-margins social captions are set. */

const assert = require("node:assert/strict");
const test = require("node:test");

const { build, SETTINGS } = require("./ae_stub.js");

const FIT = {
    fitBoundary: true,
    fitWidth: 800,
    fitMaxFontSize: 400,
    wordsPerLine: 2
};

/* Where a word actually lands, measured from its own current metrics
   rather than assumed ones. */
function edges(layer) {
    const rect = layer.sourceRectAtTime(0, false);
    const originX = layer.transform("Position").value[0] -
        layer.transform("Anchor Point").value[0];
    return { left: originX + rect.left, right: originX + rect.left + rect.width };
}

function lineWidth(layers) {
    const spans = layers.map(edges);
    return Math.max(...spans.map((s) => s.right)) -
        Math.min(...spans.map((s) => s.left));
}

function linesOf(precomp, wordsPerLine) {
    const out = [];
    for (let i = 0; i < precomp.created.length; i += wordsPerLine) {
        out.push(precomp.created.slice(i, i + wordsPerLine));
    }
    return out;
}

function fontSizeOf(layer) {
    return layer.textDocument.fontSize;
}

// --- filling the boundary --------------------------------------------

test("every line is scaled until it fills the boundary", () => {
    const { precomp } = build(4, FIT);

    for (const line of linesOf(precomp, 2)) {
        assert.ok(Math.abs(lineWidth(line) - 800) < 1,
            `line came out ${lineWidth(line).toFixed(1)}px wide, wanted 800`);
    }
});

test("a one-word line and a two-word line end up the same width", () => {
    // 3 words at 2 per line gives lines of 2 and 1
    const { precomp } = build(3, FIT);
    const lines = linesOf(precomp, 2);

    assert.equal(lines.length, 2);
    assert.ok(Math.abs(lineWidth(lines[0]) - lineWidth(lines[1])) < 1,
        `lines differ: ${lineWidth(lines[0]).toFixed(1)} vs ${lineWidth(lines[1]).toFixed(1)}`);
});

test("a long line shrinks and a short line grows", () => {
    const { precomp } = build(4, FIT);
    // word 0 is the narrowest, word 3 the widest, at a shared base size
    const sizes = precomp.created.map(fontSizeOf);

    assert.ok(sizes[0] > SETTINGS.fontSize,
        "the narrow first line should have been scaled up");
    assert.ok(sizes[3] < sizes[0],
        "the wider second line needs less size than the narrow first one");
});

test("the boundary defaults to the comp width less the safe margins", () => {
    const { precomp } = build(2, Object.assign({}, FIT, {
        fitWidth: 0, safeMargin: 100
    }));

    // stub comp is 1080 wide, so 1080 - 2*100
    assert.ok(Math.abs(lineWidth(linesOf(precomp, 2)[0]) - 880) < 1);
});

test("type never grows past the maximum size", () => {
    const { precomp } = build(2, Object.assign({}, FIT, {
        fitWidth: 6000, fitMaxFontSize: 100
    }));

    for (const layer of precomp.created) {
        assert.ok(fontSizeOf(layer) <= 100,
            `word ${layer.index} reached ${fontSizeOf(layer)}px`);
    }
});

// --- the rest of the layout keeps up ---------------------------------

test("anchor points are recomputed for the fitted size", () => {
    const { precomp } = build(4, FIT);

    for (const layer of precomp.created) {
        const rect = layer.sourceRectAtTime(0, false);
        assert.ok(
            Math.abs(layer.transform("Anchor Point").value[0] -
                (rect.left + rect.width / 2)) < 0.001,
            `word ${layer.index} anchor does not match its fitted width`
        );
    }
});

test("lines stack without overlapping once their sizes differ", () => {
    const { precomp } = build(4, FIT);
    const lines = linesOf(precomp, 2);

    const firstBaseline = lines[0][0].transform("Position").value[1] -
        lines[0][0].transform("Anchor Point").value[1];
    const secondBaseline = lines[1][0].transform("Position").value[1] -
        lines[1][0].transform("Anchor Point").value[1];
    const secondHeight = lines[1][0].sourceRectAtTime(0, false).height;

    assert.ok(secondBaseline - firstBaseline >= secondHeight * 0.9,
        `lines only ${(secondBaseline - firstBaseline).toFixed(1)}px apart ` +
        `for a ${secondHeight.toFixed(1)}px line`);
});

test("a large final one-word line stays below every glyph on the previous line", () => {
    for (const count of [3, 5]) {
        const { precomp } = build(count, FIT);
        const lines = linesOf(precomp, 2).map(line => line.map(layer => {
            const rect = layer.sourceRectAtTime(0, false);
            const baseline = layer.transform("Position").value[1] -
                layer.transform("Anchor Point").value[1];
            return { top: baseline + rect.top, bottom: baseline + rect.top + rect.height };
        }));
        for (let i = 1; i < lines.length; i++) {
            const previousBottom = Math.max(...lines[i - 1].map(rect => rect.bottom));
            const nextTop = Math.min(...lines[i].map(rect => rect.top));
            assert.ok(nextTop > previousBottom,
                `line ${i} starts at ${nextTop}, above the previous bottom ${previousBottom}`);
        }
    }
});

test("a fitted line still centres on the anchor", () => {
    const { precomp, pos } = build(4, FIT);
    const line = linesOf(precomp, 2)[0];
    const spans = line.map(edges);
    const centre = (Math.min(...spans.map((s) => s.left)) +
        Math.max(...spans.map((s) => s.right))) / 2;

    assert.ok(Math.abs(centre - pos.x) < 1,
        `line centred at ${centre.toFixed(1)}, expected ${pos.x}`);
});

// --- it composes with shuffling --------------------------------------

test("a shuffled look survives being re-sized to fit", () => {
    const { precomp } = build(6, Object.assign({}, FIT, {
        styleShuffle: true,
        shuffleVariants: ["solid", "highlight", "outline"],
        shuffleSeed: 2024,
        highlightColor: [1, 0, 0]
    }));

    let outlines = 0;
    for (const layer of precomp.created) {
        const meta = JSON.parse(layer.comment);
        if (meta.variant === "outline") {
            outlines += 1;
            assert.equal(layer.textDocument.applyFill, false,
                `word ${layer.index} lost its hollow look when refitted`);
        }
    }
    assert.ok(outlines > 0, "expected at least one outlined word");
});

// --- leaving it off must change nothing -------------------------------

test("with fitting off the base font size is untouched", () => {
    const { precomp } = build(4, { wordsPerLine: 2 });

    for (const layer of precomp.created) {
        assert.equal(fontSizeOf(layer), SETTINGS.fontSize);
    }
});

test("with fitting off the layout is exactly what it always was", () => {
    const plain = build(4, { wordsPerLine: 2, lineHeight: 70 });
    const alsoPlain = build(4, {
        wordsPerLine: 2, lineHeight: 70, fitBoundary: false, fitWidth: 800
    });

    plain.precomp.created.forEach((layer, i) => {
        assert.deepEqual(
            Array.from(alsoPlain.precomp.created[i].transform("Position").value),
            Array.from(layer.transform("Position").value),
            `word ${i} moved`
        );
    });
});

// --- tracking as the second lever ------------------------------------

const CAPPED = Object.assign({}, FIT, {
    wordsPerLine: 1,
    fitMaxFontSize: 100   // far too small to fill 800px on its own
});

test("tracking opens up to close what the size cap left short", () => {
    const { precomp } = build(2, Object.assign({}, CAPPED, {
        fitMaxTracking: 3000
    }));

    for (const line of linesOf(precomp, 1)) {
        assert.ok(Math.abs(lineWidth(line) - 800) < 1,
            `line came out ${lineWidth(line).toFixed(1)}px, wanted 800`);
    }
    assert.ok(precomp.created[0].textDocument.tracking > 0,
        "tracking should have been opened up");
});

test("tracking never runs past its ceiling", () => {
    const { precomp } = build(2, Object.assign({}, CAPPED, {
        fitMaxTracking: 120
    }));

    for (const layer of precomp.created) {
        assert.ok(layer.textDocument.tracking <= 120,
            `word ${layer.index} reached ${layer.textDocument.tracking}`);
    }
});

test("a tracking ceiling of zero leaves tracking alone", () => {
    const { precomp } = build(2, Object.assign({}, CAPPED, {
        fitMaxTracking: 0
    }));

    for (const layer of precomp.created) {
        assert.equal(layer.textDocument.tracking, 0);
    }
});

test("a line that already fills the boundary gets no extra tracking", () => {
    const { precomp } = build(4, Object.assign({}, FIT, {
        fitMaxTracking: 3000
    }));

    for (const layer of precomp.created) {
        assert.equal(layer.textDocument.tracking, 0,
            `word ${layer.index} was tracked out despite the line fitting`);
    }
});
