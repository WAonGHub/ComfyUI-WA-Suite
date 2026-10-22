import os
import re

try:
    import folder_paths
except ImportError:
    folder_paths = None

try:
    from server import PromptServer
except ImportError:
    PromptServer = None

from .utils import SUITE_CATEGORY, any_type

_COMMENT_ONLY_RE = re.compile(r"^\s*/\*\s*\d+\s*\*/\s*$")
_INSPIRE_SPLIT_RE = re.compile(r"\n\s*-+\s*\n")
_INSPIRE_BLOCK_RE = re.compile(
    r"^(?:(?:positive:(?P<positive>.*?)|negative:(?P<negative>.*?)|name:(?P<name>.*?))\n*)+$",
    re.DOTALL | re.IGNORECASE,
)


def _get_inspire_prompt_files() -> list[str]:
    files_list = ["<use connected prompts wire>"]
    if folder_paths is None:
        return files_list
    try:
        prompts_paths = folder_paths.get_folder_paths("inspire_prompts")
        for prompts_path in prompts_paths:
            if not os.path.isdir(prompts_path):
                continue
            for root, _dirs, files in os.walk(prompts_path):
                for file in files:
                    if file.endswith(".txt"):
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, prompts_path)
                        if rel_path not in files_list:
                            files_list.append(rel_path)
    except Exception:
        pass
    return files_list


def _count_prompts_in_string(text: str, mode: str) -> int:
    if not text or not text.strip():
        return 0

    is_auto = mode.startswith("auto")

    # 1. Inspire Pack format (`---` separated blocks or `positive:` blocks)
    if mode.startswith("inspire") or (
        is_auto
        and (
            re.search(r"(?:^|\n)\s*---+\s*(?:\n|$)", text)
            or re.search(r"(?:^|\n)\s*positive\s*:", text, re.IGNORECASE)
        )
    ):
        blocks = _INSPIRE_SPLIT_RE.split(text)
        valid_blocks = 0
        for b in blocks:
            b_str = b.strip()
            if not b_str:
                continue
            if _INSPIRE_BLOCK_RE.search(b_str) or not re.search(r"(?:^|\n)\s*positive\s*:", text, re.IGNORECASE):
                valid_blocks += 1
        return valid_blocks

    # 2. Impact StringSelector `#` multiline blocks
    if mode.startswith("hash"):
        lines = text.split("\n")
        blocks = []
        cur = ""
        for line in lines:
            if line.startswith("#"):
                if cur.strip():
                    blocks.append(cur.strip())
                cur = line + "\n"
            else:
                cur += line + "\n"
        if cur.strip():
            blocks.append(cur.strip())
        return len(blocks)

    # 3. Line-by-line prompt list
    lines = text.splitlines()
    if mode == "lines (up to last non-empty row)":
        last_non_empty = -1
        for i in range(len(lines) - 1, -1, -1):
            s = lines[i].strip()
            if s and not _COMMENT_ONLY_RE.match(s):
                last_non_empty = i
                break
        return last_non_empty + 1

    # Default for lines: count non-empty lines (ignoring empty /*0*/ placeholders)
    count = 0
    for line in lines:
        s = line.strip()
        if s and not _COMMENT_ONLY_RE.match(s):
            count += 1
    return count


class WFA_PromptCounter:
    """
    WFA Prompt Counter: Reads the total prompt count and 0-based `end_index` (`count - 1`)
    from Inspire Pack Batch Prompts (`ZIPPED_PROMPT`, `.txt` files, or `---` prompt strings),
    `WFA Text Index Switch` / `StringSelector` multiline prompt lists, or any ComfyUI `LIST`.
    """

    @classmethod
    def INPUT_TYPES(cls):
        inspire_files = _get_inspire_prompt_files()
        return {
            "required": {
                "mode": (
                    [
                        "auto-detect (Inspire / lines / list)",
                        "inspire format (--- separated blocks)",
                        "lines (non-empty lines only)",
                        "lines (up to last non-empty row)",
                        "hash (#) multiline blocks",
                    ],
                    {
                        "default": "auto-detect (Inspire / lines / list)",
                        "tooltip": (
                            "How to count prompts when a text string is connected:\n"
                            "• auto-detect: Automatically detects Inspire '---' blocks, ZIPPED_PROMPT lists, or multiline prompt lists.\n"
                            "• inspire format: Counts '---' separated prompt blocks.\n"
                            "• lines (non-empty): Counts non-empty lines.\n"
                            "• lines (up to last non-empty row): Returns highest row index + 1 (ideal for indexed row lists)."
                        ),
                    },
                ),
                "inspire_prompt_file": (
                    inspire_files,
                    {
                        "default": inspire_files[0],
                        "tooltip": "Optional: If no wire is connected to `prompts`, reads the prompt count directly from this Inspire Pack prompt file.",
                    },
                ),
            },
            "optional": {
                "prompts": (
                    any_type,
                    {
                        "tooltip": "Connect Inspire `zipped_prompt`, a multiline prompt `STRING`, or any `LIST` here.",
                    },
                ),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    INPUT_IS_LIST = True
    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("end_index", "count")
    OUTPUT_TOOLTIPS = (
        "0-based last index (count - 1). Connect this directly to `end_index` on WFA Loop Iterator!",
        "Total number of prompts found.",
    )
    FUNCTION = "count_prompts"
    CATEGORY = f"{SUITE_CATEGORY}/Iterators"

    def count_prompts(
        self,
        mode,
        inspire_prompt_file=None,
        prompts=None,
        unique_id=None,
    ):
        mode_str = mode[0] if isinstance(mode, list) and mode else str(mode)
        file_choice = (
            inspire_prompt_file[0]
            if isinstance(inspire_prompt_file, list) and inspire_prompt_file
            else str(inspire_prompt_file or "<use connected prompts wire>")
        )

        count = 0

        if prompts is not None and len(prompts) > 0:
            # Case 1: Multiple items received via ComfyUI OUTPUT_IS_LIST=True (e.g. Inspire zipped_prompt list)
            if len(prompts) > 1:
                count = len(prompts)
            else:
                single = prompts[0]
                if isinstance(single, str):
                    count = _count_prompts_in_string(single, mode_str)
                elif isinstance(single, (list, tuple)):
                    # Check if single is one Inspire ZIPPED_PROMPT tuple: (pos_str, neg_str, name_str)
                    if (
                        len(single) == 3
                        and all(isinstance(x, str) for x in single)
                    ):
                        count = 1
                    else:
                        count = len(single)
                elif single is not None:
                    count = 1
        elif (
            file_choice
            and file_choice != "<use connected prompts wire>"
            and folder_paths is not None
        ):
            # Read directly from Inspire Pack prompt file if selected
            try:
                for d in folder_paths.get_folder_paths("inspire_prompts"):
                    candidate = os.path.join(d, file_choice)
                    if os.path.isfile(candidate):
                        with open(candidate, "r", encoding="utf-8") as f:
                            data = f.read()
                        count = _count_prompts_in_string(data, "inspire format (--- separated blocks)")
                        break
            except Exception:
                count = 0

        end_index = max(0, count - 1)

        if PromptServer is not None and getattr(PromptServer, "instance", None) is not None and unique_id is not None:
            uid = unique_id[0] if isinstance(unique_id, list) else unique_id
            PromptServer.instance.send_sync(
                "wfa-prompt-counter-feedback",
                {
                    "node_id": str(uid),
                    "count": count,
                    "end_index": end_index,
                },
            )

        return (end_index, count)


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
                        "default": 10,
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
        end_index: int = 10,
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
    "WFA_PromptCounter": WFA_PromptCounter,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WFA_LoopIterator": "WFA Loop Iterator ⚡ (WFA Suite)",
    "WFA_PromptCounter": "WFA Prompt Counter ⚡ (WFA Suite)",
}
