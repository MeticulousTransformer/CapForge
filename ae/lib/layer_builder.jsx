/* AE layer generation from a normalized TranscriptDocument.
   Never destroys user work: everything goes into a fresh precomp inside
   the "CapForge" project folder. */

var KCF_FOLDER_NAME = "CapForge";

/* Rounded-rectangle shape layer (solids can't have corner radius).
   Positioned by its center, like a solid. */
function KCF_addRoundRect(comp, name, w, h, color, radius, x, y) {
    var shape = comp.layers.addShape();
    shape.name = name;
    var group = shape.property("ADBE Root Vectors Group")
        .addProperty("ADBE Vector Group");
    var rect = group.property("ADBE Vectors Group")
        .addProperty("ADBE Vector Shape - Rect");
    rect.property("ADBE Vector Rect Size").setValue([w, h]);
    rect.property("ADBE Vector Rect Roundness").setValue(radius || 0);
    var fill = group.property("ADBE Vectors Group")
        .addProperty("ADBE Vector Graphic - Fill");
    fill.property("ADBE Vector Fill Color").setValue(
        [color[0], color[1], color[2], 1]);
    shape.property("Transform").property("Position").setValue([x, y]);
    return shape;
}

function KCF_findOrCreateFolder(proj, name) {
    for (var i = 1; i <= proj.numItems; i++) {
        var item = proj.item(i);
        if (item instanceof FolderItem && item.name === name) {
            return item;
        }
    }
    return proj.items.addFolder(name);
}

/* Anchor preset -> base {x, y} in comp pixels. */
function KCF_anchorPosition(settings, comp) {
    var margin = settings.safeMargin;                  // px from edge
    var x, y;
    switch (settings.anchorPreset) {
    case "bottom_center": x = comp.width / 2; y = comp.height - margin; break;
    case "center":        x = comp.width / 2; y = comp.height / 2;      break;
    case "top_center":    x = comp.width / 2; y = margin + settings.fontSize; break;
    default:              x = settings.x;     y = settings.y;           break;
    }
    return { x: x, y: y + (settings.verticalOffset || 0) };
}

function KCF_wordsForCaption(doc, caption) {
    var byId = {};
    for (var i = 0; i < doc.words.length; i++) {
        byId[doc.words[i].id] = doc.words[i];
    }
    var out = [];
    for (var j = 0; j < caption.wordIds.length; j++) {
        var w = byId[caption.wordIds[j]];
        if (w) { out.push(w); }
    }
    return out;
}

/* Break word indices into visual lines.
   wordsPerLine / charsPerLine: 0 disables that limit.
   minWordsPerLine rebalances short lines when the limits allow it. */
function KCF_breakLines(words, settings) {
    var maxWpl = settings.wordsPerLine || 0;
    var minWpl = settings.minWordsPerLine || 0;
    var maxCpl = settings.charsPerLine || 0;
    var lines = [[]];
    var lineChars = 0;

    function charsForLine(indices) {
        var total = 0;
        for (var ci = 0; ci < indices.length; ci++) {
            var word = words[indices[ci]];
            var wordText = word.text + (word.punctuationAfter || "");
            total += wordText.length + (ci > 0 ? 1 : 0);
        }
        return total;
    }

    for (var i = 0; i < words.length; i++) {
        var text = words[i].text + (words[i].punctuationAfter || "");
        var cur = lines[lines.length - 1];
        var wouldBe = lineChars + (cur.length > 0 ? 1 : 0) + text.length;
        if (cur.length > 0 &&
                ((maxWpl > 0 && cur.length >= maxWpl) ||
                 (maxCpl > 0 && wouldBe > maxCpl))) {
            lines.push([]);
            lineChars = 0;
            cur = lines[lines.length - 1];
            wouldBe = text.length;
        }
        cur.push(i);
        lineChars = wouldBe;
    }

    if (maxWpl > 0 && minWpl > maxWpl) { minWpl = maxWpl; }
    for (var li = lines.length - 1; li > 0; li--) {
        while (lines[li].length < minWpl &&
                lines[li - 1].length > minWpl) {
            var moveIndex = lines[li - 1][lines[li - 1].length - 1];
            if (maxCpl > 0 &&
                    charsForLine([moveIndex].concat(lines[li])) > maxCpl) {
                break;
            }
            lines[li - 1].pop();
            lines[li].unshift(moveIndex);
        }
    }
    return lines;
}

/* Width each line is stretched to, or 0 when fitting is off.
   A boundary of 0 means "the comp, inside the safe margins". */
function KCF_fitTargetWidth(comp, settings) {
    if (!settings.fitBoundary) { return 0; }
    var width = settings.fitWidth;
    if (!width || width <= 0) {
        width = comp.width - (settings.safeMargin || 0) * 2;
    }
    return (width > 0) ? width : 0;
}

/* Scale each line's type until the line spans target.
   Word spacing is fixed, so the glyphs share whatever is left once the
   gaps are taken out. Two passes: type metrics are not perfectly linear
   in point size, so the first guess is re-measured and corrected. */
function KCF_restyleLine(layers, rects, wordStyles, indices, size, tracking) {
    for (var i = 0; i < indices.length; i++) {
        var idx = indices[i];
        var style = KCF_withFontSize(wordStyles[idx], size);
        style.tracking = tracking;
        KCF_styleTextLayer(layers[idx], style);
        rects[idx] = layers[idx].sourceRectAtTime(0, false);
    }
}

/* Glyph width of a line as it currently stands. */
function KCF_lineGlyphWidth(rects, indices) {
    var total = 0;
    for (var i = 0; i < indices.length; i++) { total += rects[indices[i]].width; }
    return total;
}

/* Open tracking until the line reaches room, or the ceiling stops it.
   AE tracking is thousandths of an em added after every character, so a
   unit widens the line by size/1000 for each character on it. */
function KCF_trackLineToWidth(layers, rects, wordStyles, words, indices,
        settings, room, size, maxTracking) {
    var chars = 0;
    for (var i = 0; i < indices.length; i++) {
        var word = words[indices[i]];
        chars += String(word.text + (word.punctuationAfter || "")).length;
    }
    if (chars <= 0) { return; }
    var tracking = settings.tracking || 0;
    for (var pass = 0; pass < 2; pass++) {
        var gap = room - KCF_lineGlyphWidth(rects, indices);
        if (gap <= 0.5) { return; }
        tracking += gap * 1000 / (size * chars);
        if (tracking > maxTracking) { tracking = maxTracking; }
        KCF_restyleLine(layers, rects, wordStyles, indices, size, tracking);
        if (tracking >= maxTracking) { return; }
    }
}

function KCF_fitLinesToWidth(layers, rects, wordStyles, words, lines, settings, target) {
    var maxSize = (settings.fitMaxFontSize > 0)
        ? settings.fitMaxFontSize : settings.fontSize * 4;
    var maxTracking = settings.fitMaxTracking || 0;
    var baseTracking = settings.tracking || 0;
    for (var l = 0; l < lines.length; l++) {
        var indices = lines[l];
        var room = target - settings.wordSpacing * (indices.length - 1);
        if (room <= 0) { continue; }
        var size = settings.fontSize;
        var capped = false;
        for (var pass = 0; pass < 2; pass++) {
            var glyphs = KCF_lineGlyphWidth(rects, indices);
            if (glyphs <= 0) { break; }
            size = size * room / glyphs;
            if (size > maxSize) { size = maxSize; capped = true; }
            if (size < 1) { size = 1; }
            KCF_restyleLine(layers, rects, wordStyles, indices, size, baseTracking);
        }
        /* Size alone cannot fill a wide boundary from a short line once
           it hits the ceiling. Tracking is the other lever on width. */
        if (capped && maxTracking > 0) {
            KCF_trackLineToWidth(layers, rects, wordStyles, words, indices,
                settings, room, size, maxTracking);
        }
    }
}

/* Full glyph bounds relative to the baseline. A tall ascender and a deep
   descender can belong to different words, so max(height) is not enough. */
function KCF_lineExtent(rects, line) {
    var top = null, bottom = null;
    for (var i = 0; i < line.length; i++) {
        var rect = rects[line[i]];
        if (top === null || rect.top < top) { top = rect.top; }
        if (bottom === null || rect.top + rect.height > bottom) {
            bottom = rect.top + rect.height;
        }
    }
    if (top === null) { top = 0; bottom = 0; }
    return { height: bottom - top, top: top, bottom: bottom };
}

/* Baseline-to-baseline offset of every line from the first.
   Unfitted captions share one gap; fitted lines differ in size, so each
   step follows the two lines it sits between. */
function KCF_lineOffsets(rects, lines, settings, fitted) {
    var offsets = [0];
    var l;
    if (!fitted) {
        var gap = (settings.lineHeight && settings.lineHeight > 0)
            ? settings.lineHeight : Math.round(settings.fontSize * 1.2);
        for (l = 1; l < lines.length; l++) { offsets.push(l * gap); }
        return offsets;
    }
    for (l = 1; l < lines.length; l++) {
        var previous = KCF_lineExtent(rects, lines[l - 1]);
        var next = KCF_lineExtent(rects, lines[l]);
        var gap = (previous.height + next.height) / 2 * 0.12;
        var step = previous.bottom - next.top + gap;
        offsets.push(offsets[l - 1] + step);
    }
    return offsets;
}

/* Build all word layers for one caption inside precomp.
   shuffler is optional; without one every word gets the same style. */
function KCF_buildCaption(precomp, doc, caption, ci, settings, pos, shuffler) {
    var words = KCF_wordsForCaption(doc, caption);
    if (words.length === 0) { return; }

    // 1) create + style layers, collect measured rects
    var layers = [], rects = [], wordStyles = [];
    var spacing = settings.wordSpacing;
    var traits = shuffler ? shuffler.nextCaption(words.length) : null;
    for (var i = 0; i < words.length; i++) {
        var displayText = words[i].text + (words[i].punctuationAfter || "");
        var layer = precomp.layers.addText(displayText);
        // kept so a refit can restyle the word without losing its look
        var wordStyle = traits ? KCF_variantStyle(settings, traits[i]) : settings;
        KCF_styleTextLayer(layer, wordStyle);
        layers.push(layer);
        wordStyles.push(wordStyle);
        rects.push(layer.sourceRectAtTime(0, false));
    }

    // 2) break into lines, then optionally stretch each to the boundary
    var lines = KCF_breakLines(words, settings);
    var fitWidth = KCF_fitTargetWidth(precomp, settings);
    if (fitWidth > 0) {
        KCF_fitLinesToWidth(layers, rects, wordStyles, words, lines, settings,
            fitWidth);
    }

    // measured after any refit, since the sizes may have just changed
    var topMost = null, bottomMost = null;
    for (var m = 0; m < rects.length; m++) {
        if (topMost === null || rects[m].top < topMost) { topMost = rects[m].top; }
        if (bottomMost === null || rects[m].top + rects[m].height > bottomMost) {
            bottomMost = rects[m].top + rects[m].height;
        }
    }
    var maxH = bottomMost - topMost;
    var lineWidths = [];
    for (var li = 0; li < lines.length; li++) {
        var lw = 0;
        for (var wi = 0; wi < lines[li].length; wi++) {
            lw += rects[lines[li][wi]].width;
        }
        lw += spacing * (lines[li].length - 1);
        lineWidths.push(lw);
    }
    var lineOffsets = KCF_lineOffsets(rects, lines, settings, fitWidth > 0);
    var blockHeight = lineOffsets[lineOffsets.length - 1];

    // bottom anchor: block grows upward so the LAST line sits at pos.y
    var baseY = pos.y;
    if (settings.anchorPreset === "bottom_center") {
        baseY = pos.y - blockHeight;
    }

    /* Anchor point, in layer space: each word gets its own horizontal
       centre so scale/rotation pivot mid-word instead of at the left edge.
       The vertical centre is shared across the caption so a pop keeps the
       line optically level rather than pivoting higher on short words than
       on ones with descenders. Fitted lines differ in size, so there the
       pivot follows each line instead of the caption as a whole. */
    function anchorYFor(lineIndex) {
        if (fitWidth <= 0) { return topMost + maxH / 2; }
        var extent = KCF_lineExtent(rects, lines[lineIndex]);
        return extent.top + extent.height / 2;
    }

    // 3) position, name, metadata, preset — per line
    var preset = KCF_PRESETS[settings.preset] || KCF_PRESETS.highlight_word;
    var perWord = (preset instanceof Function) ? preset : preset.perWord;
    var layouts = [];
    var minX = null, maxX = null, minY = null, maxY = null;
    for (var l = 0; l < lines.length; l++) {
        var anchorY = anchorYFor(l);
        var lineY = baseY + lineOffsets[l];
        var startX;
        if (settings.alignment === "left") { startX = pos.x; }
        else if (settings.alignment === "right") { startX = pos.x - lineWidths[l]; }
        else { startX = pos.x - lineWidths[l] / 2; }
        if (minX === null || startX < minX) { minX = startX; }
        if (maxX === null || startX + lineWidths[l] > maxX) { maxX = startX + lineWidths[l]; }

        var cursor = startX;
        for (var k = 0; k < lines[l].length; k++) {
            var idx = lines[l][k];
            var lyr = layers[idx];
            var w = words[idx];
            /* The layer origin ends up at basePos - anchor, which keeps the
               glyphs' left edge at the cursor and their baseline at lineY. */
            var anchor = [rects[idx].left + rects[idx].width / 2, anchorY];
            var basePos = [cursor + rects[idx].width / 2, lineY + anchorY];
            var glyphTop = lineY + rects[idx].top;
            var glyphBottom = glyphTop + rects[idx].height;
            if (minY === null || glyphTop < minY) { minY = glyphTop; }
            if (maxY === null || glyphBottom > maxY) { maxY = glyphBottom; }
            lyr.property("Transform").property("Anchor Point").setValue(anchor);
            lyr.property("Transform").property("Position").setValue(basePos);
            lyr.name = "KCF_C" + KCF_pad3(ci) + "_W" + KCF_pad3(idx) + "_" + w.text;
            lyr.comment = JSON.stringify({
                tool: "CapForge",
                captionId: caption.id,
                wordId: w.id,
                start: w.start,
                end: w.end,
                line: l,
                variant: traits ? traits[idx].look : null,
                font: traits ? traits[idx].font : null,
                preset: settings.preset
            });
            lyr.inPoint = caption.start;
            lyr.outPoint = Math.max(caption.end, caption.start + 0.05);
            if (settings.shadow) { KCF_addDropShadow(lyr, settings); }
            perWord(lyr, w, caption, settings, basePos);
            layouts.push({ layer: lyr, word: w, rect: rects[idx],
                pos: basePos, anchor: anchor });
            cursor += rects[idx].width + spacing;
        }
    }

    // preset-specific extra layers (e.g. per-word boxes)
    if (preset.after) {
        preset.after(precomp, layouts, caption, ci, settings);
    }

    // 4) optional background box behind all lines
    if (settings.backgroundBox) {
        var pad = Math.round(settings.fontSize * 0.35);
        var boxW = Math.ceil((maxX - minX) + pad * 2);
        var boxH = Math.ceil((maxY - minY) + pad * 2);
        var box = KCF_addRoundRect(
            precomp, "KCF_C" + KCF_pad3(ci) + "_BOX",
            boxW, boxH, settings.boxColor, settings.boxRadius || 0,
            (minX + maxX) / 2,
            (minY + maxY) / 2);
        box.inPoint = caption.start;
        box.outPoint = Math.max(caption.end, caption.start + 0.05);
        // Old looks keep their solid box. Explicit 0 is fully transparent.
        var boxOpacity = settings.boxOpacity;
        if (typeof boxOpacity !== "number" || !isFinite(boxOpacity)) { boxOpacity = 100; }
        KCF_prop(box, "Opacity").setValue(Math.max(0, Math.min(100, boxOpacity)));
        // The background must also sit behind preset extras such as the
        // active-word boxes. This fresh precomp contains generated layers only.
        box.moveToEnd();
    }
}

/* Main entry: generate one precomp with all captions, drop it in the
   active comp. Returns the precomp name. */
function KCF_generate(doc, settings) {
    var proj = app.project;
    if (!proj) { throw new Error("No project open."); }
    var activeComp = proj.activeItem;
    if (!(activeComp && activeComp instanceof CompItem)) {
        throw new Error("No active composition selected.");
    }
    if (!doc || !doc.captions || doc.captions.length === 0) {
        throw new Error("No captions in transcript. Transcribe first.");
    }
    if (!doc.words || doc.words.length === 0) {
        throw new Error("Transcript has text but no word timings. " +
            "Animation requires word timings.");
    }

    app.beginUndoGroup("KCF Generate Captions");
    var precomp = null;
    try {
        var folder = KCF_findOrCreateFolder(proj, KCF_FOLDER_NAME);
        var name = "KCF_Captions_" + KCF_timestamp();
        var duration = Math.max(activeComp.duration, (doc.duration || 0) + 1);
        precomp = proj.items.addComp(
            name, activeComp.width, activeComp.height,
            activeComp.pixelAspect, duration, activeComp.frameRate);
        precomp.parentFolder = folder;
        precomp.comment = JSON.stringify({ tool: "CapForge", kind: "caption-precomp" });

        var pos = KCF_anchorPosition(settings, precomp);
        var shuffler = KCF_shufflerFor(settings);
        for (var ci = 0; ci < doc.captions.length; ci++) {
            KCF_buildCaption(precomp, doc, doc.captions[ci], ci, settings, pos,
                shuffler);
        }

        var compLayer = activeComp.layers.add(precomp);
        compLayer.name = name;
        compLayer.moveToBeginning();
        return name;
    } catch (error) {
        // This object was created by this call; existing project items are
        // never rolled back or removed when a font/effect/preset fails.
        if (precomp) { try { precomp.remove(); } catch (cleanupError) {} }
        throw error;
    } finally {
        app.endUndoGroup();
    }
}

/* A name is not proof of ownership: an editor may use the same prefix.
   Older unmarked outputs are left for the editor to remove manually. */
function KCF_isGeneratedPrecomp(item) {
    if (!(item instanceof CompItem) || !item.comment) { return false; }
    try {
        var metadata = JSON.parse(item.comment);
        return metadata && metadata.tool === "CapForge" && metadata.kind === "caption-precomp";
    } catch (error) { return false; }
}

/* Remove only marked generated caption precomps; caller confirms first. */
function KCF_clearGenerated() {
    var proj = app.project;
    if (!proj) { return 0; }
    app.beginUndoGroup("KCF Clear Generated Captions");
    var removed = 0;
    try {
        var doomed = [];
        for (var i = 1; i <= proj.numItems; i++) {
            var item = proj.item(i);
            if (KCF_isGeneratedPrecomp(item)) {
                doomed.push(item);
            }
        }
        for (var d = 0; d < doomed.length; d++) {
            doomed[d].remove();
            removed++;
        }
    } finally {
        app.endUndoGroup();
    }
    return removed;
}
