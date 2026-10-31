import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const CHAR_COCKPIT_CLASS = "WFA_CharacterLoraCockpit";
const GEN_DECK_CLASS = "WFA_GenerationDeck";
const INSPECTOR_CLASS = "WFA_PromptInspector";
const PIPE_IN_CLASS = "WFA_CockpitPipeIn";
const PIPE_OUT_CLASS = "WFA_CockpitPipeOut";
const ALL_COCKPIT_CLASSES = new Set([CHAR_COCKPIT_CLASS, GEN_DECK_CLASS, INSPECTOR_CLASS]);

const PIPE_COLOR = "#4ade80";
const STYLE_ID = "wfa-cockpit-suite-styles";

let sharedCockpitMeta = {
    loaded: false,
    loras: ["None"],
    samplers: ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_sde", "uni_pc", "er_sde", "ddim"],
    schedulers: ["normal", "karras", "exponential", "sgm_uniform", "simple", "ddim_uniform", "beta"],
};
const metaListeners = new Set();

function registerPipeColors() {
    try {
        if (window.LGraphCanvas?.link_type_colors) {
            window.LGraphCanvas.link_type_colors.WFA_PIPE = PIPE_COLOR;
        }
        if (app.canvas?.default_connection_color_byType) {
            app.canvas.default_connection_color_byType.WFA_PIPE = PIPE_COLOR;
        }
    } catch (_) {}
}

async function fetchCockpitMeta(force = false) {
    if (sharedCockpitMeta.loaded && !force) return sharedCockpitMeta;
    try {
        const resp = await api.fetchApi(`/wfa/cockpit_meta${force ? "?refresh=1" : ""}`);
        if (resp && resp.ok) {
            const data = await resp.json();
            if (data && data.ok) {
                if (Array.isArray(data.loras) && data.loras.length) sharedCockpitMeta.loras = data.loras;
                if (Array.isArray(data.samplers) && data.samplers.length) sharedCockpitMeta.samplers = data.samplers;
                if (Array.isArray(data.schedulers) && data.schedulers.length) sharedCockpitMeta.schedulers = data.schedulers;
                sharedCockpitMeta.loaded = true;
                for (const fn of metaListeners) {
                    try {
                        fn(sharedCockpitMeta);
                    } catch (_) {}
                }
            }
        }
    } catch (_) {}
    return sharedCockpitMeta;
}

function getNodeById(nodeId) {
    if (!app.graph) return null;
    if (typeof app.graph.getNodeById === "function") {
        const n = app.graph.getNodeById(Number(nodeId)) || app.graph.getNodeById(String(nodeId));
        if (n) return n;
    }
    return app.graph._nodes_by_id?.[nodeId] || null;
}

function escapeHtml(str) {
    return String(str || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function highlightPromptHtml(raw) {
    if (!raw) {
        return `<span class="wfa-ck-muted">Run a generation to inspect the compiled prompt & token breakdown...</span>`;
    }
    let html = escapeHtml(raw);
    html = html.replace(/\/\*[\s\S]*?\*\//g, (m) => `<span class="wfa-hl-warn" title="Unreplaced comment/placeholder">${m}</span>`);
    html = html.replace(/&lt;lora:[^&]+?&gt;/gi, (m) => `<span class="wfa-hl-lora">${m}</span>`);
    html = html.replace(/\{[^{}\n]+\}/g, (m) => `<span class="wfa-hl-dyn">${m}</span>`);
    html = html.replace(/\([^()\n]+:\s*-?\d+(?:\.\d+)?\)/g, (m) => `<span class="wfa-hl-wt">${m}</span>`);
    return html;
}

function formatShortLoraLabel(loraName) {
    if (!loraName || loraName === "None") return "— None —";
    const norm = String(loraName).replace(/\\/g, "/");
    const parts = norm.split("/");
    const file = parts[parts.length - 1].replace(/\.(safetensors|ckpt|pt|bin)$/i, "");
    if (parts.length > 1) {
        const folder = parts[parts.length - 2];
        return `${folder} / ${file}`;
    }
    return file;
}

function loraStem(loraName) {
    const norm = String(loraName || "").replace(/\\/g, "/");
    const base = norm.split("/").pop() || "";
    return base.replace(/\.[^.]+$/, "");
}

function formatLoraWt(val) {
    const r = Math.round(Number(val) * 10000) / 10000;
    if (Number.isInteger(r)) return r.toFixed(1);
    return String(r);
}

function gcd(a, b) {
    let x = Math.abs(Math.round(a));
    let y = Math.abs(Math.round(b));
    while (y !== 0) {
        const t = y;
        y = x % y;
        x = t;
    }
    return x || 1;
}

function formatAspectBadge(w, h) {
    const d = gcd(w, h);
    const rw = Math.round(w / d);
    const rh = Math.round(h / d);
    const ratioStr = rw <= 25 && rh <= 25 ? `${rw}:${rh}` : `${(w / Math.max(1, h)).toFixed(2)}:1`;
    const mp = ((w * h) / 1000000).toFixed(2);
    return `${ratioStr} • ${mp}MP`;
}

function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
        textarea.wfa-ck-hidden-ta {
            position: absolute !important;
            width: 1px !important;
            height: 1px !important;
            opacity: 0 !important;
            pointer-events: none !important;
            z-index: -1 !important;
        }

        .wfa-ck-card {
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
            color: #f4f4f6 !important;
            user-select: none !important;
        }

        .wfa-ck-header {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            justify-content: space-between !important;
            gap: 5px !important;
            padding: 4px 7px !important;
            background: #121215 !important;
            border-bottom: 1px solid #2e2e36 !important;
            min-height: 26px !important;
            flex: 0 0 auto !important;
            box-sizing: border-box !important;
        }

        .wfa-ck-badge {
            font-size: 11px !important;
            font-weight: 700 !important;
            color: #4ade80 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }

        .wfa-ck-badge.wfa-muted {
            color: #a1a1aa !important;
        }

        .wfa-ck-badge.wfa-warn {
            color: #fbbf24 !important;
        }

        .wfa-ck-row-btns {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            gap: 3px !important;
            flex: 0 0 auto !important;
        }

        .wfa-ck-mini-btn {
            background: #27272e !important;
            color: #d4d4d8 !important;
            border: 1px solid #3f3f46 !important;
            border-radius: 4px !important;
            padding: 1px 6px !important;
            font-family: inherit !important;
            font-size: 10px !important;
            font-weight: 600 !important;
            line-height: 16px !important;
            cursor: pointer !important;
            transition: background 0.1s ease, border-color 0.1s ease, color 0.1s ease !important;
        }

        .wfa-ck-mini-btn:hover {
            background: #353540 !important;
            color: #ffffff !important;
            border-color: #52525b !important;
        }

        .wfa-ck-mini-btn.wfa-active {
            background: rgba(74, 222, 128, 0.18) !important;
            color: #4ade80 !important;
            border-color: rgba(74, 222, 128, 0.55) !important;
        }

        .wfa-ck-mini-btn.wfa-mode-blue {
            background: rgba(56, 189, 248, 0.16) !important;
            color: #7dd3fc !important;
            border-color: rgba(56, 189, 248, 0.55) !important;
        }

        .wfa-ck-body {
            flex: 1 1 auto !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            box-sizing: border-box !important;
            display: flex !important;
            flex-direction: column !important;
        }

        /* --- Character LoRA Cockpit Rows --- */
        .wfa-char-row {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            gap: 4px !important;
            padding: 5px 6px !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
            box-sizing: border-box !important;
            flex: 0 0 auto !important;
        }

        .wfa-char-row.wfa-even {
            background: #1c1c21 !important;
        }

        .wfa-char-row.wfa-odd {
            background: #26262e !important;
        }

        .wfa-char-row.wfa-live-on {
            box-shadow: inset 3px 0 0 #4ade80 !important;
        }

        .wfa-char-footer {
            flex: 1 1 auto !important;
            min-height: 24px !important;
            background: #121215 !important;
            padding: 5px 7px !important;
            font-size: 10.5px !important;
            line-height: 15px !important;
            color: #71717a !important;
            overflow-y: auto !important;
            word-break: break-word !important;
            box-sizing: border-box !important;
        }

        .wfa-char-toggle {
            min-width: 42px !important;
            height: 22px !important;
            border-radius: 4px !important;
            border: 1px solid #3f3f46 !important;
            background: #141418 !important;
            color: #71717a !important;
            font-family: inherit !important;
            font-size: 11px !important;
            font-weight: 700 !important;
            cursor: pointer !important;
            padding: 0 5px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 3px !important;
            flex: 0 0 auto !important;
        }

        .wfa-char-toggle.wfa-on {
            background: rgba(74, 222, 128, 0.16) !important;
            border-color: #4ade80 !important;
            color: #4ade80 !important;
        }

        .wfa-char-ovr {
            width: 24px !important;
            height: 22px !important;
            border-radius: 4px !important;
            border: 1px solid #3f3f46 !important;
            background: #141418 !important;
            color: #52525b !important;
            font-size: 10px !important;
            font-weight: 700 !important;
            cursor: pointer !important;
            padding: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            flex: 0 0 auto !important;
        }

        .wfa-char-ovr.wfa-on {
            background: rgba(251, 191, 36, 0.18) !important;
            border-color: #fbbf24 !important;
            color: #fbbf24 !important;
        }

        .wfa-lora-pick-wrap {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            flex: 1 1 auto !important;
            min-width: 70px !important;
            height: 22px !important;
            background: #121215 !important;
            border: 1px solid #383842 !important;
            border-radius: 4px !important;
            overflow: hidden !important;
        }

        .wfa-lora-pick-wrap:hover {
            border-color: #52525b !important;
        }

        .wfa-lora-pick-btn {
            flex: 1 1 auto !important;
            min-width: 0 !important;
            height: 100% !important;
            background: transparent !important;
            border: none !important;
            color: #e4e4e7 !important;
            font-family: inherit !important;
            font-size: 11px !important;
            text-align: left !important;
            padding: 0 6px !important;
            cursor: pointer !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }

        .wfa-lora-pick-btn.wfa-none {
            color: #63636e !important;
        }

        .wfa-lora-clear-btn {
            width: 18px !important;
            height: 100% !important;
            background: transparent !important;
            border: none !important;
            border-left: 1px solid #27272e !important;
            color: #71717a !important;
            font-size: 10px !important;
            cursor: pointer !important;
            padding: 0 !important;
            flex: 0 0 auto !important;
        }

        .wfa-lora-clear-btn:hover {
            color: #f87171 !important;
            background: rgba(248, 113, 113, 0.12) !important;
        }

        .wfa-str-group {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            gap: 2px !important;
            flex: 0 0 auto !important;
        }

        .wfa-str-lbl {
            font-size: 9px !important;
            font-weight: 700 !important;
            color: #a1a1aa !important;
        }

        .wfa-ck-num, .wfa-ck-input, .wfa-ck-select {
            background: #121215 !important;
            color: #f4f4f6 !important;
            border: 1px solid #383842 !important;
            border-radius: 4px !important;
            font-family: inherit !important;
            font-size: 11px !important;
            height: 22px !important;
            padding: 0 5px !important;
            box-sizing: border-box !important;
            outline: none !important;
        }

        .wfa-ck-num {
            -moz-appearance: textfield !important;
            appearance: textfield !important;
        }

        .wfa-ck-num::-webkit-outer-spin-button,
        .wfa-ck-num::-webkit-inner-spin-button {
            -webkit-appearance: none !important;
            margin: 0 !important;
        }

        .wfa-ck-num:focus, .wfa-ck-input:focus, .wfa-ck-select:focus {
            border-color: #38bdf8 !important;
        }

        .wfa-str-num {
            width: 44px !important;
            text-align: center !important;
            padding: 0 3px !important;
        }

        /* Searchable LoRA Popover */
        .wfa-lora-popover {
            position: absolute !important;
            top: 28px !important;
            left: 6px !important;
            right: 6px !important;
            bottom: 6px !important;
            background: #141418 !important;
            border: 1px solid #4ade80 !important;
            border-radius: 6px !important;
            z-index: 50 !important;
            display: flex !important;
            flex-direction: column !important;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.65) !important;
            overflow: hidden !important;
        }

        .wfa-lora-pop-top {
            display: flex !important;
            gap: 4px !important;
            padding: 5px !important;
            background: #0f0f12 !important;
            border-bottom: 1px solid #27272e !important;
        }

        .wfa-lora-pop-list {
            flex: 1 1 auto !important;
            overflow-y: auto !important;
            padding: 3px !important;
        }

        .wfa-lora-pop-item {
            padding: 4px 7px !important;
            font-size: 11px !important;
            color: #d4d4d8 !important;
            border-radius: 4px !important;
            cursor: pointer !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }

        .wfa-lora-pop-item:hover, .wfa-lora-pop-item.wfa-sel {
            background: rgba(74, 222, 128, 0.16) !important;
            color: #4ade80 !important;
        }

        /* --- Generation Deck Sections --- */
        .wfa-deck-sec {
            padding: 6px 7px !important;
            border-bottom: 1px solid #27272f !important;
            display: flex !important;
            flex-direction: column !important;
            gap: 5px !important;
            flex: 0 0 auto !important;
        }

        .wfa-deck-sec:nth-child(even) {
            background: #1d1d23 !important;
        }

        .wfa-deck-line {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            gap: 5px !important;
            width: 100% !important;
        }

        .wfa-deck-field {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            gap: 4px !important;
            flex: 1 1 0 !important;
            min-width: 0 !important;
        }

        .wfa-deck-lbl {
            font-size: 10px !important;
            font-weight: 700 !important;
            color: #a1a1aa !important;
            white-space: nowrap !important;
            flex: 0 0 auto !important;
        }

        .wfa-deck-pill {
            flex: 1 1 0 !important;
            height: 23px !important;
            border-radius: 4px !important;
            border: 1px solid #3f3f46 !important;
            background: #141418 !important;
            color: #a1a1aa !important;
            font-family: inherit !important;
            font-size: 10px !important;
            font-weight: 700 !important;
            cursor: pointer !important;
            padding: 0 6px !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 4px !important;
        }

        .wfa-deck-pill:hover {
            border-color: #52525b !important;
            color: #f4f4f6 !important;
        }

        .wfa-deck-pill.wfa-on {
            background: rgba(74, 222, 128, 0.14) !important;
            border-color: rgba(74, 222, 128, 0.6) !important;
            color: #4ade80 !important;
            box-shadow: inset 2px 0 0 #4ade80 !important;
        }

        .wfa-deck-pill.wfa-alt-blue {
            background: rgba(56, 189, 248, 0.14) !important;
            border-color: rgba(56, 189, 248, 0.55) !important;
            color: #7dd3fc !important;
        }

        /* --- 2D Aspect Ratio & Resolution Pad --- */
        .wfa-res-2d-wrap {
            display: flex !important;
            flex-direction: row !important;
            align-items: stretch !important;
            gap: 8px !important;
            width: 100% !important;
        }

        .wfa-res-pad-canvas {
            width: 114px !important;
            height: 114px !important;
            flex: 0 0 114px !important;
            background: #111115 !important;
            border: 1px solid #383842 !important;
            border-radius: 5px !important;
            cursor: crosshair !important;
            touch-action: none !important;
            box-sizing: border-box !important;
            transition: border-color 0.1s ease !important;
        }

        .wfa-res-pad-canvas:hover,
        .wfa-res-pad-canvas.wfa-dragging {
            border-color: #4ade80 !important;
        }

        .wfa-res-right-col {
            flex: 1 1 0 !important;
            min-width: 0 !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: space-between !important;
            height: 114px !important;
            box-sizing: border-box !important;
        }

        .wfa-res-chips {
            display: grid !important;
            grid-template-columns: repeat(3, 1fr) !important;
            gap: 3px !important;
        }

        .wfa-res-chip {
            height: 21px !important;
            font-family: inherit !important;
            font-size: 9.5px !important;
            font-weight: 600 !important;
            background: #141418 !important;
            color: #a1a1aa !important;
            border: 1px solid #32323b !important;
            border-radius: 3px !important;
            cursor: pointer !important;
            padding: 0 2px !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
        }

        .wfa-res-chip:hover {
            color: #ffffff !important;
            border-color: #52525b !important;
        }

        .wfa-res-chip.wfa-match {
            background: rgba(74, 222, 128, 0.16) !important;
            color: #4ade80 !important;
            border-color: #4ade80 !important;
        }

        .wfa-toggles-grid {
            display: grid !important;
            grid-template-columns: 1fr 1fr !important;
            gap: 4px !important;
        }

        /* --- Prompt Inspector --- */
        .wfa-insp-prompt {
            padding: 8px 9px !important;
            font-size: 11.5px !important;
            line-height: 17px !important;
            color: #e4e4e7 !important;
            white-space: pre-wrap !important;
            word-break: break-word !important;
            user-select: text !important;
        }

        .wfa-ck-muted {
            color: #71717a !important;
            font-style: italic !important;
        }

        .wfa-hl-lora {
            color: #4ade80 !important;
            background: rgba(74, 222, 128, 0.12) !important;
            border: 1px solid rgba(74, 222, 128, 0.32) !important;
            border-radius: 3px !important;
            padding: 0 3px !important;
            font-weight: 600 !important;
        }

        .wfa-hl-warn {
            color: #fde68a !important;
            background: rgba(245, 158, 11, 0.28) !important;
            border: 1px solid #f59e0b !important;
            border-radius: 3px !important;
            padding: 0 3px !important;
            font-weight: 700 !important;
        }

        .wfa-hl-wt {
            color: #7dd3fc !important;
        }

        .wfa-hl-dyn {
            color: #d8b4fe !important;
        }

        .wfa-insp-row {
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            justify-content: space-between !important;
            gap: 8px !important;
            padding: 3px 8px !important;
            font-size: 11px !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04) !important;
            flex: 0 0 auto !important;
        }

        .wfa-insp-row:nth-child(even) {
            background: #23232b !important;
        }

        .wfa-insp-tag {
            flex: 1 1 auto !important;
            min-width: 0 !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            white-space: nowrap !important;
            color: #e4e4e7 !important;
        }

        .wfa-insp-tok {
            flex: 0 0 auto !important;
            font-size: 10px !important;
            font-weight: 700 !important;
            padding: 1px 5px !important;
            border-radius: 3px !important;
            background: rgba(56, 189, 248, 0.14) !important;
            color: #7dd3fc !important;
        }

        .wfa-insp-tok.wfa-lora {
            background: rgba(74, 222, 128, 0.14) !important;
            color: #4ade80 !important;
        }

        .wfa-insp-tok.wfa-warn {
            background: rgba(245, 158, 11, 0.25) !important;
            color: #fbbf24 !important;
        }
    `;
    document.head.appendChild(style);
}

function attachWheelGuard(el) {
    el.addEventListener(
        "wheel",
        (e) => {
            if (e.ctrlKey) return;
            e.stopPropagation();
        },
        { passive: true }
    );
}

function attachOutsideBlur(containerEl) {
    const handler = (e) => {
        if (!containerEl.contains(e.target) && containerEl.contains(document.activeElement)) {
            document.activeElement?.blur?.();
        }
    };
    window.addEventListener("pointerdown", handler, true);
}

/* ============================================================================
 * 1. WFA CHARACTER LORA COCKPIT (5-Slot C1–C5 Manager via WFA_PIPE)
 * ========================================================================== */
function defaultCharSlots() {
    return [0, 1, 2, 3, 4].map((i) => ({
        ui_enable: i === 0,
        override: false,
        lora_name: "None",
        str_solo: 0.9,
        str_multi: 0.5,
    }));
}

function parseCharState(raw) {
    const slots = defaultCharSlots();
    let mode = "auto";
    if (!raw) return { mode, slots };
    try {
        const obj = JSON.parse(raw);
        if (obj?.mode && ["auto", "batch", "ui"].includes(String(obj.mode).toLowerCase())) {
            mode = String(obj.mode).toLowerCase();
        }
        if (Array.isArray(obj?.slots)) {
            for (let i = 0; i < Math.min(5, obj.slots.length); i++) {
                const s = obj.slots[i];
                if (s && typeof s === "object") {
                    slots[i].ui_enable = Boolean(s.ui_enable);
                    slots[i].override = Boolean(s.override);
                    slots[i].lora_name = String(s.lora_name || "None");
                    const solo = Number(s.str_solo);
                    const multi = Number(s.str_multi);
                    if (!Number.isNaN(solo)) slots[i].str_solo = solo;
                    if (!Number.isNaN(multi)) slots[i].str_multi = multi;
                }
            }
        }
    } catch (_) {}
    return { mode, slots };
}

function buildCharCockpitUI(node, masterTa) {
    if (!masterTa || masterTa.dataset.wfaCkEnhanced === "true") return;
    const host = masterTa.parentElement;
    if (!host) return;

    masterTa.dataset.wfaCkEnhanced = "true";
    ensureStyles();
    masterTa.classList.add("wfa-ck-hidden-ta");

    const stateWidget = node.widgets?.find((x) => x.name === "cockpit_state");
    if (stateWidget) {
        stateWidget.options = { ...(stateWidget.options || {}), getMinHeight: () => 120 };
    }

    const card = document.createElement("div");
    card.className = "wfa-ck-card";

    const header = document.createElement("div");
    header.className = "wfa-ck-header";

    const badge = document.createElement("div");
    badge.className = "wfa-ck-badge";

    const topBtns = document.createElement("div");
    topBtns.className = "wfa-ck-row-btns";

    const btnMode = document.createElement("button");
    btnMode.type = "button";
    btnMode.className = "wfa-ck-mini-btn wfa-active";

    const btnAllOff = document.createElement("button");
    btnAllOff.type = "button";
    btnAllOff.className = "wfa-ck-mini-btn";
    btnAllOff.textContent = "All Off";
    btnAllOff.title = "Turn off all UI C1–C5 switches";

    const btnClrOvr = document.createElement("button");
    btnClrOvr.type = "button";
    btnClrOvr.className = "wfa-ck-mini-btn";
    btnClrOvr.textContent = "Clr Ovr";
    btnClrOvr.title = "Clear all row Override locks";

    const btnRefresh = document.createElement("button");
    btnRefresh.type = "button";
    btnRefresh.className = "wfa-ck-mini-btn";
    btnRefresh.textContent = "↻";
    btnRefresh.title = "Refresh LoRAs from disk";

    topBtns.append(btnMode, btnAllOff, btnClrOvr, btnRefresh);
    header.append(badge, topBtns);

    const body = document.createElement("div");
    body.className = "wfa-ck-body";
    attachWheelGuard(body);

    card.append(header, body);
    host.insertBefore(card, masterTa);
    attachOutsideBlur(card);

    let state = parseCharState(masterTa.value);
    let lastLiveFeedback = null;
    let isInternalSync = false;
    let activePopover = null;

    function persist() {
        isInternalSync = true;
        const json = JSON.stringify(state);
        masterTa.value = json;
        if (stateWidget) {
            stateWidget.value = json;
            stateWidget.callback?.(json);
        }
        isInternalSync = false;
        node.setDirtyCanvas?.(true, true);
    }

    function closePopover() {
        if (activePopover) {
            activePopover.remove();
            activePopover = null;
        }
    }

    function openLoraPopover(slotIdx) {
        closePopover();
        const pop = document.createElement("div");
        pop.className = "wfa-lora-popover";

        const top = document.createElement("div");
        top.className = "wfa-lora-pop-top";

        const searchIn = document.createElement("input");
        searchIn.type = "text";
        searchIn.className = "wfa-ck-input";
        searchIn.style.flex = "1";
        searchIn.placeholder = `Search LoRA for C${slotIdx + 1}...`;

        const closeBtn = document.createElement("button");
        closeBtn.type = "button";
        closeBtn.className = "wfa-ck-mini-btn";
        closeBtn.textContent = "✕";
        closeBtn.addEventListener("mousedown", (e) => {
            e.preventDefault();
            e.stopPropagation();
            closePopover();
        });

        top.append(searchIn, closeBtn);

        const listEl = document.createElement("div");
        listEl.className = "wfa-lora-pop-list";
        attachWheelGuard(listEl);

        pop.append(top, listEl);
        card.appendChild(pop);
        activePopover = pop;

        let filtered = [];
        let selIndex = 0;

        function selectValue(val) {
            state.slots[slotIdx].lora_name = val;
            lastLiveFeedback = null;
            persist();
            closePopover();
            renderRows();
        }

        function renderFiltered() {
            const terms = searchIn.value
                .trim()
                .toLowerCase()
                .split(/\s+/)
                .filter(Boolean);
            const all = sharedCockpitMeta.loras || ["None"];
            filtered = all.filter((item) => {
                if (!terms.length) return true;
                const low = item.toLowerCase();
                return terms.every((t) => low.includes(t));
            });
            selIndex = 0;
            listEl.innerHTML = "";
            const cap = Math.min(filtered.length, 200);
            for (let k = 0; k < cap; k++) {
                const name = filtered[k];
                const el = document.createElement("div");
                el.className = "wfa-lora-pop-item" + (k === selIndex ? " wfa-sel" : "");
                el.textContent = name === "None" ? "— None —" : name.replace(/\\/g, " / ");
                el.title = name;
                el.addEventListener("mousedown", (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    selectValue(name);
                });
                listEl.appendChild(el);
            }
        }

        searchIn.addEventListener("input", renderFiltered);
        searchIn.addEventListener("keydown", (e) => {
            e.stopPropagation();
            if (e.key === "Escape") {
                e.preventDefault();
                closePopover();
            } else if (e.key === "ArrowDown") {
                e.preventDefault();
                if (filtered.length) {
                    selIndex = Math.min(Math.min(filtered.length, 200) - 1, selIndex + 1);
                    Array.from(listEl.children).forEach((c, idx) => c.classList.toggle("wfa-sel", idx === selIndex));
                    listEl.children[selIndex]?.scrollIntoView({ block: "nearest" });
                }
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                if (filtered.length) {
                    selIndex = Math.max(0, selIndex - 1);
                    Array.from(listEl.children).forEach((c, idx) => c.classList.toggle("wfa-sel", idx === selIndex));
                    listEl.children[selIndex]?.scrollIntoView({ block: "nearest" });
                }
            } else if (e.key === "Enter") {
                e.preventDefault();
                if (filtered[selIndex] !== undefined) {
                    selectValue(filtered[selIndex]);
                }
            }
        });

        renderFiltered();
        setTimeout(() => searchIn.focus(), 10);
    }

    function computeLocalPreviewTags() {
        if (lastLiveFeedback && typeof lastLiveFeedback.lora_tags === "string") {
            return lastLiveFeedback.lora_tags;
        }
        const activeIdxs = state.slots
            .map((s, idx) => (s.ui_enable ? idx : -1))
            .filter((idx) => idx >= 0);
        const multi = activeIdxs.length >= 2;
        const tags = [];
        for (const idx of activeIdxs) {
            const s = state.slots[idx];
            if (s.lora_name && s.lora_name !== "None") {
                const wt = multi ? s.str_multi : s.str_solo;
                if (Math.abs(wt) > 1e-6) {
                    tags.push(`<lora:${loraStem(s.lora_name)}:${formatLoraWt(wt)}>`);
                }
            }
        }
        return tags.join(", ");
    }

    function updateHeaderAndFooter(footerEl) {
        if (state.mode === "auto") {
            btnMode.textContent = "⚡ Auto";
            btnMode.className = "wfa-ck-mini-btn wfa-active";
            btnMode.title = "Mode: Auto (follows Generation Deck 'Prompts: File / UI' switch in WFA_PIPE). Click to cycle Auto → Batch → UI.";
        } else if (state.mode === "batch") {
            btnMode.textContent = "⚡ Batch";
            btnMode.className = "wfa-ck-mini-btn wfa-active";
            btnMode.title = "Mode: Forced Batch Enable (uses c1..c5 batch wires unless Ovr is active). Click to cycle.";
        } else {
            btnMode.textContent = "✎ UI";
            btnMode.className = "wfa-ck-mini-btn wfa-mode-blue";
            btnMode.title = "Mode: Forced UI Enable (uses [✓ C1..C5] toggles on this card). Click to cycle.";
        }

        if (lastLiveFeedback && lastLiveFeedback.summary) {
            badge.textContent = `● ${lastLiveFeedback.summary}`;
            badge.classList.toggle("wfa-muted", lastLiveFeedback.summary.startsWith("0"));
        } else {
            const uiOn = state.slots
                .map((s, idx) => (s.ui_enable ? idx : -1))
                .filter((idx) => idx >= 0);
            const multi = uiOn.length >= 2;
            if (!uiOn.length) {
                badge.textContent = "○ UI: 0 Active";
                badge.classList.add("wfa-muted");
            } else {
                badge.classList.remove("wfa-muted");
                const desc = uiOn
                    .map((i) => {
                        const st = multi ? state.slots[i].str_multi : state.slots[i].str_solo;
                        return `C${i + 1}:${Number(st).toFixed(2)}`;
                    })
                    .join(", ");
                badge.textContent = `● ${multi ? "Multi" : "Solo"} • ${desc}`;
            }
        }

        if (footerEl) {
            const previewTags = computeLocalPreviewTags();
            if (previewTags) {
                footerEl.innerHTML = `<span class="wfa-hl-lora">${escapeHtml(previewTags)}</span>`;
            } else {
                footerEl.innerHTML = `<span class="wfa-ck-muted">No active character LoRA tags selected.</span>`;
            }
        }
    }

    let footerBox = null;

    function renderRows() {
        body.innerHTML = "";
        for (let i = 0; i < 5; i++) {
            const slot = state.slots[i];
            const liveActive = lastLiveFeedback?.resolved_active?.[i] ?? slot.ui_enable;

            const row = document.createElement("div");
            row.className =
                `wfa-char-row ${i % 2 === 0 ? "wfa-even" : "wfa-odd"}` +
                (liveActive ? " wfa-live-on" : "");

            const btnEnable = document.createElement("button");
            btnEnable.type = "button";
            btnEnable.className = "wfa-char-toggle" + (slot.ui_enable ? " wfa-on" : "");
            btnEnable.textContent = `${slot.ui_enable ? "✓" : "○"} C${i + 1}`;
            btnEnable.title = `Toggle UI Enable for C${i + 1}`;
            btnEnable.addEventListener("mousedown", (e) => {
                e.preventDefault();
                e.stopPropagation();
                slot.ui_enable = !slot.ui_enable;
                lastLiveFeedback = null;
                persist();
                renderRows();
            });

            const btnOvr = document.createElement("button");
            btnOvr.type = "button";
            btnOvr.className = "wfa-char-ovr" + (slot.override ? " wfa-on" : "");
            btnOvr.textContent = "Ovr";
            btnOvr.title = `Override Batch for C${i + 1}: When highlighted, forces C${i + 1} to use this UI switch even during Batch File runs.`;
            btnOvr.addEventListener("mousedown", (e) => {
                e.preventDefault();
                e.stopPropagation();
                slot.override = !slot.override;
                lastLiveFeedback = null;
                persist();
                renderRows();
            });

            const pickWrap = document.createElement("div");
            pickWrap.className = "wfa-lora-pick-wrap";

            const isNone = !slot.lora_name || slot.lora_name === "None";
            const pickBtn = document.createElement("button");
            pickBtn.type = "button";
            pickBtn.className = "wfa-lora-pick-btn" + (isNone ? " wfa-none" : "");
            pickBtn.textContent = formatShortLoraLabel(slot.lora_name);
            pickBtn.title = isNone ? `Click to pick C${i + 1} LoRA` : `${slot.lora_name}\n(Click to change)`;
            pickBtn.addEventListener("mousedown", (e) => {
                e.preventDefault();
                e.stopPropagation();
                openLoraPopover(i);
            });

            pickWrap.appendChild(pickBtn);
            if (!isNone) {
                const clrBtn = document.createElement("button");
                clrBtn.type = "button";
                clrBtn.className = "wfa-lora-clear-btn";
                clrBtn.textContent = "✕";
                clrBtn.title = "Clear LoRA (set to None)";
                clrBtn.addEventListener("mousedown", (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    slot.lora_name = "None";
                    lastLiveFeedback = null;
                    persist();
                    renderRows();
                });
                pickWrap.appendChild(clrBtn);
            }

            const soloGrp = document.createElement("div");
            soloGrp.className = "wfa-str-group";
            const soloLbl = document.createElement("span");
            soloLbl.className = "wfa-str-lbl";
            soloLbl.textContent = "S";
            soloLbl.title = "Solo Strength (used when 1 character is active)";
            const soloIn = document.createElement("input");
            soloIn.type = "number";
            soloIn.step = "0.02";
            soloIn.className = "wfa-ck-num wfa-str-num";
            soloIn.value = Number(slot.str_solo).toFixed(2);
            soloIn.title = `C${i + 1} Solo Strength`;
            soloIn.addEventListener("change", () => {
                const v = parseFloat(soloIn.value);
                slot.str_solo = Number.isNaN(v) ? 0.9 : Math.round(v * 100) / 100;
                soloIn.value = slot.str_solo.toFixed(2);
                lastLiveFeedback = null;
                persist();
                updateHeaderAndFooter(footerBox);
            });
            soloGrp.append(soloLbl, soloIn);

            const multiGrp = document.createElement("div");
            multiGrp.className = "wfa-str-group";
            const multiLbl = document.createElement("span");
            multiLbl.className = "wfa-str-lbl";
            multiLbl.textContent = "M";
            multiLbl.title = "Multi / Duo Strength (used when 2+ characters are active)";
            const multiIn = document.createElement("input");
            multiIn.type = "number";
            multiIn.step = "0.02";
            multiIn.className = "wfa-ck-num wfa-str-num";
            multiIn.value = Number(slot.str_multi).toFixed(2);
            multiIn.title = `C${i + 1} Multi/Duo Strength`;
            multiIn.addEventListener("change", () => {
                const v = parseFloat(multiIn.value);
                slot.str_multi = Number.isNaN(v) ? 0.5 : Math.round(v * 100) / 100;
                multiIn.value = slot.str_multi.toFixed(2);
                lastLiveFeedback = null;
                persist();
                updateHeaderAndFooter(footerBox);
            });
            multiGrp.append(multiLbl, multiIn);

            row.append(btnEnable, btnOvr, pickWrap, soloGrp, multiGrp);
            body.appendChild(row);
        }

        footerBox = document.createElement("div");
        footerBox.className = "wfa-char-footer";
        attachWheelGuard(footerBox);
        body.appendChild(footerBox);

        updateHeaderAndFooter(footerBox);
    }

    btnMode.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const order = ["auto", "batch", "ui"];
        const nextIdx = (order.indexOf(state.mode) + 1) % order.length;
        state.mode = order[nextIdx];
        lastLiveFeedback = null;
        persist();
        updateHeaderAndFooter(footerBox);
    });

    btnAllOff.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        for (const s of state.slots) s.ui_enable = false;
        lastLiveFeedback = null;
        persist();
        renderRows();
    });

    btnClrOvr.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        for (const s of state.slots) s.override = false;
        lastLiveFeedback = null;
        persist();
        renderRows();
    });

    btnRefresh.addEventListener("mousedown", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        await fetchCockpitMeta(true);
        renderRows();
    });

    const protoDesc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    if (protoDesc?.get && protoDesc?.set) {
        Object.defineProperty(masterTa, "value", {
            get() {
                return protoDesc.get.call(this);
            },
            set(val) {
                protoDesc.set.call(this, val);
                if (!isInternalSync) {
                    state = parseCharState(val);
                    renderRows();
                }
            },
            configurable: true,
        });
    }

    node._wfaApplyCharFeedback = (detail) => {
        lastLiveFeedback = detail;
        renderRows();
    };

    if (!masterTa.value) persist();
    fetchCockpitMeta(false).then(() => renderRows());
    renderRows();
}

/* ============================================================================
 * 2. WFA GENERATION DECK (Unified Control Panel + 2D Aspect Ratio Pad)
 * ========================================================================== */
const RES_PRESETS = [
    [832, 1216],
    [896, 1152],
    [1024, 1024],
    [1152, 896],
    [1216, 832],
    [768, 1344],
];

function defaultDeckState() {
    const samplers = sharedCockpitMeta.samplers;
    const scheds = sharedCockpitMeta.schedulers;
    return {
        package_name: "Output_Set",
        use_batch: true,
        file_batch: false,
        batch_size: 1,
        width: 896,
        height: 1152,
        snap: 16,
        pad_max: 1536,
        seed: 4260,
        seed_mode: "increment",
        steps: 28,
        cfg: 3.5,
        sampler_name: samplers.includes("er_sde") ? "er_sde" : samplers[0] || "euler",
        scheduler: scheds.includes("simple") ? "simple" : scheds[0] || "normal",
        refiner_pct: 0.3,
        refiner_scale: 1.3,
        toggles: [
            { label: "Color Match", value: false },
            { label: "2nd Refiner", value: true },
            { label: "Upscale 2x", value: true },
            { label: "3rd Refiner", value: false },
        ],
    };
}

function parseDeckState(raw) {
    const st = defaultDeckState();
    if (!raw) return st;
    try {
        const p = JSON.parse(raw);
        if (!p || typeof p !== "object") return st;
        if (p.package_name !== undefined) st.package_name = String(p.package_name);
        if (p.use_batch !== undefined) st.use_batch = Boolean(p.use_batch);
        if (p.file_batch !== undefined) st.file_batch = Boolean(p.file_batch);
        if (p.batch_size !== undefined) st.batch_size = Math.max(1, parseInt(p.batch_size, 10) || 1);
        if (p.width !== undefined) st.width = Math.max(64, parseInt(p.width, 10) || 896);
        if (p.height !== undefined) st.height = Math.max(64, parseInt(p.height, 10) || 1152);
        if (p.snap !== undefined) st.snap = Math.max(1, parseInt(p.snap, 10) || 16);
        if (p.pad_max !== undefined) st.pad_max = Math.max(512, parseInt(p.pad_max, 10) || 1536);
        if (p.seed !== undefined) st.seed = Math.max(0, parseInt(p.seed, 10) || 0);
        if (p.seed_mode) st.seed_mode = String(p.seed_mode);
        if (p.steps !== undefined) st.steps = Math.max(1, parseInt(p.steps, 10) || 28);
        if (p.cfg !== undefined && !Number.isNaN(Number(p.cfg))) st.cfg = Number(p.cfg);
        if (p.sampler_name) st.sampler_name = String(p.sampler_name);
        if (p.scheduler) st.scheduler = String(p.scheduler);
        if (p.refiner_pct !== undefined && !Number.isNaN(Number(p.refiner_pct))) st.refiner_pct = Number(p.refiner_pct);
        if (p.refiner_scale !== undefined && !Number.isNaN(Number(p.refiner_scale))) st.refiner_scale = Number(p.refiner_scale);
        if (Array.isArray(p.toggles)) {
            for (let i = 0; i < Math.min(4, p.toggles.length); i++) {
                if (p.toggles[i] && typeof p.toggles[i] === "object") {
                    if (p.toggles[i].label) st.toggles[i].label = String(p.toggles[i].label);
                    if (p.toggles[i].value !== undefined) st.toggles[i].value = Boolean(p.toggles[i].value);
                }
            }
        }
    } catch (_) {}
    return st;
}

function snapValue(val, snap) {
    const v = Math.max(64, Math.round(Number(val) || 64));
    const s = Math.max(1, Math.round(Number(snap) || 1));
    return s <= 1 ? v : Math.max(s, Math.round(v / s) * s);
}

function buildGenerationDeckUI(node, masterTa) {
    if (!masterTa || masterTa.dataset.wfaCkEnhanced === "true") return;
    const host = masterTa.parentElement;
    if (!host) return;

    masterTa.dataset.wfaCkEnhanced = "true";
    ensureStyles();
    masterTa.classList.add("wfa-ck-hidden-ta");

    const stateWidget = node.widgets?.find((w) => w.name === "deck_state");
    if (stateWidget) {
        stateWidget.options = { ...(stateWidget.options || {}), getMinHeight: () => 120 };
    }

    const card = document.createElement("div");
    card.className = "wfa-ck-card";

    const header = document.createElement("div");
    header.className = "wfa-ck-header";

    const badge = document.createElement("div");
    badge.className = "wfa-ck-badge";

    const rollTopBtn = document.createElement("button");
    rollTopBtn.type = "button";
    rollTopBtn.className = "wfa-ck-mini-btn";
    rollTopBtn.textContent = "🎲 New Seed";
    rollTopBtn.title = "Generate a fresh random seed now";

    header.append(badge, rollTopBtn);

    const body = document.createElement("div");
    body.className = "wfa-ck-body";
    attachWheelGuard(body);

    card.append(header, body);
    host.insertBefore(card, masterTa);
    attachOutsideBlur(card);

    let st = parseDeckState(masterTa.value);
    let isInternalSync = false;

    function persist() {
        isInternalSync = true;
        const json = JSON.stringify(st);
        masterTa.value = json;
        if (stateWidget) {
            stateWidget.value = json;
            stateWidget.callback?.(json);
        }
        isInternalSync = false;
        updateBadge();
        node.setDirtyCanvas?.(true, true);
    }

    function updateBadge() {
        const modeTxt = st.use_batch ? "Batch File" : "Single UI";
        badge.textContent = `● ${modeTxt} • ${st.width}×${st.height} • B:${st.batch_size}`;
    }

    function advanceSeedAfterQueue() {
        if (st.seed_mode === "increment") {
            st.seed = Math.max(0, (Number(st.seed) || 0) + 1);
            persist();
            renderDeck();
        } else if (st.seed_mode === "decrement") {
            st.seed = Math.max(0, (Number(st.seed) || 0) - 1);
            persist();
            renderDeck();
        } else if (st.seed_mode === "randomize") {
            st.seed = Math.floor(Math.random() * 2147483647);
            persist();
            renderDeck();
        }
    }

    if (stateWidget) {
        stateWidget.afterQueued = () => advanceSeedAfterQueue();
    }

    rollTopBtn.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        st.seed = Math.floor(Math.random() * 2147483647);
        persist();
        renderDeck();
    });

    function renderDeck() {
        body.innerHTML = "";

        /* Section 1: Package & Batch Switches */
        const sec1 = document.createElement("div");
        sec1.className = "wfa-deck-sec";

        const pkgLine = document.createElement("div");
        pkgLine.className = "wfa-deck-line";
        const pkgLbl = document.createElement("span");
        pkgLbl.className = "wfa-deck-lbl";
        pkgLbl.textContent = "PKG";
        pkgLbl.title = "Package / Folder / Subject Name";
        const pkgIn = document.createElement("input");
        pkgIn.type = "text";
        pkgIn.className = "wfa-ck-input";
        pkgIn.style.flex = "1";
        pkgIn.value = st.package_name;
        pkgIn.placeholder = "Package / Folder Name...";
        pkgIn.addEventListener("input", () => {
            st.package_name = pkgIn.value;
            persist();
        });
        pkgLine.append(pkgLbl, pkgIn);

        const modeLine = document.createElement("div");
        modeLine.className = "wfa-deck-line";

        const btnUseBatch = document.createElement("button");
        btnUseBatch.type = "button";
        btnUseBatch.className = "wfa-deck-pill " + (st.use_batch ? "wfa-on" : "wfa-alt-blue");
        btnUseBatch.textContent = st.use_batch ? "⚡ Prompts: File" : "✎ Prompts: UI";
        btnUseBatch.title = "Toggle between Batch File prompts/settings and Single UI inputs";
        btnUseBatch.addEventListener("mousedown", (e) => {
            e.preventDefault();
            e.stopPropagation();
            st.use_batch = !st.use_batch;
            persist();
            renderDeck();
        });

        const btnFileBatch = document.createElement("button");
        btnFileBatch.type = "button";
        btnFileBatch.className = "wfa-deck-pill" + (st.file_batch ? " wfa-on" : "");
        btnFileBatch.textContent = st.file_batch ? "File B-Size" : "Manual B-Size";
        btnFileBatch.title = "Toggle whether batch_size comes from Batch File or Manual Batch input";
        btnFileBatch.addEventListener("mousedown", (e) => {
            e.preventDefault();
            e.stopPropagation();
            st.file_batch = !st.file_batch;
            persist();
            renderDeck();
        });

        const bField = document.createElement("div");
        bField.style.display = "flex";
        bField.style.alignItems = "center";
        bField.style.gap = "3px";
        const bLbl = document.createElement("span");
        bLbl.className = "wfa-deck-lbl";
        bLbl.textContent = "B:";
        const bIn = document.createElement("input");
        bIn.type = "number";
        bIn.min = "1";
        bIn.max = "64";
        bIn.className = "wfa-ck-num";
        bIn.style.width = "42px";
        bIn.value = st.batch_size;
        bIn.addEventListener("change", () => {
            st.batch_size = Math.max(1, parseInt(bIn.value, 10) || 1);
            bIn.value = st.batch_size;
            persist();
        });
        bField.append(bLbl, bIn);

        modeLine.append(btnUseBatch, btnFileBatch, bField);
        sec1.append(pkgLine, modeLine);

        /* Section 2: Interactive 2D Aspect Ratio & Resolution Pad + Controls */
        const sec2 = document.createElement("div");
        sec2.className = "wfa-deck-sec";

        const wrap2d = document.createElement("div");
        wrap2d.className = "wfa-res-2d-wrap";

        const PAD_CSS = 114;
        const MARGIN = 8;
        const PLOT = PAD_CSS - MARGIN * 2;
        const dpr = Math.max(2, window.devicePixelRatio || 1);

        const padCanvas = document.createElement("canvas");
        padCanvas.className = "wfa-res-pad-canvas";
        padCanvas.width = Math.round(PAD_CSS * dpr);
        padCanvas.height = Math.round(PAD_CSS * dpr);
        padCanvas.title =
            "2D Resolution & Aspect Ratio Pad\n• Drag anywhere to set Width × Height\n• Shift + Drag: Lock 1:1 Square\n• Alt + Drag: Scale keeping current Aspect Ratio";

        const rightCol = document.createElement("div");
        rightCol.className = "wfa-res-right-col";

        // Right Row 1: W ⇄ H
        const resLine = document.createElement("div");
        resLine.className = "wfa-deck-line";

        const wLbl = document.createElement("span");
        wLbl.className = "wfa-deck-lbl";
        wLbl.textContent = "W";
        const wIn = document.createElement("input");
        wIn.type = "number";
        wIn.step = String(st.snap || 16);
        wIn.className = "wfa-ck-num";
        wIn.style.flex = "1";
        wIn.style.minWidth = "46px";
        wIn.value = st.width;

        const swapBtn = document.createElement("button");
        swapBtn.type = "button";
        swapBtn.className = "wfa-ck-mini-btn";
        swapBtn.textContent = "⇄";
        swapBtn.title = "Swap Width ↔ Height (Portrait / Landscape)";

        const hLbl = document.createElement("span");
        hLbl.className = "wfa-deck-lbl";
        hLbl.textContent = "H";
        const hIn = document.createElement("input");
        hIn.type = "number";
        hIn.step = String(st.snap || 16);
        hIn.className = "wfa-ck-num";
        hIn.style.flex = "1";
        hIn.style.minWidth = "46px";
        hIn.value = st.height;

        resLine.append(wLbl, wIn, swapBtn, hLbl, hIn);

        // Right Row 2: Snap + Pad Max
        const snapMaxLine = document.createElement("div");
        snapMaxLine.className = "wfa-deck-line";

        const snapField = document.createElement("div");
        snapField.className = "wfa-deck-field";
        const snapLbl = document.createElement("span");
        snapLbl.className = "wfa-deck-lbl";
        snapLbl.textContent = "Snap";
        const snapSel = document.createElement("select");
        snapSel.className = "wfa-ck-select";
        snapSel.style.width = "100%";
        snapSel.title = "Dimension alignment multiple (÷16 or ÷32 prevents patch-padding edge blur)";
        for (const d of [1, 8, 16, 32, 64]) {
            const opt = document.createElement("option");
            opt.value = String(d);
            opt.textContent = `÷${d}`;
            if (st.snap === d) opt.selected = true;
            snapSel.appendChild(opt);
        }
        snapField.append(snapLbl, snapSel);

        const maxField = document.createElement("div");
        maxField.className = "wfa-deck-field";
        const maxLbl = document.createElement("span");
        maxLbl.className = "wfa-deck-lbl";
        maxLbl.textContent = "Max";
        const maxSel = document.createElement("select");
        maxSel.className = "wfa-ck-select";
        maxSel.style.width = "100%";
        maxSel.title = "Maximum resolution ceiling of the 2D pad";
        for (const m of [1536, 2048, 2560, 3072]) {
            const opt = document.createElement("option");
            opt.value = String(m);
            opt.textContent = String(m);
            if ((st.pad_max || 1536) === m) opt.selected = true;
            maxSel.appendChild(opt);
        }
        maxField.append(maxLbl, maxSel);

        snapMaxLine.append(snapField, maxField);

        // Right Row 3 & 4: 3×2 Preset Chips
        const chipsGrid = document.createElement("div");
        chipsGrid.className = "wfa-res-chips";
        const chipEntries = [];
        for (const [pw, ph] of RES_PRESETS) {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "wfa-res-chip";
            chip.textContent = pw === ph ? `${pw}²` : `${pw}×${ph}`;
            chip.addEventListener("mousedown", (e) => {
                e.preventDefault();
                e.stopPropagation();
                st.width = snapValue(pw, st.snap);
                st.height = snapValue(ph, st.snap);
                syncResControls();
            });
            chipsGrid.appendChild(chip);
            chipEntries.push({ btn: chip, pw, ph });
        }

        rightCol.append(resLine, snapMaxLine, chipsGrid);
        wrap2d.append(padCanvas, rightCol);
        sec2.appendChild(wrap2d);

        let isDraggingPad = false;
        let dragLockedRatio = 1;

        function drawPad() {
            const ctx = padCanvas.getContext("2d");
            if (!ctx) return;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, PAD_CSS, PAD_CSS);

            ctx.fillStyle = "#111115";
            ctx.fillRect(0, 0, PAD_CSS, PAD_CSS);

            const effMax = Math.max(st.pad_max || 1536, st.width, st.height);
            const gridStep = effMax > 2048 ? 256 : 128;

            // Dotted grid
            for (let gx = 0; gx <= effMax; gx += gridStep) {
                for (let gy = 0; gy <= effMax; gy += gridStep) {
                    const px = MARGIN + (gx / effMax) * PLOT;
                    const py = MARGIN + (gy / effMax) * PLOT;
                    const isMajor = gx % 512 === 0 && gy % 512 === 0;
                    ctx.fillStyle = isMajor ? "rgba(255, 255, 255, 0.30)" : "rgba(255, 255, 255, 0.11)";
                    ctx.fillRect(px - 0.6, py - 0.6, isMajor ? 1.5 : 1.1, isMajor ? 1.5 : 1.1);
                }
            }

            // 1:1 Square diagonal dashed guide
            ctx.save();
            ctx.strokeStyle = "rgba(255, 255, 255, 0.12)";
            ctx.lineWidth = 1;
            ctx.setLineDash([3, 3]);
            ctx.beginPath();
            ctx.moveTo(MARGIN, MARGIN);
            ctx.lineTo(MARGIN + PLOT, MARGIN + PLOT);
            ctx.stroke();
            ctx.restore();

            // Active W × H proportional rectangle from top-left origin
            const rw = Math.max(2, Math.min(PLOT, (st.width / effMax) * PLOT));
            const rh = Math.max(2, Math.min(PLOT, (st.height / effMax) * PLOT));
            const tx = MARGIN + rw;
            const ty = MARGIN + rh;

            ctx.fillStyle = "rgba(74, 222, 128, 0.15)";
            ctx.fillRect(MARGIN, MARGIN, rw, rh);

            ctx.strokeStyle = isDraggingPad ? "#4ade80" : "rgba(74, 222, 128, 0.80)";
            ctx.lineWidth = 1.25;
            ctx.strokeRect(MARGIN, MARGIN, rw, rh);

            // Origin dot (top-left, like mxSlider2D)
            ctx.beginPath();
            ctx.arc(MARGIN, MARGIN, 2.3, 0, Math.PI * 2);
            ctx.fillStyle = "#4ade80";
            ctx.fill();

            // Handle thumb at (tx, ty)
            if (isDraggingPad) {
                ctx.beginPath();
                ctx.arc(tx, ty, 8.5, 0, Math.PI * 2);
                ctx.fillStyle = "rgba(74, 222, 128, 0.25)";
                ctx.fill();
            }
            ctx.beginPath();
            ctx.arc(tx, ty, 4.8, 0, Math.PI * 2);
            ctx.fillStyle = "#141418";
            ctx.fill();
            ctx.lineWidth = 2;
            ctx.strokeStyle = isDraggingPad ? "#ffffff" : "#4ade80";
            ctx.stroke();

            // Bottom-left Aspect Ratio & Megapixels pill overlay
            const lbl = formatAspectBadge(st.width, st.height);
            ctx.font = '600 8.5px "JetBrains Mono", Consolas, monospace';
            const tw = ctx.measureText(lbl).width;
            const bx = 4;
            const by = PAD_CSS - 15;
            ctx.fillStyle = "rgba(14, 14, 18, 0.84)";
            ctx.fillRect(bx, by, tw + 6, 12);
            ctx.fillStyle = "#d4d4d8";
            ctx.fillText(lbl, bx + 3, by + 9);
        }

        function syncResControls() {
            wIn.value = st.width;
            hIn.value = st.height;
            wIn.step = String(st.snap || 16);
            hIn.step = String(st.snap || 16);
            for (const item of chipEntries) {
                item.btn.classList.toggle("wfa-match", st.width === item.pw && st.height === item.ph);
            }
            drawPad();
            persist();
        }

        function applyPadPointer(e) {
            const rect = padCanvas.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            const localX = ((e.clientX - rect.left) / rect.width) * PAD_CSS;
            const localY = ((e.clientY - rect.top) / rect.height) * PAD_CSS;
            const normX = Math.max(0, Math.min(1, (localX - MARGIN) / PLOT));
            const normY = Math.max(0, Math.min(1, (localY - MARGIN) / PLOT));

            const effMax = Math.max(st.pad_max || 1536, 512);
            let rawW = Math.max(256, normX * effMax);
            let rawH = Math.max(256, normY * effMax);

            if (e.shiftKey) {
                const sq = (rawW + rawH) * 0.5;
                rawW = sq;
                rawH = sq;
            } else if (e.altKey && dragLockedRatio > 0) {
                if (dragLockedRatio >= 1) {
                    rawH = rawW / dragLockedRatio;
                } else {
                    rawW = rawH * dragLockedRatio;
                }
                rawW = Math.max(256, Math.min(effMax, rawW));
                rawH = Math.max(256, Math.min(effMax, rawH));
            }

            st.width = snapValue(rawW, st.snap);
            st.height = snapValue(rawH, st.snap);
            syncResControls();
        }

        padCanvas.addEventListener("mousedown", (e) => {
            e.stopPropagation();
        });

        padCanvas.addEventListener("pointerdown", (e) => {
            if (e.button !== 0) return;
            e.preventDefault();
            e.stopPropagation();
            isDraggingPad = true;
            dragLockedRatio = st.width / Math.max(1, st.height);
            padCanvas.classList.add("wfa-dragging");
            try {
                padCanvas.setPointerCapture(e.pointerId);
            } catch (_) {}
            applyPadPointer(e);
        });

        padCanvas.addEventListener("pointermove", (e) => {
            if (!isDraggingPad) return;
            e.preventDefault();
            e.stopPropagation();
            applyPadPointer(e);
        });

        const endPadDrag = (e) => {
            if (!isDraggingPad) return;
            e.stopPropagation();
            isDraggingPad = false;
            padCanvas.classList.remove("wfa-dragging");
            try {
                padCanvas.releasePointerCapture(e.pointerId);
            } catch (_) {}
            drawPad();
        };
        padCanvas.addEventListener("pointerup", endPadDrag);
        padCanvas.addEventListener("pointercancel", endPadDrag);

        wIn.addEventListener("change", () => {
            st.width = snapValue(wIn.value, st.snap);
            syncResControls();
        });

        hIn.addEventListener("change", () => {
            st.height = snapValue(hIn.value, st.snap);
            syncResControls();
        });

        swapBtn.addEventListener("mousedown", (e) => {
            e.preventDefault();
            e.stopPropagation();
            const tmp = st.width;
            st.width = st.height;
            st.height = tmp;
            syncResControls();
        });

        snapSel.addEventListener("change", () => {
            st.snap = parseInt(snapSel.value, 10) || 16;
            st.width = snapValue(st.width, st.snap);
            st.height = snapValue(st.height, st.snap);
            syncResControls();
        });

        maxSel.addEventListener("change", () => {
            st.pad_max = parseInt(maxSel.value, 10) || 1536;
            syncResControls();
        });

        /* Section 3: Steps, CFG, Sampler, Scheduler, Seed, Refiner */
        const sec3 = document.createElement("div");
        sec3.className = "wfa-deck-sec";

        const scLine = document.createElement("div");
        scLine.className = "wfa-deck-line";

        const stpField = document.createElement("div");
        stpField.className = "wfa-deck-field";
        const stpLbl = document.createElement("span");
        stpLbl.className = "wfa-deck-lbl";
        stpLbl.textContent = "Steps";
        const stpIn = document.createElement("input");
        stpIn.type = "number";
        stpIn.min = "1";
        stpIn.max = "200";
        stpIn.className = "wfa-ck-num";
        stpIn.style.width = "100%";
        stpIn.value = st.steps;
        stpIn.addEventListener("change", () => {
            st.steps = Math.max(1, parseInt(stpIn.value, 10) || 28);
            stpIn.value = st.steps;
            persist();
        });
        stpField.append(stpLbl, stpIn);

        const cfgField = document.createElement("div");
        cfgField.className = "wfa-deck-field";
        const cfgLbl = document.createElement("span");
        cfgLbl.className = "wfa-deck-lbl";
        cfgLbl.textContent = "CFG";
        const cfgIn = document.createElement("input");
        cfgIn.type = "number";
        cfgIn.step = "0.1";
        cfgIn.min = "0";
        cfgIn.className = "wfa-ck-num";
        cfgIn.style.width = "100%";
        cfgIn.value = Number(st.cfg).toFixed(2);
        cfgIn.addEventListener("change", () => {
            const v = parseFloat(cfgIn.value);
            st.cfg = Number.isNaN(v) ? 3.5 : Math.round(v * 100) / 100;
            cfgIn.value = st.cfg.toFixed(2);
            persist();
        });
        cfgField.append(cfgLbl, cfgIn);
        scLine.append(stpField, cfgField);

        const smLine = document.createElement("div");
        smLine.className = "wfa-deck-line";

        const smpField = document.createElement("div");
        smpField.className = "wfa-deck-field";
        const smpLbl = document.createElement("span");
        smpLbl.className = "wfa-deck-lbl";
        smpLbl.textContent = "Smp";
        const smpSel = document.createElement("select");
        smpSel.className = "wfa-ck-select";
        smpSel.style.width = "100%";
        const samplerOpts = sharedCockpitMeta.samplers.includes(st.sampler_name)
            ? sharedCockpitMeta.samplers
            : [st.sampler_name, ...sharedCockpitMeta.samplers];
        for (const sName of samplerOpts) {
            const opt = document.createElement("option");
            opt.value = sName;
            opt.textContent = sName;
            if (sName === st.sampler_name) opt.selected = true;
            smpSel.appendChild(opt);
        }
        smpSel.addEventListener("change", () => {
            st.sampler_name = smpSel.value;
            persist();
        });
        smpField.append(smpLbl, smpSel);

        const schField = document.createElement("div");
        schField.className = "wfa-deck-field";
        const schLbl = document.createElement("span");
        schLbl.className = "wfa-deck-lbl";
        schLbl.textContent = "Sch";
        const schSel = document.createElement("select");
        schSel.className = "wfa-ck-select";
        schSel.style.width = "100%";
        const schedOpts = sharedCockpitMeta.schedulers.includes(st.scheduler)
            ? sharedCockpitMeta.schedulers
            : [st.scheduler, ...sharedCockpitMeta.schedulers];
        for (const scName of schedOpts) {
            const opt = document.createElement("option");
            opt.value = scName;
            opt.textContent = scName;
            if (scName === st.scheduler) opt.selected = true;
            schSel.appendChild(opt);
        }
        schSel.addEventListener("change", () => {
            st.scheduler = schSel.value;
            persist();
        });
        schField.append(schLbl, schSel);
        smLine.append(smpField, schField);

        const sdLine = document.createElement("div");
        sdLine.className = "wfa-deck-line";

        const sdLbl = document.createElement("span");
        sdLbl.className = "wfa-deck-lbl";
        sdLbl.textContent = "Seed";
        const sdIn = document.createElement("input");
        sdIn.type = "number";
        sdIn.min = "0";
        sdIn.className = "wfa-ck-num";
        sdIn.style.flex = "1";
        sdIn.value = st.seed;
        sdIn.addEventListener("change", () => {
            st.seed = Math.max(0, parseInt(sdIn.value, 10) || 0);
            sdIn.value = st.seed;
            persist();
        });

        const sdModeSel = document.createElement("select");
        sdModeSel.className = "wfa-ck-select";
        for (const m of ["increment", "fixed", "randomize", "decrement"]) {
            const opt = document.createElement("option");
            opt.value = m;
            opt.textContent = m;
            if (m === st.seed_mode) opt.selected = true;
            sdModeSel.appendChild(opt);
        }
        sdModeSel.addEventListener("change", () => {
            st.seed_mode = sdModeSel.value;
            persist();
        });

        sdLine.append(sdLbl, sdIn, sdModeSel);

        const rfLine = document.createElement("div");
        rfLine.className = "wfa-deck-line";

        const rpField = document.createElement("div");
        rpField.className = "wfa-deck-field";
        const rpLbl = document.createElement("span");
        rpLbl.className = "wfa-deck-lbl";
        rpLbl.textContent = "Ref %";
        const rpIn = document.createElement("input");
        rpIn.type = "number";
        rpIn.step = "0.05";
        rpIn.min = "0";
        rpIn.max = "1";
        rpIn.className = "wfa-ck-num";
        rpIn.style.width = "100%";
        rpIn.value = Number(st.refiner_pct).toFixed(2);
        rpIn.addEventListener("change", () => {
            const v = parseFloat(rpIn.value);
            st.refiner_pct = Number.isNaN(v) ? 0.3 : Math.round(v * 100) / 100;
            rpIn.value = st.refiner_pct.toFixed(2);
            persist();
        });
        rpField.append(rpLbl, rpIn);

        const rsField = document.createElement("div");
        rsField.className = "wfa-deck-field";
        const rsLbl = document.createElement("span");
        rsLbl.className = "wfa-deck-lbl";
        rsLbl.textContent = "Ref ×";
        const rsIn = document.createElement("input");
        rsIn.type = "number";
        rsIn.step = "0.05";
        rsIn.min = "0.25";
        rsIn.max = "4";
        rsIn.className = "wfa-ck-num";
        rsIn.style.width = "100%";
        rsIn.value = Number(st.refiner_scale).toFixed(2);
        rsIn.addEventListener("change", () => {
            const v = parseFloat(rsIn.value);
            st.refiner_scale = Number.isNaN(v) ? 1.3 : Math.round(v * 100) / 100;
            rsIn.value = st.refiner_scale.toFixed(2);
            persist();
        });
        rsField.append(rsLbl, rsIn);
        rfLine.append(rpField, rsField);

        sec3.append(scLine, smLine, sdLine, rfLine);

        /* Section 4: 4 Customizable Feature Toggles */
        const sec4 = document.createElement("div");
        sec4.className = "wfa-deck-sec";
        sec4.style.borderBottom = "none";

        const tGrid = document.createElement("div");
        tGrid.className = "wfa-toggles-grid";
        st.toggles.forEach((tg, idx) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "wfa-deck-pill" + (tg.value ? " wfa-on" : "");
            btn.textContent = `${tg.value ? "✓" : "○"} ${tg.label}`;
            btn.title = `Output toggle_${idx + 1} (${tg.value ? "true" : "false"})\n• Click: Toggle ON/OFF\n• Shift+Click: Rename toggle label`;
            btn.addEventListener("mousedown", (e) => {
                if (e.button !== 0) return;
                e.preventDefault();
                e.stopPropagation();
                if (e.shiftKey) {
                    const nextName = window.prompt(`Rename toggle_${idx + 1}:`, tg.label);
                    if (nextName && nextName.trim()) {
                        tg.label = nextName.trim();
                        persist();
                        renderDeck();
                    }
                    return;
                }
                tg.value = !tg.value;
                persist();
                renderDeck();
            });
            tGrid.appendChild(btn);
        });
        sec4.appendChild(tGrid);

        body.append(sec1, sec2, sec3, sec4);

        for (const item of chipEntries) {
            item.btn.classList.toggle("wfa-match", st.width === item.pw && st.height === item.ph);
        }
        drawPad();
        updateBadge();
    }

    const protoDesc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    if (protoDesc?.get && protoDesc?.set) {
        Object.defineProperty(masterTa, "value", {
            get() {
                return protoDesc.get.call(this);
            },
            set(val) {
                protoDesc.set.call(this, val);
                if (!isInternalSync) {
                    st = parseDeckState(val);
                    renderDeck();
                }
            },
            configurable: true,
        });
    }

    metaListeners.add(() => renderDeck());
    if (!masterTa.value) persist();
    fetchCockpitMeta(false).then(() => renderDeck());
    renderDeck();
}

/* ============================================================================
 * 3. WFA PROMPT INSPECTOR (Syntax-Highlighted Final Prompt + Token Breakdown)
 * ========================================================================== */
function buildPromptInspectorUI(node, masterTa) {
    if (!masterTa || masterTa.dataset.wfaCkEnhanced === "true") return;
    const host = masterTa.parentElement;
    if (!host) return;

    masterTa.dataset.wfaCkEnhanced = "true";
    ensureStyles();
    masterTa.classList.add("wfa-ck-hidden-ta");

    const cacheWidget = node.widgets?.find((x) => x.name === "inspector_cache");
    if (cacheWidget) {
        cacheWidget.options = { ...(cacheWidget.options || {}), getMinHeight: () => 120 };
    }

    const card = document.createElement("div");
    card.className = "wfa-ck-card";

    const header = document.createElement("div");
    header.className = "wfa-ck-header";

    const badge = document.createElement("div");
    badge.className = "wfa-ck-badge wfa-muted";
    badge.textContent = "Tokens: —";

    const topBtns = document.createElement("div");
    topBtns.className = "wfa-ck-row-btns";

    const tabPrompt = document.createElement("button");
    tabPrompt.type = "button";
    tabPrompt.className = "wfa-ck-mini-btn wfa-active";
    tabPrompt.textContent = "Prompt";

    const tabTokens = document.createElement("button");
    tabTokens.type = "button";
    tabTokens.className = "wfa-ck-mini-btn";
    tabTokens.textContent = "Tokens";

    const btnCopy = document.createElement("button");
    btnCopy.type = "button";
    btnCopy.className = "wfa-ck-mini-btn";
    btnCopy.textContent = "Copy";
    btnCopy.title = "Copy raw compiled prompt to clipboard";

    topBtns.append(tabPrompt, tabTokens, btnCopy);
    header.append(badge, topBtns);

    const body = document.createElement("div");
    body.className = "wfa-ck-body";
    attachWheelGuard(body);

    card.append(header, body);
    host.insertBefore(card, masterTa);

    let activeTab = "prompt";
    let isInternalSync = false;
    let data = {
        text: "",
        token_count: 0,
        chunks: 0,
        is_exact: false,
        lora_count: 0,
        unreplaced_count: 0,
        breakdown: [],
    };

    try {
        if (masterTa.value) {
            const parsed = JSON.parse(masterTa.value);
            if (parsed && typeof parsed === "object") data = { ...data, ...parsed };
        }
    } catch (_) {}

    function persistCache() {
        isInternalSync = true;
        const json = JSON.stringify(data);
        masterTa.value = json;
        if (cacheWidget) cacheWidget.value = json;
        isInternalSync = false;
    }

    function renderInspector() {
        tabPrompt.classList.toggle("wfa-active", activeTab === "prompt");
        tabTokens.classList.toggle("wfa-active", activeTab === "tokens");

        if (!data.text) {
            badge.textContent = "○ Waiting for prompt...";
            badge.className = "wfa-ck-badge wfa-muted";
        } else {
            const prefix = data.is_exact ? "" : "~";
            let txt = `● ${prefix}${data.token_count} tok (${data.chunks}ch)`;
            if (data.lora_count > 0) txt += ` • ${data.lora_count} LoRA`;
            if (data.unreplaced_count > 0) txt += ` • ⚠ ${data.unreplaced_count} /*...*/`;
            badge.textContent = txt;
            badge.className = "wfa-ck-badge" + (data.unreplaced_count > 0 ? " wfa-warn" : "");
        }

        body.innerHTML = "";
        if (activeTab === "prompt") {
            const pBox = document.createElement("div");
            pBox.className = "wfa-insp-prompt";
            pBox.innerHTML = highlightPromptHtml(data.text);
            body.appendChild(pBox);
        } else {
            const rows = data.breakdown || [];
            if (!rows.length) {
                const pBox = document.createElement("div");
                pBox.className = "wfa-insp-prompt";
                pBox.innerHTML = highlightPromptHtml("");
                body.appendChild(pBox);
            } else {
                for (const item of rows) {
                    const r = document.createElement("div");
                    r.className = "wfa-insp-row";

                    const t = document.createElement("div");
                    t.className = "wfa-insp-tag";
                    t.textContent = item.tag;
                    t.title = item.tag;

                    const k = document.createElement("div");
                    k.className =
                        "wfa-insp-tok" +
                        (item.kind === "lora" ? " wfa-lora" : item.kind === "warn" ? " wfa-warn" : "");
                    k.textContent = item.kind === "lora" ? "LoRA" : `${item.tokens}t`;

                    r.append(t, k);
                    body.appendChild(r);
                }
            }
        }
    }

    tabPrompt.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        activeTab = "prompt";
        renderInspector();
    });

    tabTokens.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        activeTab = "tokens";
        renderInspector();
    });

    btnCopy.addEventListener("mousedown", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        try {
            await navigator.clipboard.writeText(data.text || "");
            btnCopy.textContent = "✓ Copied";
            setTimeout(() => {
                btnCopy.textContent = "Copy";
            }, 1100);
        } catch (_) {}
    });

    const protoDesc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    if (protoDesc?.get && protoDesc?.set) {
        Object.defineProperty(masterTa, "value", {
            get() {
                return protoDesc.get.call(this);
            },
            set(val) {
                protoDesc.set.call(this, val);
                if (!isInternalSync && val) {
                    try {
                        const parsed = JSON.parse(val);
                        if (parsed && typeof parsed === "object") {
                            data = { ...data, ...parsed };
                            renderInspector();
                        }
                    } catch (_) {}
                }
            },
            configurable: true,
        });
    }

    node._wfaApplyInspectorPayload = (payload) => {
        data = { ...data, ...payload };
        persistCache();
        renderInspector();
    };

    renderInspector();
}

function tryAttachCockpitNode(node) {
    const cls = node.comfyClass || node.type;
    if (cls === CHAR_COCKPIT_CLASS) {
        const w = node.widgets?.find((x) => x.name === "cockpit_state");
        const ta = w?.inputEl || w?.element;
        if (ta && ta.tagName === "TEXTAREA" && ta.parentElement) {
            buildCharCockpitUI(node, ta);
            return true;
        }
    } else if (cls === GEN_DECK_CLASS) {
        const w = node.widgets?.find((x) => x.name === "deck_state");
        const ta = w?.inputEl || w?.element;
        if (ta && ta.tagName === "TEXTAREA" && ta.parentElement) {
            buildGenerationDeckUI(node, ta);
            return true;
        }
    } else if (cls === INSPECTOR_CLASS) {
        const w = node.widgets?.find((x) => x.name === "inspector_cache");
        const ta = w?.inputEl || w?.element;
        if (ta && ta.tagName === "TEXTAREA" && ta.parentElement) {
            buildPromptInspectorUI(node, ta);
            return true;
        }
    }
    return false;
}

app.registerExtension({
    name: "WFA.CockpitSuite",
    async setup() {
        registerPipeColors();
        fetchCockpitMeta(false);

        api.addEventListener("wfa-char-cockpit-feedback", ({ detail }) => {
            if (!detail || detail.node_id == null) return;
            const node = getNodeById(String(detail.node_id));
            node?._wfaApplyCharFeedback?.(detail);
        });

        api.addEventListener("wfa-prompt-inspector-update", ({ detail }) => {
            if (!detail || detail.node_id == null) return;
            const node = getNodeById(String(detail.node_id));
            node?._wfaApplyInspectorPayload?.(detail);
        });
    },
    async nodeCreated(node) {
        registerPipeColors();
        const cls = node.comfyClass || node.type;
        if (!ALL_COCKPIT_CLASSES.has(cls)) return;
        let attempts = 0;
        const poll = () => {
            if (tryAttachCockpitNode(node) || attempts > 60) return;
            attempts++;
            setTimeout(poll, 50);
        };
        setTimeout(poll, 50);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const isCockpitUI = ALL_COCKPIT_CLASSES.has(nodeData.name);
        const isPipeHelper = nodeData.name === PIPE_IN_CLASS || nodeData.name === PIPE_OUT_CLASS;
        if (!isCockpitUI && !isPipeHelper) return;

        if (isCockpitUI) {
            const origOnNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const res = origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined;
                if (nodeData.name === CHAR_COCKPIT_CLASS) {
                    this.size = [470, 300];
                } else if (nodeData.name === GEN_DECK_CLASS) {
                    this.size = [395, 480];
                } else if (nodeData.name === INSPECTOR_CLASS) {
                    this.size = [440, 300];
                }
                return res;
            };

            const origOnExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (output) {
                const res = origOnExecuted ? origOnExecuted.apply(this, arguments) : undefined;
                if (nodeData.name === INSPECTOR_CLASS && output?.wfa_inspector?.[0]) {
                    this._wfaApplyInspectorPayload?.(output.wfa_inspector[0]);
                }
                return res;
            };

            const origOnDrawForeground = nodeType.prototype.onDrawForeground;
            nodeType.prototype.onDrawForeground = function () {
                if (origOnDrawForeground) origOnDrawForeground.apply(this, arguments);
                tryAttachCockpitNode(this);
            };
        }
    },
});
