# rendering/tree_renderer.py
from __future__ import annotations

from typing import Optional

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.colors import white, black, HexColor

import config as cfg
from core.data_models import F0Group, F1Section, F1Leaf
from utils.pdf_primitives import (
    line,
    bookmark,
    link_rect,
    node_box,
    page_footer,
    back_button,
    nav_badge,
    section_nav_button,
)

# ═════════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════════


def draw_tree_pages(
    c: rl_canvas.Canvas,
    group: F0Group,
    first_page: int,
    overview_page: int,
    total_pages: int,
    col_labels: dict,
) -> int:
    """
    Draw all F1 tree pages for one F0Group onto canvas c.
    Calls c.showPage() between pages, NOT after the last one.
    Returns number of pages drawn.
    """
    h_chunks = _chunk_sections(group.f1_sections, cfg.MAX_COLS_PER_PAGE)
    pages, section_pages = _plan_all_pages(h_chunks)
    n_pages = len(pages)

    for page_i, page_spec in enumerate(pages):
        pg = first_page + page_i
        prev_pg = (first_page + page_i - 1) if page_i > 0 else None
        next_pg = (first_page + page_i + 1) if page_i < n_pages - 1 else None

        _draw_page(
            c,
            group,
            page_spec,
            pg,
            overview_page,
            prev_pg,
            next_pg,
            page_i,
            n_pages,
            total_pages,
            col_labels,
            section_pages=section_pages,
            first_page=first_page,
        )

        if page_i < n_pages - 1:
            c.showPage()

    return n_pages


# ═════════════════════════════════════════════════════════════════════════════
# Page spec
# ═════════════════════════════════════════════════════════════════════════════


class _ColSpec:
    """What to render in one column on one page."""

    def __init__(self, section: F1Section, leaf_offset: int, leaf_count: int):
        self.section = section
        self.leaf_offset = leaf_offset
        self.leaf_count = leaf_count


class _PageSpec:
    """What one physical page should render."""

    def __init__(self, col_specs: list[_ColSpec], is_continuation: bool = False):
        self.col_specs = col_specs
        self.is_continuation = is_continuation


# ═════════════════════════════════════════════════════════════════════════════
# Page planning
# ═════════════════════════════════════════════════════════════════════════════


def _leaves_per_col() -> int:
    """How many leaves fit vertically in one column."""
    f0_area = cfg.F0_H + 40
    l1_area = cfg.L1_H + 30
    avail = cfg.USABLE_TOP - cfg.USABLE_BOT - f0_area - l1_area - 20
    return max(1, int(avail // (cfg.LEAF_H + cfg.LEAF_GAP)))


def _plan_all_pages(
    h_chunks: list[list[F1Section]],
) -> tuple[list[_PageSpec], dict[int, list[int]]]:
    """
    For each horizontal chunk:
    - Page 1: all columns, each showing first N leaves
    - Continuation pages: only overflowing columns, shared per batch

    Returns:
        pages           : list of _PageSpec
        section_pages   : maps id(section) -> [page_indices] where it appears
    """
    pages: list[_PageSpec] = []
    section_pages: dict[int, list[int]] = {}
    capacity = _leaves_per_col()

    for chunk in h_chunks:
        # First page — all columns, first N leaves each
        first_specs = [
            _ColSpec(sec, 0, min(capacity, len(sec.leaves))) for sec in chunk
        ]
        page_i = len(pages)
        pages.append(_PageSpec(first_specs, is_continuation=False))
        for spec in first_specs:
            section_pages.setdefault(id(spec.section), []).append(page_i)

        # Track offsets per section
        offsets = [min(capacity, len(sec.leaves)) for sec in chunk]

        while True:
            overflow_specs = []
            for sec, off in zip(chunk, offsets):
                remaining = len(sec.leaves) - off
                if remaining > 0:
                    show = min(capacity, remaining)
                    overflow_specs.append(_ColSpec(sec, off, show))

            if not overflow_specs:
                break

            page_i = len(pages)
            pages.append(_PageSpec(overflow_specs, is_continuation=True))
            for spec in overflow_specs:
                section_pages.setdefault(id(spec.section), []).append(page_i)

            # Advance offsets for overflowing columns
            new_offsets = list(offsets)
            for i, sec in enumerate(chunk):
                for spec in overflow_specs:
                    if spec.section is sec:
                        new_offsets[i] = spec.leaf_offset + spec.leaf_count
            offsets = new_offsets

    return pages, section_pages


# ═════════════════════════════════════════════════════════════════════════════
# Single page renderer
# ═════════════════════════════════════════════════════════════════════════════


def _draw_page(
    c: rl_canvas.Canvas,
    group: F0Group,
    page_spec: _PageSpec,
    pg: int,
    overview_page: int,
    prev_pg: Optional[int],
    next_pg: Optional[int],
    page_i: int,
    n_pages: int,
    total_pages: int,
    col_labels,
    section_pages: dict[int, list[int]] | None = None,
    first_page: int = 1,
) -> None:

    _draw_header(c, group, page_i, n_pages)
    bookmark(c, pg)
    back_button(c, overview_page)
    page_footer(c, pg, total_pages)

    col_specs = page_spec.col_specs
    if not col_specs:
        return

    n_cols = len(col_specs)
    geom = _compute_geometry(n_cols)

    # connectors first (drawn under nodes)
    _draw_connectors(c, col_specs, geom)

    # nodes on top of connectors
    _draw_f0_node(c, group, geom, overview_page)
    _draw_nav_badges(c, geom, prev_pg, next_pg, page_i, n_pages)
    _draw_l1_nodes(c, col_specs, geom, section_pages=section_pages,
                   page_i=page_i, first_page=first_page)
    _draw_leaf_nodes(c, col_specs, geom)
    _draw_legend(c, col_specs, group)
    _draw_level_legend(c, col_labels)


# ═════════════════════════════════════════════════════════════════════════════
# Header
# ═════════════════════════════════════════════════════════════════════════════


def _draw_header(
    c: rl_canvas.Canvas, group: F0Group, page_i: int, n_pages: int
) -> None:
    c.setFillColor(cfg.COL_HEADER)
    c.rect(0, cfg.PAGE_H - cfg.HEADER_H, cfg.PAGE_W, cfg.HEADER_H, fill=1, stroke=0)

    f0_display = group.code if group.code.startswith("=") else f"={group.code}"
    cont = f"  ({page_i + 1}/{n_pages})" if n_pages > 1 else ""
    text = f"{f0_display}  —  {group.description}{cont}"

    c.setFont(cfg.FONT_BOLD, cfg.TREE_HEADER_FS)
    c.setFillColor(white)
    c.drawString(cfg.MARGIN, cfg.PAGE_H - cfg.HEADER_H + 0.55 * 28.35, text)


# ═════════════════════════════════════════════════════════════════════════════
# Geometry
# ═════════════════════════════════════════════════════════════════════════════


class _Geom:
    def __init__(self):
        self.f0_y: float = 0.0
        self.f0_cx: float = 0.0
        self.bus_y: float = 0.0
        self.l1_y: float = 0.0
        self.l1_top_y: float = 0.0
        self.leaf_top: float = 0.0
        self.col_w: float = 0.0
        self.node_w: float = 0.0
        self.leaf_nw: float = 0.0
        self.col_xs: list[float] = []


def _compute_geometry(n_cols: int) -> _Geom:
    g = _Geom()

    g.f0_cx = cfg.PAGE_W / 2
    g.f0_y = cfg.USABLE_TOP - cfg.F0_H

    g.l1_top_y = g.f0_y - 40
    g.l1_y = g.l1_top_y - cfg.L1_H
    g.leaf_top = g.l1_y - 30
    g.bus_y = (g.f0_y + g.l1_top_y) / 2

    g.col_w = cfg.USABLE_W / n_cols
    g.node_w = max(90.0, min(float(cfg.L1_W), g.col_w - 14))
    g.leaf_nw = max(90.0, min(float(cfg.LEAF_W), g.col_w - 10))

    g.col_xs = [cfg.USABLE_X + g.col_w * (i + 0.5) for i in range(n_cols)]

    return g


# ═════════════════════════════════════════════════════════════════════════════
# Connectors
# ═════════════════════════════════════════════════════════════════════════════


def _draw_connectors(c: rl_canvas.Canvas, col_specs: list[_ColSpec], g: _Geom) -> None:
    n_cols = len(col_specs)

    # F0 → bus
    line(c, g.f0_cx, g.f0_y, g.f0_cx, g.bus_y)

    # Horizontal bus across all columns
    if n_cols > 1:
        line(c, g.col_xs[0], g.bus_y, g.col_xs[-1], g.bus_y)

    for spec, cx in zip(col_specs, g.col_xs):
        leaves = spec.section.leaves[
            spec.leaf_offset : spec.leaf_offset + spec.leaf_count
        ]

        # Bus drop → L1 top
        line(c, cx, g.bus_y, cx, g.l1_top_y)

        if not leaves:
            continue

        n_leaves = len(leaves)

        # Spine x = left edge of L1 node + small indent
        # This is the vertical line that runs down from L1
        leaf_nx = cx - g.leaf_nw / 2 + g.leaf_nw * 0.15
        spine_x = leaf_nx - 12

        # Vertical spine from L1 bottom to midpoint of last leaf
        last_top = g.leaf_top - (n_leaves - 1) * (cfg.LEAF_H + cfg.LEAF_GAP)
        last_mid = last_top - cfg.LEAF_H / 2

        line(c, cx, g.l1_y, spine_x, g.l1_y)
        line(c, spine_x, g.l1_y, spine_x, last_mid)

        # Horizontal tick from spine to leaf left edge at each leaf midpoint
        for ri in range(n_leaves):
            lt = g.leaf_top - ri * (cfg.LEAF_H + cfg.LEAF_GAP)
            lny = lt - cfg.LEAF_H
            lmid = lny + cfg.LEAF_H / 2

            # Horizontal tick: spine → leaf left edge
            line(c, spine_x, lmid, leaf_nx, lmid)


# ═════════════════════════════════════════════════════════════════════════════
# Nodes
# ═════════════════════════════════════════════════════════════════════════════


def _draw_f0_node(
    c: rl_canvas.Canvas, group: F0Group, g: _Geom, overview_page: int
) -> None:
    f0_display = group.code if group.code.startswith("=") else f"={group.code}"
    node_box(
        c,
        x=g.f0_cx - cfg.F0_W / 2,
        y=g.f0_y,
        w=cfg.F0_W,
        h=cfg.F0_H,
        code=f0_display,
        description=group.description,
        code_fs=cfg.TREE_F0_CODE_FS,
        desc_fs=cfg.TREE_F0_DESC_FS,
        fill=cfg.COL_F0_FILL,
        text_color=cfg.COL_F0_TEXT,
        border=black,
        link_page=overview_page,
    )


def _draw_nav_badges(
    c: rl_canvas.Canvas,
    g: _Geom,
    prev_pg: Optional[int],
    next_pg: Optional[int],
    page_i: int,
    n_pages: int,
) -> None:
    badge_y = g.f0_y + cfg.F0_H / 2
    if prev_pg is not None:
        nav_badge(c, badge_y, f"← {page_i}/{n_pages}", prev_pg, align="left")
    if next_pg is not None:
        nav_badge(c, badge_y, f"{page_i + 2}/{n_pages} →", next_pg, align="right")


def _draw_l1_nodes(
    c: rl_canvas.Canvas,
    col_specs: list[_ColSpec],
    g: _Geom,
    section_pages: dict[int, list[int]] | None = None,
    page_i: int = 0,
    first_page: int = 1,
) -> None:
    """L1 node always shown — it is an explicit row in Excel."""
    for spec, cx in zip(col_specs, g.col_xs):
        sec = spec.section
        label = f"={sec.label}" if not sec.label.startswith("=") else sec.label
        node_box(
            c,
            x=cx - g.node_w / 2,
            y=g.l1_y,
            w=g.node_w,
            h=cfg.L1_H,
            code=label,
            description=sec.description,
            code_fs=cfg.TREE_L1_FS,
            desc_fs=cfg.TREE_LEAF_DESC_FS,
            fill=cfg.COL_L1_FILL,
            text_color=cfg.COL_L1_TEXT,
            border=black,
        )

        # Section nav buttons — only if this section spans multiple pages
        if section_pages is None:
            continue
        pages_for_sec = section_pages.get(id(sec), [])
        if len(pages_for_sec) <= 1:
            continue

        pos_in_sec = pages_for_sec.index(page_i) if page_i in pages_for_sec else -1
        if pos_in_sec < 0:
            continue

        # "→ next" button below L1 node (if not last page of this section)
        if pos_in_sec < len(pages_for_sec) - 1:
            next_sec_page_i = pages_for_sec[pos_in_sec + 1]
            target_pg = first_page + next_sec_page_i
            n_sec = len(pages_for_sec)
            section_nav_button(
                c, cx, g.l1_y,
                label=f"cont. {pos_in_sec + 2}/{n_sec} →",
                target_page=target_pg,
                direction="down",
            )

        # "← prev" button above L1 node (if not first page of this section)
        if pos_in_sec > 0:
            prev_sec_page_i = pages_for_sec[pos_in_sec - 1]
            target_pg = first_page + prev_sec_page_i
            n_sec = len(pages_for_sec)
            section_nav_button(
                c, cx, g.l1_y,
                label=f"← {pos_in_sec}/{n_sec} back",
                target_page=target_pg,
                direction="down",
            )


def _draw_leaf_nodes(c: rl_canvas.Canvas, col_specs: list[_ColSpec], g: _Geom) -> None:
    for spec, cx in zip(col_specs, g.col_xs):
        leaves = spec.section.leaves[
            spec.leaf_offset : spec.leaf_offset + spec.leaf_count
        ]

        # Leaf left edge — shifted right (same as connector calc)
        leaf_nx = cx - g.leaf_nw / 2 + g.leaf_nw * 0.15

        for ri, leaf in enumerate(leaves):
            lt = g.leaf_top - ri * (cfg.LEAF_H + cfg.LEAF_GAP)
            lny = lt - cfg.LEAF_H

            display = leaf.code + (" *" if not leaf.is_common else "")
            border = cfg.COL_SPEC_BORDER if not leaf.is_common else black

            node_box(
                c,
                x=leaf_nx,
                y=lny,
                w=g.leaf_nw,
                h=cfg.LEAF_H,
                code=display,
                description=leaf.description,
                code_fs=cfg.TREE_LEAF_CODE_FS,
                desc_fs=cfg.TREE_LEAF_DESC_FS,
                border=border,
                dashed=not leaf.is_common,
                count=len(leaf.raw_codes),
            )


# ═════════════════════════════════════════════════════════════════════════════
# Legends
# ═════════════════════════════════════════════════════════════════════════════


def _draw_legend(
    c: rl_canvas.Canvas, col_specs: list[_ColSpec], group: F0Group
) -> None:
    """
    Draw legend at bottom of page for specific (non-common) leaves.
    Uses whichever list is shorter — present_in or absent_from —
    to minimise text while keeping the format consistent:
      * =MQA21..29 — present in: G001..G003   (minority)
      * =MQA21..29 — absent in:  G005         (majority)
    """
    from core.excel_parser import _group_instances_ranges

    # Collect all specific leaves from this page
    specific: list[F1Leaf] = []
    for spec in col_specs:
        leaves = spec.section.leaves[
            spec.leaf_offset : spec.leaf_offset + spec.leaf_count
        ]
        for leaf in leaves:
            if not leaf.is_common:
                specific.append(leaf)

    if not specific:
        return

    total = group.count
    all_instances = set(group.instances)

    # Draw legend box at bottom
    legend_x = cfg.USABLE_X
    legend_y = cfg.USABLE_BOT + 0.4 * 28.35
    line_h = 11.0
    fs = 8.0

    c.setFont(cfg.FONT_BOLD, fs)
    c.setFillColor(black)
    c.drawString(legend_x, legend_y + (len(specific)) * line_h, "NOTES:")

    c.setFont(cfg.FONT_REG, fs)
    c.setFillColor(HexColor("#555555"))

    for i, leaf in enumerate(specific):
        present = set(leaf.present_in)
        absent = sorted(all_instances - present)

        if len(present) > total / 2:
            # Majority present → show the shorter absent list
            instances_str = _group_instances_ranges(absent) if absent else "—"
            label = "absent in"
        else:
            # Minority present → show the shorter present list
            instances_str = _group_instances_ranges(sorted(present)) if present else "—"
            label = "present in"

        text = f"{leaf.code} * — {label}: {instances_str}"
        y = legend_y + (len(specific) - 1 - i) * line_h
        c.drawString(legend_x, y, text)


def _draw_level_legend(c: rl_canvas.Canvas, col_labels: dict) -> None:
    items = [
        (cfg.COL_L1_FILL, cfg.COL_L1_TEXT, col_labels["f1"]),
        (cfg.COL_F0_FILL, cfg.COL_F0_TEXT, col_labels["f0"]),
    ]

    box_w = 16.0
    box_h = 16.0
    fs = 8.5
    gap = 6.0
    row_h = box_h + gap
    pad_x = 8.0

    # Total legend block width — estimate
    legend_w = box_w + pad_x + 160.0
    legend_x = cfg.USABLE_X + cfg.USABLE_W - legend_w
    legend_y = cfg.USABLE_TOP - 10.0

    for i, (fill, text_col, label) in enumerate(items):
        y = legend_y - i * row_h

        # Coloured box
        c.setFillColor(fill)
        c.setStrokeColor(black)
        c.setLineWidth(0.7)
        c.roundRect(legend_x, y - box_h, box_w, box_h, cfg.NODE_R, fill=1, stroke=1)

        # Label
        c.setFont(cfg.FONT_REG, fs)
        c.setFillColor(black)
        c.drawString(legend_x + box_w + pad_x, y - box_h + 4, label)


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════


def _chunk_sections(sections: list[F1Section], max_cols: int) -> list[list[F1Section]]:
    if not sections:
        return [[]]
    return [sections[i : i + max_cols] for i in range(0, len(sections), max_cols)]
