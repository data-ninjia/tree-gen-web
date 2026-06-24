# core/validator.py
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ValidationResult:
    errors:   list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def report(self) -> str:
        lines = []
        if self.errors:
            lines.append("ERRORS (generation blocked):")
            for e in self.errors:
                lines.append(f"  ✗ {e}")
        if self.warnings:
            lines.append("WARNINGS (generation will proceed):")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        if not self.errors and not self.warnings:
            lines.append("  ✓ Input file looks good.")
        return "\n".join(lines)


def validate(
    excel_path: str,
    column_map: dict[str, str] | None = None,
) -> ValidationResult:
    result = ValidationResult()

    try:
        df = pd.read_excel(excel_path, dtype=str)
    except Exception as e:
        result.errors.append(f"Cannot read file: {e}")
        return result

    df.columns = [c.strip() for c in df.columns]
    df = df.fillna("").apply(
        lambda col: col.str.strip() if col.dtype == "object" else col
    )

    # ── 1. Required columns ───────────────────────────────────────────────
    if column_map:
        f0_col   = column_map.get("Main System")
        f1_col   = column_map.get("System / Subsystem")
        desc_col = column_map.get("Description")
        if not f0_col:
            result.errors.append("Column map is missing 'Main System' role.")
        if not f1_col:
            result.errors.append("Column map is missing 'System / Subsystem' role.")
        if not desc_col:
            result.errors.append("Column map is missing 'Description' role.")
    else:
        f0_col   = _find_col(df, ["F0 ANNN", "F0"])
        f1_col   = _find_col(df, ["F1 AAANN", "F1"])
        desc_col = _find_col(df, ["Code Description", "Description"])

        if not f0_col:
            result.errors.append(
                "Missing Main System column. Expected a column containing 'F0 ANNN' or 'F0'."
            )
        if not f1_col:
            result.errors.append(
                "Missing System/Subsystem column. Expected a column containing 'F1 AAANN' or 'F1'."
            )
        if not desc_col:
            result.errors.append(
                "Missing Description column. "
                "Expected a column containing 'Code Description' or 'Description'."
            )

    if not result.ok:
        return result

    # ── 2. At least one data row ──────────────────────────────────────────
    data_rows = df[df[f0_col] != ""]
    if data_rows.empty:
        result.errors.append("Main System column is empty — no data found.")
        return result

    # ── 3. F0 format ──────────────────────────────────────────────────────
    bad_f0 = [
        v for v in df[f0_col].unique()
        if v and not re.match(r"^=?[A-Za-z]+[\dn]+$", v)
    ]
    if bad_f0:
        result.errors.append(
            f"Invalid Main System values (expected letters+digits, e.g. G001 or G00n): "
            f"{', '.join(sorted(bad_f0)[:10])}"
            + (" …" if len(bad_f0) > 10 else "")
        )

    # ── 4. F1 format ──────────────────────────────────────────────────────
    bad_f1 = []
    for v in df[f1_col].unique():
        if not v:
            continue
        if re.match(r"^[A-Za-z]{2,5}$", v):
            continue
        if re.match(r"^[A-Za-z]{2,3}\d{2}$", v):
            continue
        bad_f1.append(v)

    if bad_f1:
        result.errors.append(
            f"Invalid System/Subsystem values (expected 2-5 letters OR letters+2digits, "
            f"e.g. MQA or MQA10): "
            f"{', '.join(sorted(bad_f1)[:10])}"
            + (" …" if len(bad_f1) > 10 else "")
        )

    # ── 5. Orphan leaf check ──────────────────────────────────────────────
    _check_orphan_leaves(df, f0_col, f1_col, result)

    # ── 6. Description length — warning at 60 chars, one per row ─────────
    DESC_MAX_LEN = 60
    for idx, row in df.iterrows():
        desc = row[desc_col]
        if not desc or len(desc) <= DESC_MAX_LEN:
            continue
        f0 = row[f0_col]
        f1 = row[f1_col] if row[f1_col] else "—"
        result.warnings.append(
            f"Row {idx + 2}: {f0}/{f1}: description exceeds {DESC_MAX_LEN} chars "
            f"and will be clipped — \"{desc[:60]}…\""
        )

    # ── 7. F0 description rows ────────────────────────────────────────────
    f0_values    = set(df[f0_col].unique()) - {""}
    f0_with_desc = set(
        df[(df[f0_col] != "") & (df[f1_col] == "") & (df[desc_col] != "")][f0_col]
    )
    missing_desc = f0_values - f0_with_desc
    if missing_desc:
        result.warnings.append(
            f"{len(missing_desc)} Main System code(s) have no description row: "
            f"{', '.join(sorted(missing_desc)[:10])}"
            + (" …" if len(missing_desc) > 10 else "")
        )

    # ── 8. Empty descriptions on leaf rows ───────────────────────────────
    leaf_rows = df[
        df[f1_col].str.match(r"^[A-Za-z]{2,3}\d{2}$") & (df[f1_col] != "")
    ]
    first_per_leaf = leaf_rows.drop_duplicates(subset=[f0_col, f1_col], keep="first")
    empty_title    = first_per_leaf[first_per_leaf[desc_col] == ""]
    if not empty_title.empty:
        examples = (
            empty_title[[f0_col, f1_col]].head(5)
            .apply(lambda r: f"{r[f0_col]} / {r[f1_col]}", axis=1)
            .tolist()
        )
        result.warnings.append(
            f"{len(empty_title)} subsystem code(s) have no description: "
            f"{', '.join(examples)}"
            + (" …" if len(empty_title) > 5 else "")
        )

    return result


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for cand in candidates:
        for col in df.columns:
            if cand.lower() in col.lower():
                return col
    return None


def _check_orphan_leaves(
    df: pd.DataFrame,
    f0_col: str,
    f1_col: str,
    result: ValidationResult,
) -> None:
    # Build per-instance header sets
    instance_headers: dict[str, set[str]] = {}
    for _, row in df.iterrows():
        f0 = row[f0_col]
        f1 = row[f1_col]
        if not f0 or not f1:
            continue
        if re.match(r"^[A-Za-z]{2,5}$", f1):
            instance_headers.setdefault(f0, set()).add(f1)

    all_headers: set[str] = set(h for hs in instance_headers.values() for h in hs)

    # ERROR: prefix has no header anywhere
    orphan_prefixes: set[str] = set()
    for f1 in df[f1_col].unique():
        if not f1:
            continue
        if re.match(r"^[A-Za-z]{2,3}\d{2}$", f1):
            prefix = re.match(r"^([A-Za-z]+)", f1).group(1)
            if prefix not in all_headers:
                orphan_prefixes.add(prefix)

    if orphan_prefixes:
        result.errors.append(
            f"Subsystem prefix(es) have no System header anywhere in the file: "
            f"{', '.join(sorted(orphan_prefixes))}. "
            f"Add a letters-only row (e.g. 'MQA') before the first subsystem of each system."
        )

    # WARNING: leaf exists in instance where its header is missing
    skipped: list[str] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        f0 = row[f0_col]
        f1 = row[f1_col]
        if not f0 or not f1:
            continue
        if re.match(r"^[A-Za-z]{2,3}\d{2}$", f1):
            prefix = re.match(r"^([A-Za-z]+)", f1).group(1)
            if prefix in all_headers:
                inst_hdrs = instance_headers.get(f0, set())
                if prefix not in inst_hdrs:
                    key = f"{f1} in {f0}"
                    if key not in seen:
                        seen.add(key)
                        skipped.append(key)

    if skipped:
        result.warnings.append(
            f"{len(skipped)} subsystem code(s) will be skipped — "
            f"their system header is missing in that Main System instance: "
            f"{', '.join(skipped[:10])}"
            + (" …" if len(skipped) > 10 else "")
        )
