import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const ITERATOR_CLASS = "WFA_LoopIterator";
const COUNTER_CLASS = "WFA_PromptCounter";
const TARGET_CLASSES = new Set([ITERATOR_CLASS, COUNTER_CLASS]);

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

function resetIteratorNode(node) {
    if (!node) return;
    const resetTo = Number(getWidgetValue(node, "reset_to", 0)) || 0;
    setWidgetValue(node, "index", resetTo);
    setWidgetValue(node, "current_loop", 1);
    pendingSteps.delete(String(node.id));
    node._wfaIteratorStatus = {
        text: `Ready • Start at ${resetTo}`,
        progress: 0,
        done: false,
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
            for (const [nodeId] of pendingSteps.entries()) {
                const node = getNodeById(nodeId);
                if (node) {
                    const curIdx = getWidgetValue(node, "index", 0);
                    const curLoop = getWidgetValue(node, "current_loop", 1);
                    const totLoops = getWidgetValue(node, "total_loops", 1);
                    node._wfaIteratorStatus = {
                        text: `Paused at Index ${curIdx} (Loop ${curLoop}/${totLoops})`,
                        progress: node._wfaIteratorStatus?.progress || 0,
                        done: false,
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
                };
                node.setDirtyCanvas?.(true, true);
            }
        });

        api.addEventListener("wfa-loop-iterator-step", ({ detail }) => {
            if (!detail || detail.node_id == null) return;
            const nodeIdStr = String(detail.node_id);
            pendingSteps.set(nodeIdStr, detail);

            const node = getNodeById(nodeIdStr);
            if (node) {
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
                    node._wfaIteratorStatus = {
                        text: `✓ Completed ${step.total_loops}/${step.total_loops} Loops (Reset to ${step.reset_to})`,
                        progress: 1,
                        done: true,
                    };
                } else {
                    const liveAutoQueue = Boolean(getWidgetValue(node, "auto_queue", true));
                    if (step.should_requeue && liveAutoQueue) {
                        shouldQueueNext = true;
                    } else {
                        node._wfaIteratorStatus = {
                            text: `Next: Index ${step.next_index} (Loop ${step.next_loop}/${step.total_loops})`,
                            progress: node._wfaIteratorStatus?.progress || 0,
                            done: false,
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

        if (nodeData.name === ITERATOR_CLASS) {
            const origOnNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const res = origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined;

                if (!this.widgets?.some((w) => w.name === "_wfa_reset_btn")) {
                    const btn = this.addWidget("button", "↺ Reset Counter to Start", null, () => {
                        resetIteratorNode(this);
                    });
                    btn.name = "_wfa_reset_btn";
                    btn.serialize = false;
                }

                if (!this.size || this.size[0] < 310) {
                    const sz = this.computeSize ? this.computeSize() : [320, 250];
                    this.size = [Math.max(320, sz[0]), sz[1]];
                }
                return res;
            };

            const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function (_, options) {
                if (origGetExtraMenuOptions) {
                    origGetExtraMenuOptions.apply(this, arguments);
                }
                options.unshift(
                    {
                        content: "⚡ Reset Iterator to Start (reset_to & Loop 1)",
                        callback: () => resetIteratorNode(this),
                    },
                    null
                );
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
            ctx.strokeStyle = status.done ? "#4ade80" : "#3f3f46";
            ctx.lineWidth = 1;
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
                ctx.fillStyle = status.done
                    ? "rgba(74, 222, 128, 0.28)"
                    : "rgba(56, 189, 248, 0.25)";
                ctx.fillRect(0, pillY, pillW * status.progress, pillH);
                ctx.restore();
            }

            // Status text
            ctx.fillStyle = status.done ? "#4ade80" : "#f4f4f6";
            ctx.textBaseline = "middle";
            ctx.fillText(status.text, 8, pillY + pillH / 2);
            ctx.restore();
        };
    },
});
