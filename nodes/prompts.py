import json
import os
import re

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

from .utils import SUITE_CATEGORY

UNTAGGED_LABEL = "UNTAGGED"

_SUITE_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_SUITE_PROMPTS_DIR = os.path.join(_SUITE_ROOT, "prompts")

_DIVIDER_SPLIT_RE = re.compile(r"(?:^|\n)[ \t]*-{3,}[ \t]*(?:\r?\n|$)")
_LABEL_BRACKET_RE = re.compile(r"\[\s*([A-Za-z0-9_+-]+)\s*\]")

# Legacy embedded negative metadata extractors:
# /*{{{896}}}[[[1152]]][[{2}]][{{2}}]{[{0.5}]}[}{1}{]{[}0.5{]}[{[false]}]{[[true]]}*/
_LEGACY_WIDTH_RE = re.compile(r"\{\{\{\s*(\d+)\s*\}\}\}")
_LEGACY_HEIGHT_RE = re.compile(r"\[\[\[\s*(\d+)\s*\]\]\]")
_LEGACY_BATCH_RE = re.compile(r"\[\[\{\s*(\d+)\s*\}\]\]")
_LEGACY_SDXL_IDX_RE = re.compile(r"\[\{\{\s*(-?\d+)\s*\}\}\]")
_LEGACY_SDXL_STR_RE = re.compile(r"\{\[\{\s*(-?\d+(?:\.\d+)?)\s*\}\]\}")
_LEGACY_ANIMA_IDX_RE = re.compile(r"\[\}\{\s*(-?\d+)\s*\}\{\]")
_LEGACY_ANIMA_STR_RE = re.compile(r"\{\[\}\s*(-?\d+(?:\.\d+)?)\s*\{\]\}")
_LEGACY_C1_RE = re.compile(r"\[\{\[\s*([A-Za-z0-9]+)\s*\]\}\]", re.IGNORECASE)
_LEGACY_C2_RE = re.compile(r"\{\[\[\s*([A-Za-z0-9]+)\s*\]\]\}", re.IGNORECASE)
_LEGACY_META_COMMENT_RE = re.compile(r"/\*\s*(?:\{\{\{|\[\[\[).*?\*/", re.DOTALL)

# Section keys recognized at start of line (or inline separated by | or ; on metadata lines)
_SECTION_KEYS_PATTERN = (
    r"positive|negative|title|name|labels|tags|"
    r"width|w|height|hight|h|size|resolution|"
    r"batch_size|batchsize|batch|"
    r"sdxl_lora|sdxl_lora_index|sdxl_index|lora_sdxl|"
    r"sdxl_strength|sdxl_lora_strength|sdxl_weight|sdxl_str|"
    r"anima_lora|anima_lora_index|anima_index|lora_anima|"
    r"anima_strength|anima_lora_strength|anima_weight|anima_str|"
    r"c[1-5]|char[1-5]|c[1-5]_lora|c[1-5]_enable|chars|characters"
)

_LINE_SECTION_RE = re.compile(
    rf"^[ \t]*(?P<key>{_SECTION_KEYS_PATTERN})[ \t]*:(?P<rest>.*)$",
    re.IGNORECASE,
)

_INLINE_META_PAIR_RE = re.compile(
    rf"(?:^|[|;])[ \t]*(?P<key>"
    r"width|w|height|hight|h|size|resolution|"
    r"batch_size|batchsize|batch|"
    r"sdxl_lora|sdxl_lora_index|sdxl_index|lora_sdxl|"
    r"sdxl_strength|sdxl_lora_strength|sdxl_weight|sdxl_str|"
    r"anima_lora|anima_lora_index|anima_index|lora_anima|"
    r"anima_strength|anima_lora_strength|anima_weight|anima_str|"
    r"c[1-5]|char[1-5]|c[1-5]_lora|c[1-5]_enable|chars|characters"
    rf")[ \t]*:[ \t]*(?P<val>[^|;]+)",
    re.IGNORECASE,
)

_PARSED_FILE_CACHE: dict[tuple[str, float], dict] = {}


def _parse_bool(val: str, default: bool = False) -> bool:
    if val is None:
        return default
    s = str(val).strip().lower()
    if not s:
        return default
    # Tolerate common fast-typing typos like 'flase' or 'ture'
    if s in ("true", "ture", "t", "1", "yes", "y", "on", "enable", "enabled"):
        return True
    if s in ("false", "flase", "fasle", "f", "0", "no", "n", "off", "disable", "disabled"):
        return False
    return default


def _parse_int(val: str, default: int = 0) -> int:
    try:
        return int(float(str(val).strip()))
    except Exception:
        return default


def _parse_float(val: str, default: float = 1.0) -> float:
    try:
        return float(str(val).strip())
    except Exception:
        return default


def _parse_lora_shorthand(val: str) -> tuple[int | None, float | None]:
    """Supports either `2` or shorthand `2:0.5` / `2 @ 0.5` / `2 0.5`."""
    s = str(val).strip()
    if not s:
        return None, None
    m = re.match(r"^(-?\d+)(?:\s*[:@]\s*|\s+)(-?\d+(?:\.\d+)?)$", s)
    if m:
        return int(m.group(1)), float(m.group(2))
    try:
        return int(float(s)), None
    except Exception:
        return None, None


def _get_prompt_search_dirs() -> list[str]:
    os.makedirs(_SUITE_PROMPTS_DIR, exist_ok=True)
    dirs: list[str] = []

    if folder_paths is not None:
        try:
            for p in folder_paths.get_folder_paths("inspire_prompts"):
                ap = os.path.abspath(p)
                if os.path.isdir(ap) and ap not in dirs:
                    dirs.append(ap)
        except Exception:
            pass

    # Fallback check for sibling ComfyUI-Inspire-Pack/prompts regardless of import order
    sibling_inspire = os.path.abspath(os.path.join(_SUITE_ROOT, "..", "ComfyUI-Inspire-Pack", "prompts"))
    if os.path.isdir(sibling_inspire) and sibling_inspire not in dirs:
        dirs.append(sibling_inspire)

    if _SUITE_PROMPTS_DIR not in dirs:
        dirs.append(_SUITE_PROMPTS_DIR)

    return dirs


def list_prompt_files() -> list[str]:
    files_list: list[str] = []
    for d in _get_prompt_search_dirs():
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fname in sorted(files):
                if fname.lower().endswith(".txt"):
                    rel = os.path.relpath(os.path.join(root, fname), d).replace("\\", "/")
                    if rel not in files_list:
                        files_list.append(rel)
    if not files_list:
        files_list = ["example_prompts.txt"]
    return files_list


def resolve_prompt_file_path(prompt_file: str) -> str | None:
    if not prompt_file:
        return None
    norm_rel = prompt_file.replace("/", os.sep).replace("\\", os.sep)
    if os.path.isabs(norm_rel) and os.path.isfile(norm_rel):
        return norm_rel
    for d in _get_prompt_search_dirs():
        cand = os.path.abspath(os.path.join(d, norm_rel))
        if os.path.isfile(cand):
            return cand
    return None


def _apply_meta_kv(meta: dict, key: str, val: str) -> None:
    k = key.strip().lower()
    v = val.strip()
    if not v:
        return

    if k in ("width", "w"):
        meta["width"] = _parse_int(v, meta.get("width"))
    elif k in ("height", "hight", "h"):
        meta["height"] = _parse_int(v, meta.get("height"))
    elif k in ("size", "resolution"):
        m = re.match(r"^(\d+)\s*[xX*,]\s*(\d+)$", v)
        if m:
            meta["width"] = int(m.group(1))
            meta["height"] = int(m.group(2))
    elif k in ("batch_size", "batchsize", "batch"):
        meta["batch_size"] = max(1, _parse_int(v, 1))
    elif k in ("sdxl_lora", "sdxl_lora_index", "sdxl_index", "lora_sdxl"):
        idx, wt = _parse_lora_shorthand(v)
        if idx is not None:
            meta["sdxl_lora"] = idx
        if wt is not None:
            meta["sdxl_strength"] = wt
    elif k in ("sdxl_strength", "sdxl_lora_strength", "sdxl_weight", "sdxl_str"):
        meta["sdxl_strength"] = _parse_float(v, 1.0)
    elif k in ("anima_lora", "anima_lora_index", "anima_index", "lora_anima"):
        idx, wt = _parse_lora_shorthand(v)
        if idx is not None:
            meta["anima_lora"] = idx
        if wt is not None:
            meta["anima_strength"] = wt
    elif k in ("anima_strength", "anima_lora_strength", "anima_weight", "anima_str"):
        meta["anima_strength"] = _parse_float(v, 1.0)
    elif k in ("chars", "characters"):
        tokens = {t.strip().upper() for t in re.split(r"[\s,|;/]+", v) if t.strip()}
        if "NONE" in tokens or "OFF" in tokens or "FALSE" in tokens:
            for ci in range(1, 6):
                meta[f"c{ci}"] = False
        else:
            for ci in range(1, 6):
                meta[f"c{ci}"] = (f"C{ci}" in tokens or f"CHAR{ci}" in tokens or str(ci) in tokens)
    else:
        for ci in range(1, 6):
            if k in (f"c{ci}", f"char{ci}", f"c{ci}_lora", f"c{ci}_enable"):
                meta[f"c{ci}"] = _parse_bool(v, False)
                break


def _parse_single_prompt_block(block: str, pending_title: str) -> dict | None:
    lines = block.splitlines()
    sections: dict[str, list[str]] = {}
    leading_lines: list[str] = []
    current_key: str | None = None
    meta: dict = {}

    multiline_keys = {"positive", "negative", "title", "name", "labels", "tags"}

    for line in lines:
        m = _LINE_SECTION_RE.match(line)
        if m:
            raw_key = m.group("key").lower()
            rest = m.group("rest")
            if raw_key in multiline_keys:
                current_key = raw_key
                sections.setdefault(current_key, []).append(rest)
            else:
                current_key = None
                # Support multiple metadata pairs on a single line e.g. `width: 896 | height: 1152 | c1: true`
                pairs = list(_INLINE_META_PAIR_RE.finditer(line))
                if len(pairs) > 1:
                    for pm in pairs:
                        _apply_meta_kv(meta, pm.group("key"), pm.group("val"))
                else:
                    _apply_meta_kv(meta, raw_key, rest)
        else:
            if current_key is not None:
                sections[current_key].append(line)
            else:
                if line.strip():
                    leading_lines.append(line.strip())

    if "positive" not in sections:
        return None

    positive_raw = "\n".join(sections.get("positive", [])).strip()
    negative_raw = "\n".join(sections.get("negative", [])).strip()

    # Determine raw title (explicit `title:`/`name:` -> inline leading line -> preceding divider title block)
    explicit_title = "\n".join(sections.get("title") or sections.get("name") or []).strip()
    if explicit_title:
        raw_title = explicit_title
    elif leading_lines and len(leading_lines) <= 2:
        raw_title = " ".join(leading_lines)
    else:
        raw_title = pending_title.strip()

    # Extract [LABEL] tags from title and optional `labels:`/`tags:` section
    found_labels: list[str] = []
    for lm in _LABEL_BRACKET_RE.finditer(raw_title):
        lbl = lm.group(1).upper()
        if lbl not in found_labels:
            found_labels.append(lbl)

    extra_labels_str = "\n".join(sections.get("labels") or sections.get("tags") or []).strip()
    if extra_labels_str:
        bracket_lbls = _LABEL_BRACKET_RE.findall(extra_labels_str)
        if bracket_lbls:
            for lbl in bracket_lbls:
                u = lbl.upper()
                if u not in found_labels:
                    found_labels.append(u)
        else:
            for tok in re.split(r"[\s,|;/]+", extra_labels_str):
                tok_clean = tok.strip("[] \t").upper()
                if tok_clean and tok_clean not in found_labels:
                    found_labels.append(tok_clean)

    clean_title = _LABEL_BRACKET_RE.sub("", raw_title)
    clean_title = re.sub(r"\s{2,}", " ", clean_title).strip(" -–—\t")
    if not clean_title and raw_title:
        clean_title = raw_title.strip()

    # Legacy metadata fallback from `negative:/*{{{896}}}[[[1152]]]...*/` when explicit section keys were omitted
    if "width" not in meta:
        mw = _LEGACY_WIDTH_RE.search(negative_raw)
        if mw:
            meta["width"] = int(mw.group(1))
    if "height" not in meta:
        mh = _LEGACY_HEIGHT_RE.search(negative_raw)
        if mh:
            meta["height"] = int(mh.group(1))
    if "batch_size" not in meta:
        mb = _LEGACY_BATCH_RE.search(negative_raw)
        if mb:
            meta["batch_size"] = max(1, int(mb.group(1)))
    if "sdxl_lora" not in meta:
        ms_i = _LEGACY_SDXL_IDX_RE.search(negative_raw)
        if ms_i:
            meta["sdxl_lora"] = int(ms_i.group(1))
    if "sdxl_strength" not in meta:
        ms_s = _LEGACY_SDXL_STR_RE.search(negative_raw)
        if ms_s:
            meta["sdxl_strength"] = float(ms_s.group(1))
    if "anima_lora" not in meta:
        ma_i = _LEGACY_ANIMA_IDX_RE.search(negative_raw)
        if ma_i:
            meta["anima_lora"] = int(ma_i.group(1))
    if "anima_strength" not in meta:
        ma_s = _LEGACY_ANIMA_STR_RE.search(negative_raw)
        if ma_s:
            meta["anima_strength"] = float(ma_s.group(1))
    if "c1" not in meta:
        mc1 = _LEGACY_C1_RE.search(negative_raw)
        if mc1:
            meta["c1"] = _parse_bool(mc1.group(1), False)
    if "c2" not in meta:
        mc2 = _LEGACY_C2_RE.search(negative_raw)
        if mc2:
            meta["c2"] = _parse_bool(mc2.group(1), False)

    negative_stripped = _LEGACY_META_COMMENT_RE.sub("", negative_raw).strip()

    return {
        "raw_title": raw_title,
        "clean_title": clean_title,
        "labels": found_labels,
        "positive": positive_raw,
        "negative_raw": negative_raw,
        "negative_stripped": negative_stripped,
        "meta": meta,
    }


def parse_prompt_text(text: str) -> dict:
    """
    Parses an entire prompt masterlist string into structured prompt entries and label counts
    with ZERO false console warnings on title headers, banners, or trailing scratchpad notes.
    """
    if not text or not text.strip():
        return {"entries": [], "labels": [], "label_counts": {}, "untagged_count": 0}

    raw_blocks = _DIVIDER_SPLIT_RE.split(text)
    entries: list[dict] = []
    pending_title = ""

    for blk in raw_blocks:
        stripped = blk.strip()
        if not stripped:
            continue

        # Fast check if this block contains a `positive:` prompt definition
        if re.search(r"(?:^|\n)[ \t]*positive[ \t]*:", stripped, re.IGNORECASE):
            parsed = _parse_single_prompt_block(stripped, pending_title)
            pending_title = ""
            if parsed is not None:
                entries.append(parsed)
        else:
            # Non-prompt block: if compact (1–3 non-empty lines), remember it as the title header for the next prompt;
            # larger blocks (like trailing tag reference scratchpads) are silently ignored without warnings.
            non_empty = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
            if 1 <= len(non_empty) <= 3 and len(stripped) <= 300:
                pending_title = " ".join(non_empty)
            else:
                pending_title = ""

    label_counts: dict[str, int] = {}
    ordered_labels: list[str] = []
    untagged_count = 0

    for entry in entries:
        lbls = entry["labels"]
        if not lbls:
            untagged_count += 1
        else:
            for lbl in lbls:
                if lbl not in label_counts:
                    label_counts[lbl] = 0
                    ordered_labels.append(lbl)
                label_counts[lbl] += 1

    return {
        "entries": entries,
        "labels": ordered_labels,
        "label_counts": label_counts,
        "untagged_count": untagged_count,
    }


def load_parsed_prompt_file(prompt_file: str, use_mtime_cache: bool = True) -> dict:
    filepath = resolve_prompt_file_path(prompt_file)
    if not filepath or not os.path.isfile(filepath):
        return {"entries": [], "labels": [], "label_counts": {}, "untagged_count": 0, "filepath": None}

    try:
        mtime = os.path.getmtime(filepath) if use_mtime_cache else -1.0
    except Exception:
        mtime = 0.0

    if use_mtime_cache:
        cache_key = (filepath, mtime)
        cached = _PARSED_FILE_CACHE.get(cache_key)
        if cached is not None:
            return cached

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    parsed = parse_prompt_text(text)
    parsed["filepath"] = filepath
    parsed["mtime"] = mtime

    if use_mtime_cache:
        # Keep cache bounded
        if len(_PARSED_FILE_CACHE) > 16:
            _PARSED_FILE_CACHE.clear()
        _PARSED_FILE_CACHE[(filepath, mtime)] = parsed

    return parsed


def filter_prompt_entries(parsed_data: dict, filter_mode: str, state_map: dict) -> list[dict]:
    """
    Filters parsed prompt entries using the UI checkbox state map `{LABEL: bool}`:
      - `Allowed Only (skip unchecked)`: Every label on the prompt must be checked (default True for unseen labels).
      - `Match ANY Checked (OR)`: Prompt passes if at least one of its labels (or UNTAGGED) is checked.
      - `Match ALL Checked (AND)`: Prompt passes if it contains all checked labels.
    """
    entries = parsed_data.get("entries", [])
    if not entries:
        return []

    def is_checked(lbl: str) -> bool:
        if not isinstance(state_map, dict):
            return True
        if lbl in state_map:
            return bool(state_map[lbl])
        # Brand-new labels default to checked so newly added tags aren't silently hidden
        return True

    mode = (filter_mode or "").strip()

    if mode.startswith("Match ANY"):
        matched = []
        for e in entries:
            lbls = e["labels"]
            if not lbls:
                if is_checked(UNTAGGED_LABEL):
                    matched.append(e)
            else:
                if any(is_checked(l) for l in lbls):
                    matched.append(e)
        return matched

    if mode.startswith("Match ALL"):
        all_known = list(parsed_data.get("labels", []))
        required = [l for l in all_known if is_checked(l)]
        want_untagged = parsed_data.get("untagged_count", 0) > 0 and is_checked(UNTAGGED_LABEL)
        if not required:
            return [e for e in entries if not e["labels"]] if want_untagged else []
        req_set = set(required)
        return [e for e in entries if req_set.issubset(set(e["labels"]))]

    # Default: "Allowed Only (skip unchecked)"
    matched = []
    for e in entries:
        lbls = e["labels"]
        if not lbls:
            if is_checked(UNTAGGED_LABEL):
                matched.append(e)
        else:
            if all(is_checked(l) for l in lbls):
                matched.append(e)
    return matched


if PromptServer is not None and getattr(PromptServer, "instance", None) is not None and web is not None:
    try:
        @PromptServer.instance.routes.get("/wfa/prompt_labels")
        async def _wfa_get_prompt_labels(request):
            prompt_file = request.rel_url.query.get("file", "")
            force_refresh = request.rel_url.query.get("refresh", "0") == "1"
            parsed = load_parsed_prompt_file(prompt_file, use_mtime_cache=not force_refresh)
            entries_summary = [
                {"labels": e["labels"]}
                for e in parsed.get("entries", [])
            ]
            return web.json_response(
                {
                    "ok": True,
                    "file": prompt_file,
                    "files": list_prompt_files(),
                    "total_prompts": len(entries_summary),
                    "labels": parsed.get("labels", []),
                    "label_counts": parsed.get("label_counts", {}),
                    "untagged_count": parsed.get("untagged_count", 0),
                    "entries": entries_summary,
                }
            )
    except Exception:
        pass


class WFA_PromptLabelFilter:
    """
    WFA Prompt Label Filter: Interactive ComfyUI canvas UI node that auto-detects all `[LABEL]`
    tags across titles in a prompt `.txt` file, renders clickable checkboxes with live prompt counts,
    and controls which prompts are passed to `WFA Batch Prompt Loader`.
    """

    @classmethod
    def INPUT_TYPES(cls):
        files = list_prompt_files()
        default_file = "MAIN.txt" if "MAIN.txt" in files else files[0]
        return {
            "required": {
                "prompt_file": (
                    files,
                    {
                        "default": default_file,
                        "tooltip": "Select the prompt masterlist `.txt` file to scan for `[LABEL]` title tags.",
                    },
                ),
                "filter_mode": (
                    [
                        "Allowed Only",
                        "Match ANY (OR)",
                        "Match ALL (AND)",
                    ],
                    {
                        "default": "Allowed Only",
                        "tooltip": (
                            "• Allowed Only: Passes prompts whose labels are ALL checked — unchecking any label (e.g. [PREG] or [M1]) skips every prompt carrying that label.\n"
                            "• Match ANY (OR): Passes any prompt that has at least 1 checked label.\n"
                            "• Match ALL (AND): Passes only prompts that have every checked label simultaneously."
                        ),
                    },
                ),
                "label_states": (
                    "STRING",
                    {
                        "default": "{}",
                        "multiline": True,
                        "tooltip": "Serialized checkbox state managed automatically by the interactive label UI.",
                    },
                ),
            },
            "optional": {
                "text_override": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Optional raw prompt list text wire (overrides `prompt_file` when connected).",
                    },
                ),
            },
        }

    RETURN_TYPES = ("WFA_PROMPT_FILTER", "INT", "INT")
    RETURN_NAMES = ("label_filter", "end_index", "count")
    FUNCTION = "build_filter"
    CATEGORY = f"{SUITE_CATEGORY}/Prompts"

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    @classmethod
    def IS_CHANGED(cls, prompt_file="", filter_mode="", label_states="{}", text_override=None):
        if text_override is not None:
            return f"override:{hash(text_override)}:{filter_mode}:{label_states}"
        fpath = resolve_prompt_file_path(prompt_file)
        mtime = os.path.getmtime(fpath) if fpath and os.path.isfile(fpath) else 0.0
        return f"{prompt_file}:{mtime}:{filter_mode}:{label_states}"

    def build_filter(
        self,
        prompt_file: str = "",
        filter_mode: str = "Allowed Only",
        label_states: str = "{}",
        text_override: str | None = None,
    ):
        try:
            state_map = json.loads(label_states) if label_states else {}
            if not isinstance(state_map, dict):
                state_map = {}
        except Exception:
            state_map = {}

        if text_override is not None and text_override.strip():
            parsed = parse_prompt_text(text_override)
        else:
            parsed = load_parsed_prompt_file(prompt_file, use_mtime_cache=True)

        filtered_entries = filter_prompt_entries(parsed, filter_mode, state_map)
        count = len(filtered_entries)
        end_index = max(0, count - 1)

        payload = {
            "prompt_file": prompt_file,
            "filter_mode": filter_mode,
            "state_map": state_map,
            "entries": filtered_entries,
            "total_unfiltered": len(parsed.get("entries", [])),
        }
        return (payload, end_index, count)


class WFA_BatchPromptLoader:
    """
    WFA Batch Prompt Loader: All-in-one replacement for Inspire's Load Prompts From File + Unzip Prompt
    + 9+ metadata regex extractor nodes. Understands prompt titles (zero false console warnings),
    supports both clean `key: value` sections (`width:`, `height:`, `sdxl_lora:`, `anima_lora:`, `c1:`..`c5:`)
    and legacy `/*{{{896}}}...*/` negative tags, and works standalone or controlled by `WFA Prompt Label Filter`.
    """

    @classmethod
    def INPUT_TYPES(cls):
        files = list_prompt_files()
        default_file = "MAIN.txt" if "MAIN.txt" in files else files[0]
        return {
            "required": {
                "prompt_file": (
                    files,
                    {
                        "default": default_file,
                        "tooltip": "Prompt `.txt` file to load when `label_filter` is not connected.",
                    },
                ),
                "index": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 999999,
                        "step": 1,
                        "tooltip": "0-based prompt index to output (wire straight from `WFA Loop Iterator` / `WFA Loop Shutdown` `index`).",
                    },
                ),
                "reload": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "Auto",
                        "label_off": "Cached",
                        "tooltip": "When Auto, automatically reloads from disk whenever the `.txt` file is edited and saved; otherwise reads from fast RAM cache.",
                    },
                ),
                "clean_title": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "Clean",
                        "label_off": "Raw",
                        "tooltip": "When Clean, removes `[LABEL]` tags from the `title` output string so only the readable title text remains.",
                    },
                ),
                "strip_meta": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "Clean",
                        "label_off": "Raw",
                        "tooltip": "When Clean, strips legacy `/*{{{width}}}[[[height]]]...*/` control blocks from `negative` while keeping all other `/*...*/` placeholders intact.",
                    },
                ),
                "default_width": (
                    "INT",
                    {
                        "default": 1024,
                        "min": 64,
                        "max": 8192,
                        "step": 8,
                        "tooltip": "Fallback width when a prompt does not specify `width:` (or legacy `{{{width}}}`).",
                    },
                ),
                "default_height": (
                    "INT",
                    {
                        "default": 1024,
                        "min": 64,
                        "max": 8192,
                        "step": 8,
                        "tooltip": "Fallback height when a prompt does not specify `height:` / `hight:` (or legacy `[[[height]]]`).",
                    },
                ),
            },
            "optional": {
                "label_filter": (
                    "WFA_PROMPT_FILTER",
                    {
                        "tooltip": "Optional control wire from `WFA Prompt Label Filter`. Overrides `prompt_file` and passes only prompts matching your checked UI labels.",
                    },
                ),
                "text_override": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Optional raw prompt list text wire (used when `label_filter` is not connected).",
                    },
                ),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = (
        "STRING",
        "STRING",
        "STRING",
        "INT",
        "INT",
        "INT",
        "INT",
        "FLOAT",
        "INT",
        "FLOAT",
        "BOOLEAN",
        "BOOLEAN",
        "BOOLEAN",
        "BOOLEAN",
        "BOOLEAN",
        "INT",
        "INT",
    )
    RETURN_NAMES = (
        "positive",
        "negative",
        "title",
        "width",
        "height",
        "batch_size",
        "sdxl_lora",
        "sdxl_strength",
        "anima_lora",
        "anima_strength",
        "c1_enable",
        "c2_enable",
        "c3_enable",
        "c4_enable",
        "c5_enable",
        "end_index",
        "count",
    )
    FUNCTION = "load_prompt"
    CATEGORY = f"{SUITE_CATEGORY}/Prompts"

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    @classmethod
    def IS_CHANGED(
        cls,
        prompt_file="",
        index=0,
        reload=True,
        clean_title=True,
        strip_meta=True,
        default_width=1024,
        default_height=1024,
        label_filter=None,
        text_override=None,
    ):
        if label_filter is not None:
            return float("NaN")
        if text_override is not None:
            return f"override:{hash(text_override)}:{index}:{clean_title}:{strip_meta}"
        if reload:
            fpath = resolve_prompt_file_path(prompt_file)
            mtime = os.path.getmtime(fpath) if fpath and os.path.isfile(fpath) else 0.0
            return f"{prompt_file}:{mtime}:{index}:{clean_title}:{strip_meta}:{default_width}:{default_height}"
        return f"{prompt_file}:{index}:{clean_title}:{strip_meta}:{default_width}:{default_height}"

    def load_prompt(
        self,
        prompt_file: str = "",
        index: int = 0,
        reload: bool = True,
        clean_title: bool = True,
        strip_meta: bool = True,
        default_width: int = 1024,
        default_height: int = 1024,
        label_filter=None,
        text_override: str | None = None,
        unique_id=None,
    ):
        if isinstance(label_filter, dict) and "entries" in label_filter:
            entries = label_filter["entries"]
        elif text_override is not None and text_override.strip():
            entries = parse_prompt_text(text_override)["entries"]
        else:
            entries = load_parsed_prompt_file(prompt_file, use_mtime_cache=True)["entries"]

        count = len(entries)
        end_index = max(0, count - 1)

        if count == 0:
            if PromptServer is not None and getattr(PromptServer, "instance", None) is not None and unique_id is not None:
                uid = unique_id[0] if isinstance(unique_id, list) else unique_id
                PromptServer.instance.send_sync(
                    "wfa-batch-prompt-feedback",
                    {
                        "node_id": str(uid),
                        "text": "⚠ 0 prompts matched active filter",
                        "warning": True,
                    },
                )
            return (
                "",
                "",
                "",
                int(default_width),
                int(default_height),
                1,
                0,
                1.0,
                0,
                1.0,
                False,
                False,
                False,
                False,
                False,
                0,
                0,
            )

        clamped_idx = max(0, min(int(index), count - 1))
        entry = entries[clamped_idx]
        meta = entry["meta"]

        pos = entry["positive"]
        neg = entry["negative_stripped"] if strip_meta else entry["negative_raw"]
        title_out = entry["clean_title"] if clean_title else entry["raw_title"]

        w = int(meta.get("width", default_width))
        h = int(meta.get("height", default_height))
        b = int(meta.get("batch_size", 1))
        sdxl_idx = int(meta.get("sdxl_lora", 0))
        sdxl_str = float(meta.get("sdxl_strength", 1.0))
        anima_idx = int(meta.get("anima_lora", 0))
        anima_str = float(meta.get("anima_strength", 1.0))
        c1 = bool(meta.get("c1", False))
        c2 = bool(meta.get("c2", False))
        c3 = bool(meta.get("c3", False))
        c4 = bool(meta.get("c4", False))
        c5 = bool(meta.get("c5", False))

        if PromptServer is not None and getattr(PromptServer, "instance", None) is not None and unique_id is not None:
            uid = unique_id[0] if isinstance(unique_id, list) else unique_id
            short_title = title_out if len(title_out) <= 34 else (title_out[:31] + "...")
            badge_txt = (
                f"[{clamped_idx}/{end_index}] {short_title} • {w}×{h}"
                if short_title
                else f"[{clamped_idx}/{end_index}] • {w}×{h}"
            )
            PromptServer.instance.send_sync(
                "wfa-batch-prompt-feedback",
                {
                    "node_id": str(uid),
                    "text": badge_txt,
                    "warning": False,
                },
            )

        return (
            pos,
            neg,
            title_out,
            w,
            h,
            b,
            sdxl_idx,
            sdxl_str,
            anima_idx,
            anima_str,
            c1,
            c2,
            c3,
            c4,
            c5,
            end_index,
            count,
        )


NODE_CLASS_MAPPINGS = {
    "WFA_BatchPromptLoader": WFA_BatchPromptLoader,
    "WFA_PromptLabelFilter": WFA_PromptLabelFilter,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WFA_BatchPromptLoader": "WFA Batch Prompt Loader ⚡ (WFA Suite)",
    "WFA_PromptLabelFilter": "WFA Prompt Label Filter ⚡ (WFA Suite)",
}
