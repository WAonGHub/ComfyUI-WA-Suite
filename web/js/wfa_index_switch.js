import { app } from "../../../scripts/app.js";

const SWITCH_CLASSES = new Set(["WFA_IndexSwitch100", "WA_OmniSwitch100"]);
const NUM_INPUTS = 100;
const SOCKET_ZONE_W = 24;
const GUTTER_W = 32;
const LABEL_START_X = SOCKET_ZONE_W + GUTTER_W; // 56px

let activeInlineInput = null;

function closeInlineInput() {
    if (activeInlineInput) {
        activeInlineInput.Cleanup?.();
        activeInlineInput = null;
    }
}

function getLinkInfoForSlot(node, slotIdx) {
    if (slotIdx < 0 || !node.inputs) return null;
    if (typeof node.getInputLink === "function") {
        try {
            const link = node.getInputLink(slotIdx);
            if (link) return link;
        } catch (_) {}
    }
    const graph = node.graph || app.graph;
    const linkId = node.inputs[slotIdx]?.link;
    if (linkId == null || !graph) return null;
    if (typeof graph.getLink === "function") {
        return graph.getLink(linkId) || null;
    }
    if (graph._links instanceof Map) {
        return graph._links.get(linkId) || null;
    }
    if (graph.links instanceof Map) {
        return graph.links.get(linkId) || null;
    }
    if (graph.links && typeof graph.links === "object") {
        return graph.links[linkId] || null;
    }
    return null;
}

function isSlotConnected(node, slotIdx) {
    if (slotIdx < 0 || !node.inputs) return false;
    if (typeof node.isInputConnected === "function") {
        try {
            return !!node.isInputConnected(slotIdx);
        } catch (_) {}
    }
    return getLinkInfoForSlot(node, slotIdx) != null;
}

function moveInputWire(node, fromSlotIdx, toSlotIdx) {
    if (fromSlotIdx < 0 || toSlotIdx < 0 || fromSlotIdx === toSlotIdx || !node.inputs) return;
    const graph = node.graph || app.graph;
    if (!graph) return;

    // 1. Capture the connection currently at fromSlotIdx before disconnecting anything
    const linkInfo = getLinkInfoForSlot(node, fromSlotIdx);
    const originId = linkInfo ? linkInfo.origin_id : null;
    const originSlot = linkInfo ? linkInfo.origin_slot : null;
    const parentId = linkInfo ? linkInfo.parentId : undefined;

    // 2. Disconnect destination slot if it currently has a wire
    if (isSlotConnected(node, toSlotIdx)) {
        node.disconnectInput(toSlotIdx);
    }

    // 3. Disconnect source slot and reconnect upstream node to destination slot
    if (linkInfo && originId != null && originSlot != null) {
        node.disconnectInput(fromSlotIdx);
        const originNode = graph.getNodeById(originId);
        if (originNode && typeof originNode.connect === "function") {
            originNode.connect(originSlot, node, toSlotIdx, parentId);
        }
    }
}

function ensureRowLabelsArray(node) {
    node.properties = node.properties || {};
    if (!Array.isArray(node.properties.rowLabels)) {
        node.properties.rowLabels = new Array(NUM_INPUTS).fill("");
    }
    while (node.properties.rowLabels.length < NUM_INPUTS) {
        node.properties.rowLabels.push("");
    }
    return node.properties.rowLabels;
}

function silenceDefaultInputNames(node) {
    if (!node.inputs) return;
    for (let i = 0; i < node.inputs.length; i++) {
        const inp = node.inputs[i];
        if (inp && inp.name && inp.name.startsWith("input_")) {
            if (inp.label !== " ") {
                inp.label = " ";
            }
        }
    }
}

function getSlotIndexForRow(node, rowIdx) {
    if (!node.inputs) return -1;
    const targetName = `input_${rowIdx}`;
    for (let i = 0; i < node.inputs.length; i++) {
        if (node.inputs[i]?.name === targetName) return i;
    }
    return -1;
}

function getRowGeometry(node, rowIdx) {
    const slotIdx = getSlotIndexForRow(node, rowIdx);
    if (slotIdx < 0) return null;

    const pos = [0, 0];
    node.getConnectionPos(true, slotIdx, pos);
    const centerY = pos[1] - node.pos[1];

    let rowH = window.LiteGraph?.NODE_SLOT_HEIGHT || 20;
    const nextSlotIdx = getSlotIndexForRow(node, rowIdx + 1);
    if (nextSlotIdx >= 0) {
        const nextPos = [0, 0];
        node.getConnectionPos(true, nextSlotIdx, nextPos);
        const diff = nextPos[1] - pos[1];
        if (diff > 4 && diff < 60) rowH = diff;
    }

    return {
        slotIdx,
        centerY,
        topY: centerY - rowH / 2,
        rowH,
    };
}

function getActiveSwitchIndex(node) {
    // If 'index' is connected to an upstream node (even through Reroutes or chained switches), follow its live value
    const graph = node.graph || app.graph;
    if (node.inputs && graph) {
        let curNode = node;
        let targetInputName = "index";
        for (let depth = 0; depth < 10 && curNode; depth++) {
            const slotIdx =
                depth === 0
                    ? curNode.inputs?.findIndex((inp) => inp?.name === targetInputName) ?? -1
                    : 0;
            if (slotIdx < 0 || !isSlotConnected(curNode, slotIdx)) break;
            const linkInfo = getLinkInfoForSlot(curNode, slotIdx);
            const originNode = linkInfo ? graph.getNodeById(linkInfo.origin_id) : null;
            if (!originNode) break;

            if (
                originNode.type === "Reroute" ||
                originNode.comfyClass === "Reroute" ||
                (!originNode.widgets?.length && originNode.inputs?.length === 1)
            ) {
                curNode = originNode;
                continue;
            }

            if (
                (originNode.comfyClass === "WFA_TextIndexSwitch" ||
                    originNode.comfyClass === "WA_TextIndexSwitch") &&
                originNode.inputs?.some((inp) => inp?.name === "select" && inp?.link != null)
            ) {
                curNode = originNode;
                targetInputName = "select";
                continue;
            }

            if (originNode.widgets) {
                const upWidget = originNode.widgets.find(
                    (w) => w.name === "select" || w.name === "index" || w.name === "value" || w.type === "number"
                );
                if (upWidget != null && upWidget.value != null) {
                    return Number(upWidget.value) || 0;
                }
            }
            break;
        }
    }
    const w = node.widgets?.find((w) => w.name === "index");
    return w ? Number(w.value) || 0 : 0;
}

function setActiveSwitchIndex(node, newIdx) {
    const w = node.widgets?.find((w) => w.name === "index");
    if (w) {
        w.value = newIdx;
        w.callback?.(newIdx);
    }
    node.setDirtyCanvas?.(true, true);
}

function insertSwitchRowAt(node, index) {
    closeInlineInput();
    const labels = ensureRowLabelsArray(node);

    // Disconnect slot 99 if occupied before shifting 98 -> 99
    const lastSlot = getSlotIndexForRow(node, NUM_INPUTS - 1);
    if (lastSlot >= 0 && isSlotConnected(node, lastSlot)) {
        node.disconnectInput(lastSlot);
    }

    for (let k = NUM_INPUTS - 1; k > index; k--) {
        const fromSlot = getSlotIndexForRow(node, k - 1);
        const toSlot = getSlotIndexForRow(node, k);
        moveInputWire(node, fromSlot, toSlot);
        labels[k] = labels[k - 1] || "";
    }

    labels[index] = "";
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
}

function deleteSwitchRowAt(node, index) {
    closeInlineInput();
    const labels = ensureRowLabelsArray(node);

    const targetSlot = getSlotIndexForRow(node, index);
    if (targetSlot >= 0 && isSlotConnected(node, targetSlot)) {
        node.disconnectInput(targetSlot);
    }

    for (let k = index; k < NUM_INPUTS - 1; k++) {
        const fromSlot = getSlotIndexForRow(node, k + 1);
        const toSlot = getSlotIndexForRow(node, k);
        moveInputWire(node, fromSlot, toSlot);
        labels[k] = labels[k + 1] || "";
    }

    labels[NUM_INPUTS - 1] = "";
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
}

function openInlineLabelEditor(node, rowIdx, graphCanvas) {
    closeInlineInput();

    const geom = getRowGeometry(node, rowIdx);
    if (!geom) return;

    const canvasEl = graphCanvas?.canvas || app.canvas?.canvas;
    const ds = graphCanvas?.ds || app.canvas?.ds;
    if (!canvasEl || !ds) return;

    const labels = ensureRowLabelsArray(node);
    const rect = canvasEl.getBoundingClientRect();
    const scale = ds.scale || 1;
    const offset = ds.offset || [0, 0];

    const rightPad = rowIdx === 0 ? 65 : 10;
    const localW = Math.max(80, node.size[0] - LABEL_START_X - rightPad);

    const screenX = rect.left + (node.pos[0] + LABEL_START_X + offset[0]) * scale;
    const screenY = rect.top + (node.pos[1] + geom.topY + offset[1]) * scale;
    const screenW = localW * scale;
    const screenH = geom.rowH * scale;

    const input = document.createElement("input");
    input.type = "text";
    input.value = labels[rowIdx] || "";
    input.placeholder = `Row ${rowIdx} label...`;

    Object.assign(input.style, {
        position: "fixed",
        left: `${screenX}px`,
        top: `${screenY}px`,
        width: `${screenW}px`,
        height: `${screenH}px`,
        margin: "0",
        padding: `0 ${Math.max(4, Math.round(6 * scale))}px`,
        boxSizing: "border-box",
        background: "#18181b",
        color: "#f4f4f6",
        caretColor: "#38bdf8",
        border: "1px solid #38bdf8",
        borderRadius: "3px",
        outline: "none",
        fontFamily: '"JetBrains Mono", "Consolas", "Monaco", monospace',
        fontSize: `${Math.max(10, Math.round(12 * scale))}px`,
        lineHeight: `${screenH}px`,
        zIndex: "99999",
        boxShadow: "0 2px 8px rgba(0,0,0,0.5)",
    });

    let closed = false;
    const commitAndClose = () => {
        if (closed) return;
        closed = true;
        labels[rowIdx] = input.value;
        window.removeEventListener("mousedown", onOutsideDown, true);
        window.removeEventListener("wheel", onWheelClose, true);
        if (input.parentNode) input.parentNode.removeChild(input);
        if (activeInlineInput === input) activeInlineInput = null;
        node.setDirtyCanvas?.(true, true);
    };

    const onOutsideDown = (ev) => {
        if (ev.target !== input) {
            commitAndClose();
        }
    };

    const onWheelClose = () => {
        commitAndClose();
    };

    input.Cleanup = commitAndClose;

    input.addEventListener("input", () => {
        labels[rowIdx] = input.value;
        node.setDirtyCanvas?.(true, true);
    });

    input.addEventListener("keydown", (ev) => {
        ev.stopPropagation();
        if (ev.key === "Enter" || ev.key === "ArrowDown") {
            ev.preventDefault();
            const nextRow = rowIdx + 1;
            commitAndClose();
            if (nextRow < NUM_INPUTS) {
                openInlineLabelEditor(node, nextRow, graphCanvas);
            }
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            const prevRow = rowIdx - 1;
            commitAndClose();
            if (prevRow >= 0) {
                openInlineLabelEditor(node, prevRow, graphCanvas);
            }
        } else if (ev.key === "Escape") {
            ev.preventDefault();
            commitAndClose();
        }
    });

    input.addEventListener("blur", () => {
        commitAndClose();
    });

    document.body.appendChild(input);
    activeInlineInput = input;

    window.addEventListener("mousedown", onOutsideDown, true);
    window.addEventListener("wheel", onWheelClose, true);

    requestAnimationFrame(() => {
        input.focus();
        input.select();
    });
}

function hitTestSwitchRow(clientX, clientY) {
    const graphCanvas = app.canvas;
    const canvasEl = graphCanvas?.canvas;
    const ds = graphCanvas?.ds;
    const nodes = app.graph?._nodes;
    if (!canvasEl || !ds || !nodes) return null;

    const rect = canvasEl.getBoundingClientRect();
    const scale = ds.scale || 1;
    const offset = ds.offset || [0, 0];

    const graphX = (clientX - rect.left) / scale - offset[0];
    const graphY = (clientY - rect.top) / scale - offset[1];

    // Check from top-most node to bottom-most
    for (let idx = nodes.length - 1; idx >= 0; idx--) {
        const node = nodes[idx];
        if (!SWITCH_CLASSES.has(node.comfyClass) && !SWITCH_CLASSES.has(node.type)) continue;
        if (node.flags?.collapsed) continue;

        const lx = graphX - node.pos[0];
        const ly = graphY - node.pos[1];

        if (lx < SOCKET_ZONE_W || lx > node.size[0] || ly < 0 || ly > node.size[1]) {
            continue;
        }

        for (let i = 0; i < NUM_INPUTS; i++) {
            const geom = getRowGeometry(node, i);
            if (!geom) continue;
            if (ly >= geom.topY && ly <= geom.topY + geom.rowH) {
                if (i === 0 && lx > node.size[0] - 60) return null;
                return {
                    node,
                    rowIdx: i,
                    inGutter: lx <= LABEL_START_X,
                    lx,
                    ly,
                };
            }
        }
    }
    return null;
}

app.registerExtension({
    name: "WFA.IndexSwitch100",
    async setup() {
        // 1. Capture-phase pointerdown so Ctrl+Click and Shift/Alt+Click are not swallowed by ComfyUI's canvas panning/selection
        window.addEventListener(
            "pointerdown",
            (e) => {
                if (e.button !== 0) return;
                const canvasEl = app.canvas?.canvas;
                if (!canvasEl || e.target !== canvasEl) return;

                const hit = hitTestSwitchRow(e.clientX, e.clientY);
                if (!hit) return;

                const { node, rowIdx, inGutter } = hit;

                if (inGutter) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();

                    if (e.ctrlKey || e.metaKey) {
                        insertSwitchRowAt(node, rowIdx);
                        openInlineLabelEditor(node, rowIdx, app.canvas);
                    } else if (e.shiftKey || e.altKey) {
                        deleteSwitchRowAt(node, rowIdx);
                    } else {
                        setActiveSwitchIndex(node, rowIdx);
                    }
                    return;
                }

                // Clicked in the label area
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();

                if (e.ctrlKey || e.metaKey) {
                    insertSwitchRowAt(node, rowIdx);
                }
                openInlineLabelEditor(node, rowIdx, app.canvas);
            },
            true
        );

        // 2. Hover tooltip on the canvas when hovering over row numbers or labels
        let lastTooltipRow = -1;
        window.addEventListener(
            "pointermove",
            (e) => {
                const canvasEl = app.canvas?.canvas;
                if (!canvasEl || e.target !== canvasEl) return;

                const hit = hitTestSwitchRow(e.clientX, e.clientY);
                if (hit && hit.inGutter) {
                    if (lastTooltipRow !== hit.rowIdx) {
                        lastTooltipRow = hit.rowIdx;
                        canvasEl.title = `Row ${hit.rowIdx}\n• Click: Set index = ${hit.rowIdx}\n• Ctrl+Click: Insert new row here (push wires & labels down)\n• Shift+Click (or Alt+Click): Delete row (pull wires & labels up)`;
                    }
                } else if (hit && !hit.inGutter) {
                    if (lastTooltipRow !== 1000 + hit.rowIdx) {
                        lastTooltipRow = 1000 + hit.rowIdx;
                        canvasEl.title = `Row ${hit.rowIdx} — Click to rename`;
                    }
                } else if (lastTooltipRow !== -1) {
                    lastTooltipRow = -1;
                    canvasEl.title = "";
                }
            },
            { passive: true }
        );
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!SWITCH_CLASSES.has(nodeData.name)) return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const res = origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined;
            ensureRowLabelsArray(this);
            silenceDefaultInputNames(this);
            if (!this.size || this.size[0] < 280) {
                this.size = [300, this.size ? this.size[1] : 2100];
            }
            return res;
        };

        const origOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const res = origOnConfigure ? origOnConfigure.apply(this, arguments) : undefined;
            ensureRowLabelsArray(this);
            silenceDefaultInputNames(this);
            return res;
        };

        const origOnDrawBackground = nodeType.prototype.onDrawBackground;
        nodeType.prototype.onDrawBackground = function (ctx) {
            if (origOnDrawBackground) origOnDrawBackground.apply(this, arguments);
            if (this.flags?.collapsed) return;

            silenceDefaultInputNames(this);
            const activeIdx = getActiveSwitchIndex(this);
            const nodeW = this.size[0];

            ctx.save();
            for (let i = 0; i < NUM_INPUTS; i++) {
                const geom = getRowGeometry(this, i);
                if (!geom) continue;

                const { topY, rowH } = geom;

                // Alternating dark grey and light grey row background
                ctx.fillStyle = i % 2 === 0 ? "#1c1c20" : "#2f2f37";
                ctx.fillRect(0, topY, nodeW, rowH);

                // Gutter cell background
                if (i === activeIdx) {
                    ctx.fillStyle = "rgba(74, 222, 128, 0.18)";
                    ctx.fillRect(SOCKET_ZONE_W, topY, GUTTER_W, rowH);
                    ctx.fillStyle = "#4ade80";
                    ctx.fillRect(SOCKET_ZONE_W, topY, 3, rowH);
                } else {
                    ctx.fillStyle = "rgba(0, 0, 0, 0.28)";
                    ctx.fillRect(SOCKET_ZONE_W, topY, GUTTER_W, rowH);
                }

                // Subtle horizontal row divider
                ctx.fillStyle = "rgba(255, 255, 255, 0.05)";
                ctx.fillRect(0, topY + rowH - 1, nodeW, 1);
            }

            // Vertical divider lines for the number gutter
            const firstGeom = getRowGeometry(this, 0);
            const lastGeom = getRowGeometry(this, NUM_INPUTS - 1);
            if (firstGeom && lastGeom) {
                const totalTop = firstGeom.topY;
                const totalH = lastGeom.topY + lastGeom.rowH - totalTop;
                ctx.fillStyle = "#454552";
                ctx.fillRect(SOCKET_ZONE_W, totalTop, 1, totalH);
                ctx.fillRect(LABEL_START_X, totalTop, 1, totalH);
            }
            ctx.restore();
        };

        const origOnDrawForeground = nodeType.prototype.onDrawForeground;
        nodeType.prototype.onDrawForeground = function (ctx) {
            if (origOnDrawForeground) origOnDrawForeground.apply(this, arguments);
            if (this.flags?.collapsed) return;

            const labels = ensureRowLabelsArray(this);
            const activeIdx = getActiveSwitchIndex(this);
            const nodeW = this.size[0];

            ctx.save();
            ctx.font = '12px "JetBrains Mono", "Consolas", "Monaco", monospace';
            ctx.textBaseline = "middle";

            for (let i = 0; i < NUM_INPUTS; i++) {
                const geom = getRowGeometry(this, i);
                if (!geom) continue;

                const { centerY, topY, rowH } = geom;

                // 1. Row number in gutter (right-aligned)
                ctx.textAlign = "right";
                if (i === activeIdx) {
                    ctx.font = 'bold 12px "JetBrains Mono", "Consolas", "Monaco", monospace';
                    ctx.fillStyle = "#4ade80";
                } else {
                    ctx.font = '12px "JetBrains Mono", "Consolas", "Monaco", monospace';
                    ctx.fillStyle = "#a1a1aa";
                }
                ctx.fillText(`${i}`, LABEL_START_X - 6, centerY);

                // 2. Custom label text in row
                const customText = labels[i] || "";
                const rightPad = i === 0 ? 65 : 10;
                const maxTextW = Math.max(40, nodeW - LABEL_START_X - 8 - rightPad);

                ctx.save();
                ctx.beginPath();
                ctx.rect(LABEL_START_X + 4, topY, maxTextW, rowH);
                ctx.clip();

                ctx.textAlign = "left";
                if (customText.length > 0) {
                    ctx.font = '12px "JetBrains Mono", "Consolas", "Monaco", monospace';
                    ctx.fillStyle = i === activeIdx ? "#ffffff" : "#e4e4e7";
                    ctx.fillText(customText, LABEL_START_X + 8, centerY);
                } else {
                    ctx.font = '11px "JetBrains Mono", "Consolas", "Monaco", monospace';
                    ctx.fillStyle = "rgba(255, 255, 255, 0.16)";
                    ctx.fillText("—", LABEL_START_X + 8, centerY);
                }
                ctx.restore();
            }

            ctx.restore();
        };
    },
});
