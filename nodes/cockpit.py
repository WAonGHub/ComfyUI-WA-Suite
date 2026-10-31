import json
import math
import os
import re

try:
    import folder_paths
except ImportError:
    folder_paths = None

try:
    import comfy.samplers
except ImportError:
    comfy = None

try:
    from aiohttp import web
except ImportError:
    web = None

try:
    from server import PromptServer
except ImportError:
    PromptServer = None

from .utils import SUITE_CATEGORY, any_type

COCKPIT_CATEGORY = f"{SUITE_CATEGORY}/Cockpit"

_LORA_TAG_RE = re.compile(r"<lora:([^:>]+):([^>]+)>", re.IGNORECASE)
_PLACEHOLDER_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_BPE_WORD_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[^\sA-Za-z0-9]")

_FALLBACK_SAMPLERS = [
    "euler",
    "euler_ancestral",
    "heun",
    "dpm_2",
    "dpm_2_ancestral",
    "lms",
    "dpm_fast",
    "dpm_adaptive",
    "dpmpp_2s_ancestral",
    "dpmpp_sde",
    "dpmpp_2m",
    "dpmpp_2m_sde",
    "dpmpp_3m_sde",
    "ddim",
    "uni_pc",
    "er_sde",
]

_FALLBACK_SCHEDULERS = [
    "normal",
    "karras",
    "exponential",
    "sgm_uniform",
    "simple",
    "ddim_uniform",
    "beta",
]


def _get_lora_list() -> list[str]:
    items = ["None"]
    if folder_paths is not None:
        try:
            for name in folder_paths.get_filename_list("loras"):
                if name and name not in items:
                    items.append(name)
        except Exception:
            pass
    return items


def _get_sampler_list() -> list[str]:
    if comfy is not None and hasattr(comfy, "samplers"):
        try:
            lst = list(comfy.samplers.KSampler.SAMPLERS)
            if lst:
                return lst
        except Exception:
            pass
    return list(_FALLBACK_SAMPLERS)


def _get_scheduler_list() -> list[str]:
    if comfy is not None and hasattr(comfy, "samplers"):
        try:
            lst = list(comfy.samplers.KSampler.SCHEDULERS)
            if lst:
                return lst
        except Exception:
            pass
    return list(_FALLBACK_SCHEDULERS)


if PromptServer is not None and getattr(PromptServer, "instance", None) is not None and web is not None:
    try:
        @PromptServer.instance.routes.get("/wfa/cockpit_meta")
        async def _wfa_get_cockpit_meta(request):
            return web.json_response(
                {
                    "ok": True,
                    "loras": _get_lora_list(),
                    "samplers": _get_sampler_list(),
                    "schedulers": _get_scheduler_list(),
                }
            )
    except Exception:
        pass


def _format_lora_weight(val: float) -> str:
    rounded = round(float(val), 4)
    if rounded == int(rounded):
        return f"{rounded:.1f}"
    return f"{rounded:g}"


def _lora_basename_no_ext(lora_name: str) -> str:
    base = os.path.basename(lora_name.replace("\\", "/"))
    stem, _ext = os.path.splitext(base)
    return stem


def _default_char_slots() -> list[dict]:
    return [
        {
            "ui_enable": idx == 0,
            "override": False,
            "lora_name": "None",
            "str_solo": 0.90,
            "str_multi": 0.50,
        }
        for idx in range(5)
    ]


def _parse_char_cockpit_state(raw: str) -> dict:
    defaults = {"slots": _default_char_slots()}
    if not raw or not str(raw).strip():
        return defaults
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return defaults
        raw_slots = parsed.get("slots")
        if not isinstance(raw_slots, list):
            return defaults
        slots = _default_char_slots()
        for i in range(min(5, len(raw_slots))):
            item = raw_slots[i]
            if isinstance(item, dict):
                slots[i]["ui_enable"] = bool(item.get("ui_enable", slots[i]["ui_enable"]))
                slots[i]["override"] = bool(item.get("override", False))
                slots[i]["lora_name"] = str(item.get("lora_name") or "None")
                try:
                    slots[i]["str_solo"] = float(item.get("str_solo", 0.90))
                except Exception:
                    slots[i]["str_solo"] = 0.90
                try:
                    slots[i]["str_multi"] = float(item.get("str_multi", 0.50))
                except Exception:
                    slots[i]["str_multi"] = 0.50
        return {"slots": slots}
    except Exception:
        return defaults


class WFA_CharacterLoraCockpit:
    """
    WFA Character LoRA Cockpit: 5-slot (C1–C5) interactive character LoRA dashboard card.
    Consolidates 8–20+ Character Switch, Override, Solo Strength, Multi/Duo Strength, LoRA Picker,
    and `<lora:name:wt>` / `LORA_STACK` builder nodes into one sleek UI node.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "use_batch": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "Batch Enable",
                        "label_off": "UI Enable",
                        "tooltip": (
                            "Controls whether C1–C5 enable flags come from connected `c1_enable`..`c5_enable` batch wires "
                            "or from the `[✓ C1]`..`[✓ C5]` buttons inside this cockpit (unless `[🔒]` Override is active on a row)."
                        ),
                    },
                ),
                "cockpit_state": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "Serialized 5-slot character LoRA cockpit state managed by the interactive UI.",
                    },
                ),
            },
            "optional": {
                "c1_enable": (
                    "BOOLEAN",
                    {
                        "forceInput": True,
                        "tooltip": "Batch C1 enable wire from `WFA Batch Prompt Switcher` / `WFA Batch Prompt Loader`.",
                    },
                ),
                "c2_enable": (
                    "BOOLEAN",
                    {
                        "forceInput": True,
                        "tooltip": "Batch C2 enable wire from `WFA Batch Prompt Switcher` / `WFA Batch Prompt Loader`.",
                    },
                ),
                "c3_enable": (
                    "BOOLEAN",
                    {
                        "forceInput": True,
                        "tooltip": "Batch C3 enable wire from `WFA Batch Prompt Switcher` / `WFA Batch Prompt Loader`.",
                    },
                ),
                "c4_enable": (
                    "BOOLEAN",
                    {
                        "forceInput": True,
                        "tooltip": "Batch C4 enable wire from `WFA Batch Prompt Switcher` / `WFA Batch Prompt Loader`.",
                    },
                ),
                "c5_enable": (
                    "BOOLEAN",
                    {
                        "forceInput": True,
                        "tooltip": "Batch C5 enable wire from `WFA Batch Prompt Switcher` / `WFA Batch Prompt Loader`.",
                    },
                ),
                "lora_stack_in": (
                    "LORA_STACK",
                    {
                        "tooltip": "Optional upstream `LORA_STACK` to merge ahead of active character LoRAs.",
                    },
                ),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = (
        "LORA_STACK",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "STRING",
        "BOOLEAN",
        "BOOLEAN",
        "BOOLEAN",
        "BOOLEAN",
        "BOOLEAN",
    )
    RETURN_NAMES = (
        "lora_stack",
        "lora_tags",
        "c1_lora_tag",
        "c2_lora_tag",
        "c3_lora_tag",
        "c4_lora_tag",
        "c5_lora_tag",
        "c1_active",
        "c2_active",
        "c3_active",
        "c4_active",
        "c5_active",
    )
    FUNCTION = "process_cockpit"
    CATEGORY = COCKPIT_CATEGORY

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def process_cockpit(
        self,
        use_batch: bool = True,
        cockpit_state: str = "",
        c1_enable: bool | None = None,
        c2_enable: bool | None = None,
        c3_enable: bool | None = None,
        c4_enable: bool | None = None,
        c5_enable: bool | None = None,
        lora_stack_in=None,
        unique_id=None,
    ):
        state = _parse_char_cockpit_state(cockpit_state)
        slots = state["slots"]
        batch_wires = [c1_enable, c2_enable, c3_enable, c4_enable, c5_enable]

        resolved_active: list[bool] = []
        for i in range(5):
            slot = slots[i]
            wire_val = batch_wires[i]
            if slot["override"]:
                is_on = bool(slot["ui_enable"])
            elif bool(use_batch) and wire_val is not None:
                is_on = bool(wire_val)
            else:
                is_on = bool(slot["ui_enable"])
            resolved_active.append(is_on)

        active_char_count = sum(1 for a in resolved_active if a)
        is_multi = active_char_count >= 2

        stack_out: list[tuple[str, float, float]] = []
        if isinstance(lora_stack_in, list):
            stack_out.extend(lora_stack_in)

        per_slot_tags: list[str] = []
        combined_tags: list[str] = []
        active_summary_parts: list[str] = []

        for i in range(5):
            slot = slots[i]
            is_on = resolved_active[i]
            lora_name = str(slot.get("lora_name") or "None").strip()
            has_lora = bool(lora_name and lora_name.lower() != "none")
            strength = float(slot["str_multi"] if is_multi else slot["str_solo"])

            if is_on and has_lora and abs(strength) > 1e-6:
                wt_str = _format_lora_weight(strength)
                tag = f"<lora:{_lora_basename_no_ext(lora_name)}:{wt_str}>"
                per_slot_tags.append(tag)
                combined_tags.append(tag)
                stack_out.append((lora_name, strength, strength))
                active_summary_parts.append(f"C{i + 1}:{wt_str}")
            else:
                per_slot_tags.append("")
                if is_on:
                    active_summary_parts.append(f"C{i + 1}:on")

        if PromptServer is not None and getattr(PromptServer, "instance", None) is not None and unique_id is not None:
            uid = unique_id[0] if isinstance(unique_id, list) else unique_id
            mode_lbl = "Multi" if is_multi else "Solo"
            summary_txt = (
                f"{mode_lbl} • " + ", ".join(active_summary_parts)
                if active_summary_parts
                else "0 Active Characters"
            )
            PromptServer.instance.send_sync(
                "wfa-char-cockpit-feedback",
                {
                    "node_id": str(uid),
                    "resolved_active": resolved_active,
                    "is_multi": is_multi,
                    "summary": summary_txt,
                },
            )

        return (
            stack_out,
            ", ".join(combined_tags),
            per_slot_tags[0],
            per_slot_tags[1],
            per_slot_tags[2],
            per_slot_tags[3],
            per_slot_tags[4],
            resolved_active[0],
            resolved_active[1],
            resolved_active[2],
            resolved_active[3],
            resolved_active[4],
        )


def _default_deck_state(samplers: list[str], schedulers: list[str]) -> dict:
    default_sampler = "er_sde" if "er_sde" in samplers else ("euler" if "euler" in samplers else samplers[0])
    default_sched = "simple" if "simple" in schedulers else ("normal" if "normal" in schedulers else schedulers[0])
    return {
        "package_name": "Output_Set",
        "use_batch": True,
        "file_batch": False,
        "batch_size": 1,
        "width": 896,
        "height": 1152,
        "snap": 16,
        "seed": 4260,
        "seed_mode": "increment",
        "steps": 28,
        "cfg": 3.5,
        "sampler_name": default_sampler,
        "scheduler": default_sched,
        "refiner_pct": 0.30,
        "refiner_scale": 1.30,
        "toggles": [
            {"label": "Color Match", "value": False},
            {"label": "2nd Refiner", "value": True},
            {"label": "Upscale 2x", "value": True},
            {"label": "3rd Refiner", "value": False},
        ],
    }


def _snap_dim(val: int, divisor: int) -> int:
    v = max(64, int(val))
    d = max(1, int(divisor))
    if d <= 1:
        return v
    return max(d, int(round(v / d) * d))


def _parse_deck_state(raw: str) -> dict:
    samplers = _get_sampler_list()
    schedulers = _get_scheduler_list()
    state = _default_deck_state(samplers, schedulers)
    if not raw or not str(raw).strip():
        return state
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return state
        for str_k in ("package_name", "seed_mode", "sampler_name", "scheduler"):
            if str_k in parsed and parsed[str_k] is not None:
                state[str_k] = str(parsed[str_k])
        for bool_k in ("use_batch", "file_batch"):
            if bool_k in parsed:
                state[bool_k] = bool(parsed[bool_k])
        for int_k in ("batch_size", "width", "height", "snap", "seed", "steps"):
            if int_k in parsed and parsed[int_k] is not None:
                try:
                    state[int_k] = int(float(parsed[int_k]))
                except Exception:
                    pass
        for flt_k in ("cfg", "refiner_pct", "refiner_scale"):
            if flt_k in parsed and parsed[flt_k] is not None:
                try:
                    state[flt_k] = float(parsed[flt_k])
                except Exception:
                    pass
        raw_toggles = parsed.get("toggles")
        if isinstance(raw_toggles, list):
            for i in range(min(4, len(raw_toggles))):
                t = raw_toggles[i]
                if isinstance(t, dict):
                    if "label" in t and str(t["label"]).strip():
                        state["toggles"][i]["label"] = str(t["label"]).strip()
                    if "value" in t:
                        state["toggles"][i]["value"] = bool(t["value"])
        return state
    except Exception:
        return state


class WFA_GenerationDeck:
    """
    WFA Generation Deck: Unified center-column cockpit dashboard card replacing 13–15+ individual
    primitive nodes (Package Name, Batch/UI Switches, Batch Size, Width×Height + Aspect Presets + Swap +
    Divisible-by Snap, Seed + Increment/Randomize, Steps, CFG, Sampler, Scheduler, Refiner % & Scale,
    and 4 customizable Feature Toggle pills).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "deck_state": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "Serialized generation deck state managed by the interactive cockpit UI.",
                    },
                ),
            },
        }

    RETURN_TYPES = (
        "STRING",
        "BOOLEAN",
        "BOOLEAN",
        "INT",
        "INT",
        "INT",
        "INT",
        "INT",
        "FLOAT",
        any_type,
        any_type,
        "FLOAT",
        "FLOAT",
        "BOOLEAN",
        "BOOLEAN",
        "BOOLEAN",
        "BOOLEAN",
    )
    RETURN_NAMES = (
        "package_name",
        "use_batch",
        "file_batch",
        "batch_size",
        "width",
        "height",
        "seed",
        "steps",
        "cfg",
        "sampler_name",
        "scheduler",
        "refiner_pct",
        "refiner_scale",
        "toggle_1",
        "toggle_2",
        "toggle_3",
        "toggle_4",
    )
    FUNCTION = "emit_deck"
    CATEGORY = COCKPIT_CATEGORY

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def emit_deck(self, deck_state: str = ""):
        st = _parse_deck_state(deck_state)
        snap = max(1, int(st["snap"]))
        w = _snap_dim(st["width"], snap)
        h = _snap_dim(st["height"], snap)
        b = max(1, int(st["batch_size"]))
        seed = max(0, int(st["seed"]))
        steps = max(1, int(st["steps"]))
        cfg = float(st["cfg"])
        ref_pct = float(st["refiner_pct"])
        ref_scale = float(st["refiner_scale"])
        toggles = st["toggles"]

        return (
            st["package_name"],
            bool(st["use_batch"]),
            bool(st["file_batch"]),
            b,
            w,
            h,
            seed,
            steps,
            cfg,
            st["sampler_name"],
            st["scheduler"],
            ref_pct,
            ref_scale,
            bool(toggles[0]["value"]),
            bool(toggles[1]["value"]),
            bool(toggles[2]["value"]),
            bool(toggles[3]["value"]),
        )


def _count_tokens_exact_or_est(text: str, clip=None) -> tuple[int, bool]:
    """
    Returns `(token_count, is_exact_clip)`.
    Strips `<lora:...>` syntax before counting so prompt-LoRA tags don't inflate token counts.
    """
    clean = _LORA_TAG_RE.sub("", text or "").strip()
    if not clean:
        return 0, clip is not None

    if clip is not None and hasattr(clip, "tokenize"):
        try:
            tokenized = clip.tokenize(clean, return_word_ids=True)
            streams = []
            if isinstance(tokenized, dict):
                streams = list(tokenized.values())
            elif isinstance(tokenized, (list, tuple)):
                streams = [tokenized]

            best_count = 0
            for stream in streams:
                if not isinstance(stream, (list, tuple)):
                    continue
                cnt = 0
                for chunk in stream:
                    if not isinstance(chunk, (list, tuple)):
                        continue
                    for item in chunk:
                        if isinstance(item, (list, tuple)) and len(item) >= 3:
                            if item[2] != 0:
                                cnt += 1
                if cnt > best_count:
                    best_count = cnt
            if best_count > 0:
                return best_count, True
        except Exception:
            pass

    # Fast word + punctuation subword estimate when `clip` is not connected
    raw_parts = _BPE_WORD_TOKEN_RE.findall(clean)
    est = 0
    for p in raw_parts:
        if len(p) <= 6 or not p.isalnum():
            est += 1
        else:
            est += math.ceil(len(p) / 5.5)
    return est, False


def _split_prompt_segments(text: str) -> list[str]:
    """Splits a prompt on top-level commas/newlines while keeping `(tag:1.2)` and `<lora:...>` intact."""
    if not text:
        return []
    segs: list[str] = []
    buf: list[str] = []
    depth_paren = 0
    depth_angle = 0
    depth_brace = 0

    for ch in text:
        if ch == "(":
            depth_paren += 1
        elif ch == ")" and depth_paren > 0:
            depth_paren -= 1
        elif ch == "<":
            depth_angle += 1
        elif ch == ">" and depth_angle > 0:
            depth_angle -= 1
        elif ch == "{":
            depth_brace += 1
        elif ch == "}" and depth_brace > 0:
            depth_brace -= 1

        if (ch == "," or ch == "\n") and depth_paren == 0 and depth_angle == 0 and depth_brace == 0:
            s = "".join(buf).strip()
            if s:
                segs.append(s)
            buf = []
        else:
            buf.append(ch)

    tail = "".join(buf).strip()
    if tail:
        segs.append(tail)
    return segs


class WFA_PromptInspector:
    """
    WFA Prompt Inspector: Merges `Final Prompt` readout + `Token Log` into a single dark-themed
    syntax-highlighted inspector panel with live token count, 1-click clipboard copy, unreplaced
    `/*PLACEHOLDER*/` warning detection, and a per-tag token breakdown view.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Connect your compiled `Final Prompt` string here.",
                    },
                ),
                "inspector_cache": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "Persists the last inspected prompt & token summary inside the UI panel.",
                    },
                ),
            },
            "optional": {
                "clip": (
                    "CLIP",
                    {
                        "tooltip": "Optional `CLIP` wire for 100% exact model tokenizer counts (otherwise uses fast BPE token estimation).",
                    },
                ),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("text", "token_count")
    OUTPUT_NODE = True
    FUNCTION = "inspect_prompt"
    CATEGORY = COCKPIT_CATEGORY

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def inspect_prompt(
        self,
        text: str = "",
        inspector_cache: str = "",
        clip=None,
        unique_id=None,
    ):
        prompt_str = str(text or "")
        total_tokens, is_exact = _count_tokens_exact_or_est(prompt_str, clip=clip)
        unreplaced = _PLACEHOLDER_COMMENT_RE.findall(prompt_str)
        loras_found = _LORA_TAG_RE.findall(prompt_str)

        segments = _split_prompt_segments(prompt_str)
        breakdown: list[dict] = []
        for seg in segments[:250]:
            if _LORA_TAG_RE.fullmatch(seg.strip()):
                breakdown.append({"tag": seg, "tokens": 0, "kind": "lora"})
            else:
                seg_toks, _ = _count_tokens_exact_or_est(seg, clip=clip)
                kind = "warn" if "/*" in seg else "tag"
                breakdown.append({"tag": seg, "tokens": seg_toks, "kind": kind})

        payload = {
            "text": prompt_str,
            "token_count": total_tokens,
            "chunks": max(1, math.ceil(total_tokens / 75)) if total_tokens > 0 else 0,
            "is_exact": is_exact,
            "lora_count": len(loras_found),
            "unreplaced_count": len(unreplaced),
            "breakdown": breakdown,
        }

        if PromptServer is not None and getattr(PromptServer, "instance", None) is not None and unique_id is not None:
            uid = unique_id[0] if isinstance(unique_id, list) else unique_id
            payload["node_id"] = str(uid)
            PromptServer.instance.send_sync("wfa-prompt-inspector-update", payload)

        return {"ui": {"wfa_inspector": [payload]}, "result": (prompt_str, total_tokens)}


NODE_CLASS_MAPPINGS = {
    "WFA_CharacterLoraCockpit": WFA_CharacterLoraCockpit,
    "WFA_GenerationDeck": WFA_GenerationDeck,
    "WFA_PromptInspector": WFA_PromptInspector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WFA_CharacterLoraCockpit": "WFA Character LoRA Cockpit ⚡ (WFA Suite)",
    "WFA_GenerationDeck": "WFA Generation Deck ⚡ (WFA Suite)",
    "WFA_PromptInspector": "WFA Prompt Inspector ⚡ (WFA Suite)",
}
