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

_SEPARATOR_MAP = {
    "space": " ",
    "underscore": "_",
    "dash": "-",
    "none": "",
}


def _sanitize_segment(seg: str) -> str:
    cleaned = _ILLEGAL_WIN_CHARS_RE.sub("_", seg).strip()
    # Windows disallows trailing dots or spaces on directory/file names
    cleaned = cleaned.rstrip(". ")
    return cleaned


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
            # Strip trailing .safetensors / .pt only if user didn't want it?
            # Note: TSC_LoRA_Stack2String keeps item[0] verbatim (including .safetensors & subfolder)
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


def _resolve_target_txt_path(
    subfolder: str,
    character: str,
    prompt_index,
    separator: str,
    save_mode: str,
) -> str:
    base_output = _get_base_output_dir()
    sub = (subfolder or "").strip()

    if sub and os.path.isabs(sub):
        drive, tail = os.path.splitdrive(sub)
        parts = [_sanitize_segment(p) for p in re.split(r"[\\/]+", tail) if _sanitize_segment(p)]
        target_dir = os.path.join(drive + os.sep, *parts) if parts else (drive + os.sep)
    else:
        parts = [_sanitize_segment(p) for p in re.split(r"[\\/]+", sub) if _sanitize_segment(p)]
        target_dir = os.path.join(base_output, *parts) if parts else base_output

    char_raw = (character or "").strip()
    if char_raw.lower().endswith(".txt"):
        char_raw = char_raw[:-4].strip()

    # Support optional nested path inside `character` e.g. "Quintuplets/Nakano Miku 3"
    char_parts = [_sanitize_segment(p) for p in re.split(r"[\\/]+", char_raw) if _sanitize_segment(p)]
    if len(char_parts) > 1:
        target_dir = os.path.join(target_dir, *char_parts[:-1])
        char_base = char_parts[-1]
    elif len(char_parts) == 1:
        char_base = char_parts[0]
    else:
        char_base = ""

    idx_str = ""
    if prompt_index is not None:
        if isinstance(prompt_index, (list, tuple)) and len(prompt_index) > 0:
            idx_str = _sanitize_segment(str(prompt_index[0]))
        else:
            idx_str = _sanitize_segment(str(prompt_index))

    sep_char = _SEPARATOR_MAP.get(separator, " ")
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

    return filepath


class WFA_SavePromptTxt:
    """
    WFA Save Prompt .txt: All-in-one prompt & LoRA logger that replaces 8+ string concat,
    LoRA stack converter, filename builder, and Save Text nodes with a single compact node.
    Builds `<ComfyUI output>/<subfolder>/<character><sep><prompt_index>.txt` automatically.
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
                            "Subfolder inside ComfyUI's 'output' directory (e.g. 'Nakano Miku' or 'Series/Miku').\n"
                            "Leave empty to save directly in 'ComfyUI/output/', or enter an absolute path (e.g. 'D:/Prompts/Miku').\n"
                            "Missing folders are created automatically."
                        ),
                    },
                ),
                "character": (
                    "STRING",
                    {
                        "default": "prompt",
                        "multiline": False,
                        "tooltip": "Character or base filename for the .txt file (e.g. 'Nakano Miku 3'). Can also be wired from a STRING node.",
                    },
                ),
                "separator": (
                    ["space", "underscore", "dash", "none"],
                    {
                        "default": "space",
                        "tooltip": "Character placed between `character` and `prompt_index` in the filename (e.g. 'Nakano Miku 3 1.txt' with 'space').",
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
                        "tooltip": "When Shown, adds section labels ([USED LORAS], [RAW PROMPT], [FINAL PROMPT], etc.) above each non-empty block.",
                    },
                ),
                "enabled": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "Enabled",
                        "label_off": "Bypassed",
                        "tooltip": "Enable or bypass writing the .txt file to disk.",
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
                "lora_stack": (
                    any_type,
                    {
                        "tooltip": "Connect a LORA_STACK directly (automatically converts to `<lora:name:model_wt:clip_wt>` without needing a LoRA String converter node) or a LoRA STRING.",
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
                        "tooltip": "Optional execution-order trigger (e.g. connect IMAGE or LATENT if you only want the .txt written after sampling finishes).",
                    },
                ),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("text", "filepath")
    FUNCTION = "save_prompt_txt"
    OUTPUT_NODE = True
    CATEGORY = f"{SUITE_CATEGORY}/IO"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")

    def save_prompt_txt(
        self,
        subfolder: str = "",
        character: str = "prompt",
        separator: str = "space",
        save_mode: str = "overwrite",
        headers: bool = False,
        enabled: bool = True,
        prompt_index=None,
        lora_stack=None,
        raw_prompt: str = "",
        raw_negative: str = "",
        refined_prompt: str = "",
        final_prompt: str = "",
        final_negative: str = "",
        trigger=None,
        unique_id=None,
    ):
        lora_str = _format_lora_stack(lora_stack)

        sections = [
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

        if not enabled:
            return (full_text, "")

        filepath = _resolve_target_txt_path(
            subfolder=subfolder,
            character=character,
            prompt_index=prompt_index,
            separator=separator,
            save_mode=save_mode,
        )

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

        return (full_text, filepath)


NODE_CLASS_MAPPINGS = {
    "WFA_SavePromptTxt": WFA_SavePromptTxt,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WFA_SavePromptTxt": "WFA Save Prompt .txt ⚡ (WFA Suite)",
}
