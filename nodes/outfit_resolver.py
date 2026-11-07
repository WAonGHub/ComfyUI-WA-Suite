import os
import re

try:
    from server import PromptServer
except ImportError:
    PromptServer = None

from .utils import SUITE_CATEGORY

PROMPTS_CATEGORY = f"{SUITE_CATEGORY}/Prompts"

_SUITE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RULES_DIR = os.path.join(_SUITE_DIR, "rules")

_RULES_FILE_CACHE: dict[tuple[str, float, str], dict] = {}

_WEIGHT_SUFFIX_RE = re.compile(r"\s*:\s*[-+]?\d+(?:\.\d+)?\s*$")
_NEGATED_PREFIX_RE = re.compile(r"^(?:no|not|without)\s+", re.IGNORECASE)
_LORA_OR_ANGLE_TAG_RE = re.compile(r"^<[^>]+>$")
_INLINE_HASH_COMMENT_RE = re.compile(r"(?:^|\s+)#.*$")
# Matches `[Name: tag1, tag2, ...]` character blocks while ignoring `[from:to:0.5]` step syntax
_CHAR_BLOCK_RE = re.compile(r"\[([A-Za-z][A-Za-z0-9_ -]{0,28}):([^\[\]]+)\]")
_CHAR_SECTION_COMMENT_RE = re.compile(r"/\*\s*(C[1-5]|CHAR\s*[1-5]|GLOBAL|SCENE)\s*:?\s*\*/", re.IGNORECASE)
_STEP_EDIT_SUFFIX_RE = re.compile(r":\s*\d*\.?\d+\s*$")


def _get_rule_files() -> list[str]:
    os.makedirs(_RULES_DIR, exist_ok=True)
    files: list[str] = []
    try:
        for root, _, filenames in os.walk(_RULES_DIR):
            for fname in sorted(filenames):
                if fname.lower().endswith(".txt"):
                    rel = os.path.relpath(os.path.join(root, fname), _RULES_DIR).replace("\\", "/")
                    files.append(rel)
    except Exception:
        pass
    if not files:
        files = ["outfit_conflicts.txt"]
    return files


def _resolve_rules_path(rules_file: str) -> str | None:
    if not rules_file:
        return None
    candidate = os.path.abspath(os.path.join(_RULES_DIR, str(rules_file)))
    if os.path.isfile(candidate):
        return candidate
    return None


def _normalize_phrase(raw: str) -> str:
    s = str(raw or "").strip()
    s = _WEIGHT_SUFFIX_RE.sub("", s)
    s = s.replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def _extract_segment_parts(seg: str) -> tuple[str, str, str, str, str]:
    """
    Splits a comma-delimited segment into `(prefix, core_raw, weight_str, suffix, norm_core)`.
    Example: `" ((white_bra:1.15))"` -> `(" ((", "white_bra", ":1.15", "))", "white bra")`.
    """
    wrapper_open = " \t\"'“”‘’([{«"
    wrapper_close = " \t\"'“”‘’)]}»"

    start = 0
    while start < len(seg) and seg[start] in wrapper_open:
        start += 1
    end = len(seg)
    while end > start and seg[end - 1] in wrapper_close:
        end -= 1

    prefix = seg[:start]
    inner = seg[start:end]
    suffix = seg[end:]

    wt_match = _WEIGHT_SUFFIX_RE.search(inner)
    if wt_match:
        core_raw = inner[: wt_match.start()]
        weight_str = inner[wt_match.start() :]
    else:
        core_raw = inner
        weight_str = ""

    norm_core = _normalize_phrase(core_raw)
    return prefix, core_raw, weight_str, suffix, norm_core


def _strip_balanced_wrappers(prefix: str, suffix: str) -> tuple[str, str, bool]:
    """
    Removes balanced wrapper pairs `( ... )`, `[ ... ]`, `{ ... }` belonging to a single segment,
    while preserving any unbalanced outer group brackets.
    Returns `(rem_prefix, rem_suffix, had_unmatched_closing_paren)`.
    """
    pairs = {")": "(", "]": "[", "}": "{"}
    p_list = list(prefix)
    s_list = list(suffix)

    while p_list and s_list:
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

    rem_p = "".join(p_list)
    rem_s = "".join(s_list)
    unmatched_close = any(ch in ")]}" for ch in s_list)
    return rem_p, rem_s, unmatched_close


def _compile_single_atom(expr: str) -> tuple[re.Pattern, bool]:
    """
    Compiles a single tag pattern (`~word`, `*wildcard*`, or exact phrase) into `(regex, allow_negated)`.
    """
    raw = expr.strip()
    is_word_mode = False
    if raw.startswith("~"):
        is_word_mode = True
        raw = raw[1:].strip()

    norm = _normalize_phrase(raw)
    allow_negated = bool(_NEGATED_PREFIX_RE.match(norm))

    if is_word_mode:
        # Word-boundary match anywhere inside a normalized tag (e.g. `~bra` matches `white lace bra`, NOT `braid`)
        parts = [re.escape(p) for p in norm.split("*")]
        body = r".*".join(parts)
        pat = re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])", re.IGNORECASE)
    elif "*" in norm:
        parts = [re.escape(p) for p in norm.split("*")]
        pat = re.compile(r"^" + r".*".join(parts) + r"$", re.IGNORECASE)
    else:
        pat = re.compile(r"^" + re.escape(norm) + r"$", re.IGNORECASE)

    return pat, allow_negated


class _CompiledGroup:
    """Matches a normalized tag against positive patterns/subgroups minus negative `-exclude` patterns."""

    def __init__(self):
        self.includes: list[tuple[re.Pattern, bool]] = []
        self.excludes: list[tuple[re.Pattern, bool]] = []
        self.include_refs: list[str] = []
        self.exclude_refs: list[str] = []

    def matches_tag(self, norm_tag: str, groups_map: dict, _seen: set | None = None) -> bool:
        if not norm_tag:
            return False
        if _seen is None:
            _seen = set()

        is_neg_tag = bool(_NEGATED_PREFIX_RE.match(norm_tag))

        # 1. Check exclusions first
        for pat, _ in self.excludes:
            if pat.search(norm_tag):
                return False
        for ref in self.exclude_refs:
            if ref not in _seen and ref in groups_map:
                if groups_map[ref].matches_tag(norm_tag, groups_map, _seen | {ref}):
                    return False

        # 2. Check inclusions
        for pat, allow_neg in self.includes:
            if is_neg_tag and not allow_neg:
                continue
            if pat.search(norm_tag):
                return True
        for ref in self.include_refs:
            if ref not in _seen and ref in groups_map:
                if groups_map[ref].matches_tag(norm_tag, groups_map, _seen | {ref}):
                    return True

        return False


def _build_group_from_csv(csv_str: str, known_groups: dict) -> _CompiledGroup:
    grp = _CompiledGroup()
    for raw_item in csv_str.split(","):
        tok = raw_item.strip()
        if not tok:
            continue
        is_excl = tok.startswith("-")
        if is_excl:
            tok = tok[1:].strip()
        if not tok:
            continue
        if tok in known_groups:
            if is_excl:
                grp.exclude_refs.append(tok)
            else:
                grp.include_refs.append(tok)
        else:
            compiled = _compile_single_atom(tok)
            if is_excl:
                grp.excludes.append(compiled)
            else:
                grp.includes.append(compiled)
    return grp


def _parse_condition_expr(expr: str, known_groups: dict, known_views: dict) -> list[list[dict]]:
    """
    Parses a `WHEN` or `UNLESS` expression into DNF: `OR` of `AND` terms.
    Comma `,` = OR; Plus `+` = AND; leading `!` = NOT.
    """
    or_branches: list[list[dict]] = []
    if not expr or not expr.strip():
        return or_branches

    for branch_str in expr.split(","):
        branch_str = branch_str.strip()
        if not branch_str:
            continue
        and_terms: list[dict] = []
        for term_raw in branch_str.split("+"):
            t = term_raw.strip()
            if not t:
                continue
            negated = False
            if t.startswith("!"):
                negated = True
                t = t[1:].strip()
            if not t:
                continue

            if t.upper() == "ANY":
                and_terms.append({"kind": "any", "negated": negated})
            elif t.upper().startswith("VIEW:"):
                vname = t[5:].strip().upper()
                and_terms.append({"kind": "view", "view": vname, "negated": negated})
            elif t in known_views and t not in known_groups:
                and_terms.append({"kind": "view", "view": t, "negated": negated})
            elif t in known_groups:
                and_terms.append({"kind": "group", "group_name": t, "negated": negated})
            else:
                grp = _build_group_from_csv(t, known_groups)
                and_terms.append({"kind": "inline_group", "group": grp, "negated": negated})

        if and_terms:
            or_branches.append(and_terms)
    return or_branches


def _parse_view_clause(expr: str) -> list[tuple[str, bool]]:
    """Parses `VIEW BACK, SIDE` or `VIEW !BACK` or `VIEW ANY`."""
    items: list[tuple[str, bool]] = []
    for part in expr.split(","):
        p = part.strip()
        if not p:
            continue
        neg = False
        if p.startswith("!"):
            neg = True
            p = p[1:].strip()
        if p.upper().startswith("VIEW:"):
            p = p[5:].strip()
        if p:
            items.append((p.upper(), neg))
    return items


def _strip_line_comments(line: str) -> str:
    """Strips `# ...` comments and full-line `// ...` comments while keeping `/*...*/` placeholders intact."""
    s = line.strip()
    if not s or s.startswith("#") or s.startswith("//"):
        return ""
    s = _INLINE_HASH_COMMENT_RE.sub("", s).strip()
    return s


def _compile_rulesheet(raw_text: str) -> dict:
    views: dict[str, _CompiledGroup] = {}
    groups: dict[str, _CompiledGroup] = {}
    stage1_rules: list[dict] = []
    combo_rules: list[dict] = []
    neg_rules: list[dict] = []

    for raw_line in raw_text.splitlines():
        line = _strip_line_comments(raw_line)
        if not line:
            continue

        # 1. @view NAME = ...
        if line.lower().startswith("@view "):
            rest = line[6:].strip()
            if "=" in rest:
                name, rhs = rest.split("=", 1)
                vname = name.strip().upper()
                if vname:
                    views[vname] = _build_group_from_csv(rhs, groups)
            continue

        # 2. @group NAME = ... or @mod NAME = ...
        if line.lower().startswith("@group ") or line.lower().startswith("@mod "):
            rest = line.split(None, 1)[1] if " " in line else ""
            if "=" in rest:
                name, rhs = rest.split("=", 1)
                gname = name.strip()
                if gname:
                    groups[gname] = _build_group_from_csv(rhs, groups)
            continue

        # 3. Pipe-separated rule lines
        clauses = [c.strip() for c in line.split("|") if c.strip()]
        if not clauses:
            continue

        head = clauses[0]
        tail_clauses = clauses[1:]

        when_expr = None
        unless_expr = None
        view_items: list[tuple[str, bool]] = []
        placeholder_str: str | None = None
        plus_neg_tags: list[str] = []

        for cl in tail_clauses:
            low = cl.lower()
            if low.startswith("when "):
                when_expr = _parse_condition_expr(cl[5:], groups, views)
            elif low.startswith("unless "):
                unless_expr = _parse_condition_expr(cl[7:], groups, views)
            elif low.startswith("view "):
                view_items = _parse_view_clause(cl[5:])
            elif low.startswith("placeholder "):
                placeholder_str = cl[12:].strip()
            elif low.startswith("+neg "):
                plus_neg_tags.extend([t.strip() for t in cl[5:].split(",") if t.strip()])

        head_low = head.lower()
        if head_low.startswith("hide "):
            target_str = head[5:].strip()
            target_grp = _build_group_from_csv(target_str, groups)
            stage1_rules.append(
                {
                    "action": "HIDE",
                    "target": target_grp,
                    "when": when_expr,
                    "unless": unless_expr,
                    "views": view_items,
                    "plus_neg": plus_neg_tags,
                }
            )
        elif head_low.startswith("replace "):
            rest = head[8:].strip()
            if "=>" in rest:
                lhs, rhs = rest.split("=>", 1)
                target_grp = _build_group_from_csv(lhs.strip(), groups)
                stage1_rules.append(
                    {
                        "action": "REPLACE",
                        "target": target_grp,
                        "replacement": rhs.strip(),
                        "replacement_norm": _normalize_phrase(rhs.strip()),
                        "when": when_expr,
                        "unless": unless_expr,
                        "views": view_items,
                        "plus_neg": plus_neg_tags,
                    }
                )
        elif head_low.startswith("combo "):
            rest = head[6:].strip()
            if "=>" in rest:
                lhs, rhs = rest.split("=>", 1)
                req_parts = [p.strip() for p in lhs.split("+") if p.strip()]
                req_groups = [_build_group_from_csv(p, groups) for p in req_parts]
                inject_str = rhs.strip().rstrip(",").strip()
                _, _, _, _, inject_norm = _extract_segment_parts(inject_str)
                combo_rules.append(
                    {
                        "req_groups": req_groups,
                        "inject": inject_str,
                        "inject_norm": inject_norm,
                        "when": when_expr,
                        "unless": unless_expr,
                        "views": view_items,
                        "placeholder": placeholder_str,
                        "plus_neg": plus_neg_tags,
                    }
                )
        elif head_low.startswith("neg "):
            neg_list = [t.strip() for t in head[4:].split(",") if t.strip()]
            neg_rules.append(
                {
                    "neg_tags": neg_list,
                    "when": when_expr,
                    "unless": unless_expr,
                    "views": view_items,
                }
            )

    return {
        "views": views,
        "groups": groups,
        "stage1": stage1_rules,
        "combos": combo_rules,
        "negs": neg_rules,
    }


def _get_compiled_rules(filepath: str | None, extra_rules: str = "") -> dict:
    mtime = 0.0
    if filepath and os.path.isfile(filepath):
        try:
            mtime = os.path.getmtime(filepath)
        except Exception:
            mtime = 0.0

    key = (filepath or "", mtime, extra_rules or "")
    cached = _RULES_FILE_CACHE.get(key)
    if cached is not None:
        return cached

    raw = ""
    if filepath and os.path.isfile(filepath):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
    if extra_rules and extra_rules.strip():
        raw = raw + "\n" + extra_rules

    compiled = _compile_rulesheet(raw)
    _RULES_FILE_CACHE[key] = compiled
    return compiled


def _tokenize_prompt_segments(text: str) -> list[dict]:
    """
    Splits prompt on `,` or `\n` while isolating `/*...*/` comments and `<...>` LoRA/embedding tags
    into their own `is_special=True` tokens (even when glued directly onto tags without commas,
    such as `/*[SKIRT], */pleated skirt` or `<lora:model:0.8>1girl`).
    """
    segments: list[dict] = []
    n = len(text)
    buf: list[str] = []
    depth_brace = 0
    i = 0

    def flush(delim: str):
        raw_seg = "".join(buf)
        buf.clear()
        stripped = raw_seg.strip()
        if not stripped:
            if raw_seg or delim:
                segments.append(
                    {
                        "raw": raw_seg,
                        "delim": delim,
                        "is_special": True,
                        "norm": "",
                        "alive": True,
                    }
                )
            return

        prefix, core_raw, weight_str, suffix, norm_core = _extract_segment_parts(raw_seg)
        segments.append(
            {
                "raw": raw_seg,
                "delim": delim,
                "is_special": False,
                "prefix": prefix,
                "core_raw": core_raw,
                "weight_str": weight_str,
                "suffix": suffix,
                "norm": norm_core,
                "alive": True,
            }
        )

    while i < n:
        ch = text[i]

        # 1. Isolate `/* ... */` comment / placeholder blocks as standalone special tokens
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            end_comment = text.find("*/", i + 2)
            if end_comment != -1:
                leading_ws = ""
                if buf:
                    buffered = "".join(buf)
                    if buffered.strip():
                        flush("")
                    else:
                        leading_ws = buffered
                        buf.clear()
                comment_raw = leading_ws + text[i : end_comment + 2]
                i = end_comment + 2
                d = ""
                if depth_brace == 0 and i < n and text[i] in (",", "\n"):
                    d = text[i]
                    i += 1
                segments.append(
                    {
                        "raw": comment_raw,
                        "delim": d,
                        "is_special": True,
                        "norm": "",
                        "alive": True,
                    }
                )
                continue

        # 2. Isolate `<...>` LoRA / textual-inversion tags as standalone special tokens
        if ch == "<" and depth_brace == 0:
            end_angle = text.find(">", i + 1)
            if end_angle != -1 and "\n" not in text[i : end_angle + 1]:
                leading_ws = ""
                if buf:
                    buffered = "".join(buf)
                    if buffered.strip():
                        flush("")
                    else:
                        leading_ws = buffered
                        buf.clear()
                angle_raw = leading_ws + text[i : end_angle + 1]
                i = end_angle + 1
                d = ""
                if i < n and text[i] in (",", "\n"):
                    d = text[i]
                    i += 1
                segments.append(
                    {
                        "raw": angle_raw,
                        "delim": d,
                        "is_special": True,
                        "norm": "",
                        "alive": True,
                    }
                )
                continue

        if ch == "{":
            depth_brace += 1
        elif ch == "}" and depth_brace > 0:
            depth_brace -= 1

        if (ch == "," or ch == "\n") and depth_brace == 0:
            flush(ch)
            i += 1
            continue

        buf.append(ch)
        i += 1

    if buf:
        flush("")

    return segments


def _detect_views(norm_tags: list[str], views_map: dict, groups_map: dict) -> set[str]:
    matched: set[str] = set()
    for vname, vgrp in views_map.items():
        if any(vgrp.matches_tag(t, groups_map) for t in norm_tags):
            matched.add(vname)
    if not matched:
        matched.add("FRONT")
    return matched


def _check_views(view_items: list[tuple[str, bool]], active_views: set[str]) -> bool:
    if not view_items:
        return True
    pos_views = [v for v, neg in view_items if not neg]
    neg_views = [v for v, neg in view_items if neg]

    for nv in neg_views:
        if nv == "ANY":
            return False
        if nv in active_views:
            return False

    if not pos_views or "ANY" in pos_views:
        return True
    return any(pv in active_views for pv in pos_views)


def _eval_condition(dnf: list[list[dict]] | None, norm_tags: list[str], active_views: set[str], groups_map: dict) -> bool:
    if dnf is None:
        return True
    if not dnf:
        return False

    for and_terms in dnf:
        branch_ok = True
        for term in and_terms:
            kind = term["kind"]
            if kind == "any":
                val = True
            elif kind == "view":
                v = term["view"]
                val = True if v == "ANY" else (v in active_views)
            elif kind == "group":
                g = groups_map.get(term["group_name"])
                val = any(g.matches_tag(t, groups_map) for t in norm_tags) if g else False
            else:
                g = term["group"]
                val = any(g.matches_tag(t, groups_map) for t in norm_tags)

            if term["negated"]:
                val = not val
            if not val:
                branch_ok = False
                break
        if branch_ok:
            return True
    return False


def _cleanup_reassembled_prompt(text: str) -> str:
    # Stash `/*...*/` comments and `<...>` tags so regex cleanup never alters their internal characters
    stash: list[str] = []

    def _save_token(m: re.Match) -> str:
        idx = len(stash)
        stash.append(m.group(0))
        return f"__WFATOK{idx}__"

    joined = re.sub(r"/\*.*?\*/|<[^>\n]+>", _save_token, text, flags=re.DOTALL)

    prev = None
    while prev != joined:
        prev = joined
        joined = re.sub(r"\(\s*,?\s*\)", "", joined)
        joined = re.sub(r"\[\s*,?\s*\]", "", joined)
        joined = re.sub(r",\s*,+", ",", joined)
        joined = re.sub(r"([(\[{|])\s*,\s*", r"\1", joined)
        joined = re.sub(r"\s*,\s*([)\]}])", r"\1", joined)
        joined = re.sub(r"\s*,\s*(:\s*[-+]?\d+(?:\.\d+)?\s*[)\]}])", r"\1", joined)
        joined = re.sub(r"\(\s*:\s*[-+]?\d+(?:\.\d+)?\s*\)", "", joined)

    joined = re.sub(r"[ \t]{2,}", " ", joined)
    joined = re.sub(r"\s+,", ",", joined)
    joined = re.sub(r",(?=[A-Za-z0-9(\[_])", ", ", joined)
    joined = joined.strip().strip(",").strip()

    for idx, original in enumerate(stash):
        joined = joined.replace(f"__WFATOK{idx}__", original)
    return joined


def _resolve_single_scope(
    scope_text: str,
    compiled_rules: dict,
    clean_placeholders: bool = True,
    inherited_views: set[str] | None = None,
    inherited_norm_tags: list[str] | None = None,
) -> dict:
    groups_map = compiled_rules["groups"]
    views_map = compiled_rules["views"]

    segments = _tokenize_prompt_segments(scope_text)

    def alive_norm_tags(include_inherited: bool = True) -> list[str]:
        own = [s["norm"] for s in segments if s["alive"] and not s["is_special"] and s["norm"]]
        if include_inherited and inherited_norm_tags:
            return own + inherited_norm_tags
        return own

    own_tags_initial = alive_norm_tags(include_inherited=False)
    local_matched_views: set[str] = set()
    for vname, vgrp in views_map.items():
        if any(vgrp.matches_tag(t, groups_map) for t in own_tags_initial):
            local_matched_views.add(vname)

    if local_matched_views:
        active_views = local_matched_views
    elif inherited_views:
        active_views = set(inherited_views)
    else:
        active_views = {"FRONT"}

    hidden_log: list[str] = []
    replaced_log: list[str] = []
    combo_log: list[str] = []
    added_negs: list[str] = []

    # --- STAGE 1: Occlusion (`HIDE` & `REPLACE`) ---
    for rule in compiled_rules["stage1"]:
        if not _check_views(rule["views"], active_views):
            continue
        cur_tags = alive_norm_tags(include_inherited=True)
        if rule["when"] is not None and not _eval_condition(rule["when"], cur_tags, active_views, groups_map):
            continue
        if rule["unless"] is not None and _eval_condition(rule["unless"], cur_tags, active_views, groups_map):
            continue

        target_grp: _CompiledGroup = rule["target"]
        did_affect = False

        if rule["action"] == "HIDE":
            for seg in segments:
                if not seg["alive"] or seg["is_special"] or not seg["norm"]:
                    continue
                if target_grp.matches_tag(seg["norm"], groups_map):
                    hidden_log.append(seg["core_raw"].strip())
                    rem_p, rem_s, unmatched_close = _strip_balanced_wrappers(seg["prefix"], seg["suffix"])
                    kept_shell = rem_p + (seg["weight_str"] if unmatched_close else "") + rem_s
                    if kept_shell.strip():
                        seg["raw"] = kept_shell
                        seg["delim"] = "," if seg["delim"] == "," else seg["delim"]
                        seg["is_special"] = True
                        seg["norm"] = ""
                    else:
                        seg["alive"] = False
                        if seg["delim"] == "\n":
                            seg["raw"] = ""
                            seg["alive"] = True
                            seg["is_special"] = True
                            seg["norm"] = ""
                    did_affect = True

        elif rule["action"] == "REPLACE":
            rep_str = rule["replacement"]
            rep_norm = rule["replacement_norm"]
            is_wildcard_suffix = rep_str.startswith("*") and len(rep_str[1:].strip()) > 0
            wildcard_suffix_word = rep_str[1:].strip() if is_wildcard_suffix else ""
            rep_word_pat = (
                _compile_single_atom(f"~{_normalize_phrase(wildcard_suffix_word)}")[0]
                if is_wildcard_suffix
                else (_compile_single_atom(f"~{rep_norm}")[0] if rep_norm else None)
            )
            # Check if another non-targeted tag in this scope already contains the replacement word (for non-wildcard replacements)
            other_has_rep = False
            if not is_wildcard_suffix and rep_word_pat is not None:
                for seg in segments:
                    if not seg["alive"] or seg["is_special"] or not seg["norm"]:
                        continue
                    if not target_grp.matches_tag(seg["norm"], groups_map) and rep_word_pat.search(seg["norm"]):
                        other_has_rep = True
                        break

            open_prefix_re = re.compile(r"^(?:partially[\s_]+|wide[\s_]+)?(?:open|unbuttoned)[\s_]+", re.IGNORECASE)
            trailing_word_re = re.compile(r"[A-Za-z]+\s*$")
            existing_alive_norms = {
                seg["norm"] for seg in segments if seg["alive"] and not seg["is_special"] and seg["norm"]
            }

            for seg in segments:
                if not seg["alive"] or seg["is_special"] or not seg["norm"]:
                    continue
                if target_grp.matches_tag(seg["norm"], groups_map):
                    old_name = seg["core_raw"].strip()
                    if is_wildcard_suffix:
                        # Suffix singularization/rewrite (e.g. `blue eyes` -> `blue eye`, `(dark-blue_eyes:1.1)` -> `(dark-blue_eye:1.1)`)
                        new_core = trailing_word_re.sub(wildcard_suffix_word, old_name).strip()
                        new_norm = _normalize_phrase(new_core)
                        if not new_core or new_norm == _normalize_phrase(wildcard_suffix_word):
                            continue
                        if new_norm in existing_alive_norms and new_norm != seg["norm"]:
                            replaced_log.append(f"{old_name}→(removed)")
                            rem_p, rem_s, unmatched_close = _strip_balanced_wrappers(seg["prefix"], seg["suffix"])
                            kept_shell = rem_p + (seg["weight_str"] if unmatched_close else "") + rem_s
                            if kept_shell.strip():
                                seg["raw"] = kept_shell
                                seg["is_special"] = True
                                seg["norm"] = ""
                            else:
                                seg["alive"] = False
                            did_affect = True
                        else:
                            replaced_log.append(f"{old_name}→{new_core}")
                            existing_alive_norms.discard(seg["norm"])
                            existing_alive_norms.add(new_norm)
                            seg["core_raw"] = new_core
                            seg["norm"] = new_norm
                            seg["raw"] = f"{seg['prefix']}{new_core}{seg['weight_str']}{seg['suffix']}"
                            did_affect = True
                        continue

                    # Preserve color/style adjectives when rewriting e.g. `open crimson hanfu` -> `crimson hanfu`
                    stripped_adj = open_prefix_re.sub("", old_name).strip()
                    stripped_adj_norm = _normalize_phrase(stripped_adj)
                    if (
                        rep_word_pat is not None
                        and stripped_adj
                        and stripped_adj_norm != seg["norm"]
                        and stripped_adj_norm != rep_norm
                        and rep_word_pat.search(stripped_adj_norm)
                    ):
                        replaced_log.append(f"{old_name}→{stripped_adj}")
                        seg["core_raw"] = stripped_adj
                        seg["norm"] = stripped_adj_norm
                        seg["raw"] = f"{seg['prefix']}{stripped_adj}{seg['weight_str']}{seg['suffix']}"
                        other_has_rep = True
                        did_affect = True
                    elif not rep_str or other_has_rep:
                        replaced_log.append(f"{old_name}→(removed)")
                        rem_p, rem_s, unmatched_close = _strip_balanced_wrappers(seg["prefix"], seg["suffix"])
                        kept_shell = rem_p + (seg["weight_str"] if unmatched_close else "") + rem_s
                        if kept_shell.strip():
                            seg["raw"] = kept_shell
                            seg["is_special"] = True
                            seg["norm"] = ""
                        else:
                            seg["alive"] = False
                        did_affect = True
                    else:
                        replaced_log.append(f"{old_name}→{rep_str}")
                        seg["core_raw"] = rep_str
                        seg["norm"] = rep_norm
                        seg["raw"] = f"{seg['prefix']}{rep_str}{seg['weight_str']}{seg['suffix']}"
                        other_has_rep = True
                        did_affect = True

        if did_affect and rule["plus_neg"]:
            for nt in rule["plus_neg"]:
                if nt not in added_negs:
                    added_negs.append(nt)

    # Reassemble after Stage 1 before running Stage 2 Combos
    surviving_own_tags = alive_norm_tags(include_inherited=False)
    surviving_all_tags = alive_norm_tags(include_inherited=True)

    # --- STAGE 2: Visible-Only Overlaps (`COMBO`) ---
    placeholders_to_replace: dict[str, str] = {}
    placeholders_to_clean: list[str] = []
    inline_injections: list[tuple[int, str]] = []

    for crule in compiled_rules["combos"]:
        ph = crule["placeholder"]
        views_ok = _check_views(crule["views"], active_views)
        when_ok = _eval_condition(crule["when"], surviving_all_tags, active_views, groups_map) if crule["when"] is not None else True
        unless_hit = _eval_condition(crule["unless"], surviving_all_tags, active_views, groups_map) if crule["unless"] is not None else False

        # Every required group in COMBO must match at least one surviving tag in THIS scope!
        first_match_seg_idx = -1
        all_reqs_met = views_ok and when_ok and not unless_hit
        if all_reqs_met:
            for g_idx, req_grp in enumerate(crule["req_groups"]):
                matched_idx = -1
                for s_idx, seg in enumerate(segments):
                    if seg["alive"] and not seg["is_special"] and seg["norm"]:
                        if req_grp.matches_tag(seg["norm"], groups_map):
                            matched_idx = s_idx
                            break
                if matched_idx == -1:
                    all_reqs_met = False
                    break
                if g_idx == 0:
                    first_match_seg_idx = matched_idx

        if all_reqs_met:
            inject_str = crule["inject"]
            inject_norm = crule["inject_norm"]
            already_present = any(t == inject_norm for t in surviving_own_tags)
            if not already_present:
                if ph and any(ph in seg["raw"] for seg in segments if seg["alive"]):
                    placeholders_to_replace[ph] = f"{inject_str}, "
                elif first_match_seg_idx >= 0:
                    inline_injections.append((first_match_seg_idx, inject_str))
                    surviving_own_tags.append(inject_norm)
                combo_log.append(inject_str)
                for nt in crule["plus_neg"]:
                    if nt not in added_negs:
                        added_negs.append(nt)
        else:
            if clean_placeholders and ph:
                placeholders_to_clean.append(ph)

    # Apply inline injections right after the first matched garment segment
    if inline_injections:
        for seg_idx, inject_str in reversed(inline_injections):
            seg = segments[seg_idx]
            if seg["delim"] == "":
                seg["delim"] = ","
            segments.insert(
                seg_idx + 1,
                {
                    "raw": f" {inject_str}",
                    "delim": ",",
                    "is_special": False,
                    "norm": _normalize_phrase(inject_str),
                    "alive": True,
                },
            )

    out_chunks: list[str] = []
    for seg in segments:
        if not seg["alive"]:
            continue
        out_chunks.append(seg["raw"] + seg["delim"])

    assembled = "".join(out_chunks)
    for ph, rep_val in placeholders_to_replace.items():
        assembled = assembled.replace(ph, rep_val)
    for ph in placeholders_to_clean:
        assembled = assembled.replace(ph, "")

    # --- STAGE 3: Standalone `NEG` Rules ---
    final_tags = alive_norm_tags(include_inherited=True)
    for nrule in compiled_rules["negs"]:
        if not _check_views(nrule["views"], active_views):
            continue
        if nrule["when"] is not None and not _eval_condition(nrule["when"], final_tags, active_views, groups_map):
            continue
        if nrule["unless"] is not None and _eval_condition(nrule["unless"], final_tags, active_views, groups_map):
            continue
        for nt in nrule["neg_tags"]:
            if nt not in added_negs:
                added_negs.append(nt)

    cleaned = _cleanup_reassembled_prompt(assembled)
    return {
        "text": cleaned,
        "views": active_views,
        "hidden": hidden_log,
        "replaced": replaced_log,
        "combos": combo_log,
        "added_negs": added_negs,
    }


def resolve_outfit_conflicts(
    positive: str,
    compiled_rules: dict,
    scope_mode: str = "Auto (Per [Char: ...] + Global)",
    clean_placeholders: bool = True,
) -> dict:
    if not positive or not positive.strip():
        return {
            "text": positive or "",
            "views": {"FRONT"},
            "hidden": [],
            "replaced": [],
            "combos": [],
            "added_negs": [],
        }

    if scope_mode.startswith("Auto"):
        # 1. Check for `/*C1*/ ... /*C2*/ ... /*GLOBAL*/` comment section markers
        sec_matches = list(_CHAR_SECTION_COMMENT_RE.finditer(positive))
        if sec_matches:
            spans: list[tuple[str, str, str]] = []
            if sec_matches[0].start() > 0:
                spans.append(("GLOBAL", "", positive[: sec_matches[0].start()]))
            for idx, sm in enumerate(sec_matches):
                kind_raw = sm.group(1).upper().replace(" ", "")
                kind = "GLOBAL" if kind_raw in ("GLOBAL", "SCENE") else kind_raw
                marker_raw = sm.group(0)
                body_start = sm.end()
                body_end = sec_matches[idx + 1].start() if idx + 1 < len(sec_matches) else len(positive)
                spans.append((kind, marker_raw, positive[body_start:body_end]))

            global_text_combined = ", ".join(body for kind, _, body in spans if kind == "GLOBAL" and body.strip())
            global_segs = _tokenize_prompt_segments(global_text_combined)
            global_tags = [s["norm"] for s in global_segs if s["alive"] and not s["is_special"] and s["norm"]]
            global_views = _detect_views(global_tags, compiled_rules["views"], compiled_rules["groups"])

            all_hidden: list[str] = []
            all_replaced: list[str] = []
            all_combos: list[str] = []
            all_negs: list[str] = []
            rebuilt_parts: list[str] = []
            combined_views: set[str] = set(global_views)

            for kind, marker_raw, body in spans:
                if not body.strip():
                    if not clean_placeholders and marker_raw:
                        rebuilt_parts.append(marker_raw)
                    continue
                if kind == "GLOBAL":
                    sub = _resolve_single_scope(body, compiled_rules, clean_placeholders=clean_placeholders)
                else:
                    sub = _resolve_single_scope(
                        body,
                        compiled_rules,
                        clean_placeholders=clean_placeholders,
                        inherited_views=global_views,
                        inherited_norm_tags=global_tags,
                    )
                    combined_views |= sub["views"]
                prefix_marker = "" if clean_placeholders else marker_raw
                if sub["text"]:
                    rebuilt_parts.append(f"{prefix_marker}{sub['text']}" if prefix_marker else sub["text"])
                elif prefix_marker:
                    rebuilt_parts.append(prefix_marker)
                all_hidden.extend(sub["hidden"])
                all_replaced.extend(sub["replaced"])
                all_combos.extend(sub["combos"])
                for nt in sub["added_negs"]:
                    if nt not in all_negs:
                        all_negs.append(nt)

            return {
                "text": _cleanup_reassembled_prompt(", ".join(rebuilt_parts)),
                "views": combined_views,
                "hidden": all_hidden,
                "replaced": all_replaced,
                "combos": all_combos,
                "added_negs": all_negs,
            }

        # 2. Check for `[Name: tags...]` character blocks (excluding `[a:b:0.5]` step edits)
        # Mask `/*...*/` comments with equal-length spaces so `[SLOT]` inside `/*[SLOT], */` doesn't break `[Name: ...]`
        masked_pos = re.sub(r"/\*.*?\*/", lambda c: " " * len(c.group(0)), positive, flags=re.DOTALL)
        matches = [
            m
            for m in _CHAR_BLOCK_RE.finditer(masked_pos)
            if not _STEP_EDIT_SUFFIX_RE.search(m.group(0)[:-1]) and "," in m.group(2)
        ]
        if matches:
            # Extract global context outside `[Name: ...]` blocks first
            outer_skeleton = positive
            for m in reversed(matches):
                outer_skeleton = outer_skeleton[: m.start()] + " /*__WFA_CHAR_SLOT__*/ " + outer_skeleton[m.end() :]

            outer_segs = _tokenize_prompt_segments(outer_skeleton)
            global_tags = [s["norm"] for s in outer_segs if s["alive"] and not s["is_special"] and s["norm"]]
            global_views = _detect_views(global_tags, compiled_rules["views"], compiled_rules["groups"])

            all_hidden: list[str] = []
            all_replaced: list[str] = []
            all_combos: list[str] = []
            all_negs: list[str] = []

            resolved_blocks: list[str] = []
            for m in matches:
                char_label = positive[m.start(1) : m.end(1)]
                char_body = positive[m.start(2) : m.end(2)]
                sub = _resolve_single_scope(
                    char_body,
                    compiled_rules,
                    clean_placeholders=clean_placeholders,
                    inherited_views=global_views,
                    inherited_norm_tags=global_tags,
                )
                resolved_blocks.append(f"[{char_label}: {sub['text']}]")
                all_hidden.extend(sub["hidden"])
                all_replaced.extend(sub["replaced"])
                all_combos.extend(sub["combos"])
                for nt in sub["added_negs"]:
                    if nt not in all_negs:
                        all_negs.append(nt)

            outer_res = _resolve_single_scope(
                outer_skeleton,
                compiled_rules,
                clean_placeholders=clean_placeholders,
            )
            all_hidden.extend(outer_res["hidden"])
            all_replaced.extend(outer_res["replaced"])
            all_combos.extend(outer_res["combos"])
            for nt in outer_res["added_negs"]:
                if nt not in all_negs:
                    all_negs.append(nt)

            rebuilt = outer_res["text"]
            for blk in resolved_blocks:
                rebuilt = rebuilt.replace("/*__WFA_CHAR_SLOT__*/", blk, 1)

            return {
                "text": _cleanup_reassembled_prompt(rebuilt),
                "views": global_views,
                "hidden": all_hidden,
                "replaced": all_replaced,
                "combos": all_combos,
                "added_negs": all_negs,
            }

    return _resolve_single_scope(positive, compiled_rules, clean_placeholders=clean_placeholders)


class WFA_OutfitConflictResolver:
    """
    WFA Outfit & Perspective Resolver: 2-stage clothing occlusion, directional conflict, and
    visible-only layer overlap resolver powered by an editable, hot-reloading `.txt` rulesheet
    inside `ComfyUI-WA-Suite/rules/`.
    """

    @classmethod
    def INPUT_TYPES(cls):
        files = _get_rule_files()
        default_file = "outfit_conflicts.txt" if "outfit_conflicts.txt" in files else files[0]
        return {
            "required": {
                "positive": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Connect your assembled positive prompt (after clothing & pose tags are inserted).",
                    },
                ),
                "rules_file": (
                    files,
                    {
                        "default": default_file,
                        "tooltip": (
                            "Select which `.txt` rulesheet inside `ComfyUI-WA-Suite/rules/` to use.\n"
                            "Edits to the `.txt` file hot-reload automatically on save without restarting ComfyUI!"
                        ),
                    },
                ),
                "enabled": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "Active",
                        "label_off": "Bypass",
                        "tooltip": "Quickly toggle conflict & overlap resolution on or off.",
                    },
                ),
                "scope_mode": (
                    [
                        "Auto (Per [Char: ...] + Global)",
                        "Whole Prompt",
                    ],
                    {
                        "default": "Auto (Per [Char: ...] + Global)",
                        "tooltip": (
                            "• Auto: Evaluates bracketed `[Char: ...]` blocks independently while inheriting global camera views.\n"
                            "• Whole Prompt: Evaluates the entire prompt as a single outfit."
                        ),
                    },
                ),
                "clean_placeholders": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "Clean Unused",
                        "label_off": "Keep /*...*/",
                        "tooltip": "Automatically strips unused `PLACEHOLDER /*...*/` comments when their `COMBO` rule does not fire.",
                    },
                ),
                "apply_neg_rules": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "label_on": "Apply +NEG",
                        "label_off": "Ignore +NEG",
                        "tooltip": "Appends `+NEG` / `NEG` safety tags from triggered rules to the optional `negative` prompt.",
                    },
                ),
            },
            "optional": {
                "negative": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Optional negative prompt passthrough (receives `+NEG` tags when rules trigger).",
                    },
                ),
                "extra_rules": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": "Optional inline rules string appended on top of the selected `.txt` rulesheet.",
                    },
                ),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("positive", "negative", "resolution_log")
    FUNCTION = "resolve"
    CATEGORY = PROMPTS_CATEGORY

    @classmethod
    def IS_CHANGED(
        cls,
        positive=None,
        rules_file="outfit_conflicts.txt",
        enabled=True,
        scope_mode="Auto (Per [Char: ...] + Global)",
        clean_placeholders=True,
        apply_neg_rules=True,
        negative=None,
        extra_rules=None,
        unique_id=None,
    ):
        path = _resolve_rules_path(rules_file) if isinstance(rules_file, str) else None
        mtime = 0.0
        if path and os.path.isfile(path):
            try:
                mtime = os.path.getmtime(path)
            except Exception:
                mtime = 0.0
        return (rules_file, mtime, enabled, scope_mode, clean_placeholders, apply_neg_rules, extra_rules)

    def resolve(
        self,
        positive: str,
        rules_file: str = "outfit_conflicts.txt",
        enabled: bool = True,
        scope_mode: str = "Auto (Per [Char: ...] + Global)",
        clean_placeholders: bool = True,
        apply_neg_rules: bool = True,
        negative: str = "",
        extra_rules: str = "",
        unique_id=None,
    ):
        pos_in = str(positive or "")
        neg_in = str(negative or "")

        if not enabled:
            self._send_badge(unique_id, "Bypassed (Off)", single_mode=True)
            return (pos_in, neg_in, "Bypassed")

        filepath = _resolve_rules_path(rules_file)
        compiled = _get_compiled_rules(filepath, extra_rules=str(extra_rules or ""))

        res = resolve_outfit_conflicts(
            pos_in,
            compiled,
            scope_mode=scope_mode,
            clean_placeholders=bool(clean_placeholders),
        )

        neg_out = neg_in
        injected_negs: list[str] = []
        if apply_neg_rules and res["added_negs"]:
            existing_neg_norms = {
                _normalize_phrase(seg["norm"])
                for seg in _tokenize_prompt_segments(neg_in)
                if not seg["is_special"] and seg["norm"]
            }
            for nt in res["added_negs"]:
                if _normalize_phrase(nt) not in existing_neg_norms:
                    injected_negs.append(nt)
                    existing_neg_norms.add(_normalize_phrase(nt))
            if injected_negs:
                appended = ", ".join(injected_negs)
                neg_out = f"{neg_in.rstrip().rstrip(',')}, {appended}" if neg_in.strip() else appended

        views_str = "+".join(sorted(res["views"]))
        log_lines = [f"View: {views_str}"]
        if res["hidden"]:
            log_lines.append(f"Hidden ({len(res['hidden'])}): {', '.join(res['hidden'])}")
        if res["replaced"]:
            log_lines.append(f"Rewritten ({len(res['replaced'])}): {', '.join(res['replaced'])}")
        if res["combos"]:
            log_lines.append(f"Combos ({len(res['combos'])}): {', '.join(res['combos'])}")
        if injected_negs:
            log_lines.append(f"+Negative ({len(injected_negs)}): {', '.join(injected_negs)}")
        if len(log_lines) == 1:
            log_lines.append("No conflicts or overlaps triggered.")

        badge_parts = [f"VIEW:{views_str}"]
        if res["hidden"]:
            badge_parts.append(f"Hid:{len(res['hidden'])}")
        if res["replaced"]:
            badge_parts.append(f"Rewrote:{len(res['replaced'])}")
        if res["combos"]:
            badge_parts.append(f"+Combo:{len(res['combos'])}")
        if len(badge_parts) == 1:
            badge_parts.append("Clean")

        self._send_badge(
            unique_id,
            " • ".join(badge_parts),
            single_mode=(len(badge_parts) == 2 and badge_parts[1] == "Clean"),
        )
        return (res["text"], neg_out, "\n".join(log_lines))

    @staticmethod
    def _send_badge(unique_id, text: str, single_mode: bool = False):
        if PromptServer is not None and getattr(PromptServer, "instance", None) is not None and unique_id is not None:
            uid = unique_id[0] if isinstance(unique_id, list) else unique_id
            PromptServer.instance.send_sync(
                "wfa-batch-prompt-feedback",
                {
                    "node_id": str(uid),
                    "text": text,
                    "warning": False,
                    "single_mode": single_mode,
                },
            )


NODE_CLASS_MAPPINGS = {
    "WFA_OutfitConflictResolver": WFA_OutfitConflictResolver,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WFA_OutfitConflictResolver": "WFA Outfit & Perspective Resolver ⚡ (WFA Suite)",
}
