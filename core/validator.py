# core/validator.py
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd


# ═════════════════════════════════════════════════════════════════════════════
# Result types
# ═════════════════════════════════════════════════════════════════════════════


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


# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════


def validate(excel_path: str) -> ValidationResult:
    """
    Validate the input Excel file against INPUT_REQUIREMENTS.md rules.
    Returns a ValidationResult — check .ok before proceeding.
    """
    result = ValidationResult()

    # ── Load ──────────────────────────────────────────────────────────────
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
    f0_col   = _find_col(df, ["F0 ANNN", "F0"])
    f1_col   = _find_col(df, ["F1 AAANN", "F1"])
    desc_col = _find_col(df, ["RDS-PP Code Description", "Description"])

    if not f0_col:
        result.errors.append(
            "Missing F0 column. Expected a column containing 'F0 ANNN' or 'F0'."
        )
    if not f1_col:
        result.errors.append(
            "Missing F1 column. Expected a column containing 'F1 AAANN' or 'F1'."
        )
    if not desc_col:
        result.errors.append(
            "Missing Description column. "
            "Expected a column containing 'RDS-PP Code Description' or 'Description'."
        )

    if not result.ok:
        return result  # can't proceed without columns

    # ── 2. At least one data row ──────────────────────────────────────────
    data_rows = df[df[f0_col] != ""]
    if data_rows.empty:
        result.errors.append("F0 column is empty — no data found.")
        return result

    # ── 3. F0 format: letters + digits ───────────────────────────────────
    bad_f0 = [
        v for v in df[f0_col].unique()
        if v and not re.match(r"^[A-Za-z]+[\dn]+$", v)
    ]
    if bad_f0:
        result.errors.append(
            f"Invalid F0 values (expected letters+digits, e.g. G001 or G00n): "
            f"{', '.join(sorted(bad_f0)[:10])}"
            + (" …" if len(bad_f0) > 10 else "")
        )

    # ── 4. F1 format: either letters-only (header) or letters+2digits (leaf)
    bad_f1 = []
    for v in df[f1_col].unique():
        if not v:
            continue
        if re.match(r"^[A-Za-z]{2,5}$", v):
            continue  # valid header
        if re.match(r"^[A-Za-z]{2,3}\d{2}$", v):
            continue  # valid leaf
        bad_f1.append(v)

    if bad_f1:
        result.errors.append(
            f"Invalid F1 values (expected 2-5 letters OR letters+2digits, "
            f"e.g. AHA or AHA10): "
            f"{', '.join(sorted(bad_f1)[:10])}"
            + (" …" if len(bad_f1) > 10 else "")
        )

    # ── 5. Every F1 leaf must be preceded by a section header ─────────────
    _check_orphan_leaves(df, f0_col, f1_col, result)

    # ── 6. Description length ─────────────────────────────────────────────
    DESC_WARN_LEN = 60
    DESC_MAX_LEN  = 120

    long_descs = df[
        (df[desc_col].str.len() > DESC_MAX_LEN) & (df[desc_col] != "")
    ]
    if not long_descs.empty:
        examples = long_descs[desc_col].iloc[:3].tolist()
        result.warnings.append(
            f"{len(long_descs)} description(s) exceed {DESC_MAX_LEN} chars and will "
            f"be clipped in node boxes. Consider shortening them. Examples: "
            + " | ".join(f'"{d[:60]}…"' for d in examples)
        )

    warn_descs = df[
        (df[desc_col].str.len() > DESC_WARN_LEN) &
        (df[desc_col].str.len() <= DESC_MAX_LEN) &
        (df[desc_col] != "")
    ]
    if not warn_descs.empty:
        result.warnings.append(
            f"{len(warn_descs)} descriptions exceed {DESC_WARN_LEN} chars "
            f"and may be truncated in node boxes. "
            f"Consider shortening them."
        )

    # ── 7. F0 description rows ────────────────────────────────────────────
    f0_values = set(df[f0_col].unique()) - {""}
    f0_with_desc = set(
        df[(df[f0_col] != "") & (df[f1_col] == "") & (df[desc_col] != "")][f0_col]
    )
    missing_desc = f0_values - f0_with_desc
    if missing_desc:
        result.warnings.append(
            f"{len(missing_desc)} F0 code(s) have no description row "
            f"(row where F1 is empty): "
            f"{', '.join(sorted(missing_desc)[:10])}"
            + (" …" if len(missing_desc) > 10 else "")
        )

    # ── 8. Empty descriptions on leaf rows ────────────────────────────────
    leaf_rows = df[
        df[f1_col].str.match(r"^[A-Za-z]{2,3}\d{2}$") & (df[f1_col] != "")
    ]
    # Only first row per F1 code matters (node title)
    first_per_leaf = leaf_rows.drop_duplicates(subset=[f0_col, f1_col], keep="first")
    empty_title = first_per_leaf[first_per_leaf[desc_col] == ""]
    if not empty_title.empty:
        examples = (
            empty_title[[f0_col, f1_col]].head(5)
            .apply(lambda r: f"{r[f0_col]} / {r[f1_col]}", axis=1)
            .tolist()
        )
        result.warnings.append(
            f"{len(empty_title)} leaf code(s) have no description on their first row: "
            f"{', '.join(examples)}"
            + (" …" if len(empty_title) > 5 else "")
        )

    return result


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════


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
    """
    Check that every leaf code has a matching section header in AT LEAST
    ONE F0 instance. A header missing from some instances is fine —
    the parser treats that as an exception leaf. A header missing from
    ALL instances means the leaf is truly orphaned and will be silently
    skipped during parsing.
    """
    # Collect which prefixes have a header in any instance
    prefixes_with_header: set[str] = set()
    for f1 in df[f1_col].unique():
        if re.match(r"^[A-Za-z]{2,5}$", f1):
            prefixes_with_header.add(f1)

    # Find leaf codes whose prefix never appears as a header anywhere
    orphan_prefixes: set[str] = set()
    for f1 in df[f1_col].unique():
        if not f1:
            continue
        if re.match(r"^[A-Za-z]{2,3}\d{2}$", f1):
            prefix = re.match(r"^([A-Za-z]+)", f1).group(1)
            if prefix not in prefixes_with_header:
                orphan_prefixes.add(prefix)

    if orphan_prefixes:
        result.errors.append(
            f"Leaf code prefix(es) have no section header row anywhere in the file: "
            f"{', '.join(sorted(orphan_prefixes))}. "
            f"Add a letters-only row (e.g. 'AHA') before the first leaf of each section."
        )
