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

_ILLEGAL_WIN_CHARS_RE = re.compile(r'[<>:"|?*\x00-\x1f]')
_COMMENT_PREFIX_RE = re.compile(r"^\s*/\*.*?\*/\s*")

_SEPARATOR_MAP = {
    "underscore": "_",
    "space": " ",
    "dash": "-",
    "none": "",
}


def _sanitize_segment(seg: str) -> str:
    cleaned = _ILLEGAL_WIN_CHARS_RE.sub("_", seg).strip()
    # Windows disallows trailing dots or spaces on directory/file names
    cleaned = cleaned.rstrip(". ")
    return cleaned


def _resolve_model_name(model_input, prompt_graph: dict | None = None, unique_id=None) -> str:
    """
    Extracts a readable model/checkpoint name whether the user connects a STRING/COMBO
    directly OR wires a ComfyUI MODEL / PIPE link (by tracing the prompt graph upstream).
    """
    if model_input is None:
        return ""
    if isinstance(model_input, (str, int, float)):
        s = str(model_input).strip()
        return "" if s.lower() == "none" else s

    if isinstance(prompt_graph, dict) and unique_id is not None:
        uid = str(unique_id[0] if isinstance(unique_id, list) else unique_id)
        cur_node = prompt_graph.get(uid)
        link = cur_node.get("inputs", {}).get("model") if isinstance(cur_node, dict) else None
        visited: set[str] = set()

        while isinstance(link, list) and len(link) >= 1:
            src_id = str(link[0])
            if src_id in visited:
                break
            visited.add(src_id)
            src_node = prompt_graph.get(src_id)
            if not isinstance(src_node, dict):
                break
            src_inputs = src_node.get("inputs") or {}
            class_type = str(src_node.get("class_type", ""))

            # 1. Check standard model/checkpoint loader input keys
            found_link = None
            for key in ("ckpt_name", "unet_name", "model_name", "base_ckpt_name", "checkpoint", "diffusion_name"):
                if key in src_inputs:
                    val = src_inputs[key]
                    if isinstance(val, str) and val.strip() and val.strip().lower() != "none":
                        return val.strip()
                    if isinstance(val, list) and len(val) >= 1:
                        found_link = val
                        break
            if found_link is not None:
                link = found_link
                continue

            # 2. Handle WFA_TextIndexSwitch or string primitive nodes if ckpt_name was wired
            if class_type == "WFA_TextIndexSwitch" and isinstance(src_inputs.get("text"), str):
                lines = src_inputs["text"].splitlines()
                sel = src_inputs.get("select", 0)
                if isinstance(sel, int) and 0 <= sel < len(lines):
                    chosen = lines[sel]
                    if src_inputs.get("strip_comment_index", True):
                        chosen = _COMMENT_PREFIX_RE.sub("", chosen)
                    return chosen.strip()

            for skey in ("value", "string", "text"):
                sval = src_inputs.get(skey)
                if isinstance(sval, str) and sval.strip() and "\n" not in sval.strip():
                    return sval.strip()

            # 3. Handle Index Switch nodes (follow selected `input_{index}` if index is known)
            idx_val = src_inputs.get("index")
            if isinstance(idx_val, int) and f"input_{idx_val}" in src_inputs:
                next_l = src_inputs.get(f"input_{idx_val}")
                if isinstance(next_l, list):
                    link = next_l
                    continue

            # 4. Follow upstream model / pipe pass-through inputs (e.g. LoraLoader, Refiner, Reroute)
            next_link = None
            for mkey in ("model", "basic_pipe", "pipe", "input", "anything"):
                if isinstance(src_inputs.get(mkey), list):
                    next_link = src_inputs[mkey]
                    break
            if next_link is None:
                for v in src_inputs.values():
                    if isinstance(v, list) and len(v) == 2:
                        next_link = v
                        break
            link = next_link

    for attr in ("ckpt_name", "model_name", "name"):
        val = getattr(model_input, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()

    return ""


def _format_lora_stack(lora_stack) -> str:
    """
    Converts a LORA_STACK (list of tuples from Efficiency Nodes, ComfyRoll, EasyUse, etc.)
    or a string into '<lora:name:model_weight:clip_weight>' format.
    """
    if lora_stack is None:
        return ""
    if isinstance(lora_stack, str):
        return lora_stack.strip()
    if not isinstance(lora_stack, (list, tuple)):
        return str(lora_stack).strip()

    formatted: list[str] = []
    for item in lora_stack:
        if not item:
            continue
        if isinstance(item, str):
            s = item.strip()
            if s and s.lower() != "none":
                formatted.append(s)
            continue
        if isinstance(item, (list, tuple)):
            name = str(item[0]).strip() if len(item) >= 1 and item[0] is not None else ""
            if not name or name.lower() == "none":
                continue
            if len(item) >= 3:
                try:
                    m_wt = round(float(item[1]), 4)
                except Exception:
                    m_wt = item[1]
                try:
                    c_wt = round(float(item[2]), 4)
                except Exception:
                    c_wt = item[2]
                formatted.append(f"<lora:{name}:{m_wt}:{c_wt}>")
            elif len(item) == 2:
                try:
                    m_wt = round(float(item[1]), 4)
                except Exception:
                    m_wt = item[1]
                formatted.append(f"<lora:{name}:{m_wt}>")
            else:
                formatted.append(f"<lora:{name}:1.0:1.0>")
    return " ".join(formatted)


def _get_base_output_dir() -> str:
    if folder_paths is not None:
        try:
            return folder_paths.get_output_directory()
        except Exception:
            pass
    return os.path.abspath("output")


def _resolve_paths(
    subfolder: str,
    character: str,
    char_folder: bool,
    prompt_index,
    separator: str,
    save_mode: str,
) -> tuple[str, str]:
    """
    Returns `(txt_filepath, image_path_prefix)`.
    Example with subfolder='T2I MAIN', character='SubjectA', char_folder=True, prompt_index=1, separator='underscore':
      - txt_filepath:      `<output>/T2I MAIN/SubjectA/SubjectA_1.txt`
      - image_path_prefix: `T2I MAIN/SubjectA/SubjectA_1_`
    """
    base_output = _get_base_output_dir()
    sub = (subfolder or "").strip()

    is_abs = bool(sub and os.path.isabs(sub))
    if is_abs:
        drive, tail = os.path.splitdrive(sub)
        sub_parts = [_sanitize_segment(p) for p in re.split(r"[\\/]+", tail) if _sanitize_segment(p)]
        target_dir = os.path.join(drive + os.sep, *sub_parts) if sub_parts else (drive + os.sep)
        rel_dir_parts: list[str] = list(sub_parts)
    else:
        sub_parts = [_sanitize_segment(p) for p in re.split(r"[\\/]+", sub) if _sanitize_segment(p)]
        target_dir = os.path.join(base_output, *sub_parts) if sub_parts else base_output
        rel_dir_parts = list(sub_parts)

    char_raw = (character or "").strip()
    if char_raw.lower().endswith(".txt"):
        char_raw = char_raw[:-4].strip()

    char_parts = [_sanitize_segment(p) for p in re.split(r"[\\/]+", char_raw) if _sanitize_segment(p)]
    if len(char_parts) > 1:
        extra_dirs = char_parts if char_folder else char_parts[:-1]
        if extra_dirs:
            target_dir = os.path.join(target_dir, *extra_dirs)
            rel_dir_parts.extend(extra_dirs)
        char_base = char_parts[-1]
    elif len(char_parts) == 1:
        char_base = char_parts[0]
        if char_folder:
            target_dir = os.path.join(target_dir, char_base)
            rel_dir_parts.append(char_base)
    else:
        char_base = ""

    idx_str = ""
    if prompt_index is not None:
        if isinstance(prompt_index, (list, tuple)) and len(prompt_index) > 0:
            idx_str = _sanitize_segment(str(prompt_index[0]))
        else:
            idx_str = _sanitize_segment(str(prompt_index))

    sep_char = _SEPARATOR_MAP.get(separator, "_")
    if char_base and idx_str:
        stem = f"{char_base}{sep_char}{idx_str}"
    elif char_base:
        stem = char_base
    elif idx_str:
        stem = idx_str
    else:
        stem = "prompt"

    os.makedirs(target_dir, exist_ok=True)
    filepath = os.path.join(target_dir, f"{stem}.txt")

    if save_mode == "auto_number" and os.path.exists(filepath):
        counter = 1
        while True:
            candidate = os.path.join(target_dir, f"{stem}_{counter:02d}.txt")
            if not os.path.exists(candidate):
                filepath = candidate
                break
            counter += 1

    rel_prefix_dir = "/".join(rel_dir_parts)
    image_prefix = f"{rel_prefix_dir}/{stem}_" if rel_prefix_dir else f"{stem}_"

    return filepath, image_prefix


class WFA_SavePromptTxt:
    """
    WFA Save Prompt .txt: All-in-one model, LoRA, and prompt logger that saves structured .txt
    files and outputs a matching `image_path` prefix (`subfolder/character/character_index_`)
    ready to wire directly into Save Image nodes.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "subfolder": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": (
                            "Top-level folder inside ComfyUI's 'output' directory (e.g. 'T2I MAIN').\n"
                            "Leave empty to use 'ComfyUI/output/' directly, or enter an absolute path (e.g. 'D:/Outputs/Project').\n"
                            "Missing folders are created automatically."
                        ),
                    },
                ),
                "character": (
                    "STRING",
                    {
                        "default": "output",
                        "multiline": False,
                        "tooltip": (
                            "Subject/group name used both as a sub-subfolder (`subfolder/character/`) "
                            "and as the base filename (`character_index.txt`). Can also be wired from a STRING node."
                        ),
                    },
                ),
                "char_folder": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "Yes",
                        "label_off": "No",
                        "tooltip": "When Yes, automatically places files inside a `<subfolder>/<character>/` sub-subfolder.",
                    },
                ),
                "separator": (
                    ["underscore", "space", "dash", "none"],
                    {
                        "default": "underscore",
                        "tooltip": "Character placed between `character` and `prompt_index` in the filename (e.g. 'name_1.txt' or 'name 1.txt').",
                    },
                ),
                "save_mode": (
                    ["overwrite", "append", "auto_number"],
                    {
                        "default": "overwrite",
                        "tooltip": (
                            "• overwrite: Replaces the .txt file if it already exists.\n"
                            "• append: Adds the new log entry to the bottom of the existing .txt file.\n"
                            "• auto_number: Never overwrites — creates '_01.txt', '_02.txt', etc. if the file exists."
                        ),
                    },
                ),
                "headers": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "label_on": "Shown",
                        "label_off": "Hidden",
                        "tooltip": "When Shown, adds section labels ([MODEL], [USED LORAS], [RAW PROMPT], [FINAL PROMPT], etc.) above each non-empty block.",
                    },
                ),
                "enabled": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "Enabled",
                        "label_off": "Bypassed",
                        "tooltip": "Enable or bypass writing the .txt file to disk (`image_path` and `text` outputs still work when Bypassed).",
                    },
                ),
            },
            "optional": {
                "prompt_index": (
                    any_type,
                    {
                        "tooltip": "Optional batch/prompt index (accepts INT or STRING directly — e.g. wire straight from WFA Loop Iterator `index`).",
                    },
                ),
                "model": (
                    any_type,
                    {
                        "tooltip": "Connect the used checkpoint/model name (STRING / COMBO) OR wire a MODEL / PIPE link directly to log which model was used.",
                    },
                ),
                "lora_stack": (
                    any_type,
                    {
                        "tooltip": "Connect a LORA_STACK directly (converts to `<lora:name:model_wt:clip_wt>` automatically) or a LoRA STRING.",
                    },
                ),
                "raw_prompt": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Raw positive prompt (before wildcard/tag expansion or refinement).",
                    },
                ),
                "raw_negative": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Raw negative prompt.",
                    },
                ),
                "refined_prompt": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Refined / intermediate positive prompt.",
                    },
                ),
                "final_prompt": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Final positive prompt used for generation.",
                    },
                ),
                "final_negative": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Final negative prompt used for generation.",
                    },
                ),
                "trigger": (
                    any_type,
                    {
                        "tooltip": (
                            "Optional execution-order trigger if nothing downstream is wired from `image_path`.\n"
                            "Note: Leave unconnected if you wire `image_path` into your Save Image node."
                        ),
                    },
                ),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "prompt": "PROMPT",
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("image_path", "text", "filepath")
    FUNCTION = "save_prompt_txt"
    OUTPUT_NODE = True
    CATEGORY = f"{SUITE_CATEGORY}/IO"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")

    def save_prompt_txt(
        self,
        subfolder: str = "",
        character: str = "output",
        char_folder: bool = True,
        separator: str = "underscore",
        save_mode: str = "overwrite",
        headers: bool = False,
        enabled: bool = True,
        prompt_index=None,
        model=None,
        lora_stack=None,
        raw_prompt: str = "",
        raw_negative: str = "",
        refined_prompt: str = "",
        final_prompt: str = "",
        final_negative: str = "",
        trigger=None,
        unique_id=None,
        prompt=None,
    ):
        model_str = _resolve_model_name(model, prompt_graph=prompt, unique_id=unique_id)
        lora_str = _format_lora_stack(lora_stack)

        sections = [
            ("MODEL", model_str),
            ("USED LORAS", lora_str),
            ("RAW PROMPT", raw_prompt),
            ("RAW NEGATIVE", raw_negative),
            ("REFINED PROMPT", refined_prompt),
            ("FINAL PROMPT", final_prompt),
            ("FINAL NEGATIVE", final_negative),
        ]

        blocks: list[str] = []
        for label, content in sections:
            if content is None:
                continue
            cleaned = str(content).strip()
            if not cleaned:
                continue
            if headers:
                blocks.append(f"[{label}]\n{cleaned}")
            else:
                blocks.append(cleaned)

        full_text = "\n\n".join(blocks)

        filepath, image_path = _resolve_paths(
            subfolder=subfolder,
            character=character,
            char_folder=char_folder,
            prompt_index=prompt_index,
            separator=separator,
            save_mode=save_mode,
        )

        if not enabled:
            return (image_path, full_text, "")

        if save_mode == "append" and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write("\n\n" + ("=" * 60) + "\n\n" + full_text + "\n")
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(full_text + ("\n" if full_text else ""))

        if PromptServer is not None and getattr(PromptServer, "instance", None) is not None and unique_id is not None:
            uid = unique_id[0] if isinstance(unique_id, list) else unique_id
            base_out = _get_base_output_dir()
            try:
                if os.path.commonpath([os.path.abspath(base_out), os.path.abspath(filepath)]) == os.path.abspath(base_out):
                    display_path = os.path.relpath(filepath, base_out).replace("\\", "/")
                else:
                    display_path = os.path.basename(filepath)
            except Exception:
                display_path = os.path.basename(filepath)

            PromptServer.instance.send_sync(
                "wfa-save-txt-feedback",
                {
                    "node_id": str(uid),
                    "display_path": display_path,
                },
            )

        return (image_path, full_text, filepath)


NODE_CLASS_MAPPINGS = {
    "WFA_SavePromptTxt": WFA_SavePromptTxt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WFA_SavePromptTxt": "WFA Save Prompt .txt ⚡ (WFA Suite)",
}
