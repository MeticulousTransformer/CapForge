const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const transcript = require("../js/transcript");
const settings = require("../js/settings");
const titles = require("../js/catalog");
const preview = require("../js/preview");
const stub = require("../../ae/tests/ae_stub");
const root = path.resolve(__dirname, "../..");

function sample() { return transcript.demo("ka-GE"); }

test("CapForge branding preserves saved looks from the earlier name", () => {
    for (const tool of ["CapForge","Kartuli Caption Forge"]) {
        const data={tool,version:1,settings:{preset:"slide_in",boxOpacity:35}};
        assert.equal(settings.isSavedLook(data),true);
        assert.equal(settings.normalize(data.settings).boxOpacity,35);
    }
    assert.equal(settings.isSavedLook({tool:"Unrelated",version:1,settings:{}}),false);
    const html=fs.readFileSync(path.join(root,"panel/index.html"),"utf8");
    assert.ok(html.includes('<title>CapForge</title>'));
    assert.ok(html.includes('<strong>CAPFORGE</strong>'));
    assert.ok(!html.includes('CAPTION FORGE'));
});

test("Georgian survives validation and edits preserve every timestamp", () => {
    const doc = transcript.validate(sample());
    const before = doc.words.map(w => [w.id, w.start, w.end]);
    transcript.editWord(doc, 0, "გამარჯობა");
    assert.deepEqual(doc.words.map(w => [w.id, w.start, w.end]), before);
    assert.ok(doc.captions[0].text.startsWith("გამარჯობა"));
    assert.equal(doc.words[0].isEdited, true);
    assert.throws(() => transcript.editWord(doc, 0, "two words"));
    assert.ok(doc.captions.every(caption => caption.wordIds.length <= 4));
});

test("reject missing timings, duplicate IDs, gaps in caption ownership, bad references and backwards captions", () => {
    for (const change of [d => delete d.words[0].start, d => d.words[1].id = 0, d => d.captions[0].wordIds[0] = 999, d => d.captions[0].end = 0.3, d => d.captions[1].start = 0.1, d => d.captions[0].wordIds.shift()]) {
        const doc = sample(); change(doc); assert.throws(() => transcript.validate(doc));
    }
});

test("imports the existing Georgian and English fixture contract without altering timing", () => {
    for (const language of ["georgian", "english"]) {
        const original = JSON.parse(fs.readFileSync(path.join(root, `backend/tests/fixtures/${language}_short.json`), "utf8"));
        assert.deepEqual(transcript.validate(original).words, original.words);
    }
});

test("settings exports contain no credentials and AE receives normalized RGB colors", () => {
    const look = settings.normalize({apiKey: "not-exported", fontSize: 9999, wordsPerLine: 2.7, fillColor: "#D6B87C"});
    assert.equal(look.apiKey, undefined); assert.equal(look.fontSize, 600); assert.equal(look.wordsPerLine, 3);
    assert.deepEqual(settings.forAE(look).fillColor, [214/255, 184/255, 124/255]);
    assert.throws(() => settings.normalize({fillColor: "red"}));
    assert.throws(() => settings.normalize({fontSize: "bad"}));
});

test("background opacity is retained in saved looks and the AE payload, including zero", () => {
    assert.equal(settings.normalize({}).boxOpacity,100);
    for (const value of [0,35,100]) {
        const look = settings.normalize({backgroundBox:true,boxOpacity:value});
        const restored = settings.normalize(JSON.parse(JSON.stringify(look)));
        assert.equal(restored.boxOpacity,value); assert.equal(settings.forAE(restored).boxOpacity,value);
    }
    assert.equal(settings.normalize({boxOpacity:-10}).boxOpacity,0);
    assert.equal(settings.normalize({boxOpacity:200}).boxOpacity,100);
    assert.throws(()=>settings.normalize({boxOpacity:"invalid"}));
});

test("canvas opacity fades only the caption background and restores text opacity", () => {
    const shapes = [], text = [], stack = [];
    const ctx = {
        globalAlpha:1, fillStyle:"", shadowBlur:0,
        save() { stack.push({alpha:this.globalAlpha,fill:this.fillStyle}); },
        restore() { const state = stack.pop(); this.globalAlpha=state.alpha; this.fillStyle=state.fill; },
        fill() { shapes.push({color:this.fillStyle,alpha:this.globalAlpha}); },
        fillText() { text.push(this.globalAlpha); },
        measureText(value) { return {width:value.length*20}; },
        createLinearGradient() { return {addColorStop(){}}; }
    };
    for (const name of ["scale","fillRect","beginPath","moveTo","lineTo","arc","arcTo","closePath","setLineDash","strokeRect","translate","strokeText"]) { ctx[name]=()=>{}; }
    const window = {matchMedia:()=>({matches:true}),requestAnimationFrame:()=>1,cancelAnimationFrame(){},KCF_WordStyles:require("../js/word_styles")};
    const context = {window,document:{hidden:false}};
    vm.createContext(context); vm.runInContext(fs.readFileSync(path.join(root,"panel/js/preview.js"),"utf8"),context);
    const canvas = {width:960,height:540,style:{},getContext:()=>ctx};
    const renderer = window.KCF_Preview.create(canvas,()=>{});
    for (const opacity of [0,35,100]) {
        shapes.length=0; text.length=0;
        renderer.set(sample(),settings.normalize({preset:"minimal",backgroundBox:true,boxOpacity:opacity,boxColor:"#123456"}));
        renderer.seek(0.3);
        const box = shapes.find(shape=>shape.color==="#123456");
        assert.ok(box); assert.equal(box.alpha,opacity/100);
        assert.ok(text.length>0); assert.ok(text.every(alpha=>alpha===1));
    }
    renderer.destroy();
});

test("gallery IDs match registered real AE presets, including the standalone Satin title", () => {
    const context = stub.loadLib();
    vm.runInContext(fs.readFileSync(path.join(root, "ae/lib/title_registry.jsx"), "utf8"), context);
    vm.runInContext(fs.readFileSync(path.join(root, "ae/titles/soft_rise.jsx"), "utf8"), context);
    assert.deepEqual(titles.all.map(t => t.id).sort(), Object.keys(context.KCF_PRESETS).sort());
    assert.throws(() => context.KCF_registerTitle("minimal", "Duplicate", () => {}));
});

test("Satin generates AE keyframes relative to word timing without moving the layout", () => {
    const context = stub.loadLib();
    vm.runInContext(fs.readFileSync(path.join(root, "ae/lib/title_registry.jsx"), "utf8"), context);
    vm.runInContext(fs.readFileSync(path.join(root, "ae/titles/soft_rise.jsx"), "utf8"), context);
    const comp = stub.makePrecomp(), layer = comp.layers.addText("გამარჯობა");
    context.KCF_PRESETS.soft_rise(layer, {start: 0.5, end: 0.9}, {start: 0.2, end: 1.4}, {}, [100, 200]);
    assert.equal(layer.inPoint, 0.5); assert.equal(layer.outPoint, 1.4);
    const position = layer.property("Transform").property("Position");
    assert.deepEqual(JSON.parse(JSON.stringify(position.keys.map(k => k.value))), [[100, 212], [100, 200]]);
});

test("preview stays silent between captions and honors word entrances and highlight windows", () => {
    const style = settings.normalize({}), word = {start:1, end:1.5}, caption = {start:0.5, end:2};
    assert.equal(preview.motion("spawn_word", word, caption, 0.9, style).alpha, 0);
    assert.equal(preview.motion("highlight_word", word, caption, 1.2, style).active, true);
    assert.equal(preview.motion("highlight_word", word, caption, 1.6, style).active, false);
    assert.equal(preview.motion("minimal", word, caption, 1.2, style).active, false);
});

test("preview wraps with the same orphan-word behavior as the AE engine", () => {
    const words = ["one", "two", "three", "four", "five"].map(text => ({text}));
    assert.deepEqual(preview.wrap(words, settings.normalize({wordsPerLine:4, minWordsPerLine:2})).map(line => line.length), [3,2]);
});

test("host rejects malformed payloads before invoking non-destructive generation", () => {
    const context = {File: function () { this.parent = {parent: {}}; }, $: {fileName:"host.jsx", evalFile() { throw Error("test bootstrap"); }}, JSON};
    vm.createContext(context); vm.runInContext(fs.readFileSync(path.join(root,"panel/host.jsx"),"utf8"),context);
    context.KCF_hostError = null;
    context.KCF_engine = {presets: {minimal: ()=>{}}};
    context.KCF_hostValidate(sample(), {preset:"minimal",fontSize:72});
    const bad = sample(); bad.words[0].end = -1;
    assert.throws(() => context.KCF_hostValidate(bad, {preset:"minimal",fontSize:72}));
    assert.throws(() => context.KCF_hostValidate(sample(), {preset:"unknown",fontSize:72}));
    let called = 0; context.KCF_engine.generate = () => {called++; return "new-precomp";};
    const result = JSON.parse(context.KCF_dispatch(JSON.stringify({action:"generate",payload:{document:sample(),settings:{preset:"minimal",fontSize:72}}})));
    assert.equal(result.ok,true); assert.equal(called,1);
    assert.equal(JSON.parse(context.KCF_dispatch(JSON.stringify({action:"removeAll"}))).ok,false);
});

test("studio exposes every visual setting from the original ScriptUI panel", () => {
    const legacy = fs.readFileSync(path.join(root, "ae/KartuliCaptionForge.jsx"), "utf8");
    const gather = legacy.slice(legacy.indexOf("function gatherSettings"), legacy.indexOf("function persistSettings"));
    const keys = [...gather.matchAll(/^\s{16}([a-zA-Z]+):/gm)].map(match => match[1]);
    assert.ok(keys.length >= 40, "read the original settings contract");
    const html = fs.readFileSync(path.join(root, "panel/index.html"), "utf8");
    const controls = new Set([...html.matchAll(/data-setting="([a-zA-Z]+)"/g)].map(match => match[1]));
    for (const key of keys.concat(Object.keys(settings.defaults))) { assert.ok(controls.has(key), `${key} has a visible studio control`); }
    assert.equal(titles.get("slide_in").name, "Slide In");
    assert.equal(titles.get("bounce_in").name, "Bounce In");
});

test("automatic wrapping and independent minimums match the original layout contract", () => {
    const words = ["one", "two", "three", "four", "five"].map(text => ({text}));
    const unlimited = settings.normalize({wordsPerLine:0,charsPerLine:0,minWordsPerLine:3});
    assert.equal(unlimited.wordsPerLine, 0); assert.equal(unlimited.charsPerLine, 0);
    assert.equal(unlimited.minWordsPerLine, 3); assert.deepEqual(preview.wrap(words, unlimited).map(line => line.length), [5]);
    assert.deepEqual(preview.wrap(words, settings.normalize({wordsPerLine:2,charsPerLine:0})).map(line => line.length), [2,2,1]);
});

test("direction dial uses the same angle convention as real AE slides", () => {
    const controls = require("../js/design_controls");
    const context = stub.loadLib();
    for (const angle of [0,45,90,180,270,315]) {
        const offset = context.KCF_slideOffset(angle,100);
        assert.ok(Math.abs(controls.angleFromPoint(offset[0],offset[1])-angle)<0.000001);
    }
    const groups = controls.fontGroups([{name:"RegularPS",family:"Family",style:"Regular"},{name:"BoldPS",family:"Family",style:"Bold"}]);
    assert.deepEqual(groups.Family, [{name:"RegularPS",style:"Regular"},{name:"BoldPS",style:"Bold"}]);
});

test("slide preview honors preroll, direction, duration, dolly and separate easing", () => {
    const word = {start:1,end:1.6}, caption = {start:0.5,end:2.5};
    const style = settings.normalize({slideAngle:90,slideDistance:120,slideDuration:1,slideDolly:50,slideEaseIn:20,slideEaseOut:80});
    const start = preview.motion("slide_in",word,caption,0.94,style);
    assert.equal(start.alpha,0); assert.ok(Math.abs(start.dx+120)<0.00001); assert.ok(Math.abs(start.scale-1.5)<0.00001);
    const early = preview.motion("slide_in",word,caption,1.14,style);
    assert.ok(early.alpha>0); assert.ok(early.dx<0); assert.ok(early.scale>1);
    const changed = preview.motion("slide_in",word,caption,1.14,Object.assign({},style,{slideEaseOut:10}));
    assert.ok(Math.abs(early.dx-changed.dx)>1);
    const end = preview.motion("slide_in",word,caption,2,style);
    assert.equal(end.alpha,1); assert.ok(Math.abs(end.dx)<0.00001); assert.ok(Math.abs(end.scale-1)<0.00001);
});

test("shuffle preview uses the AE source and repeats fixed seeds exactly", () => {
    const source = fs.readFileSync(path.join(root,"ae/lib/style_shuffle.jsx"),"utf8").replace(/\r\n/g,"\n").trim();
    assert.ok(fs.readFileSync(path.join(root,"panel/js/word_styles.js"),"utf8").replace(/\r\n/g,"\n").includes(source), "generated browser adapter contains current shared engine");
    const wordStyles = require("../js/word_styles"), context = stub.loadLib();
    const look = settings.normalize({styleShuffle:true,shuffleSeed:123,shuffleFonts:["ArialMT","OtherFont"]});
    const browser = wordStyles.create(look), engine = context.KCF_shufflerFor(look);
    for (const count of [4,3,2,5,4]) { assert.deepEqual(browser.nextCaption(count), JSON.parse(JSON.stringify(engine.nextCaption(count)))); }
    const trait = wordStyles.variant(look,{look:"outline",font:"OtherFont"});
    assert.equal(trait.font,"OtherFont"); assert.equal(trait.fill,false); assert.equal(trait.stroke,true);
    assert.equal(settings.forAE(look).shuffleSeed,123); assert.deepEqual(settings.forAE(look).shuffleFonts,look.shuffleFonts);
});
