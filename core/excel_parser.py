# core/excel_parser.py
from __future__ import annotations

import re
from collections import defaultdict, OrderedDict

import pandas as pd

from core.data_models import RootNode, Section, Node


# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════


def parse(
    excel_path: str,
    column_map: dict[str, str] | None = None,
) -> tuple[list[RootNode], dict[str, str]]:
    """
    Parse Excel file into a list of RootNode objects.

    column_map roles:
        "Main System"        → F0 column (e.g. G001)
        "System / Subsystem" → F1 column (e.g. MQA, MQA01)
        "Description"        → description column
    """
    df = _load(excel_path)
    cols = _detect_columns(df, column_map)

    raw_groups = _group_roots(df, cols)
    roots = [_build_root(df, rec, cols) for rec in raw_groups]

    col_labels = {
        "f0": cols["root"],
        "f1": cols["level1"],
    }
    return roots, col_labels


# ═════════════════════════════════════════════════════════════════════════════
# Loading
# ═════════════════════════════════════════════════════════════════════════════


def _load(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    return df.fillna("").apply(
        lambda col: col.str.strip() if col.dtype == "object" else col
    )


# ═════════════════════════════════════════════════════════════════════════════
# Column detection
# ═════════════════════════════════════════════════════════════════════════════


def _detect_columns(
    df: pd.DataFrame,
    column_map: dict[str, str] | None = None,
) -> dict[str, str]:
    if column_map:
        missing = [r for r in ["Main System", "System / Subsystem", "Description"]
                   if not column_map.get(r)]
        if missing:
            raise ValueError(f"column_map is missing roles: {missing}")
        return {
            "root":   column_map["Main System"],
            "level1": column_map["System / Subsystem"],
            "desc":   column_map["Description"],
        }

    def find(candidates: list[str]) -> str:
        for cand in candidates:
            for col in df.columns:
                if cand.lower() in col.lower():
                    return col
        raise ValueError(
            f"Cannot find column matching {candidates}. "
            f"Available: {list(df.columns)}"
        )

    return {
        "root":   find(["F0 ANNN", "F0"]),
        "level1": find(["F1 AAANN", "F1"]),
        "desc":   find(["Code Description", "Description"]),
    }


# ═════════════════════════════════════════════════════════════════════════════
# Root grouping
# ═════════════════════════════════════════════════════════════════════════════


def _f0_group_key(code: str) -> str:
    m = re.match(r"^([A-Za-z]+)(\d+)$", code)
    if not m:
        return code
    return m.group(1) + m.group(2)[:-1]


def _generalise_f0_code(instances: list[str]) -> str:
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
        letters   = m.group(1)
        digit_len = len(m.group(2))
        digit_prefix = prefix[len(letters):]
        padded = (digit_prefix + "0" * digit_len)[: digit_len - 1]
        return "=" + letters + padded + "n"
    return "=" + prefix + "n"


def _generalise_desc_from_list(descs: list[str]) -> str:
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


def _group_roots(df: pd.DataFrame, cols: dict) -> list[dict]:
    f0_col   = cols["root"]
    f1_col   = cols["level1"]
    desc_col = cols["desc"]

    f0_desc: dict[str, str] = {}
    for _, row in df.iterrows():
        f0   = row[f0_col]
        f1   = row[f1_col]
        desc = row[desc_col]
        if f0 and not f1 and desc and f0 not in f0_desc:
            f0_desc[f0] = desc

    raw: dict[str, list[str]] = defaultdict(list)
    for f0 in df[f0_col].dropna().unique():
        f0 = str(f0).strip()
        if f0:
            raw[_f0_group_key(f0)].append(f0)

    records = []
    for key, instances in raw.items():
        instances_sorted = sorted(instances)
        gen_code = _generalise_f0_code(instances_sorted)
        raw_desc = f0_desc.get(instances_sorted[0], "")
        gen_desc = (
            _generalise_desc_from_list(
                [f0_desc.get(i, "") for i in instances_sorted]
            )
            if len(instances) > 1 else raw_desc
        )
        records.append({
            "code":        gen_code,
            "description": gen_desc,
            "instances":   instances_sorted,
            "count":       len(instances),
        })

    merged: OrderedDict[str, dict] = OrderedDict()
    for rec in records:
        m = re.match(r"^=?([A-Za-z]+)", rec["code"])
        letter = m.group(1) if m else rec["code"]
        mkey   = letter + "|" + rec["description"]
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


def _build_root(df: pd.DataFrame, rec: dict, cols: dict) -> RootNode:
    sections = _parse_sections(df, rec["instances"], cols)
    return RootNode(
        code=rec["code"],
        description=rec["description"],
        instances=rec["instances"],
        count=rec["count"],
        sections=sections,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Section + Node parsing
# ═════════════════════════════════════════════════════════════════════════════


def _is_section_header(f1: str) -> bool:
    """Letters only 2-5 chars — section header (e.g. MQA, GC)."""
    return bool(re.match(r"^[A-Za-z]{2,5}$", f1.strip()))


def _parse_sections(
    df: pd.DataFrame,
    f0_instances: list[str],
    cols: dict,
) -> list[Section]:
    total  = len(f0_instances)
    f0_set = set(f0_instances)
    f0_col, f1_col, desc_col = cols["root"], cols["level1"], cols["desc"]

    rows = df[(df[f0_col].isin(f0_set)) & (df[f1_col] != "")]

    # ── Step 1: collect per-instance data ────────────────────────────────
    instance_sections: dict[str, OrderedDict] = {
        f0: OrderedDict() for f0 in f0_instances
    }

    for _, row in rows.iterrows():
        f0   = row[f0_col]
        f1   = row[f1_col]
        desc = row[desc_col]
        if f0 not in instance_sections:
            continue
        if _is_section_header(f1):
            if f1 not in instance_sections[f0]:
                instance_sections[f0][f1] = {"desc": desc, "nodes": []}
        else:
            m = re.match(r"^([A-Za-z]+)", f1)
            prefix = m.group(1) if m else None
            if prefix and prefix in instance_sections[f0]:
                instance_sections[f0][prefix]["nodes"].append((f1, desc))

    # ── Step 2: aggregate across instances ───────────────────────────────
    all_prefixes: OrderedDict[str, str]          = OrderedDict()
    node_instances: dict[str, dict[str, set]]    = defaultdict(lambda: defaultdict(set))
    node_desc_map:  dict[str, dict[str, str]]    = defaultdict(dict)
    node_order:     dict[str, list[str]]         = defaultdict(list)

    for f0, sections in instance_sections.items():
        for prefix, data in sections.items():
            if prefix not in all_prefixes:
                all_prefixes[prefix] = data["desc"]
            for node_code, node_desc_val in data["nodes"]:
                node_instances[prefix][node_code].add(f0)
                if node_code not in node_desc_map[prefix]:
                    node_desc_map[prefix][node_code] = node_desc_val
                if node_code not in node_order[prefix]:
                    node_order[prefix].append(node_code)

    # ── Step 3 & 4: group + build nodes ──────────────────────────────────
    result: list[Section] = []

    for prefix, sec_desc in all_prefixes.items():
        section = Section(prefix=prefix, label=prefix, description=sec_desc, nodes=[])

        groups: OrderedDict[str, list[str]] = OrderedDict()
        for node_code in node_order[prefix]:
            nd   = node_desc_map[prefix].get(node_code, "")
            dk   = _last_digit_key(node_code)
            tmpl = re.sub(r"\d+", "#", nd)
            key  = dk + "|" + tmpl
            if key not in groups:
                groups[key] = []
            groups[key].append(node_code)

        all_optional_codes: list[str] = []

        for key, codes in groups.items():
            static_codes   = [
                c for c in sorted(codes)
                if len(node_instances[prefix].get(c, set())) == total
            ]
            optional_codes = [c for c in sorted(codes) if c not in static_codes]
            all_optional_codes.extend(optional_codes)

            if static_codes:
                section.nodes.append(Node(
                    code=_build_range_code(static_codes),
                    description=_build_range_desc(static_codes, node_desc_map[prefix]),
                    is_static=True,
                    raw_codes=static_codes,
                    raw_descriptions={c: node_desc_map[prefix].get(c, "") for c in static_codes},
                    raw_present_in={},
                    present_in=list(f0_instances),
                ))

        section.nodes = _merge_static_nodes(section.nodes)

        if all_optional_codes:
            all_optional_sorted = sorted(all_optional_codes)
            present: set[str] = set()
            raw_pres: dict[str, list[str]] = {}
            for c in all_optional_sorted:
                inst = node_instances[prefix].get(c, set())
                present |= inst
                raw_pres[c] = sorted(inst)
            section.nodes.append(Node(
                code=_build_range_code(all_optional_sorted),
                description=_build_range_desc(all_optional_sorted, node_desc_map[prefix]),
                is_static=False,
                raw_codes=all_optional_sorted,
                raw_descriptions={c: node_desc_map[prefix].get(c, "") for c in all_optional_sorted},
                raw_present_in=raw_pres,
                present_in=sorted(present),
            ))

        if section.nodes:
            result.append(section)

    return result


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════


def _last_digit_key(code: str) -> str:
    m = re.match(r"^([A-Za-z]+\d*)(\d)$", code)
    if m:
        return m.group(1) + "#"
    return code


def _build_range_code(codes: list[str]) -> str:
    if not codes:
        return ""
    s = sorted(codes)
    if len(s) == 1:
        return "=" + s[0]
    return "=" + s[0] + ".." + s[-1][-2:]


def _build_range_desc(codes: list[str], desc_map: dict[str, str]) -> str:
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
    last_tokens  = tokenised[-1]
    result = []
    for i, token in enumerate(first_tokens):
        all_values = [t[i] for t in tokenised]
        if i % 2 == 1:
            result.append(
                f"{first_tokens[i]}..{last_tokens[i]}"
                if len(set(all_values)) > 1 else token
            )
        else:
            result.append(token)
    return "".join(result)


def _group_instances_ranges(instances: list[str]) -> str:
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


def _merge_static_nodes(nodes: list[Node]) -> list[Node]:
    if not nodes:
        return []

    def tokenise(s: str) -> list[str]:
        return re.split(r"(\d+(?:\.\.\d+)?)", s)

    def text_tokens(desc: str) -> tuple[str, ...]:
        parts = tokenise(desc)
        return tuple(parts[i] for i in range(0, len(parts), 2))

    merged: list[Node] = []
    i = 0
    while i < len(nodes):
        node = nodes[i]

        if not node.is_static:
            merged.append(node)
            i += 1
            continue

        run        = [node]
        base_text  = text_tokens(node.description)
        j = i + 1
        while j < len(nodes) and nodes[j].is_static:
            if text_tokens(nodes[j].description) == base_text:
                run.append(nodes[j])
                j += 1
            else:
                break

        if len(run) == 1:
            merged.append(node)
            i = j
            continue

        parts_first  = tokenise(run[0].description)
        parts_last   = tokenise(run[-1].description)
        do_merge = False
        if len(parts_first) == len(parts_last):
            num_indices  = [k for k in range(len(parts_first)) if k % 2 == 1]
            diff_indices = [k for k in num_indices if parts_first[k] != parts_last[k]]
            if len(diff_indices) == 1:
                do_merge = True

        if not do_merge:
            for r in run:
                merged.append(r)
            i = j
            continue

        all_codes     = sorted(c for r in run for c in r.raw_codes)
        all_raw_descs = {}
        for r in run:
            all_raw_descs.update(r.raw_descriptions)

        combined_code = _build_range_code(all_codes)
        combined_desc = _collapse_desc_ranges(run[0].description, run[-1].description)

        merged.append(Node(
            code=combined_code,
            description=combined_desc,
            is_static=True,
            raw_codes=all_codes,
            raw_descriptions=all_raw_descs,
            raw_present_in={},
            present_in=node.present_in,
        ))
        i = j

    return merged


def _collapse_desc_ranges(first_desc: str, last_desc: str) -> str:
    def tokenise(s: str) -> list[str]:
        return re.split(r"(\d+(?:\.\.\d+)?)", s)

    parts_f = tokenise(first_desc)
    parts_l = tokenise(last_desc)
    if len(parts_f) != len(parts_l):
        return first_desc

    result = []
    for i, (tf, tl) in enumerate(zip(parts_f, parts_l)):
        if i % 2 == 1:
            fn        = re.match(r"(\d+)", tf)
            ln        = re.findall(r"\d+", tl)
            first_num = fn.group(1) if fn else tf
            last_num  = ln[-1] if ln else tl
            result.append(f"{first_num}..{last_num}" if first_num != last_num else first_num)
        else:
            result.append(tf)
    return "".join(result)
