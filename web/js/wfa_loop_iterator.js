import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const ITERATOR_CLASS = "WFA_LoopIterator";
const SHUTDOWN_ITERATOR_CLASS = "WFA_LoopIteratorShutdown";
const COUNTER_CLASS = "WFA_PromptCounter";
const SAVE_TXT_CLASS = "WFA_SavePromptTxt";
const ITERATOR_CLASSES = new Set([ITERATOR_CLASS, SHUTDOWN_ITERATOR_CLASS]);
const TARGET_CLASSES = new Set([ITERATOR_CLASS, SHUTDOWN_ITERATOR_CLASS, COUNTER_CLASS, SAVE_TXT_CLASS]);

const pendingSteps = new Map();
let runWasAborted = false;

function getNodeById(nodeId) {
    if (!app.graph) return null;
    if (typeof app.graph.getNodeById === "function") {
        const n = app.graph.getNodeById(Number(nodeId)) || app.graph.getNodeById(String(nodeId));
        if (n) return n;
    }
    return app.graph._nodes_by_id?.[nodeId] || null;
}

function setWidgetValue(node, name, val) {
    const w = node?.widgets?.find((w) => w.name === name);
    if (w) {
        w.value = val;
        w.callback?.(val);
    }
}

function getWidgetValue(node, name, fallback) {
    const w = node?.widgets?.find((w) => w.name === name);
    return w && w.value !== undefined ? w.value : fallback;
}

function updateResetButtonAppearance(node) {
    const btn = node?.widgets?.find((w) => w._wfaResetBtn || w.name === "Reset Counter");
    if (!btn) return;
    if (node._wfaCountdownActive && node._wfaCountdownRemaining > 0) {
        const lbl = `✖ ABORT SHUTDOWN (${node._wfaCountdownRemaining}s)`;
        btn.name = lbl;
        btn.label = lbl;
    } else {
        btn.name = "Reset Counter";
        btn.label = "↺ Reset Counter";
    }
}

async function cancelPendingShutdown(node) {
    try {
        await api.fetchApi("/wfa/cancel_power", { method: "POST" });
    } catch (_) {}
    if (node) {
        node._wfaCountdownActive = false;
        node._wfaCountdownRemaining = 0;
        updateResetButtonAppearance(node);
        node._wfaIteratorStatus = {
            text: "✓ Completed • Auto-Shutdown Aborted",
            progress: 1,
            done: true,
            warning: false,
        };
        node.setDirtyCanvas?.(true, true);
        app.graph?.setDirtyCanvas?.(true, true);
    }
}

function resetIteratorNode(node) {
    if (!node) return;
    if (node._wfaCountdownActive) {
        cancelPendingShutdown(node);
    }
    const resetTo = Number(getWidgetValue(node, "reset_to", 0)) || 0;
    setWidgetValue(node, "index", resetTo);
    setWidgetValue(node, "current_loop", 1);
    pendingSteps.delete(String(node.id));
    node._wfaCountdownActive = false;
    node._wfaCountdownRemaining = 0;
    updateResetButtonAppearance(node);
    node._wfaIteratorStatus = {
        text: `Ready • Start at ${resetTo}`,
        progress: 0,
        done: false,
        warning: false,
    };
    node.setDirtyCanvas?.(true, true);
    app.graph?.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: "WFA.LoopIterator",
    async setup() {
        api.addEventListener("execution_start", () => {
            runWasAborted = false;
        });

        const handleAbort = () => {
            runWasAborted = true;
            api.fetchApi("/wfa/cancel_power", { method: "POST" }).catch(() => {});
            for (const [nodeId] of pendingSteps.entries()) {
                const node = getNodeById(nodeId);
                if (node) {
                    node._wfaCountdownActive = false;
                    node._wfaCountdownRemaining = 0;
                    updateResetButtonAppearance(node);
                    const curIdx = getWidgetValue(node, "index", 0);
                    const curLoop = getWidgetValue(node, "current_loop", 1);
                    const totLoops = getWidgetValue(node, "total_loops", 1);
                    node._wfaIteratorStatus = {
                        text: `Paused at Index ${curIdx} (Loop ${curLoop}/${totLoops})`,
                        progress: node._wfaIteratorStatus?.progress || 0,
                        done: false,
                        warning: false,
                    };
                    node.setDirtyCanvas?.(true, true);
                }
            }
            pendingSteps.clear();
        };

        api.addEventListener("execution_interrupted", handleAbort);
        api.addEventListener("execution_error", handleAbort);

        api.addEventListener("wfa-prompt-counter-feedback", ({ detail }) => {
            if (!detail || detail.node_id == null) return;
            const node = getNodeById(String(detail.node_id));
            if (node) {
                node._wfaIteratorStatus = {
                    text: `${detail.count} Prompts • end_index: ${detail.end_index}`,
                    progress: 1,
                    done: true,
                    warning: false,
                };
                node.setDirtyCanvas?.(true, true);
            }
        });

        api.addEventListener("wfa-save-txt-feedback", ({ detail }) => {
            if (!detail || detail.node_id == null) return;
            const node = getNodeById(String(detail.node_id));
            if (node) {
                node._wfaIteratorStatus = {
                    text: `✓ Saved: ${detail.display_path}`,
                    progress: 1,
                    done: true,
                    warning: false,
                };
                node.setDirtyCanvas?.(true, true);
            }
        });

        api.addEventListener("wfa-power-countdown", ({ detail }) => {
            if (!detail || detail.node_id == null) return;
            const node = getNodeById(String(detail.node_id));
            if (!node) return;

            if (detail.cancelled) {
                node._wfaCountdownActive = false;
                node._wfaCountdownRemaining = 0;
                updateResetButtonAppearance(node);
                node._wfaIteratorStatus = {
                    text: `✓ ${detail.reason || "Auto-Shutdown Aborted"}`,
                    progress: 1,
                    done: true,
                    warning: false,
                };
                node.setDirtyCanvas?.(true, true);
                app.graph?.setDirtyCanvas?.(true, true);
                return;
            }

            if (detail.executing_now) {
                node._wfaCountdownActive = false;
                node._wfaCountdownRemaining = 0;
                updateResetButtonAppearance(node);
                node._wfaIteratorStatus = {
                    text: `⚡ Executing: ${detail.action}...`,
                    progress: 1,
                    done: false,
                    warning: true,
                };
                node.setDirtyCanvas?.(true, true);
                app.graph?.setDirtyCanvas?.(true, true);
                return;
            }

            const rem = Number(detail.remaining) || 0;
            const tot = Math.max(1, Number(detail.total) || 60);
            node._wfaCountdownActive = true;
            node._wfaCountdownRemaining = rem;
            updateResetButtonAppearance(node);
            node._wfaIteratorStatus = {
                text: `⚠ ${detail.action} in ${rem}s • Click button to Abort`,
                progress: Math.min(1, Math.max(0, rem / tot)),
                done: false,
                warning: true,
            };
            node.setDirtyCanvas?.(true, true);
            app.graph?.setDirtyCanvas?.(true, true);
        });

        api.addEventListener("wfa-loop-iterator-step", ({ detail }) => {
            if (!detail || detail.node_id == null) return;
            const nodeIdStr = String(detail.node_id);
            pendingSteps.set(nodeIdStr, detail);

            const node = getNodeById(nodeIdStr);
            if (node) {
                node._wfaCountdownActive = false;
                node._wfaCountdownRemaining = 0;
                updateResetButtonAppearance(node);

                // Keep widget on current_index while generating so connected WFA switches highlight the active row
                setWidgetValue(node, "index", detail.current_index);
                setWidgetValue(node, "current_loop", detail.current_loop);
                setWidgetValue(node, "end_index", detail.end_index);

                const span = Math.max(1, detail.end_index - detail.reset_to + 1);
                const idxOffset = Math.max(0, detail.current_index - detail.reset_to);
                const totalSteps = span * Math.max(1, detail.total_loops);
                const completedSteps = (detail.current_loop - 1) * span + idxOffset + 1;
                const progress = Math.min(1, Math.max(0, completedSteps / totalSteps));

                node._wfaIteratorStatus = {
                    text: `Loop ${detail.current_loop}/${detail.total_loops} • Index ${detail.current_index}/${detail.end_index}`,
                    progress,
                    done: false,
                    warning: false,
                };
                node.setDirtyCanvas?.(true, true);
                app.graph?.setDirtyCanvas?.(true, true);
            }
        });

        // Fired with detail === null when the entire current prompt finishes executing
        api.addEventListener("executing", async ({ detail }) => {
            if (detail !== null) return;
            if (runWasAborted || pendingSteps.size === 0) {
                pendingSteps.clear();
                return;
            }

            const stepsToApply = Array.from(pendingSteps.values());
            pendingSteps.clear();

            let shouldQueueNext = false;

            for (const step of stepsToApply) {
                const node = getNodeById(step.node_id);
                if (!node) continue;

                // Advance widgets to next_index and next_loop now that generation finished
                setWidgetValue(node, "index", step.next_index);
                setWidgetValue(node, "current_loop", step.next_loop);

                if (step.finished_all) {
                    const actionVal = String(
                        getWidgetValue(node, "after_run", getWidgetValue(node, "on_complete", "Do Nothing"))
                    );
                    if (node.comfyClass === SHUTDOWN_ITERATOR_CLASS && !actionVal.startsWith("Do Nothing")) {
                        const delaySec =
                            Number(getWidgetValue(node, "delay_sec", getWidgetValue(node, "shutdown_delay_sec", 60))) ||
                            60;
                        node._wfaIteratorStatus = {
                            text: `✓ All Loops Done • Starting ${delaySec}s Power Countdown...`,
                            progress: 1,
                            done: false,
                            warning: true,
                        };
                    } else {
                        node._wfaIteratorStatus = {
                            text: `✓ Completed ${step.total_loops}/${step.total_loops} Loops (Reset to ${step.reset_to})`,
                            progress: 1,
                            done: true,
                            warning: false,
                        };
                    }
                } else {
                    const liveAutoQueue = Boolean(getWidgetValue(node, "auto_queue", true));
                    if (step.should_requeue && liveAutoQueue) {
                        shouldQueueNext = true;
                    } else {
                        node._wfaIteratorStatus = {
                            text: `Next: Index ${step.next_index} (Loop ${step.next_loop}/${step.total_loops})`,
                            progress: node._wfaIteratorStatus?.progress || 0,
                            done: false,
                            warning: false,
                        };
                    }
                }
                node.setDirtyCanvas?.(true, true);
            }

            app.graph?.setDirtyCanvas?.(true, true);

            if (shouldQueueNext && !runWasAborted) {
                await app.queuePrompt(0, 1);
            }
        });
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!TARGET_CLASSES.has(nodeData.name)) return;

        if (ITERATOR_CLASSES.has(nodeData.name)) {
            const LEGACY_ACTION_MAP = {
                "Close ComfyUI & Shut Down PC": "Shut Down PC",
                "Close ComfyUI & Sleep PC": "Sleep PC",
                "Close ComfyUI & Hibernate PC": "Hibernate PC",
                "Close ComfyUI Only (Keep PC On)": "Close ComfyUI",
                "Do Nothing (Disabled)": "Do Nothing",
            };

            const origOnNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const res = origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined;

                if (!this.widgets?.some((w) => w._wfaResetBtn || w.name === "Reset Counter" || w.name === "_wfa_reset_btn")) {
                    const btn = this.addWidget("button", "Reset Counter", null, () => {
                        if (this._wfaCountdownActive) {
                            cancelPendingShutdown(this);
                        } else {
                            resetIteratorNode(this);
                        }
                    });
                    btn.label = "↺ Reset Counter";
                    btn._wfaResetBtn = true;
                    btn.serialize = false;
                }

                if (this.computeSize) {
                    const sz = this.computeSize();
                    this.size = [sz[0], sz[1]];
                }
                return res;
            };

            if (nodeData.name === SHUTDOWN_ITERATOR_CLASS) {
                const origOnConfigure = nodeType.prototype.onConfigure;
                nodeType.prototype.onConfigure = function (info) {
                    const res = origOnConfigure ? origOnConfigure.apply(this, arguments) : undefined;
                    const w = this.widgets?.find((w) => w.name === "after_run");
                    if (w && LEGACY_ACTION_MAP[w.value]) {
                        w.value = LEGACY_ACTION_MAP[w.value];
                    }
                    return res;
                };
            }

            const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function (_, options) {
                if (origGetExtraMenuOptions) {
                    origGetExtraMenuOptions.apply(this, arguments);
                }
                const extraItems = [
                    {
                        content: "↺ Reset Counter",
                        callback: () => resetIteratorNode(this),
                    },
                ];
                if (nodeData.name === SHUTDOWN_ITERATOR_CLASS) {
                    extraItems.unshift({
                        content: "✖ Abort Scheduled Shutdown",
                        callback: () => cancelPendingShutdown(this),
                    });
                }
                extraItems.push(null);
                options.unshift(...extraItems);
            };
        }

        const origOnDrawForeground = nodeType.prototype.onDrawForeground;
        nodeType.prototype.onDrawForeground = function (ctx, graphCanvas, canvasEl, lowQuality) {
            if (origOnDrawForeground) origOnDrawForeground.apply(this, arguments);
            if (this.flags?.collapsed) return;
            if (lowQuality || graphCanvas?.low_quality || app.canvas?.low_quality) return;

            const status = this._wfaIteratorStatus;
            if (!status || !status.text) return;

            const titleH = window.LiteGraph?.NODE_TITLE_HEIGHT || 30;
            const pillH = 20;
            const pillY = -titleH - pillH - 4;

            ctx.save();
            ctx.font = 'bold 11px "JetBrains Mono", "Consolas", sans-serif';
            const textW = ctx.measureText(status.text).width;
            const pillW = Math.max(160, textW + 18);

            // Background pill
            ctx.fillStyle = "#18181b";
            ctx.strokeStyle = status.warning ? "#ef4444" : status.done ? "#4ade80" : "#3f3f46";
            ctx.lineWidth = status.warning ? 1.5 : 1;
            ctx.beginPath();
            ctx.roundRect(0, pillY, pillW, pillH, 5);
            ctx.fill();
            ctx.stroke();

            // Progress fill
            if (status.progress > 0) {
                ctx.save();
                ctx.beginPath();
                ctx.roundRect(0, pillY, pillW, pillH, 5);
                ctx.clip();
                ctx.fillStyle = status.warning
                    ? "rgba(239, 68, 68, 0.30)"
                    : status.done
                      ? "rgba(74, 222, 128, 0.28)"
                      : "rgba(56, 189, 248, 0.25)";
                ctx.fillRect(0, pillY, pillW * status.progress, pillH);
                ctx.restore();
            }

            // Status text
            ctx.fillStyle = status.warning ? "#fca5a5" : status.done ? "#4ade80" : "#f4f4f6";
            ctx.textBaseline = "middle";
            ctx.fillText(status.text, 8, pillY + pillH / 2);
            ctx.restore();
        };
    },
});
