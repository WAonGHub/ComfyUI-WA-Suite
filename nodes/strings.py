import re
from functools import lru_cache
from .utils import SUITE_CATEGORY


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
            optional_inputs[f"find_{i}"] = ("STRING", {"default": "", "multiline": False})
            optional_inputs[f"replace_{i}"] = ("STRING", {"default": "", "multiline": False})

        return {
            "required": {
                "text": ("STRING", {"forceInput": True}),
                "mode": (
                    ["simultaneous (single-pass)", "sequential (chained)"],
                    {"default": "simultaneous (single-pass)"},
                ),
                "case_sensitive": ("BOOLEAN", {"default": True}),
                "use_regex": ("BOOLEAN", {"default": False}),
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


NODE_CLASS_MAPPINGS = {
    **_FIND_REPLACE_CLASSES,
    "WFA_TextIndexSwitch": WFA_TextIndexSwitch,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **_FIND_REPLACE_NAMES,
    "WFA_TextIndexSwitch": "WFA Text Index Switch ⚡ (WFA Suite)",
}
