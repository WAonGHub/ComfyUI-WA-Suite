import { app } from "../../../scripts/app.js";

const SIZES = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100];

const FIND_REPLACE_VARIANTS = SIZES.map((count) => ({
    type: `WFA_FindAndReplace${count}`,
    count,
    label: `WFA Find & Replace ${count} ⚡`,
}));

const VARIANT_TYPES = new Set([
    ...SIZES.map((c) => `WFA_FindAndReplace${c}`),
    ...SIZES.map((c) => `WA_FindAndReplace${c}`),
]);

function getCurrentSize(node) {
    const cls = node.comfyClass || node.type || "";
    const match = cls.match(/(\d+)$/);
    return match ? Number(match[1]) : null;
}

function getSlotLinkInfo(node, slotIdx) {
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
    return null;
}

function upgradeFindReplaceNode(oldNode, targetType) {
    const graph = oldNode.graph || app.graph;
    if (!graph || !window.LiteGraph) return;

    const newNode = window.LiteGraph.createNode(targetType);
    if (!newNode) return;

    graph.add(newNode);

    // 1. Copy position, width, title, colors, and properties
    newNode.pos = [oldNode.pos[0], oldNode.pos[1]];
    if (oldNode.size && newNode.size) {
        newNode.size[0] = oldNode.size[0];
    }
    if (
        oldNode.title &&
        !oldNode.title.startsWith("WFA Find & Replace") &&
        !oldNode.title.startsWith("WA Find & Replace")
    ) {
        newNode.title = oldNode.title;
    }
    if (oldNode.color) newNode.color = oldNode.color;
    if (oldNode.bgcolor) newNode.bgcolor = oldNode.bgcolor;
    if (oldNode.boxcolor) newNode.boxcolor = oldNode.boxcolor;
    if (oldNode.properties) {
        newNode.properties = JSON.parse(JSON.stringify(oldNode.properties));
    }

    // 2. Copy all widget values (mode, case_sensitive, use_regex, find_1..N, replace_1..N)
    if (oldNode.widgets && newNode.widgets) {
        for (const oldW of oldNode.widgets) {
            const newW = newNode.widgets.find((w) => w.name === oldW.name);
            if (newW) {
                newW.value = oldW.value;
                if (oldW.label && oldW.label !== oldW.name) {
                    newW.label = oldW.label;
                }
            }
        }
    }

    // 3. Capture and transfer all incoming wires (text, find_k, replace_k, etc.)
    if (oldNode.inputs) {
        const incomingConnections = [];
        for (let i = 0; i < oldNode.inputs.length; i++) {
            const oldInp = oldNode.inputs[i];
            if (!oldInp) continue;
            const linkInfo = getSlotLinkInfo(oldNode, i);
            if (linkInfo) {
                incomingConnections.push({
                    inputName: oldInp.name,
                    inputType: oldInp.type || "STRING",
                    customLabel: oldInp.label,
                    originId: linkInfo.origin_id,
                    originSlot: linkInfo.origin_slot,
                    parentId: linkInfo.parentId,
                });
            } else if (oldInp.label && oldInp.label !== oldInp.name) {
                const newSlotIdx = newNode.findInputSlot ? newNode.findInputSlot(oldInp.name) : -1;
                if (newSlotIdx >= 0 && newNode.inputs[newSlotIdx]) {
                    newNode.inputs[newSlotIdx].label = oldInp.label;
                }
            }
        }

        for (const conn of incomingConnections) {
            let newSlotIdx = newNode.findInputSlot ? newNode.findInputSlot(conn.inputName) : -1;
            if (newSlotIdx === -1 && typeof newNode.addInput === "function") {
                const matchingWidget = newNode.widgets?.find((w) => w.name === conn.inputName);
                newNode.addInput(
                    conn.inputName,
                    conn.inputType,
                    matchingWidget ? { widget: { name: conn.inputName } } : undefined
                );
                newSlotIdx = newNode.findInputSlot(conn.inputName);
            }
            if (newSlotIdx >= 0) {
                if (conn.customLabel && conn.customLabel !== conn.inputName && newNode.inputs[newSlotIdx]) {
                    newNode.inputs[newSlotIdx].label = conn.customLabel;
                }
                const originNode = graph.getNodeById(conn.originId);
                if (originNode && typeof originNode.connect === "function") {
                    originNode.connect(conn.originSlot, newNode, newSlotIdx, conn.parentId);
                }
            }
        }
    }

    // 4. Capture and transfer all outgoing wires from 'text' output
    const outgoingConnections = [];
    const allNodes = graph._nodes || [];
    for (const targetNode of allNodes) {
        if (!targetNode || targetNode === oldNode || !targetNode.inputs) continue;
        for (let s = 0; s < targetNode.inputs.length; s++) {
            const linkInfo = getSlotLinkInfo(targetNode, s);
            if (linkInfo && linkInfo.origin_id === oldNode.id) {
                outgoingConnections.push({
                    originSlot: linkInfo.origin_slot,
                    targetNode,
                    targetSlot: s,
                    parentId: linkInfo.parentId,
                });
            }
        }
    }

    for (const outConn of outgoingConnections) {
        newNode.connect(outConn.originSlot, outConn.targetNode, outConn.targetSlot, outConn.parentId);
    }

    // 5. Remove old node and select the upgraded node
    graph.remove(oldNode);
    if (app.canvas) {
        app.canvas.selectNode(newNode);
        app.canvas.setDirty(true, true);
    }
}

app.registerExtension({
    name: "WFA.FindAndReplaceUpgrade",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!VARIANT_TYPES.has(nodeData.name)) return;

        const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function (_, options) {
            if (origGetExtraMenuOptions) {
                origGetExtraMenuOptions.apply(this, arguments);
            }

            const curSize = getCurrentSize(this);
            const topMenuItems = [];

            // Quick +10 and -10 step items right at the top
            if (curSize != null && curSize + 10 <= 100) {
                const nextSize = curSize + 10;
                topMenuItems.push({
                    content: `⚡ Expand +10 Entries (to ${nextSize})`,
                    callback: () => upgradeFindReplaceNode(this, `WFA_FindAndReplace${nextSize}`),
                });
            }
            if (curSize != null && curSize - 10 >= 10) {
                const prevSize = curSize - 10;
                topMenuItems.push({
                    content: `⚡ Shrink -10 Entries (to ${prevSize})`,
                    callback: () => upgradeFindReplaceNode(this, `WFA_FindAndReplace${prevSize}`),
                });
            }

            // Submenu with all sizes 10..100
            const submenuOptions = FIND_REPLACE_VARIANTS.map((variant) => ({
                content:
                    variant.count === curSize
                        ? `✓ ${variant.label} (Current)`
                        : `⚡ ${variant.label}`,
                disabled: variant.count === curSize,
                callback: () => {
                    if (variant.count !== curSize) {
                        upgradeFindReplaceNode(this, variant.type);
                    }
                },
            }));

            topMenuItems.push({
                content: "⚡ Convert Find & Replace Size (10–100)",
                has_submenu: true,
                submenu: {
                    options: submenuOptions,
                },
            });

            options.unshift(...topMenuItems, null);
        };
    },
});
