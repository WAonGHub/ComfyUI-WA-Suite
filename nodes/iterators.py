import os
import re
import subprocess
import sys
import threading
import time

try:
    import folder_paths
except ImportError:
    folder_paths = None

try:
    from aiohttp import web
except ImportError:
    web = None

try:
    from server import PromptServer
except ImportError:
    PromptServer = None

try:
    import comfy.model_management as model_management
except ImportError:
    model_management = None

from .prompts import list_prompt_files, parse_prompt_text, resolve_prompt_file_path
from .utils import SUITE_CATEGORY, any_type

_POWER_LOCK = threading.Lock()
_POWER_STATE = {
    "generation": 0,
    "cancel_event": threading.Event(),
    "active_node_id": None,
}


def _cancel_pending_power_action(reason: str = "Shutdown aborted by user.") -> str | None:
    with _POWER_LOCK:
        _POWER_STATE["generation"] += 1
        _POWER_STATE["cancel_event"].set()
        node_id = _POWER_STATE["active_node_id"]
        _POWER_STATE["active_node_id"] = None

    if os.name == "nt":
        try:
            subprocess.Popen(
                ["shutdown", "/a"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass

    if node_id is not None and PromptServer is not None and getattr(PromptServer, "instance", None) is not None:
        try:
            PromptServer.instance.send_sync(
                "wfa-power-countdown",
                {
                    "node_id": str(node_id),
                    "cancelled": True,
                    "reason": reason,
                },
            )
        except Exception:
            pass
    return node_id


if PromptServer is not None and getattr(PromptServer, "instance", None) is not None and web is not None:
    try:
        @PromptServer.instance.routes.post("/wfa/cancel_power")
        async def _wfa_cancel_power_route(request):
            node_id = _cancel_pending_power_action("Shutdown aborted by user.")
            return web.json_response({"ok": True, "node_id": node_id})
    except Exception:
        pass


def _execute_system_power_action(action: str) -> None:
    # Free GPU VRAM and flush output streams cleanly before closing ComfyUI / powering off
    if model_management is not None:
        try:
            model_management.unload_all_models()
            model_management.soft_empty_cache()
        except Exception:
            pass

    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass

    no_win_flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    if action in ("Shut Down PC", "Close ComfyUI & Shut Down PC"):
        if os.name == "nt":
            subprocess.Popen(
                [
                    "shutdown",
                    "/s",
                    "/f",
                    "/t",
                    "5",
                    "/c",
                    "WFA Loop Iterator finished all generations — shutting down PC.",
                ],
                creationflags=no_win_flag,
            )
        else:
            subprocess.Popen(["shutdown", "-h", "now"])
        time.sleep(1.0)
        os._exit(0)

    elif action in ("Sleep PC", "Close ComfyUI & Sleep PC"):
        if os.name == "nt":
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    "Start-Sleep -Seconds 2; Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)",
                ],
                creationflags=no_win_flag,
            )
        else:
            subprocess.Popen(["systemctl", "suspend"])
        time.sleep(0.5)
        os._exit(0)

    elif action in ("Hibernate PC", "Close ComfyUI & Hibernate PC"):
        if os.name == "nt":
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    "Start-Sleep -Seconds 2; shutdown /h",
                ],
                creationflags=no_win_flag,
            )
        else:
            subprocess.Popen(["systemctl", "hibernate"])
        time.sleep(0.5)
        os._exit(0)

    elif action in ("Close ComfyUI", "Close ComfyUI Only (Keep PC On)"):
        time.sleep(0.5)
        os._exit(0)


def _start_power_watchdog(node_id: str, action: str, delay_sec: int, target_prompt_id: str | None) -> None:
    if not action or action.startswith("Do Nothing"):
        return
    if PromptServer is None or getattr(PromptServer, "instance", None) is None:
        return

    with _POWER_LOCK:
        _POWER_STATE["generation"] += 1
        my_gen = _POWER_STATE["generation"]
        _POWER_STATE["cancel_event"].set()
        cancel_event = threading.Event()
        _POWER_STATE["cancel_event"] = cancel_event
        _POWER_STATE["active_node_id"] = str(node_id)

    delay_sec = max(5, int(delay_sec))

    def _worker():
        server = getattr(PromptServer, "instance", None)
        pq = getattr(server, "prompt_queue", None) if server is not None else None
        if server is None or pq is None:
            return

        # Phase 1: Wait until the final generation (KSampler, Refiners, SaveImage, etc.) 100% completes
        while True:
            if cancel_event.is_set() or _POWER_STATE["generation"] != my_gen:
                return

            if model_management is not None:
                try:
                    if model_management.processing_interrupted():
                        _cancel_pending_power_action("Final generation interrupted — shutdown cancelled.")
                        return
                except Exception:
                    pass

            try:
                running, queued = pq.get_current_queue_volatile()
            except Exception:
                running, queued = [], []

            running_ids = [item[1] for item in running if len(item) > 1]

            if target_prompt_id and target_prompt_id in running_ids:
                time.sleep(0.4)
                continue

            if target_prompt_id:
                try:
                    hist = pq.get_history(prompt_id=target_prompt_id) or {}
                    entry = hist.get(target_prompt_id)
                    if entry is not None:
                        status_dict = entry.get("status") or {}
                        if status_dict.get("status_str") != "success" or not status_dict.get("completed", False):
                            _cancel_pending_power_action("Final run did not complete cleanly — shutdown cancelled.")
                            return
                except Exception:
                    pass

            if len(running) == 0 and len(queued) == 0:
                break

            time.sleep(0.4)

        # Brief grace pause so frontend processes `executing(null)`, resets widgets, and renders final saved image
        for _ in range(6):
            if cancel_event.is_set() or _POWER_STATE["generation"] != my_gen:
                return
            time.sleep(0.25)

        # Phase 2: Live cancelable countdown
        for remaining in range(delay_sec, 0, -1):
            if cancel_event.is_set() or _POWER_STATE["generation"] != my_gen:
                return
            try:
                if pq.get_tasks_remaining() > 0:
                    _cancel_pending_power_action("New generation started — shutdown cancelled.")
                    return
            except Exception:
                pass

            try:
                server.send_sync(
                    "wfa-power-countdown",
                    {
                        "node_id": str(node_id),
                        "remaining": remaining,
                        "total": delay_sec,
                        "action": action,
                        "cancelled": False,
                    },
                )
            except Exception:
                pass

            for _ in range(4):
                if cancel_event.is_set() or _POWER_STATE["generation"] != my_gen:
                    return
                time.sleep(0.25)

        if cancel_event.is_set() or _POWER_STATE["generation"] != my_gen:
            return
        try:
            if pq.get_tasks_remaining() > 0:
                _cancel_pending_power_action("New generation started — shutdown cancelled.")
                return
        except Exception:
            pass

        try:
            server.send_sync(
                "wfa-power-countdown",
                {
                    "node_id": str(node_id),
                    "remaining": 0,
                    "total": delay_sec,
                    "action": action,
                    "executing_now": True,
                    "cancelled": False,
                },
            )
        except Exception:
            pass

        _execute_system_power_action(action)

    t = threading.Thread(target=_worker, name="WFA-PowerWatchdog", daemon=True)
    t.start()

_COMMENT_ONLY_RE = re.compile(r"^\s*/\*\s*\d+\s*\*/\s*$")
_INSPIRE_SPLIT_RE = re.compile(r"\n\s*-+\s*\n")
_INSPIRE_BLOCK_RE = re.compile(
    r"^(?:(?:positive:(?P<positive>.*?)|negative:(?P<negative>.*?)|name:(?P<name>.*?))\n*)+$",
    re.DOTALL | re.IGNORECASE,
)


def _get_inspire_prompt_files() -> list[str]:
    files_list = ["<use connected prompts wire>"]
    for rel_path in list_prompt_files():
        if rel_path not in files_list:
            files_list.append(rel_path)
    return files_list


def _count_prompts_in_string(text: str, mode: str) -> int:
    if not text or not text.strip():
        return 0

    is_auto = mode.startswith("auto")

    # 1. Inspire / WFA Batch Prompt format (`---` separated blocks or `positive:` blocks)
    if mode.startswith("inspire") or (
        is_auto
        and (
            re.search(r"(?:^|\n)\s*---+\s*(?:\n|$)", text)
            or re.search(r"(?:^|\n)\s*positive\s*:", text, re.IGNORECASE)
        )
    ):
        if re.search(r"(?:^|\n)\s*positive\s*:", text, re.IGNORECASE):
            return len(parse_prompt_text(text)["entries"])
        blocks = _INSPIRE_SPLIT_RE.split(text)
        return sum(1 for b in blocks if b.strip())

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
                elif isinstance(single, dict) and "entries" in single:
                    count = len(single["entries"])
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
        elif file_choice and file_choice != "<use connected prompts wire>":
            # Read directly from Inspire Pack or WFA Suite prompt file if selected
            try:
                candidate = resolve_prompt_file_path(file_choice)
                if candidate and os.path.isfile(candidate):
                    with open(candidate, "r", encoding="utf-8", errors="ignore") as f:
                        data = f.read()
                    count = _count_prompts_in_string(data, "inspire format (--- separated blocks)")
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
                        "label_on": "Enabled",
                        "label_off": "Paused",
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


class WFA_LoopIteratorShutdown(WFA_LoopIterator):
    """
    WFA Loop Iterator (Auto-Shutdown): Copy of WFA Loop Iterator with overnight power-saving
    automation. After the very last loop & index finishes generating AND saving its final image,
    runs a cancelable safety countdown and cleanly closes ComfyUI + shuts down / sleeps / hibernates your PC.
    """

    @classmethod
    def INPUT_TYPES(cls):
        base = WFA_LoopIterator.INPUT_TYPES()
        req = dict(base["required"])
        req["after_run"] = (
            [
                "Shut Down PC",
                "Sleep PC",
                "Hibernate PC",
                "Close ComfyUI",
                "Do Nothing",
            ],
            {
                "default": "Shut Down PC",
                "tooltip": (
                    "Action to perform AFTER the final generation in the final loop completely finishes saving:\n"
                    "• Shut Down PC: Unloads VRAM, closes ComfyUI cleanly, and powers off your PC.\n"
                    "• Sleep PC: Closes ComfyUI cleanly and puts your PC into low-power Sleep.\n"
                    "• Hibernate PC: Closes ComfyUI cleanly and hibernates your PC.\n"
                    "• Close ComfyUI: Closes ComfyUI (dropping GPU power to idle) while keeping Windows running.\n"
                    "• Do Nothing: Behaves identically to the standard WFA Loop Iterator."
                ),
            },
        )
        req["delay_sec"] = (
            "INT",
            {
                "default": 60,
                "min": 5,
                "max": 3600,
                "step": 5,
                "tooltip": (
                    "Safety countdown (in seconds) AFTER the final image finishes saving before power-off triggers.\n"
                    "During this countdown, you can click '✖ ABORT SHUTDOWN' right on the node to cancel."
                ),
            },
        )
        return {
            "required": req,
            "optional": dict(base["optional"]),
            "hidden": dict(base["hidden"]),
        }

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def iterate(
        self,
        index: int = 0,
        reset_to: int = 0,
        end_index: int = 10,
        step: int = 1,
        total_loops: int = 3,
        current_loop: int = 1,
        auto_queue: bool = True,
        after_run: str = "Shut Down PC",
        delay_sec: int = 60,
        trigger_signal=None,
        unique_id=None,
        **kwargs,
    ):
        # Support any legacy workflow kwargs seamlessly
        action_val = after_run or kwargs.get("on_complete", "Shut Down PC")
        delay_val = int(kwargs.get("shutdown_delay_sec", delay_sec))

        step_val = max(1, int(step))
        total_loops_val = max(1, int(total_loops))
        reset_to_val = max(0, int(reset_to))
        end_index_val = max(reset_to_val, int(end_index))

        active_index = int(index)
        if active_index > end_index_val:
            active_index = reset_to_val
        active_loop = max(1, min(int(current_loop), total_loops_val))

        is_final_step = (active_index + step_val > end_index_val) and (active_loop >= total_loops_val)

        if not is_final_step and _POWER_STATE["active_node_id"] is not None:
            _cancel_pending_power_action("New iterator step started.")

        result = super().iterate(
            index=index,
            reset_to=reset_to,
            end_index=end_index,
            step=step,
            total_loops=total_loops,
            current_loop=current_loop,
            auto_queue=auto_queue,
            trigger_signal=trigger_signal,
            unique_id=unique_id,
        )

        if (
            is_final_step
            and action_val
            and not str(action_val).startswith("Do Nothing")
            and PromptServer is not None
            and getattr(PromptServer, "instance", None) is not None
            and unique_id is not None
        ):
            uid = unique_id[0] if isinstance(unique_id, list) else unique_id
            target_prompt_id = None
            try:
                pq = getattr(PromptServer.instance, "prompt_queue", None)
                if pq is not None:
                    running, _ = pq.get_current_queue_volatile()
                    if running and len(running[0]) > 1:
                        target_prompt_id = running[0][1]
            except Exception:
                target_prompt_id = None

            _start_power_watchdog(
                node_id=str(uid),
                action=str(action_val),
                delay_sec=delay_val,
                target_prompt_id=target_prompt_id,
            )

        return result


NODE_CLASS_MAPPINGS = {
    "WFA_LoopIterator": WFA_LoopIterator,
    "WFA_LoopIteratorShutdown": WFA_LoopIteratorShutdown,
    "WFA_PromptCounter": WFA_PromptCounter,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WFA_LoopIterator": "WFA Loop Iterator ⚡ (WFA Suite)",
    "WFA_LoopIteratorShutdown": "WFA Loop Shutdown ⚡ (WFA Suite)",
    "WFA_PromptCounter": "WFA Prompt Counter ⚡ (WFA Suite)",
}
