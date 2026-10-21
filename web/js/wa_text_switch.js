import { app } from "../../../scripts/app.js";

const GUTTER_WIDTH = 44;
const ROW_MIN_HEIGHT = 24;
const TOTAL_ROWS = 100;

const STYLE_ID = "wa-text-switch-styles";

function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
        .wa-ts-container {
            position: relative !important;
            width: 100% !important;
            height: 100% !important;
            background: #18181b !important;
            border: 1px solid #3f3f46 !important;
            border-radius: 6px !important;
            overflow: hidden !important;
            padding: 0 !important;
            box-sizing: border-box !important;
        }

        .wa-ts-list {
            position: absolute !important;
            top: 0 !important;
            left: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            overflow-y: scroll !important;
            overflow-x: hidden !important;
            z-index: 2 !important;
            box-sizing: border-box !important;
        }

        .wa-ts-row {
            display: flex !important;
            flex-direction: row !important;
            align-items: stretch !important;
            width: 100% !important;
            min-height: ${ROW_MIN_HEIGHT}px !important;
            box-sizing: border-box !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
        }

        /* Alternating dark grey and light grey rows */
        .wa-ts-row.wa-even {
            background-color: #1c1c20 !important;
        }

        .wa-ts-row.wa-odd {
            background-color: #2f2f37 !important;
        }

        /* Highlight for the row matching the 'select' input */
        .wa-ts-row.wa-selected {
            box-shadow: inset 3px 0 0 #4ade80 !important;
        }

        /* Highlight for the currently focused row */
        .wa-ts-row.wa-focused {
            outline: 1px solid rgba(56, 189, 248, 0.55) !important;
            outline-offset: -1px !important;
        }

        .wa-ts-gutter-cell {
            width: ${GUTTER_WIDTH}px !important;
            min-width: ${GUTTER_WIDTH}px !important;
            max-width: ${GUTTER_WIDTH}px !important;
            padding: 3px 8px 3px 4px !important;
            box-sizing: border-box !important;
            text-align: right !important;
            font-family: "JetBrains Mono", "Consolas", "Monaco", "Courier New", monospace !important;
            font-size: 12px !important;
            line-height: 18px !important;
            color: #a1a1aa !important;
            background: rgba(0, 0, 0, 0.28) !important;
            border-right: 1px solid #454552 !important;
            cursor: pointer !important;
            user-select: none !important;
            display: flex !important;
            align-items: flex-start !important;
            justify-content: flex-end !important;
        }

        .wa-ts-gutter-cell:hover {
            color: #ffffff !important;
            background: rgba(255, 255, 255, 0.12) !important;
        }

        .wa-ts-row.wa-selected .wa-ts-gutter-cell {
            color: #4ade80 !important;
            font-weight: 700 !important;
            background: rgba(74, 222, 128, 0.16) !important;
        }

        .wa-ts-row.wa-focused .wa-ts-gutter-cell {
            color: #38bdf8 !important;
            font-weight: 700 !important;
        }

        .wa-ts-cell-input {
            flex: 1 1 auto !important;
            width: calc(100% - ${GUTTER_WIDTH}px) !important;
            min-height: ${ROW_MIN_HEIGHT}px !important;
            height: ${ROW_MIN_HEIGHT}px;
            margin: 0 !important;
            padding: 3px 8px !important;
            border: none !important;
            outline: none !important;
            box-sizing: border-box !important;
            background: transparent !important;
            color: #f4f4f6 !important;
            caret-color: #38bdf8 !important;
            font-family: "JetBrains Mono", "Consolas", "Monaco", "Courier New", monospace !important;
            font-size: 13px !important;
            line-height: 18px !important;
            resize: none !important;
            overflow: hidden !important;
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
            overflow-wrap: break-word !important;
        }

        .wa-ts-cell-input::selection {
            background: rgba(56, 189, 248, 0.32) !important;
        }

        textarea.wa-ts-hidden-textarea {
            position: absolute !important;
            width: 1px !important;
            height: 1px !important;
            opacity: 0 !important;
            pointer-events: none !important;
            z-index: -1 !important;
        }
    `;
    document.head.appendChild(style);
}

function buildRowListEditor(node, masterTextarea) {
    if (!masterTextarea || masterTextarea.dataset.waEnhanced === "true") return;
    const host = masterTextarea.parentElement;
    if (!host) return;

    masterTextarea.dataset.waEnhanced = "true";
    ensureStyles();

    // Do NOT override host (.dom-widget) position: absolute!
    // Instead create an inner container that fills host.
    masterTextarea.classList.add("wa-ts-hidden-textarea");

    const containerEl = document.createElement("div");
    containerEl.className = "wa-ts-container";

    const listEl = document.createElement("div");
    listEl.className = "wa-ts-list";
    containerEl.appendChild(listEl);

    // Forward Ctrl+Wheel to canvas zoom, allow normal wheel to scroll rows
    listEl.addEventListener(
        "wheel",
        (e) => {
            if (e.ctrlKey) return;
            e.stopPropagation();
        },
        { passive: true }
    );

    // Blur focused row input immediately when clicking outside (e.g. clicking node title bar to drag)
    const onOutsidePointerDown = (e) => {
        if (!containerEl.contains(e.target) && containerEl.contains(document.activeElement)) {
            document.activeElement?.blur?.();
        }
    };
    window.addEventListener("pointerdown", onOutsidePointerDown, true);
    window.addEventListener("mousedown", onOutsidePointerDown, true);

    const rowEls = [];
    const cellInputs = [];
    let isInternalSync = false;

    function autoResizeCell(cell) {
        cell.style.height = `${ROW_MIN_HEIGHT}px`;
        const scH = cell.scrollHeight;
        if (scH > ROW_MIN_HEIGHT) {
            cell.style.height = `${scH}px`;
        }
    }

    function syncToMasterTextarea() {
        isInternalSync = true;
        let lastNonEmpty = -1;
        for (let i = cellInputs.length - 1; i >= 0; i--) {
            if (cellInputs[i].value.length > 0) {
                lastNonEmpty = i;
                break;
            }
        }
        const values = [];
        for (let i = 0; i <= lastNonEmpty; i++) {
            values.push(cellInputs[i].value.replace(/\r?\n/g, " "));
        }
        const joined = values.join("\n");
        masterTextarea.value = joined;

        const textWidget = node.widgets?.find((w) => w.name === "text");
        if (textWidget) {
            textWidget.value = joined;
            textWidget.callback?.(joined);
        }
        isInternalSync = false;
    }

    function loadFromMasterTextarea() {
        if (isInternalSync) return;
        const raw = masterTextarea.value || "";
        const lines = raw.split(/\r?\n/);
        for (let i = 0; i < TOTAL_ROWS; i++) {
            const val = i < lines.length ? lines[i] : "";
            if (cellInputs[i].value !== val) {
                cellInputs[i].value = val;
            }
            autoResizeCell(cellInputs[i]);
        }
        updateSelectedRowHighlight();
    }

    let lastHighlightedRow = -1;

    function resolveUpstreamIntValue(startNode, inputName) {
        let curNode = startNode;
        const graph = startNode.graph || app.graph;
        if (!graph) return null;

        for (let depth = 0; depth < 10 && curNode; depth++) {
            const slotIdx =
                depth === 0
                    ? curNode.inputs?.findIndex((inp) => inp?.name === inputName) ?? -1
                    : 0;
            if (slotIdx < 0) break;

            let link = null;
            if (typeof curNode.getInputLink === "function") {
                try {
                    link = curNode.getInputLink(slotIdx);
                } catch (_) {}
            }
            if (!link) {
                const linkId = curNode.inputs?.[slotIdx]?.link;
                if (linkId != null && typeof graph.getLink === "function") {
                    link = graph.getLink(linkId);
                }
            }
            if (!link) break;

            const originNode = graph.getNodeById(link.origin_id);
            if (!originNode) break;

            // If it's a Reroute node, keep walking upstream
            if (
                originNode.type === "Reroute" ||
                originNode.comfyClass === "Reroute" ||
                (!originNode.widgets?.length && originNode.inputs?.length === 1)
            ) {
                curNode = originNode;
                continue;
            }

            // If upstream node is another WFA Text/INT Index Switch whose 'select' is also wired, keep walking
            if (
                TARGET_CLASSES.has(originNode.comfyClass) &&
                originNode.inputs?.some((inp) => inp?.name === "select" && inp?.link != null)
            ) {
                curNode = originNode;
                inputName = "select";
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
        return null;
    }

    function getSelectedRow() {
        const upstreamVal = resolveUpstreamIntValue(node, "select");
        if (upstreamVal !== null) return upstreamVal;
        const selectWidget = node.widgets?.find((w) => w.name === "select");
        return selectWidget ? Number(selectWidget.value) || 0 : 0;
    }

    function updateSelectedRowHighlight(force = false) {
        const sel = getSelectedRow();
        if (!force && sel === lastHighlightedRow) return;
        lastHighlightedRow = sel;
        for (let i = 0; i < rowEls.length; i++) {
            rowEls[i].classList.toggle("wa-selected", i === sel);
        }
    }

    node._waUpdateSelectedHighlight = updateSelectedRowHighlight;

    function insertRowAt(index) {
        for (let k = TOTAL_ROWS - 1; k > index; k--) {
            cellInputs[k].value = cellInputs[k - 1].value;
            autoResizeCell(cellInputs[k]);
        }
        cellInputs[index].value = "";
        autoResizeCell(cellInputs[index]);
        syncToMasterTextarea();
        cellInputs[index].focus();
    }

    function deleteRowAt(index) {
        for (let k = index; k < TOTAL_ROWS - 1; k++) {
            cellInputs[k].value = cellInputs[k + 1].value;
            autoResizeCell(cellInputs[k]);
        }
        cellInputs[TOTAL_ROWS - 1].value = "";
        autoResizeCell(cellInputs[TOTAL_ROWS - 1]);
        syncToMasterTextarea();
    }

    const fragment = document.createDocumentFragment();

    for (let i = 0; i < TOTAL_ROWS; i++) {
        const rowEl = document.createElement("div");
        rowEl.className = "wa-ts-row " + (i % 2 === 0 ? "wa-even" : "wa-odd");

        const gutterEl = document.createElement("div");
        gutterEl.className = "wa-ts-gutter-cell";
        gutterEl.textContent = `${i}`;
        gutterEl.title = `Row ${i}\n• Click: Set select = ${i}\n• Ctrl+Click: Insert new row here (push below down)\n• Shift+Click (or Alt+Click): Delete row (pull below up)`;
        gutterEl.addEventListener("mousedown", (e) => {
            e.preventDefault();
            e.stopPropagation();

            if (e.ctrlKey || e.metaKey) {
                insertRowAt(i);
                return;
            }

            if (e.shiftKey || e.altKey) {
                deleteRowAt(i);
                return;
            }

            const selectWidget = node.widgets?.find((w) => w.name === "select");
            if (selectWidget) {
                selectWidget.value = i;
                selectWidget.callback?.(i);
                updateSelectedRowHighlight();
                node.setDirtyCanvas?.(true, true);
            }
        });

        const cell = document.createElement("textarea");
        cell.className = "wa-ts-cell-input";
        cell.rows = 1;
        cell.spellcheck = false;

        cell.addEventListener("focus", () => {
            rowEl.classList.add("wa-focused");
            if (app.canvas) {
                app.canvas.selectNode(node);
                app.canvas.bringToFront(node);
            }
        });

        cell.addEventListener("blur", () => {
            rowEl.classList.remove("wa-focused");
        });

        cell.addEventListener("input", () => {
            autoResizeCell(cell);
            syncToMasterTextarea();
        });

        // Multi-line paste distributes lines across subsequent rows automatically
        cell.addEventListener("paste", (e) => {
            const clipText = e.clipboardData?.getData("text/plain") || "";
            if (clipText.includes("\n")) {
                e.preventDefault();
                const pastedLines = clipText.split(/\r?\n/);
                for (let k = 0; k < pastedLines.length && i + k < TOTAL_ROWS; k++) {
                    cellInputs[i + k].value = pastedLines[k];
                    autoResizeCell(cellInputs[i + k]);
                }
                syncToMasterTextarea();
            }
        });

        // Keyboard navigation: Enter / ArrowDown moves to next row, ArrowUp moves to previous row
        cell.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (i + 1 < TOTAL_ROWS) {
                    cellInputs[i + 1].focus();
                }
            } else if (e.key === "ArrowDown" && i + 1 < TOTAL_ROWS) {
                const atEnd = cell.selectionStart === cell.value.length;
                if (atEnd || !cell.value.includes("\n")) {
                    e.preventDefault();
                    cellInputs[i + 1].focus();
                }
            } else if (e.key === "ArrowUp" && i - 1 >= 0) {
                const atStart = cell.selectionStart === 0;
                if (atStart || !cell.value.includes("\n")) {
                    e.preventDefault();
                    cellInputs[i - 1].focus();
                }
            }
        });

        rowEl.appendChild(gutterEl);
        rowEl.appendChild(cell);
        fragment.appendChild(rowEl);

        rowEls.push(rowEl);
        cellInputs.push(cell);
    }

    listEl.appendChild(fragment);
    host.insertBefore(containerEl, masterTextarea);

    const protoDesc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    if (protoDesc && protoDesc.get && protoDesc.set) {
        Object.defineProperty(masterTextarea, "value", {
            get() {
                return protoDesc.get.call(this);
            },
            set(val) {
                protoDesc.set.call(this, val);
                loadFromMasterTextarea();
            },
            configurable: true,
        });
    }

    if (typeof ResizeObserver !== "undefined") {
        const ro = new ResizeObserver(() => {
            for (let i = 0; i < cellInputs.length; i++) {
                if (cellInputs[i].value.length > 0) {
                    autoResizeCell(cellInputs[i]);
                }
            }
        });
        ro.observe(listEl);
    }

    const selectWidget = node.widgets?.find((w) => w.name === "select");
    if (selectWidget && !selectWidget._waHooked) {
        selectWidget._waHooked = true;
        const origCallback = selectWidget.callback;
        selectWidget.callback = function () {
            if (origCallback) origCallback.apply(this, arguments);
            updateSelectedRowHighlight();
        };
    }

    loadFromMasterTextarea();
}

function tryAttachWhenMounted(node) {
    const textWidget = node.widgets?.find((w) => w.name === "text");
    const textarea = textWidget?.inputEl || textWidget?.element;
    if (textarea && textarea.tagName === "TEXTAREA" && textarea.dataset.waEnhanced !== "true") {
        if (textarea.parentElement) {
            buildRowListEditor(node, textarea);
            return true;
        }
    }
    return textarea?.dataset.waEnhanced === "true";
}

const TARGET_CLASSES = new Set(["WFA_TextIndexSwitch", "WA_TextIndexSwitch", "WFA_IntIndexSwitch"]);

app.registerExtension({
    name: "WFA.TextIndexSwitch",
    async nodeCreated(node) {
        if (!TARGET_CLASSES.has(node.comfyClass) && !TARGET_CLASSES.has(node.type)) return;
        let attempts = 0;
        const pollMount = () => {
            if (tryAttachWhenMounted(node) || attempts > 60) return;
            attempts++;
            setTimeout(pollMount, 50);
        };
        setTimeout(pollMount, 50);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!TARGET_CLASSES.has(nodeData.name)) return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const res = origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined;
            this.size = [540, 480];
            return res;
        };

        const origOnDrawForeground = nodeType.prototype.onDrawForeground;
        nodeType.prototype.onDrawForeground = function () {
            if (origOnDrawForeground) origOnDrawForeground.apply(this, arguments);
            tryAttachWhenMounted(this);
            this._waUpdateSelectedHighlight?.();
        };
    },
});
