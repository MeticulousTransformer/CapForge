/* Shared stub of the After Effects object model for the ae/tests suite.
   Covers what KCF_buildCaption and the animation presets touch: text
   layers, shape layers, and transform properties that record the
   keyframes, eases and interpolation the presets set. */

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const LIB = path.join(__dirname, "..", "lib");
const LIB_FILES = [
    "text_measure.jsx", "style_shuffle.jsx", "presets.jsx", "layer_builder.jsx"
];

/* The .jsx libs are ExtendScript, so they run in a vm context with the
   handful of AE globals they reference stubbed in. */
function loadLib() {
    const context = {
        ParagraphJustification: { LEFT_JUSTIFY: 1 },
        KeyframeInterpolationType: { HOLD: 2 },
        KeyframeEase: function (speed, influence) {
            this.speed = speed;
            this.influence = influence;
        }
    };
    vm.createContext(context);
    for (const file of LIB_FILES) {
        vm.runInContext(fs.readFileSync(path.join(LIB, file), "utf8"), context);
    }
    return context;
}

/* The size the per-word metrics below are quoted at. A layer styled at
   any other size reports metrics scaled from these. */
const BASE_FONT_SIZE = 60;

/* Distinct per-word metrics so a bug cannot hide behind equal numbers. */
function rectFor(index) {
    return {
        left: 2,
        top: -30 - index * 3,
        width: 100 + index * 25,
        height: 40 + index * 3
    };
}

/* Real text metrics answer to both size and tracking, which is what
   lets the boundary fitter converge — a stub with fixed widths would
   make any fitting code look like it worked. AE tracking is thousandths
   of an em, applied after every character. */
function rectAtSize(index, fontSize, tracking, charCount) {
    const base = rectFor(index);
    const size = fontSize > 0 ? fontSize : BASE_FONT_SIZE;
    const k = size / BASE_FONT_SIZE;
    const spread = (tracking || 0) / 1000 * size * (charCount || 0);
    return {
        left: base.left * k,
        top: base.top * k,
        width: base.width * k + spread,
        height: base.height * k
    };
}

/* Effect properties that report a maximum in real AE. Drop Shadow's
   opacity runs to 255, not 100 — code that scales a percentage into it
   has to read the range rather than assume one. */
const PROPERTY_MAX = { "ADBE Drop Shadow-0002": 255 };

function makeProperty(name) {
    const keys = [];
    const eases = [];
    const hasMax = Object.prototype.hasOwnProperty.call(PROPERTY_MAX, name);
    return {
        name,
        isSpatial: name === "Position",
        hasMax,
        maxValue: hasMax ? PROPERTY_MAX[name] : undefined,
        value: null,
        keys,
        eases,
        interpolation: null,
        get numKeys() { return keys.length; },
        setValue(v) { this.value = v; },
        setValueAtTime(time, value) { keys.push({ time, value }); },
        setInterpolationTypeAtKey(index, type) { this.interpolation = type; },
        setTemporalEaseAtKey(index, easeIn, easeOut) {
            eases.push({ index, easeIn, easeOut });
        }
    };
}

function makeLayer(index, options, text) {
    const props = {};
    const effects = {};
    /* KCF_styleTextLayer reads .value, mutates it, then sets it back, so
       one persistent object records the whole TextDocument. */
    const sourceText = {
        value: {
            text: String(text || ""),
            font: "", fontSize: 0, tracking: 0,
            autoLeading: true, leading: 0,
            applyFill: true, fillColor: [1, 1, 1],
            applyStroke: false, strokeColor: [0, 0, 0], strokeWidth: 0,
            strokeOverFill: false, justification: null,
            fauxBold: false, fauxItalic: false,
            allCaps: false, smallCaps: false,
            horizontalScale: 100, verticalScale: 100, baselineShift: 0,
            resetCharStyle() {
                Object.assign(this, {
                    font: "", fontSize: 12, tracking: 0,
                    autoLeading: true, leading: 0,
                    applyFill: true, fillColor: [1, 1, 1],
                    applyStroke: false, strokeColor: [0, 0, 0], strokeWidth: 0,
                    strokeOverFill: false, fauxBold: false, fauxItalic: false,
                    allCaps: false, smallCaps: false,
                    horizontalScale: 100, verticalScale: 100, baselineShift: 0
                });
            }
        },
        applied: null,
        setValue(doc) { sourceText.applied = doc; }
    };
    // AE rejects fractional tracking at assignment, even when a fitting
    // calculation legitimately produced a fractional estimate.
    let tracking = 0;
    Object.defineProperty(sourceText.value, "tracking", {
        enumerable: true,
        get() { return tracking; },
        set(value) {
            if (!Number.isInteger(value)) { throw new Error("Unable to set tracking: value is not an integer."); }
            tracking = value;
        }
    });
    function prop(name) {
        if (!props[name]) { props[name] = makeProperty(name); }
        return props[name];
    }
    return {
        sourceText,
        get textDocument() { return sourceText.value; },
        index,
        name: "",
        comment: "",
        inPoint: 0,
        outPoint: 0,
        motionBlur: false,
        containingComp: options.comp,
        props,
        effects,
        transform: prop,
        text,
        sourceRectAtTime() {
            return rectAtSize(index, sourceText.value.fontSize,
                sourceText.value.tracking, String(text || "").length);
        },
        property(name) {
            if (name === "Transform") { return { property: prop }; }
            if (name === "Source Text") { return sourceText; }
            if (name === "Effects") {
                return {
                    addProperty(matchName) {
                        if (options.noEffects) {
                            throw new Error("effect unavailable");
                        }
                        if (!effects[matchName]) {
                            effects[matchName] = { matchName, property: prop };
                        }
                        return effects[matchName];
                    }
                };
            }
            throw new Error("unexpected property: " + name);
        }
    };
}

/* Only the vector property chain KCF_addRoundRect walks. */
function makeShape() {
    const props = {};
    function prop(name) {
        if (!props[name]) { props[name] = makeProperty(name); }
        return props[name];
    }
    /* Every node in a shape's vector tree is both navigable and settable,
       so hand back a leaf that also carries the group methods. */
    const vectorNode = {
        addProperty() { return vectorNode; },
        property(name) {
            const leaf = prop(name);
            leaf.addProperty = () => vectorNode;
            leaf.property = (child) => vectorNode.property(child);
            return leaf;
        },
        setValue() {}
    };
    return {
        name: "",
        comment: "",
        inPoint: 0,
        outPoint: 0,
        props,
        transform: prop,
        moveAfter() {},
        get position() { return prop("Position").value; },
        get size() { return prop("ADBE Vector Rect Size").value; },
        property(name) {
            if (name === "Transform") { return { property: prop }; }
            return vectorNode;
        }
    };
}

function makePrecomp(options) {
    const opts = options || {};
    const rf = opts.rectFor || rectFor;
    const created = [];
    const shapes = [];
    const layerStack = []; // AE index order: new layers start at the top.
    const comp = {
        width: opts.width || 1080,
        height: opts.height || 1920,
        motionBlur: false,
        created,
        shapes,
        layerStack,
        layers: {
            addText(source) {
                const layer = makeLayer(created.length, {
                    rectFor: rf, comp, noEffects: opts.noEffects
                }, source);
                created.push(layer);
                layerStack.unshift(layer);
                return layer;
            },
            addShape() {
                const shape = makeShape();
                shape.moveAfter = function (other) {
                    layerStack.splice(layerStack.indexOf(shape), 1);
                    layerStack.splice(layerStack.indexOf(other) + 1, 0, shape);
                };
                shape.moveToEnd = function () {
                    layerStack.splice(layerStack.indexOf(shape), 1);
                    layerStack.push(shape);
                };
                shapes.push(shape);
                layerStack.unshift(shape);
                return shape;
            }
        }
    };
    return comp;
}

function makeInput(wordCount) {
    const words = [];
    for (let i = 0; i < wordCount; i += 1) {
        words.push({
            id: "w" + i,
            text: "word" + i,
            punctuationAfter: "",
            start: i * 0.5,
            end: i * 0.5 + 0.4
        });
    }
    const caption = {
        id: "c0",
        wordIds: words.map((w) => w.id),
        start: 0,
        end: wordCount * 0.5
    };
    return { doc: { words, captions: [caption] }, caption };
}

const SETTINGS = {
    preset: "minimal",
    fontSize: 60,
    font: "Arial",
    fillColor: [1, 1, 1],
    highlightColor: [1, 0.8, 0],
    boxRadius: 8,
    tracking: 0,
    lineHeight: 0,
    wordSpacing: 12,
    wordsPerLine: 0,
    minWordsPerLine: 0,
    charsPerLine: 0,
    alignment: "center",
    anchorPreset: "center",
    stroke: false,
    shadow: false,
    backgroundBox: false
};

/* Run KCF_buildCaption over `wordCount` words and hand back everything
   a test needs to check the result. */
function build(wordCount, overrides) {
    const context = loadLib();
    const precomp = makePrecomp();
    const { doc, caption } = makeInput(wordCount);
    const settings = Object.assign({}, SETTINGS, overrides || {});
    const pos = { x: 960, y: 540 };
    // same construction KCF_generate uses, so tests exercise real wiring
    const shuffler = context.KCF_shufflerFor(settings);
    context.KCF_buildCaption(precomp, doc, caption, 0, settings, pos, shuffler);
    return { context, precomp, settings, pos, doc, caption, shuffler };
}

/* Comp-space left edge of a word, derived the way AE derives it: the
   layer origin sits at Position - Anchor Point. */
function leftEdge(layer) {
    return layer.transform("Position").value[0] -
        layer.transform("Anchor Point").value[0] +
        rectFor(layer.index).left;
}

/* Baseline of a word in comp space. */
function baseline(layer) {
    return layer.transform("Position").value[1] -
        layer.transform("Anchor Point").value[1];
}

/* A bare text layer, for unit-testing the styling helpers on their own. */
function makeTextLayer(options) {
    const comp = makePrecomp(options);
    return comp.layers.addText("word");
}

module.exports = {
    loadLib, rectFor, rectAtSize, BASE_FONT_SIZE, makePrecomp, makeInput,
    SETTINGS, build, leftEdge, baseline, makeTextLayer
};
