import { app } from "../../../scripts/app.js";

const SWITCH_CLASSES = new Set(["WFA_IndexSwitch100", "WA_OmniSwitch100"]);
const NUM_INPUTS = 100;
const SOCKET_ZONE_W = 18;
const GUTTER_W = 32;
const LABEL_START_X = SOCKET_ZONE_W + GUTTER_W; // 50px

let activeInlineInput = null;

function closeInlineInput() {
    if (activeInlineInput) {
        activeInlineInput.Cleanup?.();
        activeInlineInput = null;
    }
}

function getLinkRecord(graph, linkId) {
    if (linkId == null || !graph) return null;
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

function moveInputWire(node, fromSlotIdx, toSlotIdx) {
    if (fromSlotIdx < 0 || toSlotIdx < 0 || !node.inputs) return;
    const fromInput = node.inputs[fromSlotIdx];
    const toInput = node.inputs[toSlotIdx];
    if (!fromInput || !toInput) return;

    const linkId = fromInput.link;
    toInput.link = linkId ?? null;
    fromInput.link = null;

    if (linkId != null) {
        const linkRec = getLinkRecord(node.graph || app.graph, linkId);
        if (linkRec) {
            linkRec.target_slot = toSlotIdx;
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
            // Single space hides default "input_28" text so we can draw our custom gutter + label
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

    // If the very last slot (99) has a wire, disconnect it before shifting 98 -> 99
    const lastSlot = getSlotIndexForRow(node, NUM_INPUTS - 1);
    if (lastSlot >= 0 && node.inputs[lastSlot]?.link != null) {
        node.disconnectInput?.(lastSlot);
    }

    for (let k = NUM_INPUTS - 1; k > index; k--) {
        const fromSlot = getSlotIndexForRow(node, k - 1);
        const toSlot = getSlotIndexForRow(node, k);
        moveInputWire(node, fromSlot, toSlot);
        labels[k] = labels[k - 1] || "";
    }

    labels[index] = "";
    node.setDirtyCanvas?.(true, true);
}

function deleteSwitchRowAt(node, index) {
    closeInlineInput();
    const labels = ensureRowLabelsArray(node);

    const targetSlot = getSlotIndexForRow(node, index);
    if (targetSlot >= 0 && node.inputs[targetSlot]?.link != null) {
        node.disconnectInput?.(targetSlot);
    }

    for (let k = index; k < NUM_INPUTS - 1; k++) {
        const fromSlot = getSlotIndexForRow(node, k + 1);
        const toSlot = getSlotIndexForRow(node, k);
        moveInputWire(node, fromSlot, toSlot);
        labels[k] = labels[k + 1] || "";
    }

    labels[NUM_INPUTS - 1] = "";
    node.setDirtyCanvas?.(true, true);
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

app.registerExtension({
    name: "WFA.IndexSwitch100",
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

        // Draw alternating dark/light grey rows BEFORE LiteGraph draws the green socket dots
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

                // Gutter cell background (between socket dot and label area)
                if (i === activeIdx) {
                    ctx.fillStyle = "rgba(74, 222, 128, 0.18)";
                    ctx.fillRect(SOCKET_ZONE_W, topY, GUTTER_W, rowH);
                    // Green active indicator bar
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

        // Draw row numbers (0..99) and custom writeable labels AFTER socket dots
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
                    // Subtle placeholder when empty instead of static "input_28"
                    ctx.font = '11px "JetBrains Mono", "Consolas", "Monaco", monospace';
                    ctx.fillStyle = "rgba(255, 255, 255, 0.16)";
                    ctx.fillText("—", LABEL_START_X + 8, centerY);
                }
                ctx.restore();
            }

            ctx.restore();
        };

        const origOnMouseDown = nodeType.prototype.onMouseDown;
        nodeType.prototype.onMouseDown = function (e, localPos, graphCanvas) {
            if (!this.flags?.collapsed && localPos) {
                const [lx, ly] = localPos;

                // Keep left socket connection zone (< SOCKET_ZONE_W) and row-0 output socket untouched
                if (lx >= SOCKET_ZONE_W) {
                    for (let i = 0; i < NUM_INPUTS; i++) {
                        const geom = getRowGeometry(this, i);
                        if (!geom) continue;

                        if (ly >= geom.topY && ly <= geom.topY + geom.rowH) {
                            // Do not intercept clicks on the 'output' socket on row 0
                            if (i === 0 && lx > this.size[0] - 60) {
                                break;
                            }

                            // Clicked inside the Row Number Gutter (SOCKET_ZONE_W .. LABEL_START_X)
                            if (lx <= LABEL_START_X) {
                                if (e.ctrlKey || e.metaKey) {
                                    insertSwitchRowAt(this, i);
                                    openInlineLabelEditor(this, i, graphCanvas);
                                } else if (e.shiftKey || e.altKey) {
                                    deleteSwitchRowAt(this, i);
                                } else {
                                    setActiveSwitchIndex(this, i);
                                }
                                return true;
                            }

                            // Clicked inside the Label Area (> LABEL_START_X)
                            if (e.ctrlKey || e.metaKey) {
                                insertSwitchRowAt(this, i);
                                openInlineLabelEditor(this, i, graphCanvas);
                                return true;
                            }
                            openInlineLabelEditor(this, i, graphCanvas);
                            return true;
                        }
                    }
                }
            }

            return origOnMouseDown ? origOnMouseDown.apply(this, arguments) : false;
        };
    },
});
