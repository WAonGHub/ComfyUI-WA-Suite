try:
    from server import PromptServer
except ImportError:
    PromptServer = None

from .utils import SUITE_CATEGORY, any_type


class WFA_LoopIterator:
    """
    WFA Loop Iterator: All-in-one INT counter, auto-rewinder, and multi-pass queue trigger.
    Counts from `index` up to `end_index` (by `step`), rewinds to `reset_to`, and repeats
    for `total_loops` passes before automatically stopping the queue cleanly (no error crash).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "index": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 999999,
                        "step": 1,
                        "tooltip": "Current INT index output for this generation. Automatically counts up after each completed run.",
                    },
                ),
                "reset_to": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 999999,
                        "step": 1,
                        "tooltip": "The INT value `index` rewinds to after reaching `end_index` (e.g. 0 or 3).",
                    },
                ),
                "end_index": (
                    "INT",
                    {
                        "default": 347,
                        "min": 0,
                        "max": 999999,
                        "step": 1,
                        "tooltip": "The final index in your prompt list to count up to (inclusive) before rewinding to `reset_to`.",
                    },
                ),
                "step": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "max": 999999,
                        "step": 1,
                        "tooltip": "Amount to increment `index` after each completed generation.",
                    },
                ),
                "total_loops": (
                    "INT",
                    {
                        "default": 3,
                        "min": 1,
                        "max": 999999,
                        "step": 1,
                        "tooltip": "How many full passes through the list (`reset_to` -> `end_index`) to run before stopping.",
                    },
                ),
                "current_loop": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "max": 999999,
                        "step": 1,
                        "tooltip": "Current pass number (1 to `total_loops`). Automatically advances after each full pass and resets to 1 when finished.",
                    },
                ),
                "auto_queue": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "Auto-Queue (Run Loop)",
                        "label_off": "Paused (Single Step)",
                        "tooltip": "When enabled, automatically triggers the next generation in ComfyUI's queue until all passes finish (replaces ImpactQueueTrigger).",
                    },
                ),
            },
            "optional": {
                "trigger_signal": (
                    any_type,
                    {
                        "tooltip": "Optional pass-through signal wire if you want this node to execute after a specific upstream node. Not required.",
                    },
                ),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("INT", "INT", "INT")
    RETURN_NAMES = ("index", "current_loop", "total_loops")
    FUNCTION = "iterate"
    OUTPUT_NODE = True
    CATEGORY = f"{SUITE_CATEGORY}/Iterators"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")

    def iterate(
        self,
        index: int = 0,
        reset_to: int = 0,
        end_index: int = 347,
        step: int = 1,
        total_loops: int = 3,
        current_loop: int = 1,
        auto_queue: bool = True,
        trigger_signal=None,
        unique_id=None,
    ):
        step = max(1, int(step))
        total_loops = max(1, int(total_loops))
        reset_to = max(0, int(reset_to))
        end_index = max(reset_to, int(end_index))

        active_index = int(index)
        if active_index > end_index:
            active_index = reset_to

        active_loop = max(1, min(int(current_loop), total_loops))

        next_index = active_index + step
        if next_index > end_index:
            # Reached the end of this pass -> rewind to reset_to
            next_index = reset_to
            if active_loop < total_loops:
                next_loop = active_loop + 1
                should_requeue = bool(auto_queue)
                finished_all = False
            else:
                # Completed all requested loops!
                next_loop = 1
                should_requeue = False
                finished_all = True
        else:
            next_loop = active_loop
            should_requeue = bool(auto_queue)
            finished_all = False

        if PromptServer is not None and getattr(PromptServer, "instance", None) is not None and unique_id is not None:
            uid = unique_id[0] if isinstance(unique_id, list) else unique_id
            PromptServer.instance.send_sync(
                "wfa-loop-iterator-step",
                {
                    "node_id": str(uid),
                    "current_index": active_index,
                    "next_index": next_index,
                    "current_loop": active_loop,
                    "next_loop": next_loop,
                    "reset_to": reset_to,
                    "end_index": end_index,
                    "total_loops": total_loops,
                    "should_requeue": should_requeue,
                    "finished_all": finished_all,
                },
            )

        return (active_index, active_loop, total_loops)


NODE_CLASS_MAPPINGS = {
    "WFA_LoopIterator": WFA_LoopIterator,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WFA_LoopIterator": "WFA Loop Iterator ⚡ (WFA Suite)",
}
