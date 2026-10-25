import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const FILTER_CLASS = "WFA_PromptLabelFilter";
const LOADER_CLASS = "WFA_BatchPromptLoader";
const SWITCH_LOADER_CLASS = "WFA_BatchPromptSwitchLoader";
const LOADER_CLASSES = new Set([LOADER_CLASS, SWITCH_LOADER_CLASS]);
const UNTAGGED_LABEL = "UNTAGGED";
const STYLE_ID = "wfa-batch-prompts-styles";

function getNodeById(nodeId) {
    if (!app.graph) return null;
    if (typeof app.graph.getNodeById === "function") {
        const n = app.graph.getNodeById(Number(nodeId)) || app.graph.getNodeById(String(nodeId));
        if (n) return n;
    }
    return app.graph._nodes_by_id?.[nodeId] || null;
}

function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
        textarea.wfa-plf-hidden-textarea {
            position: absolute !important;
            width: 1px !important;
            height: 1px !important;
            opacity: 0 !important;
            pointer-events: none !important;
            z-index: -1 !important;
        }

        .wfa-plf-container {
            position: relative !important;
            width: 100% !important;
            height: 100% !important;
            display: flex !important;
            flex-direction: column !important;
            background: #18181b !important;
            border: 1px solid #3f3f46 !important;
            border-radius: 6px !important;
            overflow: hidden !important;
            box-sizing: border-box !important;
            font-family: "JetBrains Mono", "Consolas", "Monaco", "Courier New", monospace !important;
            user-select: none !important;
        }

        .wfa-plf-toolbar {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            justify-content: space-between !important;
            gap: 4px !important;
            padding: 4px 6px !important;
            background: #121215 !important;
            border-bottom: 1px solid #2e2e36 !important;
            flex: 0 0 auto !important;
            min-height: 26px !important;
            box-sizing: border-box !important;
        }

        .wfa-plf-status {
            font-size: 11px !important;
            font-weight: 700 !important;
            color: #4ade80 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }

        .wfa-plf-status.wfa-zero {
            color: #f87171 !important;
        }

        .wfa-plf-actions {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            gap: 3px !important;
            flex: 0 0 auto !important;
        }

        .wfa-plf-btn {
            background: #27272e !important;
            color: #d4d4d8 !important;
            border: 1px solid #3f3f46 !important;
            border-radius: 4px !important;
            padding: 1px 5px !important;
            font-family: inherit !important;
            font-size: 10px !important;
            font-weight: 600 !important;
            line-height: 15px !important;
            cursor: pointer !important;
            transition: background 0.1s ease, color 0.1s ease, border-color 0.1s ease !important;
        }

        .wfa-plf-btn:hover {
            background: #383842 !important;
            color: #ffffff !important;
            border-color: #52525b !important;
        }

        .wfa-plf-btn:active {
            background: #4ade80 !important;
            color: #09090b !important;
            border-color: #4ade80 !important;
        }

        .wfa-plf-scroll {
            flex: 1 1 auto !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            padding: 5px !important;
            box-sizing: border-box !important;
        }

        .wfa-plf-grid {
            display: grid !important;
            grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)) !important;
            gap: 4px !important;
            width: 100% !important;
            box-sizing: border-box !important;
        }

        .wfa-plf-chip {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            justify-content: space-between !important;
            gap: 5px !important;
            padding: 4px 6px !important;
            border-radius: 4px !important;
            background: #1f1f25 !important;
            border: 1px solid #2e2e36 !important;
            cursor: pointer !important;
            box-sizing: border-box !important;
            min-height: 24px !important;
            transition: background 0.08s ease, border-color 0.08s ease !important;
        }

        .wfa-plf-chip:hover {
            background: #292932 !important;
            border-color: #454552 !important;
        }

        .wfa-plf-chip.wfa-checked {
            background: rgba(74, 222, 128, 0.10) !important;
            border-color: rgba(74, 222, 128, 0.42) !important;
            box-shadow: inset 2px 0 0 #4ade80 !important;
        }

        .wfa-plf-chip.wfa-checked:hover {
            background: rgba(74, 222, 128, 0.16) !important;
            border-color: rgba(74, 222, 128, 0.65) !important;
        }

        .wfa-plf-chip-left {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            gap: 5px !important;
            min-width: 0 !important;
            flex: 1 1 auto !important;
        }

        .wfa-plf-box {
            width: 13px !important;
            height: 13px !important;
            min-width: 13px !important;
            border-radius: 3px !important;
            border: 1px solid #52525b !important;
            background: #141417 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            font-size: 10px !important;
            font-weight: 900 !important;
            color: transparent !important;
            box-sizing: border-box !important;
        }

        .wfa-plf-chip.wfa-checked .wfa-plf-box {
            background: #4ade80 !important;
            border-color: #4ade80 !important;
            color: #09090b !important;
        }

        .wfa-plf-name {
            font-size: 11px !important;
            font-weight: 600 !important;
            color: #71717a !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }

        .wfa-plf-chip.wfa-checked .wfa-plf-name {
            color: #f4f4f6 !important;
        }

        .wfa-plf-count {
            font-size: 10px !important;
            color: #63636e !important;
            background: rgba(0, 0, 0, 0.28) !important;
            padding: 1px 4px !important;
            border-radius: 3px !important;
            flex: 0 0 auto !important;
        }

        .wfa-plf-chip.wfa-checked .wfa-plf-count {
            color: #86efac !important;
            background: rgba(74, 222, 128, 0.14) !important;
        }

        .wfa-plf-hint {
            margin-top: 5px !important;
            padding: 5px 6px !important;
            font-size: 10px !important;
            line-height: 14px !important;
            color: #a1a1aa !important;
            background: rgba(255, 255, 255, 0.03) !important;
            border: 1px dashed #3f3f46 !important;
            border-radius: 4px !important;
        }
    `;
    document.head.appendChild(style);
}

function parseStateMap(raw) {
    if (!raw || typeof raw !== "string") return {};
    try {
        const obj = JSON.parse(raw);
        if (obj && typeof obj === "object" && !Array.isArray(obj)) {
            return obj;
        }
    } catch (_) {}
    return {};
}

function computeActivePromptCount(fileMeta, filterMode, stateMap) {
    const entries = fileMeta?.entries || [];
    if (!entries.length) return 0;

    const isChecked = (lbl) => {
        if (stateMap && Object.prototype.hasOwnProperty.call(stateMap, lbl)) {
            return Boolean(stateMap[lbl]);
        }
        return true;
    };

    const mode = String(filterMode || "").trim();

    if (mode.startsWith("Match ANY")) {
        let matched = 0;
        for (const e of entries) {
            const lbls = e.labels || [];
            if (!lbls.length) {
                if (isChecked(UNTAGGED_LABEL)) matched++;
            } else if (lbls.some((l) => isChecked(l))) {
                matched++;
            }
        }
        return matched;
    }

    if (mode.startsWith("Match ALL")) {
        const known = fileMeta?.labels || [];
        const required = known.filter((l) => isChecked(l));
        const wantUntagged = (fileMeta?.untagged_count || 0) > 0 && isChecked(UNTAGGED_LABEL);
        if (!required.length) {
            if (!wantUntagged) return 0;
            return entries.filter((e) => !(e.labels && e.labels.length)).length;
        }
        let matched = 0;
        for (const e of entries) {
            const set = new Set(e.labels || []);
            if (required.every((r) => set.has(r))) {
                matched++;
            }
        }
        return matched;
    }

    // Default: Allowed Only
    let matched = 0;
    for (const e of entries) {
        const lbls = e.labels || [];
        if (!lbls.length) {
            if (isChecked(UNTAGGED_LABEL)) matched++;
        } else if (lbls.every((l) => isChecked(l))) {
            matched++;
        }
    }
    return matched;
}

function buildLabelFilterUI(node, masterTextarea) {
    if (!masterTextarea || masterTextarea.dataset.wfaPlfEnhanced === "true") return;
    const host = masterTextarea.parentElement;
    if (!host) return;

    masterTextarea.dataset.wfaPlfEnhanced = "true";
    ensureStyles();
    masterTextarea.classList.add("wfa-plf-hidden-textarea");

    const containerEl = document.createElement("div");
    containerEl.className = "wfa-plf-container";

    const toolbarEl = document.createElement("div");
    toolbarEl.className = "wfa-plf-toolbar";

    const statusEl = document.createElement("div");
    statusEl.className = "wfa-plf-status";
    statusEl.textContent = "Scanning...";

    const actionsEl = document.createElement("div");
    actionsEl.className = "wfa-plf-actions";

    const btnAll = document.createElement("button");
    btnAll.type = "button";
    btnAll.className = "wfa-plf-btn";
    btnAll.textContent = "All";
    btnAll.title = "Check all detected labels";

    const btnNone = document.createElement("button");
    btnNone.type = "button";
    btnNone.className = "wfa-plf-btn";
    btnNone.textContent = "None";
    btnNone.title = "Uncheck all detected labels";

    const btnInv = document.createElement("button");
    btnInv.type = "button";
    btnInv.className = "wfa-plf-btn";
    btnInv.textContent = "Inv";
    btnInv.title = "Invert checked labels";

    const btnReload = document.createElement("button");
    btnReload.type = "button";
    btnReload.className = "wfa-plf-btn";
    btnReload.textContent = "↻";
    btnReload.title = "Re-scan prompt .txt file from disk for new [LABEL] tags";

    actionsEl.appendChild(btnAll);
    actionsEl.appendChild(btnNone);
    actionsEl.appendChild(btnInv);
    actionsEl.appendChild(btnReload);

    toolbarEl.appendChild(statusEl);
    toolbarEl.appendChild(actionsEl);

    const scrollEl = document.createElement("div");
    scrollEl.className = "wfa-plf-scroll";

    const gridEl = document.createElement("div");
    gridEl.className = "wfa-plf-grid";
    scrollEl.appendChild(gridEl);

    const hintEl = document.createElement("div");
    hintEl.className = "wfa-plf-hint";
    hintEl.style.display = "none";
    scrollEl.appendChild(hintEl);

    containerEl.appendChild(toolbarEl);
    containerEl.appendChild(scrollEl);

    // Allow wheel scrolling inside checkbox list while preserving Ctrl+Wheel canvas zoom
    scrollEl.addEventListener(
        "wheel",
        (e) => {
            if (e.ctrlKey) return;
            e.stopPropagation();
        },
        { passive: true }
    );

    host.insertBefore(containerEl, masterTextarea);

    let stateMap = parseStateMap(masterTextarea.value);
    let currentMeta = {
        total_prompts: 0,
        labels: [],
        label_counts: {},
        untagged_count: 0,
        entries: [],
    };
    let isInternalSync = false;

    function getPromptFileWidget() {
        return node.widgets?.find((w) => w.name === "prompt_file");
    }

    function getFilterModeWidget() {
        return node.widgets?.find((w) => w.name === "filter_mode");
    }

    function getStateWidget() {
        return node.widgets?.find((w) => w.name === "label_states");
    }

    function getDisplayLabels() {
        const list = [...(currentMeta.labels || [])];
        if ((currentMeta.untagged_count || 0) > 0) {
            list.push(UNTAGGED_LABEL);
        }
        return list;
    }

    function isLabelChecked(lbl) {
        if (Object.prototype.hasOwnProperty.call(stateMap, lbl)) {
            return Boolean(stateMap[lbl]);
        }
        return true;
    }

    function persistState() {
        isInternalSync = true;
        const serialized = JSON.stringify(stateMap);
        masterTextarea.value = serialized;
        const sw = getStateWidget();
        if (sw) {
            sw.value = serialized;
            sw.callback?.(serialized);
        }
        isInternalSync = false;
        node.setDirtyCanvas?.(true, true);
    }

    function updateStatusCounter() {
        const modeVal = getFilterModeWidget()?.value || "Allowed Only";
        const total = currentMeta.total_prompts || 0;
        const active = computeActivePromptCount(currentMeta, modeVal, stateMap);
        statusEl.textContent = `● Active: ${active} / ${total}`;
        statusEl.title = `${active} of ${total} prompts will pass with current [${modeVal}] filter`;
        statusEl.classList.toggle("wfa-zero", total > 0 && active === 0);
    }

    function renderChips() {
        gridEl.innerHTML = "";
        const displayLabels = getDisplayLabels();
        const counts = currentMeta.label_counts || {};

        for (const lbl of displayLabels) {
            const checked = isLabelChecked(lbl);
            const cnt = lbl === UNTAGGED_LABEL ? currentMeta.untagged_count || 0 : counts[lbl] || 0;

            const chip = document.createElement("div");
            chip.className = "wfa-plf-chip" + (checked ? " wfa-checked" : "");
            chip.title =
                `[${lbl}] — ${cnt} prompt${cnt === 1 ? "" : "s"}\n` +
                `• Click: Toggle [${lbl}]\n` +
                `• Ctrl+Click (or Alt+Click): Solo [${lbl}] (uncheck all others)`;

            const left = document.createElement("div");
            left.className = "wfa-plf-chip-left";

            const box = document.createElement("div");
            box.className = "wfa-plf-box";
            box.textContent = "✓";

            const name = document.createElement("div");
            name.className = "wfa-plf-name";
            name.textContent = lbl === UNTAGGED_LABEL ? "[UNTAGGED]" : `[${lbl}]`;

            const countBadge = document.createElement("div");
            countBadge.className = "wfa-plf-count";
            countBadge.textContent = `${cnt}`;

            left.appendChild(box);
            left.appendChild(name);
            chip.appendChild(left);
            chip.appendChild(countBadge);

            chip.addEventListener("mousedown", (e) => {
                if (e.button !== 0) return;
                e.preventDefault();
                e.stopPropagation();

                if (e.ctrlKey || e.metaKey || e.altKey) {
                    for (const k of getDisplayLabels()) {
                        stateMap[k] = k === lbl;
                    }
                } else {
                    stateMap[lbl] = !isLabelChecked(lbl);
                }
                persistState();
                renderChips();
                updateStatusCounter();
            });

            gridEl.appendChild(chip);
        }

        if ((currentMeta.labels || []).length === 0) {
            hintEl.style.display = "block";
            hintEl.textContent =
                (currentMeta.total_prompts || 0) > 0
                    ? "No [TAGS] in titles yet. Add tags like [CORE] [MODERN] [F1] to prompt titles and click ↻."
                    : "No prompts found in selected file.";
        } else {
            hintEl.style.display = "none";
        }

        updateStatusCounter();
    }

    function setAllLabels(val) {
        for (const lbl of getDisplayLabels()) {
            stateMap[lbl] = Boolean(val);
        }
        persistState();
        renderChips();
    }

    function invertAllLabels() {
        for (const lbl of getDisplayLabels()) {
            stateMap[lbl] = !isLabelChecked(lbl);
        }
        persistState();
        renderChips();
    }

    async function fetchLabels(forceRefresh = false) {
        const fw = getPromptFileWidget();
        const fileVal = fw?.value || "";
        if (!fileVal) {
            currentMeta = { total_prompts: 0, labels: [], label_counts: {}, untagged_count: 0, entries: [] };
            renderChips();
            return;
        }
        try {
            statusEl.textContent = "Scanning...";
            const qs = `file=${encodeURIComponent(fileVal)}${forceRefresh ? "&refresh=1" : ""}`;
            const resp = await api.fetchApi(`/wfa/prompt_labels?${qs}`);
            if (resp && resp.ok) {
                const data = await resp.json();
                if (data && data.ok) {
                    currentMeta = data;
                    if (forceRefresh && Array.isArray(data.files) && fw?.options?.values) {
                        fw.options.values = data.files;
                    }
                    // Ensure newly discovered labels are explicitly initialized to true if not yet in stateMap
                    let stateChanged = false;
                    for (const lbl of getDisplayLabels()) {
                        if (!Object.prototype.hasOwnProperty.call(stateMap, lbl)) {
                            stateMap[lbl] = true;
                            stateChanged = true;
                        }
                    }
                    if (stateChanged) {
                        persistState();
                    }
                    renderChips();
                    return;
                }
            }
        } catch (_) {}
        renderChips();
    }

    btnAll.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        setAllLabels(true);
    });

    btnNone.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        setAllLabels(false);
    });

    btnInv.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        invertAllLabels();
    });

    btnReload.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        fetchLabels(true);
    });

    // Sync external workflow loads (`onConfigure` setting textarea.value)
    const protoDesc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    if (protoDesc && protoDesc.get && protoDesc.set) {
        Object.defineProperty(masterTextarea, "value", {
            get() {
                return protoDesc.get.call(this);
            },
            set(val) {
                protoDesc.set.call(this, val);
                if (!isInternalSync) {
                    stateMap = parseStateMap(val);
                    renderChips();
                }
            },
            configurable: true,
        });
    }

    const fw = getPromptFileWidget();
    if (fw && !fw._wfaPlfHooked) {
        fw._wfaPlfHooked = true;
        const origCb = fw.callback;
        fw.callback = function () {
            const r = origCb ? origCb.apply(this, arguments) : undefined;
            fetchLabels(false);
            return r;
        };
    }

    const mw = getFilterModeWidget();
    if (mw && !mw._wfaPlfHooked) {
        mw._wfaPlfHooked = true;
        const origCb = mw.callback;
        mw.callback = function () {
            const r = origCb ? origCb.apply(this, arguments) : undefined;
            updateStatusCounter();
            return r;
        };
    }

    node._wfaPlfApi = {
        reload: () => fetchLabels(true),
        checkAll: () => setAllLabels(true),
        uncheckAll: () => setAllLabels(false),
        syncFromWidget: () => {
            const sw = getStateWidget();
            if (sw && typeof sw.value === "string") {
                stateMap = parseStateMap(sw.value);
            }
            fetchLabels(false);
        },
    };

    fetchLabels(false);
}

function tryAttachFilterUI(node) {
    const sw = node.widgets?.find((w) => w.name === "label_states");
    const textarea = sw?.inputEl || sw?.element;
    if (textarea && textarea.tagName === "TEXTAREA" && textarea.dataset.wfaPlfEnhanced !== "true") {
        if (textarea.parentElement) {
            buildLabelFilterUI(node, textarea);
            return true;
        }
    }
    return textarea?.dataset.wfaPlfEnhanced === "true";
}

const LEGACY_FILTER_MODE_MAP = {
    "Allowed Only (skip unchecked)": "Allowed Only",
    "Match ANY Checked (OR)": "Match ANY (OR)",
    "Match ALL Checked (AND)": "Match ALL (AND)",
};

app.registerExtension({
    name: "WFA.BatchPrompts",
    async setup() {
        api.addEventListener("wfa-batch-prompt-feedback", ({ detail }) => {
            if (!detail || detail.node_id == null) return;
            const node = getNodeById(String(detail.node_id));
            if (node) {
                node._wfaBatchPromptStatus = {
                    text: detail.text || "",
                    warning: Boolean(detail.warning),
                    singleMode: Boolean(detail.single_mode),
                };
                node.setDirtyCanvas?.(true, true);
            }
        });
    },
    async nodeCreated(node) {
        if (node.comfyClass !== FILTER_CLASS && node.type !== FILTER_CLASS) return;
        let attempts = 0;
        const pollMount = () => {
            if (tryAttachFilterUI(node) || attempts > 60) return;
            attempts++;
            setTimeout(pollMount, 50);
        };
        setTimeout(pollMount, 50);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === FILTER_CLASS) {
            const origOnNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const res = origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined;
                this.size = [320, 260];
                return res;
            };

            const origOnConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function () {
                const res = origOnConfigure ? origOnConfigure.apply(this, arguments) : undefined;
                const mw = this.widgets?.find((w) => w.name === "filter_mode");
                if (mw && LEGACY_FILTER_MODE_MAP[mw.value]) {
                    mw.value = LEGACY_FILTER_MODE_MAP[mw.value];
                }
                setTimeout(() => {
                    this._wfaPlfApi?.syncFromWidget?.();
                }, 60);
                return res;
            };

            const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function (_, options) {
                if (origGetExtraMenuOptions) {
                    origGetExtraMenuOptions.apply(this, arguments);
                }
                options.unshift(
                    {
                        content: "↻ Reload Labels from .txt File",
                        callback: () => this._wfaPlfApi?.reload?.(),
                    },
                    {
                        content: "✓ Check All Labels",
                        callback: () => this._wfaPlfApi?.checkAll?.(),
                    },
                    {
                        content: "✖ Uncheck All Labels",
                        callback: () => this._wfaPlfApi?.uncheckAll?.(),
                    },
                    null
                );
            };

            const origOnDrawForeground = nodeType.prototype.onDrawForeground;
            nodeType.prototype.onDrawForeground = function () {
                if (origOnDrawForeground) origOnDrawForeground.apply(this, arguments);
                tryAttachFilterUI(this);
            };
        }

        if (LOADER_CLASSES.has(nodeData.name)) {
            const origOnDrawForeground = nodeType.prototype.onDrawForeground;
            nodeType.prototype.onDrawForeground = function (ctx, graphCanvas, canvasEl, lowQuality) {
                if (origOnDrawForeground) origOnDrawForeground.apply(this, arguments);
                if (this.flags?.collapsed) return;
                if (lowQuality || graphCanvas?.low_quality || app.canvas?.low_quality) return;

                const status = this._wfaBatchPromptStatus;
                if (!status || !status.text) return;

                const titleH = window.LiteGraph?.NODE_TITLE_HEIGHT || 30;
                const pillH = 20;
                const pillY = -titleH - pillH - 4;

                const strokeColor = status.warning
                    ? "#ef4444"
                    : status.singleMode
                      ? "#38bdf8"
                      : "#4ade80";
                const fillTint = status.warning
                    ? "rgba(239, 68, 68, 0.25)"
                    : status.singleMode
                      ? "rgba(56, 189, 248, 0.20)"
                      : "rgba(74, 222, 128, 0.18)";
                const textColor = status.warning
                    ? "#fca5a5"
                    : status.singleMode
                      ? "#7dd3fc"
                      : "#4ade80";

                ctx.save();
                ctx.font = 'bold 11px "JetBrains Mono", "Consolas", sans-serif';
                const textW = ctx.measureText(status.text).width;
                const pillW = Math.max(150, textW + 18);

                ctx.fillStyle = "#18181b";
                ctx.strokeStyle = strokeColor;
                ctx.lineWidth = status.warning ? 1.5 : 1;
                ctx.beginPath();
                ctx.roundRect(0, pillY, pillW, pillH, 5);
                ctx.fill();
                ctx.stroke();

                ctx.save();
                ctx.beginPath();
                ctx.roundRect(0, pillY, pillW, pillH, 5);
                ctx.clip();
                ctx.fillStyle = fillTint;
                ctx.fillRect(0, pillY, pillW, pillH);
                ctx.restore();

                ctx.fillStyle = textColor;
                ctx.textBaseline = "middle";
                ctx.fillText(status.text, 8, pillY + pillH / 2);
                ctx.restore();
            };
        }
    },
});
