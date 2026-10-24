import os
import re
from functools import lru_cache
from .utils import SUITE_CATEGORY

_BANLISTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
    "banlists",
)
_BANLIST_FILE_CACHE = {}


@lru_cache(maxsize=128)
def _compile_simultaneous_literal(keys: tuple[str, ...], case_sensitive: bool) -> re.Pattern:
    """
    Compiles a single-pass alternation regex from literal search strings.
    Longer keys are placed first so longer substrings match before shorter prefixes.
    Cached via lru_cache so repeated runs with the same rules skip compilation entirely.
    """
    sorted_keys = sorted(keys, key=len, reverse=True)
    escaped = [re.escape(k) for k in sorted_keys]
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile("|".join(escaped), flags)


@lru_cache(maxsize=256)
def _compile_single_pattern(pattern_str: str, use_regex: bool, case_sensitive: bool) -> re.Pattern:
    """Cached single-rule regex compiler for regex or case-insensitive replacements."""
    expr = pattern_str if use_regex else re.escape(pattern_str)
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(expr, flags)


@lru_cache(maxsize=128)
def _compile_simultaneous_regex(patterns: tuple[str, ...], case_sensitive: bool) -> re.Pattern:
    """
    Compiles multiple regex patterns into a single pass using top-level capturing groups.
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    combined = "|".join(f"({p})" for p in patterns)
    return re.compile(combined, flags)


class _WAFindAndReplaceBase:
    """
    Base class for high-performance WA Find & Replace nodes.
    Supports both Simultaneous (single-pass compiled regex) and Sequential (chained) modes.
    """

    NUM_ENTRIES = 60

    @classmethod
    def INPUT_TYPES(cls):
        optional_inputs = {}
        for i in range(1, cls.NUM_ENTRIES + 1):
            optional_inputs[f"find_{i}"] = (
                "STRING",
                {
                    "default": "",
                    "multiline": False,
                    "tooltip": f"Search string #{i} to find in the input text (e.g. /*(MOOD)*/).",
                },
            )
            optional_inputs[f"replace_{i}"] = (
                "STRING",
                {
                    "default": "",
                    "multiline": False,
                    "tooltip": f"Replacement text #{i} that will replace matches of find_{i}.",
                },
            )

        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Input text in which all active find/replace rules will be applied.",
                    },
                ),
                "mode": (
                    ["simultaneous (single-pass)", "sequential (chained)"],
                    {
                        "default": "simultaneous (single-pass)",
                        "tooltip": (
                            "• simultaneous (single-pass): Replaces all find rules in one pass so earlier replacements are never modified by later rules.\n"
                            "• sequential (chained): Runs rule 1, then rule 2 on the result of rule 1, etc. (allows nested tags inside replacements)."
                        ),
                    },
                ),
                "case_sensitive": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": (
                            "• true: Uppercase/lowercase letters must match exactly (e.g. /*(MOOD)*/ only matches /*(MOOD)*/).\n"
                            "• false: Ignores uppercase/lowercase differences (matches /*(MOOD)*/, /*(mood)*/, and /*(Mood)*/)."
                        ),
                    },
                ),
                "use_regex": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": (
                            "• false (Recommended): Treats find strings as exact literal text (safe for special symbols like /*(TAG)*/).\n"
                            "• true: Treats find strings as Regular Expression (RegEx) patterns where symbols like *, (), [], | act as wildcards/groups."
                        ),
                    },
                ),
            },
            "optional": optional_inputs,
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "find_and_replace"
    CATEGORY = f"{SUITE_CATEGORY}/Strings"

    def find_and_replace(
        self,
        text: str,
        mode: str,
        case_sensitive: bool = True,
        use_regex: bool = False,
        **kwargs,
    ):
        if not text:
            return (text,)

        # Collect only non-empty active rules
        pairs: list[tuple[str, str]] = []
        for i in range(1, self.NUM_ENTRIES + 1):
            f_val = kwargs.get(f"find_{i}", "")
            if f_val:
                r_val = kwargs.get(f"replace_{i}", "") or ""
                # Skip no-op literal rules when case_sensitive is True
                if not use_regex and case_sensitive and f_val == r_val:
                    continue
                pairs.append((f_val, r_val))

        if not pairs:
            return (text,)

        is_simultaneous = mode.startswith("simultaneous")

        if is_simultaneous:
            if not use_regex:
                # Single-pass literal replacement using O(1) dict lookup per match
                lookup: dict[str, str] = {}
                ordered_keys: list[str] = []
                for f_val, r_val in pairs:
                    norm_key = f_val if case_sensitive else f_val.lower()
                    if norm_key not in lookup:
                        lookup[norm_key] = r_val
                        ordered_keys.append(f_val)

                pattern = _compile_simultaneous_literal(tuple(ordered_keys), case_sensitive)
                if case_sensitive:
                    result = pattern.sub(lambda m: lookup[m.group(0)], text)
                else:
                    result = pattern.sub(lambda m: lookup[m.group(0).lower()], text)
                return (result,)
            else:
                # Single-pass regex replacement
                patterns = tuple(f_val for f_val, _ in pairs)
                replacements = [r_val for _, r_val in pairs]
                # Count groups per sub-pattern so we can map m.lastindex accurately
                group_to_rule: dict[int, int] = {}
                current_group = 1
                for rule_idx, p in enumerate(patterns):
                    group_to_rule[current_group] = rule_idx
                    compiled_sub = _compile_single_pattern(p, True, case_sensitive)
                    current_group += 1 + compiled_sub.groups

                pattern = _compile_simultaneous_regex(patterns, case_sensitive)
                result = pattern.sub(
                    lambda m: replacements[group_to_rule[m.lastindex]],
                    text,
                )
                return (result,)

        else:
            # Sequential (Chained) Mode
            result = text
            if not use_regex and case_sensitive:
                # Native C-level str.replace is fastest for sequential exact literal strings
                for f_val, r_val in pairs:
                    if f_val in result:
                        result = result.replace(f_val, r_val)
            else:
                for f_val, r_val in pairs:
                    pattern = _compile_single_pattern(f_val, use_regex, case_sensitive)
                    result = pattern.sub(r_val, result)
            return (result,)


FIND_REPLACE_SIZES = (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)

_FIND_REPLACE_CLASSES = {}
_FIND_REPLACE_NAMES = {}

for _size in FIND_REPLACE_SIZES:
    _cls_name = f"WFA_FindAndReplace{_size}"
    _cls = type(
        _cls_name,
        (_WAFindAndReplaceBase,),
        {
            "__doc__": f"WFA Find & Replace {_size}: {_size}-entry string find and replace node.",
            "NUM_ENTRIES": _size,
        },
    )
    globals()[_cls_name] = _cls
    _FIND_REPLACE_CLASSES[_cls_name] = _cls
    _FIND_REPLACE_NAMES[_cls_name] = f"WFA Find & Replace {_size} ⚡ (WFA Suite)"


_COMMENT_PREFIX_RE = re.compile(r"^\s*/\*\s*\d+\s*\*/\s*")
_ANY_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/")
_WEIGHT_SUFFIX_RE = re.compile(r":\s*[-+]?\d*\.?\d+\s*$")


def _normalize_tag_key(raw: str) -> str:
    """Normalizes a tag for comparison: lowercase, underscores to spaces, collapsed whitespace."""
    s = _WEIGHT_SUFFIX_RE.sub("", raw.strip())
    return " ".join(s.replace("_", " ").lower().split())


def _compile_banlist_rules(banlist_str: str):
    """
    Parses a banlist string (stripping any /*...*/ comments) into:
    - exact_set: set of normalized tag strings
    - wildcard_regexes: list of compiled regexes for entries containing '*'
    - clean_entries: list of normalized entries (for partial/phrase modes and active_banlist output)
    """
    cleaned = _ANY_BLOCK_COMMENT_RE.sub("", banlist_str or "")
    raw_items = [item.strip() for item in re.split(r"[,\n\r]+", cleaned) if item.strip()]

    wrapper_chars = "\"'“”‘’()[]{}<>«»"
    exact_set: set[str] = set()
    wildcard_regexes: list[re.Pattern] = []
    clean_entries: list[str] = []

    for item in raw_items:
        core = item.strip(wrapper_chars).strip()
        norm = _normalize_tag_key(core)
        if not norm:
            continue
        clean_entries.append(norm)
        if "*" in norm:
            # Convert wildcard '*' into regex '.*'
            parts = [re.escape(p) for p in norm.split("*")]
            pat = re.compile(r"^" + r".*".join(parts) + r"$", re.IGNORECASE)
            wildcard_regexes.append(pat)
        else:
            exact_set.add(norm)

    return exact_set, wildcard_regexes, clean_entries


def _is_tag_banned(
    norm_tag: str,
    exact_set: set[str],
    wildcard_regexes: list[re.Pattern],
    clean_entries: list[str],
    match_mode: str,
) -> bool:
    if not norm_tag:
        return False

    if norm_tag in exact_set:
        return True

    for pat in wildcard_regexes:
        if pat.match(norm_tag):
            return True

    if match_mode.startswith("contains"):
        # Check if any banned word/phrase appears as a word or substring in norm_tag
        for entry in clean_entries:
            entry_clean = entry.replace("*", "").strip()
            if entry_clean and entry_clean in norm_tag:
                return True

    return False


def _strip_balanced_wrappers(prefix: str, suffix: str) -> tuple[str, str]:
    """
    If a single tag is wrapped in its own balanced parentheses/brackets like `(blue eyes:1.2)`,
    removes those balanced pairs while preserving any unbalanced outer group brackets like `(( tag1, tag2 ))`.
    """
    pairs = {")": "(", "]": "[", "}": "{"}
    p_list = list(prefix)
    s_list = list(suffix)

    while p_list and s_list:
        # Find last opening bracket in p_list and first matching closing bracket in s_list
        last_open_idx = -1
        for idx in range(len(p_list) - 1, -1, -1):
            if p_list[idx] in "([{":
                last_open_idx = idx
                break
        if last_open_idx == -1:
            break

        open_ch = p_list[last_open_idx]
        first_close_idx = -1
        for idx in range(len(s_list)):
            if s_list[idx] in ")]}" and pairs.get(s_list[idx]) == open_ch:
                first_close_idx = idx
                break
        if first_close_idx == -1:
            break

        p_list.pop(last_open_idx)
        s_list.pop(first_close_idx)

    return "".join(p_list), "".join(s_list)


def _filter_prompt_tags(text: str, banlist_str: str, match_mode: str) -> str:
    exact_set, wildcard_regexes, clean_entries = _compile_banlist_rules(banlist_str)
    if not clean_entries or not text:
        return text

    if match_mode.startswith("raw text"):
        result = text
        encl_chars = r"\"'‘’“”«»\(\)\[\]\{\}<>"
        for entry in clean_entries:
            entry_clean = entry.replace("*", "").strip()
            if not entry_clean:
                continue
            flex_pattern = r"[\s_]+".join(re.escape(w) for w in entry_clean.split())
            pattern = re.compile(
                r"(?<!\w)["
                + encl_chars
                + r"]*"
                + flex_pattern
                + r"(?::\s*[-+]?\d*\.?\d+)?["
                + encl_chars
                + r"]*(?!\w)",
                re.IGNORECASE,
            )
            result = pattern.sub("", result)
        result = re.sub(r"\s*,\s*,\s*", ", ", result)
        result = re.sub(r"\s+", " ", result)
        result = re.sub(r"\s+([,.;?!])", r"\1", result)
        return result.strip(" ,")

    # Tokenize by comma, pipe, or newline while keeping delimiters
    parts = re.split(r"([,|\n])", text)
    out_parts: list[str] = []

    wrapper_chars = " \t\"'“”‘’()[]{}<>«»"
    i = 0
    while i < len(parts):
        seg = parts[i]
        delim = parts[i + 1] if i + 1 < len(parts) else ""

        # Do not touch /*...*/ placeholder comments like /*(MOOD)*/
        if "/*" in seg and "*/" in seg:
            out_parts.append(seg + delim)
            i += 2
            continue

        # Separate leading wrapper chars, core tag, and trailing wrapper chars
        start_idx = 0
        while start_idx < len(seg) and seg[start_idx] in wrapper_chars:
            start_idx += 1
        end_idx = len(seg)
        while end_idx > start_idx and seg[end_idx - 1] in wrapper_chars:
            end_idx -= 1

        prefix = seg[:start_idx]
        core = seg[start_idx:end_idx]
        suffix = seg[end_idx:]

        # If suffix contains a weight like `:1.2)` where `:1.2` was inside `core`
        norm_core = _normalize_tag_key(core)

        if norm_core and _is_tag_banned(norm_core, exact_set, wildcard_regexes, clean_entries, match_mode):
            rem_prefix, rem_suffix = _strip_balanced_wrappers(prefix, suffix)
            kept_shell = rem_prefix + rem_suffix
            if delim == "\n" or delim == "|":
                out_parts.append(kept_shell + delim)
            else:
                # Comma delimiter is dropped along with the banned tag; keep only unbalanced group brackets
                if kept_shell.strip():
                    out_parts.append(kept_shell)
        else:
            out_parts.append(seg + delim)

        i += 2

    joined = "".join(out_parts)

    # Clean up empty parentheses/brackets and redundant commas/spaces left after tag removal
    prev = None
    while prev != joined:
        prev = joined
        joined = re.sub(r"\(\s*,?\s*\)", "", joined)
        joined = re.sub(r"\[\s*,?\s*\]", "", joined)
        joined = re.sub(r",\s*,+", ",", joined)
        joined = re.sub(r"([(\[{|])\s*,\s*", r"\1 ", joined)
        joined = re.sub(r"\{\s*\|\s*", "{ ", joined)
        joined = re.sub(r"\|\s*\|\s*", "| ", joined)
        joined = re.sub(r"\|\s*\}", " }", joined)
        joined = re.sub(r"\{\s*\}", "", joined)

    joined = re.sub(r"[ \t]{2,}", " ", joined)
    joined = re.sub(r"\s+,", ",", joined)
    return joined.strip().strip(",").strip()



class WFA_TextIndexSwitch:
    """
    WFA Text Index Switch: Multiline prompt/text selector with row numbers and
    alternating dark/light grey row shading in the UI.
    Each line (row 0, 1, 2, ...) corresponds to its row index.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                    },
                ),
                "select": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 9999,
                        "step": 1,
                        "tooltip": "Row index (0–99) to select and output. Tip: Click any row number in the left gutter to select it directly.",
                    },
                ),
                "strip_comment_index": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": "If enabled, automatically strips leading /*0*/, /*1*/, etc. from pasted prompts.",
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("STRING", "selected_index")
    FUNCTION = "select_line"
    CATEGORY = f"{SUITE_CATEGORY}/Strings"

    def select_line(self, text: str, select: int = 0, strip_comment_index: bool = True):
        if not text:
            return ("", select)

        lines = text.splitlines()
        if 0 <= select < len(lines):
            chosen = lines[select]
        else:
            chosen = ""

        if chosen and strip_comment_index:
            chosen = _COMMENT_PREFIX_RE.sub("", chosen)

        return (chosen.strip(), select)


class WFA_TagBanlistSwitch:
    """
    WFA Tag Banlist Switch: 100-row selectable tag banlist / prompt filter UI.
    Each row (0–99) holds a customizable list of banned tags (e.g. eye colors, facial features
    when a character is looking away). Supports /*LABEL*/ row comments, * wildcards, weighted tags,
    and preserves outer prompt grouping syntax.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Main prompt text to filter using the selected banlist row.",
                    },
                ),
                "banlists": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": (
                            "100-row Banlist table (0–99). Enter comma-separated tags to remove on each row.\n"
                            "Tip: You can label rows using /*LOOKING AWAY*/ at the start of a row, and use * wildcards like *eyes*."
                        ),
                    },
                ),
                "select": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 9999,
                        "step": 1,
                        "tooltip": "Row index (0–99) of the active banlist to apply. Click any row number in the left gutter to select it.",
                    },
                ),
                "match_mode": (
                    [
                        "exact tag (supports * wildcard)",
                        "contains word (remove any tag containing banned word)",
                        "raw text phrase removal",
                    ],
                    {
                        "default": "exact tag (supports * wildcard)",
                        "tooltip": (
                            "• exact tag (supports * wildcard): Removes tags matching the banned entry (ignores case, _ vs space, and (tag:1.2) weights). Supports * wildcards like *eyes*.\n"
                            "• contains word: Removes any comma-separated tag that contains the banned word (e.g. 'eyes' removes 'blue eyes', 'closed eyes', etc.).\n"
                            "• raw text phrase removal: Strips banned words/phrases directly from sentences or prose."
                        ),
                    },
                ),
            },
            "optional": {
                "extra_banlist": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Optional additional banned tags string to combine with the selected banlist row.",
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("text", "active_banlist", "selected_index")
    FUNCTION = "apply_banlist"
    CATEGORY = f"{SUITE_CATEGORY}/Strings"

    def apply_banlist(
        self,
        text: str,
        banlists: str = "",
        select: int = 0,
        match_mode: str = "exact tag (supports * wildcard)",
        extra_banlist: str = "",
    ):
        chosen_row = ""
        if banlists:
            lines = banlists.splitlines()
            if 0 <= select < len(lines):
                chosen_row = lines[select]

        combined_banlist = chosen_row
        if extra_banlist:
            combined_banlist = f"{chosen_row}, {extra_banlist}" if chosen_row else extra_banlist

        _, _, clean_entries = _compile_banlist_rules(combined_banlist)
        active_banlist_str = ", ".join(clean_entries)

        if not text or not clean_entries:
            return (text, active_banlist_str, select)

        filtered = _filter_prompt_tags(text, combined_banlist, match_mode)
        return (filtered, active_banlist_str, select)


def _get_banlist_files() -> list[str]:
    """Lists all .txt files inside ComfyUI-WA-Suite/banlists/ (including subfolders)."""
    os.makedirs(_BANLISTS_DIR, exist_ok=True)
    files: list[str] = []
    try:
        for root, _, filenames in os.walk(_BANLISTS_DIR):
            for fname in sorted(filenames):
                if fname.lower().endswith(".txt"):
                    rel = os.path.relpath(os.path.join(root, fname), _BANLISTS_DIR).replace("\\", "/")
                    files.append(rel)
    except Exception:
        pass
    if not files:
        files = ["banned_tags.txt"]
    return files


def _resolve_banlist_path(banlist_file: str) -> str | None:
    if not banlist_file:
        return None
    candidate = os.path.abspath(os.path.join(_BANLISTS_DIR, banlist_file))
    if os.path.isfile(candidate):
        return candidate
    return None


def _build_smart_phrase_regex(core: str) -> str:
    """Converts a banned tag phrase into a regex matching spaces/underscores and * wildcards."""
    parts = re.split(r"[\s_]+", core)
    token_exprs = []
    for p in parts:
        if not p:
            continue
        subparts = [re.escape(sp) for sp in p.split("*")]
        token_exprs.append(r"[\w-]*".join(subparts))
    return r"[\s_]+".join(token_exprs)


def _get_compiled_banlist_file(filepath: str, mode: str):
    """Loads and caches compiled patterns for a .txt banlist file keyed by (filepath, mtime, mode)."""
    try:
        mtime = os.path.getmtime(filepath)
    except Exception:
        mtime = 0.0

    cache_key = (filepath, mtime, mode)
    cached = _BANLIST_FILE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        raw_lines = [line.strip() for line in f if line.strip()]

    wrapper_chars = "\"'‘’“”«»()[]{}<>"

    if mode == "LP Tag Mode (RemoveBannedTagsFromTags)":
        banned_set = set()
        for line in raw_lines:
            if line.startswith("#") or line.startswith("//"):
                continue
            tok = line.rstrip(",").strip().lower()
            while tok and tok[0] in wrapper_chars:
                tok = tok[1:].strip()
            while tok and tok[-1] in wrapper_chars:
                tok = tok[:-1].strip()
            if tok:
                banned_set.add(tok)
                banned_set.add(tok.replace("_", " "))
                banned_set.add(tok.replace(" ", "_"))
        _BANLIST_FILE_CACHE[cache_key] = banned_set
        return banned_set

    if mode == "LP Text Mode (RemoveBannedTagsFromText)":
        encl_chars = r'\"\'‘’“”«»\(\)\[\]\{\}<>'
        # Sort longest first so multi-word phrases (e.g. 'red lips,') match before shorter suffixes ('lips,')
        sorted_lines = sorted(raw_lines, key=len, reverse=True)
        patterns = []
        for tag in sorted_lines:
            if tag.startswith("#") or tag.startswith("//"):
                continue
            patterns.append(
                re.compile(
                    r"(?<!\w)["
                    + re.escape(encl_chars)
                    + r"]*"
                    + re.escape(tag.lower())
                    + r"["
                    + re.escape(encl_chars)
                    + r"]*(?!\w)",
                    re.IGNORECASE,
                )
            )
        _BANLIST_FILE_CACHE[cache_key] = patterns
        return patterns

    # Default: "Smart Text & Tag Filter (recommended)"
    core_phrases: list[str] = []
    seen_cores: set[str] = set()
    for line in raw_lines:
        if line.startswith("#") or line.startswith("//"):
            continue
        cleaned = line.rstrip(",").strip()
        while cleaned and cleaned[0] in wrapper_chars:
            cleaned = cleaned[1:].strip()
        while cleaned and cleaned[-1] in wrapper_chars:
            cleaned = cleaned[:-1].strip()
        cleaned_lower = cleaned.lower()
        if cleaned_lower and cleaned_lower not in seen_cores:
            seen_cores.add(cleaned_lower)
            core_phrases.append(cleaned_lower)

    # Sort longest phrases first so 'blue eyeliner' / 'red lips' / 'dark-blue eyes' match before 'eyeliner' / 'lips' / 'blue eyes'
    core_phrases.sort(key=len, reverse=True)

    chunk_size = 400
    compiled_chunks: list[tuple[re.Pattern, re.Pattern]] = []
    for i in range(0, len(core_phrases), chunk_size):
        chunk = core_phrases[i : i + chunk_size]
        exprs = [_build_smart_phrase_regex(c) for c in chunk if c]
        if not exprs:
            continue
        alt = "(?:" + "|".join(exprs) + ")"
        # 1. Standalone bracketed/weighted tag e.g. (glasses), (blue eyes:1.2), [red eyes]
        wrapped_re = re.compile(
            r"[\(\[\{<\"'‘’“”«»]+\s*"
            + alt
            + r"(?:\s*:\s*-?\d+(?:\.\d+)?)?\s*[\)\]\}>\"'‘’“”«»]+\s*,?",
            re.IGNORECASE,
        )
        # 2. Bare or weighted tag in text/comma list e.g. blue eyes, or blue eyes:1.2
        bare_re = re.compile(
            r"(?<![\w-])"
            + alt
            + r"(?:\s*:\s*-?\d+(?:\.\d+)?)?(?![\w-])\s*,?",
            re.IGNORECASE,
        )
        compiled_chunks.append((wrapped_re, bare_re))

    _BANLIST_FILE_CACHE[cache_key] = compiled_chunks
    return compiled_chunks


class WFA_RemoveBannedTags:
    """
    WFA Remove Banned Tags: Compact file-based banned tag remover (upgraded from LevelPixel's
    RemoveBannedTagsFromText). Reads any selectable .txt banlist from `ComfyUI-WA-Suite/banlists/`
    and automatically re-evaluates whenever you edit and save the .txt file.
    """

    @classmethod
    def INPUT_TYPES(cls):
        files = _get_banlist_files()
        default_file = "banned_tags.txt" if "banned_tags.txt" in files else files[0]
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Input prompt or tag string to remove banned tags from.",
                    },
                ),
                "banlist_file": (
                    files,
                    {
                        "default": default_file,
                        "tooltip": (
                            "Select which .txt banlist file inside 'ComfyUI-WA-Suite/banlists/' to use.\n"
                            "Drop any number of custom .txt files into that folder and press R (or F5) to see them here."
                        ),
                    },
                ),
                "mode": (
                    [
                        "Smart Text & Tag Filter (recommended)",
                        "LP Text Mode (RemoveBannedTagsFromText)",
                        "LP Tag Mode (RemoveBannedTagsFromTags)",
                    ],
                    {
                        "default": "Smart Text & Tag Filter (recommended)",
                        "tooltip": (
                            "• Smart Text & Tag Filter: Works whether lines in .txt end with a comma or not, matches longest phrases first (so 'lips' never eats half of 'red lips'), matches spaces & underscores, and removes (tag:1.2) weights cleanly.\n"
                            "• LP Text Mode: LevelPixel's RemoveBannedTagsFromText regex behavior (sorted longest-first).\n"
                            "• LP Tag Mode: LevelPixel's RemoveBannedTagsFromTags comma-split token filter."
                        ),
                    },
                ),
                "enabled": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "Enabled",
                        "label_off": "Bypassed",
                        "tooltip": "Enable or bypass the banlist filter (when Bypassed, outputs the input text unchanged).",
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "remove_banned_tags"
    CATEGORY = f"{SUITE_CATEGORY}/Strings"

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    @classmethod
    def IS_CHANGED(cls, text="", banlist_file="banned_tags.txt", mode="", enabled=True):
        filepath = _resolve_banlist_path(banlist_file)
        mtime = os.path.getmtime(filepath) if filepath and os.path.isfile(filepath) else 0.0
        return f"{banlist_file}:{mtime}:{mode}:{enabled}"

    def remove_banned_tags(
        self,
        text: str,
        banlist_file: str = "banned_tags.txt",
        mode: str = "Smart Text & Tag Filter (recommended)",
        enabled: bool = True,
    ):
        if not text or not enabled:
            return (text,)

        filepath = _resolve_banlist_path(banlist_file)
        if not filepath:
            return (text,)

        compiled = _get_compiled_banlist_file(filepath, mode)
        if not compiled:
            return (text,)

        if mode == "LP Tag Mode (RemoveBannedTagsFromTags)":
            wrapper_chars = "\"'‘’“”«»()[]{}<>"
            tokens = text.split(",")
            kept_tokens = []
            for token in tokens:
                check = token.strip().lower()
                while check and check[0] in wrapper_chars:
                    check = check[1:].strip()
                while check and check[-1] in wrapper_chars:
                    check = check[:-1:].strip()
                if check in compiled:
                    continue
                kept_tokens.append(token)
            return (",".join(kept_tokens),)

        if mode == "LP Text Mode (RemoveBannedTagsFromText)":
            out = text
            for pattern in compiled:
                out = pattern.sub("", out)
            out = re.sub(r"\s+", " ", out)
            out = re.sub(r"\s+([,.;?!])", r"\1", out)
            return (out.strip(),)

        # Smart Text & Tag Filter (recommended)
        orig_ended_with_comma = text.rstrip().endswith(",")
        out = text
        for wrapped_re, bare_re in compiled:
            out = wrapped_re.sub("", out)
            out = bare_re.sub("", out)

        # Clean up spacing, empty groups, and leftover duplicate/leading/trailing commas
        out = re.sub(r",\s*([\)\]\}>])", r"\1", out)
        out = re.sub(r"([\(\[\{<])\s*,\s*", r"\1", out)
        out = re.sub(r"[\(\[\{<]\s*(?::\s*-?\d+(?:\.\d+)?)?\s*[\)\]\}>]\s*,?", "", out)
        out = re.sub(r"[ \t]+", " ", out)
        out = re.sub(r"\s+([,.;?!\)\]\}>])", r"\1", out)
        out = re.sub(r"([\(\[\{<])\s+", r"\1", out)
        out = re.sub(r"(?:,\s*){2,}", ", ", out)
        out = re.sub(r"^\s*,\s*", "", out)
        out = out.strip()
        if out.endswith(",") and not orig_ended_with_comma:
            out = out[:-1].rstrip()

        return (out,)


NODE_CLASS_MAPPINGS = {
    **_FIND_REPLACE_CLASSES,
    "WFA_TextIndexSwitch": WFA_TextIndexSwitch,
    "WFA_TagBanlistSwitch": WFA_TagBanlistSwitch,
    "WFA_RemoveBannedTags": WFA_RemoveBannedTags,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **_FIND_REPLACE_NAMES,
    "WFA_TextIndexSwitch": "WFA Text Index Switch ⚡ (WFA Suite)",
    "WFA_TagBanlistSwitch": "WFA Tag Banlist Switch ⚡ (WFA Suite)",
    "WFA_RemoveBannedTags": "WFA Remove Banned Tags ⚡ (WFA Suite)",
}
