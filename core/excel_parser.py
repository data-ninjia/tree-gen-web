# core/excel_parser.py
from __future__ import annotations

import re
from collections import defaultdict, OrderedDict

import pandas as pd

from core.data_models import F0Group, F1Section, F1Leaf


# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════


def parse(excel_path: str) -> tuple[list[F0Group], dict[str, str]]:
    """
    Read Excel file and return list of F0Group objects.

    Expected input format (see INPUT_REQUIREMENTS.md):
      - One row per item
      - F0 column: letters + digits, e.g. G001, T001
      - F1 column: either
          (a) letters only, 2-5 chars → section header, e.g. AHA, MDA
          (b) letters + exactly 2 digits → leaf code, e.g. AHA10, MDA11
      - Description column: free text
    """
    df = _load(excel_path)
    f0_col, f1_col, desc_col = _detect_columns(df)
    raw_groups = _group_f0(df, f0_col, f1_col, desc_col)
    groups = [_build_f0_group(df, rec, f0_col, f1_col, desc_col) for rec in raw_groups]
    col_labels = {"f0": f0_col, "f1": f1_col}
    return groups, col_labels


# ═════════════════════════════════════════════════════════════════════════════
# Loading & column detection
# ═════════════════════════════════════════════════════════════════════════════


def _load(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    return df.fillna("").apply(
        lambda col: col.str.strip() if col.dtype == "object" else col
    )


def _detect_columns(df: pd.DataFrame) -> tuple[str, str, str]:
    def find(candidates: list[str]) -> str:
        for cand in candidates:
            for col in df.columns:
                if cand.lower() in col.lower():
                    return col
        raise ValueError(
            f"Cannot find column matching {candidates}. "
            f"Available: {list(df.columns)}"
        )

    return (
        find(["F0 ANNN", "F0"]),
        find(["F1 AAANN", "F1"]),
        find(["RDS-PP Code Description", "Description"]),
    )


# ═════════════════════════════════════════════════════════════════════════════
# F0 grouping
# ═════════════════════════════════════════════════════════════════════════════


def _f0_group_key(code: str) -> str:
    """G001 → 'G00',  W101 → 'W10'."""
    m = re.match(r"^([A-Za-z]+)(\d+)$", code)
    if not m:
        return code
    return m.group(1) + m.group(2)[:-1]


def _generalise_f0_code(instances: list[str]) -> str:
    """['G001'..'G028'] → '=G00n',  ['K001'] → '=K001'."""
    if len(instances) == 1:
        code = instances[0]
        return code if code.startswith("=") else f"={code}"

    common = []
    for chars in zip(*instances):
        if len(set(chars)) == 1:
            common.append(chars[0])
        else:
            break
    prefix = "".join(common)

    m = re.match(r"^([A-Za-z]+)(\d+)$", instances[0])
    if m:
        letters = m.group(1)
        digit_len = len(m.group(2))
        digit_prefix = prefix[len(letters):]
        padded = (digit_prefix + "0" * digit_len)[: digit_len - 1]
        return "=" + letters + padded + "n"

    return "=" + prefix + "n"


def _generalise_desc_from_list(descs: list[str]) -> str:
    """Numbers that differ across descriptions → 'n', same → kept."""
    if not descs:
        return ""
    if len(descs) == 1:
        return descs[0]

    def tokenise(s: str) -> list[str]:
        return re.split(r"(\d+)", s)

    tokenised = [tokenise(d) for d in descs]
    if len(set(len(t) for t in tokenised)) > 1:
        return descs[0]

    result = []
    for i, token in enumerate(tokenised[0]):
        all_values = [t[i] for t in tokenised]
        if i % 2 == 1:
            result.append("n" if len(set(all_values)) > 1 else token)
        else:
            result.append(token)
    return "".join(result)


def _group_f0(
    df: pd.DataFrame,
    f0_col: str,
    f1_col: str,
    desc_col: str,
) -> list[dict]:
    # Collect F0 descriptions from rows where F1 is empty
    f0_desc: dict[str, str] = {}
    for _, row in df.iterrows():
        f0 = row[f0_col]
        f1 = row[f1_col]
        desc = row[desc_col]
        if f0 and not f1 and desc and f0 not in f0_desc:
            f0_desc[f0] = desc

    # Group by key (letters + all-but-last digit)
    raw: dict[str, list[str]] = defaultdict(list)
    for f0 in df[f0_col].dropna().unique():
        f0 = f0.strip()
        if f0:
            raw[_f0_group_key(f0)].append(f0)

    records = []
    for key, instances in raw.items():
        instances_sorted = sorted(instances)
        gen_code = _generalise_f0_code(instances_sorted)
        raw_desc = f0_desc.get(instances_sorted[0], "")
        gen_desc = (
            _generalise_desc_from_list([f0_desc.get(i, "") for i in instances_sorted])
            if len(instances) > 1
            else raw_desc
        )
        records.append({
            "code": gen_code,
            "description": gen_desc,
            "instances": instances_sorted,
            "count": len(instances),
        })

    # Post-merge: same letter prefix + same description → one group
    merged: OrderedDict[str, dict] = OrderedDict()
    for rec in records:
        m = re.match(r"^=?([A-Za-z]+)", rec["code"])
        letter = m.group(1) if m else rec["code"]
        mkey = letter + "|" + rec["description"]
        if mkey in merged:
            merged[mkey]["instances"].extend(rec["instances"])
            merged[mkey]["count"] += rec["count"]
        else:
            merged[mkey] = dict(rec)

    result = []
    for rec in merged.values():
        rec["instances"] = sorted(rec["instances"])
        if rec["count"] > 1:
            rec["code"] = _generalise_f0_code(rec["instances"])
        result.append(rec)

    return sorted(result, key=lambda r: r["code"])


# ═════════════════════════════════════════════════════════════════════════════
# F0Group builder
# ═════════════════════════════════════════════════════════════════════════════


def _build_f0_group(
    df: pd.DataFrame,
    rec: dict,
    f0_col: str,
    f1_col: str,
    desc_col: str,
) -> F0Group:
    sections = _parse_f1(df, rec["instances"], f0_col, f1_col, desc_col)
    return F0Group(
        code=rec["code"],
        description=rec["description"],
        instances=rec["instances"],
        count=rec["count"],
        f1_sections=sections,
    )


# ═════════════════════════════════════════════════════════════════════════════
# F1 parsing
# ═════════════════════════════════════════════════════════════════════════════


def _is_section_header(f1: str) -> bool:
    """
    True if F1 value is a section header: 2-5 letters, no digits.
    e.g. AHA, MDA, BFA → True
         AHA10, MDA11  → False
    """
    return bool(re.match(r"^[A-Za-z]{2,5}$", f1.strip()))


def _parse_f1(
    df: pd.DataFrame,
    f0_instances: list[str],
    f0_col: str,
    f1_col: str,
    desc_col: str,
) -> list[F1Section]:
    """
    Parse F1 rows for a group of F0 instances into F1Section objects.

    Structure expected in input:
      AHA        → section header (letters only)
      AHA01      → leaf under AHA
      AHA10      → leaf under AHA
      AHA11      → leaf under AHA
      ...

    Grouping of leaves:
      - Leaves with same description template (numbers→#) AND differing only
        in last digit → grouped into a range (AHA01..03, AHA11..19)
      - Otherwise → each leaf is its own entry
    """
    total = len(f0_instances)
    f0_set = set(f0_instances)

    rows = df[(df[f0_col].isin(f0_set)) & (df[f1_col] != "")]

    # ── Step 1: collect per-instance data preserving Excel row order ──────
    # instance_sections[f0][prefix] = {"desc": str, "leaves": [(code, desc), ...]}
    instance_sections: dict[str, OrderedDict] = {
        f0: OrderedDict() for f0 in f0_instances
    }

    for _, row in rows.iterrows():
        f0 = row[f0_col]
        f1 = row[f1_col]
        desc = row[desc_col]

        if f0 not in instance_sections:
            continue

        if _is_section_header(f1):
            if f1 not in instance_sections[f0]:
                instance_sections[f0][f1] = {"desc": desc, "leaves": []}
        else:
            m = re.match(r"^([A-Za-z]+)", f1)
            prefix = m.group(1) if m else None
            if prefix and prefix in instance_sections[f0]:
                instance_sections[f0][prefix]["leaves"].append((f1, desc))

    # ── Step 2: aggregate across all instances ────────────────────────────
    # all_prefixes: ordered list of section prefixes (first-seen order)
    # leaf_instances[prefix][leaf_code] = set of f0 instances containing it
    # leaf_desc[prefix][leaf_code] = first-seen description
    # leaf_order[prefix] = ordered list of leaf codes (first-seen order)
    all_prefixes: OrderedDict[str, str] = OrderedDict()
    leaf_instances: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    leaf_desc: dict[str, dict[str, str]] = defaultdict(dict)
    leaf_order: dict[str, list[str]] = defaultdict(list)

    for f0, sections in instance_sections.items():
        for prefix, data in sections.items():
            if prefix not in all_prefixes:
                all_prefixes[prefix] = data["desc"]
            for leaf_code, leaf_desc_val in data["leaves"]:
                leaf_instances[prefix][leaf_code].add(f0)
                if leaf_code not in leaf_desc[prefix]:
                    leaf_desc[prefix][leaf_code] = leaf_desc_val
                if leaf_code not in leaf_order[prefix]:
                    leaf_order[prefix].append(leaf_code)

    # ── Step 3: group leaf codes ──────────────────────────────────────────
    # Two leaf codes belong to the same group if:
    #   1. Same description template (all numbers replaced with #)
    #   2. Differ only in the last character (last digit)
    # This means AHA11..19 group together (same template, same last-digit slot)
    # but MDA11 "Rotor blade A" and MDA12 "Rotor blade B" do NOT
    # (different templates).
    result: list[F1Section] = []

    for prefix, sec_desc in all_prefixes.items():
        section = F1Section(
            prefix=prefix,
            label=prefix,
            description=sec_desc,
            leaves=[],
        )

        # Group key = (last_digit_key, desc_template)
        groups: OrderedDict[str, list[str]] = OrderedDict()
        for leaf_code in leaf_order[prefix]:
            node_desc = leaf_desc[prefix].get(leaf_code, "")
            dk = _last_digit_key(leaf_code)
            tmpl = re.sub(r"\d+", "#", node_desc)
            key = dk + "|" + tmpl
            if key not in groups:
                groups[key] = []
            groups[key].append(leaf_code)

        # Build F1Leaf per group, splitting common vs exception within group
        for key, codes in groups.items():
            codes_sorted = sorted(codes)

            common_codes = [
                c for c in codes_sorted
                if len(leaf_instances[prefix].get(c, set())) == total
            ]
            exception_codes = [
                c for c in codes_sorted
                if c not in common_codes
            ]

            if common_codes:
                section.leaves.append(F1Leaf(
                    code=_build_range_code(common_codes),
                    description=_build_range_desc(common_codes, leaf_desc[prefix]),
                    is_common=True,
                    raw_codes=common_codes,
                    present_in=list(f0_instances),
                ))

            # Each exception code gets its own F1Leaf with its exact present_in.
            # _merge_exception_leaves will later combine those with identical sets.
            for c in exception_codes:
                present_c = sorted(leaf_instances[prefix].get(c, set()))
                section.leaves.append(F1Leaf(
                    code="=" + c,
                    description=leaf_desc[prefix].get(c, ""),
                    is_common=False,
                    raw_codes=[c],
                    present_in=present_c,
                ))

        # Merge consecutive common leaves with same text tokens and one
        # varying number (last position only)
        section.leaves = _merge_common_leaves(section.leaves)

        # Merge consecutive exception leaves with identical present_in sets
        section.leaves = _merge_exception_leaves(section.leaves, f0_instances)

        if section.leaves:
            result.append(section)

    return result


# ═════════════════════════════════════════════════════════════════════════════
# Leaf code / description helpers
# ═════════════════════════════════════════════════════════════════════════════


def _last_digit_key(code: str) -> str:
    """
    Return the code with last digit replaced by '#'.
    ACA11 → 'ACA1#',  MQA01 → 'MQA0#',  BFA10 → 'BFA1#'
    """
    m = re.match(r"^([A-Za-z]+\d*)(\d)$", code)
    if m:
        return m.group(1) + "#"
    return code


def _build_range_code(codes: list[str]) -> str:
    """
    Single code → '=ACA01'
    Multiple    → '=ACA11..19'
    """
    if not codes:
        return ""
    s = sorted(codes)
    if len(s) == 1:
        return "=" + s[0]
    return "=" + s[0] + ".." + s[-1][-2:]


def _build_range_desc(codes: list[str], desc_map: dict[str, str]) -> str:
    """
    Build display description for a group of codes.
    Numbers that differ across descriptions → shown as first..last range.
    Numbers that are the same → kept as-is.
    """
    descs = [desc_map.get(c, "") for c in sorted(codes)]
    if not descs:
        return ""
    if len(descs) == 1:
        return descs[0]

    def tokenise(s: str) -> list[str]:
        return re.split(r"(\d+)", s)

    tokenised = [tokenise(d) for d in descs]
    if len(set(len(t) for t in tokenised)) > 1:
        return descs[0]

    first_tokens = tokenised[0]
    last_tokens = tokenised[-1]
    result = []
    for i, token in enumerate(first_tokens):
        all_values = [t[i] for t in tokenised]
        if i % 2 == 1:
            result.append(
                f"{first_tokens[i]}..{last_tokens[i]}"
                if len(set(all_values)) > 1
                else token
            )
        else:
            result.append(token)
    return "".join(result)


def _group_instances_ranges(instances: list[str]) -> str:
    """
    Compress sorted instance list into compact range string.
    ['G001','G002','G003','G005'] → 'G001..G003, G005'
    """
    if not instances:
        return ""

    def split(code: str):
        m = re.match(r"^([A-Za-z]+)(\d+)$", code)
        if m:
            return m.group(1), int(m.group(2)), len(m.group(2))
        return code, None, 0

    groups = []
    run_start = run_end = run_prefix = run_pad = None

    def flush():
        if run_start is None:
            return
        fmt = f"{run_prefix}{str(run_start).zfill(run_pad)}"
        if run_start == run_end:
            groups.append(fmt)
        else:
            groups.append(fmt + ".." + run_prefix + str(run_end).zfill(run_pad))

    for code in sorted(instances):
        prefix, num, pad = split(code)
        if num is None:
            flush()
            run_start = run_end = run_prefix = run_pad = None
            groups.append(code)
            continue
        if run_prefix == prefix and run_pad == pad and num == run_end + 1:
            run_end = num
        else:
            flush()
            run_prefix, run_start, run_end, run_pad = prefix, num, num, pad

    flush()
    return ", ".join(groups)


# ═════════════════════════════════════════════════════════════════════════════
# Leaf merging
# ═════════════════════════════════════════════════════════════════════════════


def _merge_common_leaves(leaves: list[F1Leaf]) -> list[F1Leaf]:
    """
    Merge consecutive common leaves that share identical text tokens
    and have exactly one varying numeric token in the last position.

    Examples that DO merge:
      MQA01..09 "System 1..9"  +  MQA10..19 "System 10..19"  → MQA01..19 "System 1..19"

    Examples that do NOT merge:
      ACA10..19 "Busbar System 1, ..."  +  ACA20..29 "Busbar System 2, ..."
      → kept separate (varying number is not in last position)

      AXC10 "Main Lighting"  +  AXC20 "Outdoor Lighting"
      → kept separate (text tokens differ)
    """
    if not leaves:
        return []

    def tokenise(s: str) -> list[str]:
        return re.split(r"(\d+(?:\.\.\d+)?)", s)

    def text_tokens(desc: str) -> tuple[str, ...]:
        parts = tokenise(desc)
        return tuple(parts[i] for i in range(0, len(parts), 2))

    merged: list[F1Leaf] = []
    i = 0
    while i < len(leaves):
        leaf = leaves[i]

        if not leaf.is_common:
            merged.append(leaf)
            i += 1
            continue

        # Build a run of common leaves with same text tokens
        run = [leaf]
        base_text = text_tokens(leaf.description)
        j = i + 1
        while j < len(leaves) and leaves[j].is_common:
            if text_tokens(leaves[j].description) == base_text:
                run.append(leaves[j])
                j += 1
            else:
                break

        if len(run) == 1:
            merged.append(leaf)
            i = j
            continue

        # Only merge if exactly one numeric token varies AND it is the last one
        parts_first = tokenise(run[0].description)
        parts_last = tokenise(run[-1].description)
        do_merge = False
        if len(parts_first) == len(parts_last):
            num_indices = [k for k in range(len(parts_first)) if k % 2 == 1]
            diff_indices = [
                k for k in num_indices
                if parts_first[k] != parts_last[k]
            ]
            if len(diff_indices) == 1 and diff_indices[0] == num_indices[-1]:
                do_merge = True

        if not do_merge:
            for r in run:
                merged.append(r)
            i = j
            continue

        # Merge the run
        all_codes = sorted(c for r in run for c in r.raw_codes)
        combined_code = _build_range_code(all_codes)
        combined_desc = _collapse_desc_ranges(run[0].description, run[-1].description)

        merged.append(F1Leaf(
            code=combined_code,
            description=combined_desc,
            is_common=True,
            raw_codes=all_codes,
            present_in=leaf.present_in,
        ))
        i = j

    return merged


def _collapse_desc_ranges(first_desc: str, last_desc: str) -> str:
    """
    Merge two already-ranged descriptions into one.
    "System 1..9"  +  "System 10..19"  →  "System 1..19"
    Takes first number from first_desc and last number from last_desc.
    """
    def tokenise(s: str) -> list[str]:
        return re.split(r"(\d+(?:\.\.\d+)?)", s)

    parts_f = tokenise(first_desc)
    parts_l = tokenise(last_desc)
    if len(parts_f) != len(parts_l):
        return first_desc

    result = []
    for i, (tf, tl) in enumerate(zip(parts_f, parts_l)):
        if i % 2 == 1:
            fn = re.match(r"(\d+)", tf)
            ln = re.findall(r"\d+", tl)
            first_num = fn.group(1) if fn else tf
            last_num = ln[-1] if ln else tl
            result.append(f"{first_num}..{last_num}" if first_num != last_num else first_num)
        else:
            result.append(tf)
    return "".join(result)


def _merge_exception_leaves(
    leaves: list[F1Leaf],
    f0_instances: list[str],
) -> list[F1Leaf]:
    """
    Merge consecutive exception leaves with identical present_in sets
    into a single leaf with combined code range.
    """
    if not leaves:
        return []

    merged: list[F1Leaf] = []
    i = 0
    while i < len(leaves):
        leaf = leaves[i]

        if leaf.is_common:
            merged.append(leaf)
            i += 1
            continue

        run = [leaf]
        target = frozenset(leaf.present_in)
        j = i + 1
        while j < len(leaves) and not leaves[j].is_common:
            if frozenset(leaves[j].present_in) == target:
                run.append(leaves[j])
                j += 1
            else:
                break

        if len(run) == 1:
            merged.append(leaf)
        else:
            all_codes = sorted(c for r in run for c in r.raw_codes)
            merged.append(F1Leaf(
                code=_build_range_code(all_codes),
                description=run[0].description,
                is_common=False,
                raw_codes=all_codes,
                present_in=sorted(target),
            ))

        i = j

    return merged
