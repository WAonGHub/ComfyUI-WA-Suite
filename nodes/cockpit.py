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
PIPE_TYPE = "WFA_PIPE"

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


def _clone_pipe(pipe) -> dict:
    if isinstance(pipe, dict):
        out = dict(pipe)
        if "c_enables" in out and isinstance(out["c_enables"], list):
            out["c_enables"] = list(out["c_enables"])
        return out
    return {}


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
    defaults = {"mode": "auto", "slots": _default_char_slots()}
    if not raw or not str(raw).strip():
        return defaults
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return defaults
        mode = str(parsed.get("mode") or "auto").strip().lower()
        if mode not in ("auto", "batch", "ui"):
            mode = "auto"
        raw_slots = parsed.get("slots")
        slots = _default_char_slots()
        if isinstance(raw_slots, list):
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
        return {"mode": mode, "slots": slots}
    except Exception:
        return defaults


def _resolve_character_loras(pipe: dict, send_ws: bool = True) -> dict:
    slots = pipe.get("char_slots")
    if not isinstance(slots, list) or len(slots) < 5:
        slots = _default_char_slots()

    c_enables = pipe.get("c_enables")
    if not isinstance(c_enables, list) or len(c_enables) < 5:
        c_enables = [None, None, None, None, None]

    char_mode = str(pipe.get("char_mode") or "auto").lower()
    if char_mode == "batch":
        eff_use_batch = True
    elif char_mode == "ui":
        eff_use_batch = False
    else:
        deck = pipe.get("deck")
        if isinstance(deck, dict) and "use_batch" in deck:
            eff_use_batch = bool(deck["use_batch"])
        else:
            eff_use_batch = any(v is not None for v in c_enables)

    resolved_active: list[bool] = []
    for i in range(5):
        slot = slots[i]
        wire_val = c_enables[i]
        if slot.get("override", False):
            is_on = bool(slot.get("ui_enable", False))
        elif eff_use_batch and wire_val is not None:
            is_on = bool(wire_val)
        else:
            is_on = bool(slot.get("ui_enable", False))
        resolved_active.append(is_on)

    active_char_count = sum(1 for a in resolved_active if a)
    is_multi = active_char_count >= 2

    stack_out: list[tuple[str, float, float]] = []
    lora_stack_in = pipe.get("lora_stack_in")
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
        strength = float(slot.get("str_multi", 0.50) if is_multi else slot.get("str_solo", 0.90))

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

    lora_tags_str = ", ".join(combined_tags)
    mode_lbl = "Multi" if is_multi else "Solo"
    summary_txt = (
        f"{mode_lbl} • " + ", ".join(active_summary_parts)
        if active_summary_parts
        else "0 Active Characters"
    )

    char_node_id = pipe.get("char_node_id")
    if (
        send_ws
        and char_node_id is not None
        and PromptServer is not None
        and getattr(PromptServer, "instance", None) is not None
    ):
        PromptServer.instance.send_sync(
            "wfa-char-cockpit-feedback",
            {
                "node_id": str(char_node_id),
                "resolved_active": resolved_active,
                "is_multi": is_multi,
                "eff_use_batch": eff_use_batch,
                "lora_tags": lora_tags_str,
                "summary": summary_txt,
            },
        )

    return {
        "lora_stack": stack_out,
        "lora_tags": lora_tags_str,
        "per_slot_tags": per_slot_tags,
        "resolved_active": resolved_active,
        "is_multi": is_multi,
        "eff_use_batch": eff_use_batch,
        "summary": summary_txt,
    }


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
        "pad_max": 1536,
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
        for int_k in ("batch_size", "width", "height", "snap", "pad_max", "seed", "steps"):
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


def _build_inspector_payload(text: str, clip=None) -> dict:
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

    return {
        "text": prompt_str,
        "token_count": total_tokens,
        "chunks": max(1, math.ceil(total_tokens / 75)) if total_tokens > 0 else 0,
        "is_exact": is_exact,
        "lora_count": len(loras_found),
        "unreplaced_count": len(unreplaced),
        "breakdown": breakdown,
    }


class WFA_CharacterLoraCockpit:
    """
    WFA Character LoRA Cockpit: Zero-clutter 5-slot (C1–C5) dashboard card using a single `WFA_PIPE`
    wire so no input/output socket stacks eat up dashboard space.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
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
                "pipe": (
                    PIPE_TYPE,
                    {
                        "tooltip": "Single WFA Cockpit Pipe wire. Chain all cockpit cards together cleanly.",
                    },
                ),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = (PIPE_TYPE,)
    RETURN_NAMES = ("pipe",)
    FUNCTION = "process_cockpit"
    CATEGORY = COCKPIT_CATEGORY

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def process_cockpit(self, cockpit_state: str = "", pipe=None, unique_id=None):
        out = _clone_pipe(pipe)
        state = _parse_char_cockpit_state(cockpit_state)
        uid = unique_id[0] if isinstance(unique_id, list) else unique_id

        out["char_mode"] = state["mode"]
        out["char_slots"] = state["slots"]
        if uid is not None:
            out["char_node_id"] = str(uid)

        out["resolved_char"] = _resolve_character_loras(out, send_ws=True)
        return (out,)


class WFA_GenerationDeck:
    """
    WFA Generation Deck: Zero-clutter center-column dashboard card with an interactive 2D Aspect Ratio
    & Resolution Pad, sampling/seed/refiner controls, and 4 renameable feature toggles — consolidated
    into a single `WFA_PIPE` wire.
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
            "optional": {
                "pipe": (
                    PIPE_TYPE,
                    {
                        "tooltip": "Single WFA Cockpit Pipe wire. Chain from Character LoRA Cockpit or Pipe In.",
                    },
                ),
            },
        }

    RETURN_TYPES = (PIPE_TYPE,)
    RETURN_NAMES = ("pipe",)
    FUNCTION = "emit_deck"
    CATEGORY = COCKPIT_CATEGORY

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def emit_deck(self, deck_state: str = "", pipe=None):
        out = _clone_pipe(pipe)
        st = _parse_deck_state(deck_state)
        snap = max(1, int(st["snap"]))
        st["width"] = _snap_dim(st["width"], snap)
        st["height"] = _snap_dim(st["height"], snap)
        st["batch_size"] = max(1, int(st["batch_size"]))
        st["seed"] = max(0, int(st["seed"]))
        st["steps"] = max(1, int(st["steps"]))

        out["deck"] = st
        if "char_slots" in out:
            out["resolved_char"] = _resolve_character_loras(out, send_ws=True)
        return (out,)


class WFA_PromptInspector:
    """
    WFA Prompt Inspector: Zero-clutter syntax-highlighted Final Prompt & Token Breakdown dashboard card
    connected via a single `WFA_PIPE` wire. Works both at the end of a pipe or chained upstream in the
    dashboard with `WFA Cockpit Pipe In` pushing live updates downstream.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
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
                "pipe": (
                    PIPE_TYPE,
                    {
                        "tooltip": "Single WFA Cockpit Pipe wire.",
                    },
                ),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = (PIPE_TYPE,)
    RETURN_NAMES = ("pipe",)
    OUTPUT_NODE = True
    FUNCTION = "inspect_prompt"
    CATEGORY = COCKPIT_CATEGORY

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def inspect_prompt(self, inspector_cache: str = "", pipe=None, unique_id=None):
        out = _clone_pipe(pipe)
        uid = unique_id[0] if isinstance(unique_id, list) else unique_id
        uid_str = str(uid) if uid is not None else None
        if uid_str is not None:
            out["inspector_node_id"] = uid_str

        payload = out.get("inspector_payload")
        if payload is None and out.get("final_prompt") is not None:
            payload = _build_inspector_payload(str(out["final_prompt"]), clip=out.get("clip"))
            out["inspector_payload"] = payload

        if isinstance(payload, dict):
            ws_payload = dict(payload)
            if uid_str is not None:
                ws_payload["node_id"] = uid_str
                if PromptServer is not None and getattr(PromptServer, "instance", None) is not None:
                    PromptServer.instance.send_sync("wfa-prompt-inspector-update", ws_payload)
            return {"ui": {"wfa_inspector": [ws_payload]}, "result": (out,)}

        return {"ui": {}, "result": (out,)}


class WFA_CockpitPipeIn:
    """
    WFA Cockpit Pipe In: Backend intake node that packs `c1_enable`..`c5_enable`, `lora_stack_in`,
    `final_prompt`, and `clip` into a single `WFA_PIPE` wire.
    Can be placed before the cockpit chain OR at the end of prompt building (receives `Pipe Out.pipe`
    + `final_prompt` + `clip` to update an upstream `WFA Prompt Inspector` with zero graph cycles).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "pipe": (
                    PIPE_TYPE,
                    {
                        "tooltip": "Optional incoming WFA Cockpit Pipe (e.g. from WFA Cockpit Pipe Out to push Final Prompt back to Prompt Inspector without cycles).",
                    },
                ),
                "c1_enable": ("BOOLEAN", {"forceInput": True, "tooltip": "Batch C1 enable flag."}),
                "c2_enable": ("BOOLEAN", {"forceInput": True, "tooltip": "Batch C2 enable flag."}),
                "c3_enable": ("BOOLEAN", {"forceInput": True, "tooltip": "Batch C3 enable flag."}),
                "c4_enable": ("BOOLEAN", {"forceInput": True, "tooltip": "Batch C4 enable flag."}),
                "c5_enable": ("BOOLEAN", {"forceInput": True, "tooltip": "Batch C5 enable flag."}),
                "lora_stack_in": ("LORA_STACK", {"tooltip": "Optional upstream LORA_STACK to merge."}),
                "final_prompt": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Compiled Final Prompt string for WFA Prompt Inspector.",
                    },
                ),
                "clip": (
                    "CLIP",
                    {
                        "tooltip": "Optional CLIP wire for 100% exact model tokenizer counts in WFA Prompt Inspector.",
                    },
                ),
            },
        }

    RETURN_TYPES = (PIPE_TYPE,)
    RETURN_NAMES = ("pipe",)
    OUTPUT_NODE = True
    FUNCTION = "pack_pipe"
    CATEGORY = COCKPIT_CATEGORY

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def pack_pipe(
        self,
        pipe=None,
        c1_enable: bool | None = None,
        c2_enable: bool | None = None,
        c3_enable: bool | None = None,
        c4_enable: bool | None = None,
        c5_enable: bool | None = None,
        lora_stack_in=None,
        final_prompt: str | None = None,
        clip=None,
    ):
        out = _clone_pipe(pipe)

        existing_c = out.get("c_enables")
        if not isinstance(existing_c, list) or len(existing_c) < 5:
            existing_c = [None, None, None, None, None]
        incoming_c = [c1_enable, c2_enable, c3_enable, c4_enable, c5_enable]
        for i in range(5):
            if incoming_c[i] is not None:
                existing_c[i] = bool(incoming_c[i])
        out["c_enables"] = existing_c

        if lora_stack_in is not None:
            out["lora_stack_in"] = list(lora_stack_in) if isinstance(lora_stack_in, list) else lora_stack_in

        if clip is not None:
            out["clip"] = clip

        if final_prompt is not None:
            out["final_prompt"] = str(final_prompt)
            payload = _build_inspector_payload(str(final_prompt), clip=out.get("clip"))
            out["inspector_payload"] = payload

            target_insp_id = out.get("inspector_node_id")
            if (
                target_insp_id is not None
                and PromptServer is not None
                and getattr(PromptServer, "instance", None) is not None
            ):
                ws_payload = dict(payload)
                ws_payload["node_id"] = str(target_insp_id)
                PromptServer.instance.send_sync("wfa-prompt-inspector-update", ws_payload)

        if "char_slots" in out and any(x is not None for x in incoming_c):
            out["resolved_char"] = _resolve_character_loras(out, send_ws=True)

        return {"ui": {}, "result": (out,)}


class WFA_CockpitPipeOut:
    """
    WFA Cockpit Pipe Out: Backend unpack node that extracts all Generation Deck settings, Character LoRA
    stacks/tags/switches, and Prompt Inspector outputs from a single `WFA_PIPE` wire.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pipe": (
                    PIPE_TYPE,
                    {
                        "tooltip": "Connect the `pipe` output from your chained WFA Cockpit dashboard cards.",
                    },
                ),
            },
            "optional": {
                "c1_enable": ("BOOLEAN", {"forceInput": True, "tooltip": "Optional Batch C1 enable override."}),
                "c2_enable": ("BOOLEAN", {"forceInput": True, "tooltip": "Optional Batch C2 enable override."}),
                "c3_enable": ("BOOLEAN", {"forceInput": True, "tooltip": "Batch C3 enable override."}),
                "c4_enable": ("BOOLEAN", {"forceInput": True, "tooltip": "Batch C4 enable override."}),
                "c5_enable": ("BOOLEAN", {"forceInput": True, "tooltip": "Batch C5 enable override."}),
                "lora_stack_in": ("LORA_STACK", {"tooltip": "Optional upstream LORA_STACK to merge."}),
            },
        }

    RETURN_TYPES = (
        PIPE_TYPE,
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
        "STRING",
        "INT",
    )
    RETURN_NAMES = (
        "pipe",
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
        "final_prompt",
        "token_count",
    )
    FUNCTION = "unpack_pipe"
    CATEGORY = COCKPIT_CATEGORY

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    def unpack_pipe(
        self,
        pipe=None,
        c1_enable: bool | None = None,
        c2_enable: bool | None = None,
        c3_enable: bool | None = None,
        c4_enable: bool | None = None,
        c5_enable: bool | None = None,
        lora_stack_in=None,
    ):
        out = _clone_pipe(pipe)

        existing_c = out.get("c_enables")
        if not isinstance(existing_c, list) or len(existing_c) < 5:
            existing_c = [None, None, None, None, None]
        incoming_c = [c1_enable, c2_enable, c3_enable, c4_enable, c5_enable]
        for i in range(5):
            if incoming_c[i] is not None:
                existing_c[i] = bool(incoming_c[i])
        out["c_enables"] = existing_c

        if lora_stack_in is not None:
            out["lora_stack_in"] = list(lora_stack_in) if isinstance(lora_stack_in, list) else lora_stack_in

        st = out.get("deck")
        if not isinstance(st, dict):
            st = _parse_deck_state("")

        snap = max(1, int(st.get("snap", 16)))
        w = _snap_dim(st.get("width", 896), snap)
        h = _snap_dim(st.get("height", 1152), snap)
        b = max(1, int(st.get("batch_size", 1)))
        seed = max(0, int(st.get("seed", 4260)))
        steps = max(1, int(st.get("steps", 28)))
        cfg = float(st.get("cfg", 3.5))
        ref_pct = float(st.get("refiner_pct", 0.30))
        ref_scale = float(st.get("refiner_scale", 1.30))
        toggles = st.get("toggles") or _default_deck_state(_FALLBACK_SAMPLERS, _FALLBACK_SCHEDULERS)["toggles"]

        char_res = _resolve_character_loras(out, send_ws=True)
        out["resolved_char"] = char_res

        per_tags = char_res["per_slot_tags"]
        res_act = char_res["resolved_active"]

        final_prompt_str = str(out.get("final_prompt") or "")
        insp_payload = out.get("inspector_payload")
        token_cnt = int(insp_payload.get("token_count", 0)) if isinstance(insp_payload, dict) else 0

        return (
            out,
            str(st.get("package_name", "Output_Set")),
            bool(st.get("use_batch", True)),
            bool(st.get("file_batch", False)),
            b,
            w,
            h,
            seed,
            steps,
            cfg,
            st.get("sampler_name", "er_sde"),
            st.get("scheduler", "simple"),
            ref_pct,
            ref_scale,
            bool(toggles[0]["value"]),
            bool(toggles[1]["value"]),
            bool(toggles[2]["value"]),
            bool(toggles[3]["value"]),
            char_res["lora_stack"],
            char_res["lora_tags"],
            per_tags[0],
            per_tags[1],
            per_tags[2],
            per_tags[3],
            per_tags[4],
            res_act[0],
            res_act[1],
            res_act[2],
            res_act[3],
            res_act[4],
            final_prompt_str,
            token_cnt,
        )


NODE_CLASS_MAPPINGS = {
    "WFA_CharacterLoraCockpit": WFA_CharacterLoraCockpit,
    "WFA_GenerationDeck": WFA_GenerationDeck,
    "WFA_PromptInspector": WFA_PromptInspector,
    "WFA_CockpitPipeIn": WFA_CockpitPipeIn,
    "WFA_CockpitPipeOut": WFA_CockpitPipeOut,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WFA_CharacterLoraCockpit": "WFA Character LoRA Cockpit ⚡ (WFA Suite)",
    "WFA_GenerationDeck": "WFA Generation Deck ⚡ (WFA Suite)",
    "WFA_PromptInspector": "WFA Prompt Inspector ⚡ (WFA Suite)",
    "WFA_CockpitPipeIn": "WFA Cockpit Pipe In ⚡ (WFA Suite)",
    "WFA_CockpitPipeOut": "WFA Cockpit Pipe Out ⚡ (WFA Suite)",
}
