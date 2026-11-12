/* Generation and removal must leave the editor's existing project alone. */
const assert = require("node:assert/strict");
const test = require("node:test");
const { loadLib, makePrecomp, makeInput, SETTINGS } = require("./ae_stub");

function projectFixture() {
    const context = loadLib();
    context.CompItem = function () {};
    context.FolderItem = function () {};
    const items = [], inserted = [], removed = [];
    const active = new context.CompItem();
    Object.assign(active, { name: "Editor's composition", comment: "Keep my notes",
        width: 1080, height: 1920, duration: 5, pixelAspect: 1, frameRate: 25,
        layers: { add(comp) { inserted.push(comp); return { moveToBeginning() {} }; } } });
    function addComp(name, width, height, pixelAspect, duration) {
        const comp = Object.assign(new context.CompItem(), makePrecomp({ width, height }), {
            name, duration, comment: "",
            remove() { removed.push(this); items.splice(items.indexOf(this), 1); }
        });
        items.push(comp);
        return comp;
    }
    const project = {
        activeItem: active,
        get numItems() { return items.length; },
        item(index) { return items[index - 1]; },
        items: {
            addComp,
            addFolder(name) {
                const folder = Object.assign(new context.FolderItem(), { name });
                items.push(folder);
                return folder;
            }
        }
    };
    let undoDepth = 0;
    context.app = { project,
        beginUndoGroup() { undoDepth++; }, endUndoGroup() { undoDepth--; } };
    return { context, active, items, inserted, removed, addComp, undoDepth: () => undoDepth };
}

test("clear removes marked generated comps but preserves user and older unmarked comps", () => {
    const fixture = projectFixture();
    const userComp = fixture.addComp("KCF_Captions_Client Animation", 1080, 1920, 1, 5);
    userComp.comment = "An editor-created composition with a similar name";
    const oldComp = fixture.addComp("KCF_Captions_20260101_120000", 1080, 1920, 1, 5);
    const { doc } = makeInput(2);
    fixture.context.KCF_generate(doc, SETTINGS);
    const generated = fixture.inserted[0];

    assert.equal(fixture.context.KCF_clearGenerated(), 1);
    assert.deepEqual(fixture.removed, [generated]);
    assert.ok(fixture.items.includes(userComp));
    assert.ok(fixture.items.includes(oldComp));
    assert.equal(fixture.active.name, "Editor's composition");
    assert.equal(fixture.active.comment, "Keep my notes");
    assert.equal(fixture.undoDepth(), 0);
});

test("a failed caption build removes only its unfinished precomp and closes Undo", () => {
    const fixture = projectFixture();
    const existing = fixture.addComp("Working scene", 1080, 1920, 1, 5);
    fixture.context.KCF_PRESETS.broken = { perWord() { throw new Error("test effect failed"); } };
    const { doc } = makeInput(2);
    assert.throws(() => fixture.context.KCF_generate(doc, { ...SETTINGS, preset: "broken" }), /test effect failed/);
    assert.equal(fixture.inserted.length, 0);
    assert.equal(fixture.removed.length, 1);
    assert.ok(fixture.items.includes(existing));
    assert.equal(fixture.items.filter(item => item instanceof fixture.context.CompItem).length, 1);
    assert.equal(fixture.undoDepth(), 0);
});
