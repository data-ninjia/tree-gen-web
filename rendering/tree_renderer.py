# rendering/tree_renderer.py
from __future__ import annotations

from typing import Optional

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.colors import white, black, HexColor

import config as cfg
from core.data_models import MainSystem, System, Subsystem
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
    group: MainSystem,
    first_page: int,
    overview_page: int,
    total_pages: int,
    col_labels: dict,
    matrix_page: int | None = None,
) -> int:
    """
    Draw all tree pages for one MainSystem onto canvas c.
    Calls c.showPage() between pages, NOT after the last one.
    Returns number of pages drawn.
    """
    h_chunks = _chunk_systems(group.systems, cfg.MAX_COLS_PER_PAGE)
    pages, system_pages = _plan_all_pages(h_chunks)
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
            system_pages=system_pages,
            first_page=first_page,
            matrix_page=matrix_page,
        )

        if page_i < n_pages - 1:
            c.showPage()

    return n_pages


# ═════════════════════════════════════════════════════════════════════════════
# Page spec
# ═════════════════════════════════════════════════════════════════════════════


class _ColSpec:
    """What to render in one column on one page."""

    def __init__(self, system: System, subsystem_offset: int, subsystem_count: int):
        self.system = system
        self.subsystem_offset = subsystem_offset
        self.subsystem_count = subsystem_count


class _PageSpec:
    """What one physical page should render."""

    def __init__(self, col_specs: list[_ColSpec], is_continuation: bool = False):
        self.col_specs = col_specs
        self.is_continuation = is_continuation


# ═════════════════════════════════════════════════════════════════════════════
# Page planning
# ═════════════════════════════════════════════════════════════════════════════


def _subsystems_per_col() -> int:
    """How many Subsystems fit vertically in one column."""
    f0_area = cfg.F0_H + 40
    l1_area = cfg.L1_H + 30
    avail = cfg.USABLE_TOP - cfg.USABLE_BOT - f0_area - l1_area - 20
    return max(1, int(avail // (cfg.LEAF_H + cfg.LEAF_GAP)))


def _plan_all_pages(
    h_chunks: list[list[System]],
) -> tuple[list[_PageSpec], dict[int, list[int]]]:
    """
    For each horizontal chunk:
    - Page 1: all columns, each showing first N subsystems
    - Continuation pages: only overflowing columns, shared per batch

    Returns:
        pages        : list of _PageSpec
        system_pages : maps id(system) -> [page_indices] where it appears
    """
    pages: list[_PageSpec] = []
    system_pages: dict[int, list[int]] = {}
    capacity = _subsystems_per_col()

    for chunk in h_chunks:
        # First page — all columns, first N subsystems each
        first_specs = [
            _ColSpec(sys, 0, min(capacity, len(sys.subsystems))) for sys in chunk
        ]
        page_i = len(pages)
        pages.append(_PageSpec(first_specs, is_continuation=False))
        for spec in first_specs:
            system_pages.setdefault(id(spec.system), []).append(page_i)

        # Track offsets per system
        offsets = [min(capacity, len(sys.subsystems)) for sys in chunk]

        while True:
            overflow_specs = []
            for sys, off in zip(chunk, offsets):
                remaining = len(sys.subsystems) - off
                if remaining > 0:
                    show = min(capacity, remaining)
                    overflow_specs.append(_ColSpec(sys, off, show))

            if not overflow_specs:
                break

            page_i = len(pages)
            pages.append(_PageSpec(overflow_specs, is_continuation=True))
            for spec in overflow_specs:
                system_pages.setdefault(id(spec.system), []).append(page_i)

            # Advance offsets for overflowing columns
            new_offsets = list(offsets)
            for i, sys in enumerate(chunk):
                for spec in overflow_specs:
                    if spec.system is sys:
                        new_offsets[i] = spec.subsystem_offset + spec.subsystem_count
            offsets = new_offsets

    return pages, system_pages


# ═════════════════════════════════════════════════════════════════════════════
# Single page renderer
# ═════════════════════════════════════════════════════════════════════════════


def _draw_page(
    c: rl_canvas.Canvas,
    group: MainSystem,
    page_spec: _PageSpec,
    pg: int,
    overview_page: int,
    prev_pg: Optional[int],
    next_pg: Optional[int],
    page_i: int,
    n_pages: int,
    total_pages: int,
    col_labels,
    system_pages: dict[int, list[int]] | None = None,
    first_page: int = 1,
    matrix_page: int | None = None,
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
    _draw_main_system_node(c, group, geom, overview_page)
    _draw_nav_badges(c, geom, prev_pg, next_pg, page_i, n_pages)
    _draw_system_nodes(c, col_specs, geom, system_pages=system_pages,
                       page_i=page_i, first_page=first_page)
    _draw_subsystem_nodes(c, col_specs, geom, total_instances=group.count)
    _draw_legend(c, col_specs, group, matrix_page=matrix_page)
    _draw_level_legend(c, col_labels)


# ═════════════════════════════════════════════════════════════════════════════
# Header
# ═════════════════════════════════════════════════════════════════════════════


def _draw_header(
    c: rl_canvas.Canvas, group: MainSystem, page_i: int, n_pages: int
) -> None:
    c.setFillColor(cfg.COL_HEADER)
    c.rect(0, cfg.PAGE_H - cfg.HEADER_H, cfg.PAGE_W, cfg.HEADER_H, fill=1, stroke=0)

    code_display = group.code if group.code.startswith("=") else f"={group.code}"
    cont = f"  ({page_i + 1}/{n_pages})" if n_pages > 1 else ""
    text = f"{code_display}  —  {group.description}{cont}"

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

    # MainSystem → bus
    line(c, g.f0_cx, g.f0_y, g.f0_cx, g.bus_y)

    # Horizontal bus across all columns
    if n_cols > 1:
        line(c, g.col_xs[0], g.bus_y, g.col_xs[-1], g.bus_y)

    for spec, cx in zip(col_specs, g.col_xs):
        subsystems = spec.system.subsystems[
            spec.subsystem_offset : spec.subsystem_offset + spec.subsystem_count
        ]

        # Bus drop → System top
        line(c, cx, g.bus_y, cx, g.l1_top_y)

        if not subsystems:
            continue

        n_subs = len(subsystems)

        leaf_nx = cx - g.leaf_nw / 2 + g.leaf_nw * 0.15
        spine_x = leaf_nx - 12

        last_top = g.leaf_top - (n_subs - 1) * (cfg.LEAF_H + cfg.LEAF_GAP)
        last_mid = last_top - cfg.LEAF_H / 2

        line(c, cx, g.l1_y, spine_x, g.l1_y)
        line(c, spine_x, g.l1_y, spine_x, last_mid)

        for ri in range(n_subs):
            lt = g.leaf_top - ri * (cfg.LEAF_H + cfg.LEAF_GAP)
            lny = lt - cfg.LEAF_H
            lmid = lny + cfg.LEAF_H / 2
            line(c, spine_x, lmid, leaf_nx, lmid)


# ═════════════════════════════════════════════════════════════════════════════
# Nodes
# ═════════════════════════════════════════════════════════════════════════════


def _draw_main_system_node(
    c: rl_canvas.Canvas, group: MainSystem, g: _Geom, overview_page: int
) -> None:
    code_display = group.code if group.code.startswith("=") else f"={group.code}"
    node_box(
        c,
        x=g.f0_cx - cfg.F0_W / 2,
        y=g.f0_y,
        w=cfg.F0_W,
        h=cfg.F0_H,
        code=code_display,
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


def _draw_system_nodes(
    c: rl_canvas.Canvas,
    col_specs: list[_ColSpec],
    g: _Geom,
    system_pages: dict[int, list[int]] | None = None,
    page_i: int = 0,
    first_page: int = 1,
) -> None:
    """Draw System (F1 header) node for each column."""
    for spec, cx in zip(col_specs, g.col_xs):
        sys = spec.system
        label = f"={sys.label}" if not sys.label.startswith("=") else sys.label
        node_box(
            c,
            x=cx - g.node_w / 2,
            y=g.l1_y,
            w=g.node_w,
            h=cfg.L1_H,
            code=label,
            description=sys.description,
            code_fs=cfg.TREE_L1_FS,
            desc_fs=cfg.TREE_LEAF_DESC_FS,
            fill=cfg.COL_L1_FILL,
            text_color=cfg.COL_L1_TEXT,
            border=black,
        )

        # System nav buttons — only if this System spans multiple pages
        if system_pages is None:
            continue
        pages_for_sys = system_pages.get(id(sys), [])
        if len(pages_for_sys) <= 1:
            continue

        pos_in_sys = pages_for_sys.index(page_i) if page_i in pages_for_sys else -1
        if pos_in_sys < 0:
            continue

        n_sys = len(pages_for_sys)

        # "← back" button just above the first subsystem on this page
        if pos_in_sys > 0:
            prev_sys_page_i = pages_for_sys[pos_in_sys - 1]
            target_pg = first_page + prev_sys_page_i
            # g.leaf_top is the top of the first subsystem box
            section_nav_button(
                c, cx, g.leaf_top,
                label=f"← {pos_in_sys}/{n_sys} back",
                target_page=target_pg,
                direction="up",
            )

        # "cont. →" button below the last subsystem, centred on the column
        if pos_in_sys < n_sys - 1:
            next_sys_page_i = pages_for_sys[pos_in_sys + 1]
            target_pg = first_page + next_sys_page_i
            n_subs = spec.subsystem_count
            last_sub_bottom = (
                g.leaf_top
                - (n_subs - 1) * (cfg.LEAF_H + cfg.LEAF_GAP)
                - cfg.LEAF_H
            )
            # Centre on the column centre (cx), not the leaf left edge
            section_nav_button(
                c, cx, last_sub_bottom,
                label=f"cont. {pos_in_sys + 2}/{n_sys} →",
                target_page=target_pg,
                direction="down",
            )


def _draw_subsystem_nodes(
    c: rl_canvas.Canvas,
    col_specs: list[_ColSpec],
    g: _Geom,
    total_instances: int = 1,
) -> None:
    """Draw Subsystem (F1 code) nodes for each column."""
    for spec, cx in zip(col_specs, g.col_xs):
        subsystems = spec.system.subsystems[
            spec.subsystem_offset : spec.subsystem_offset + spec.subsystem_count
        ]

        leaf_nx = cx - g.leaf_nw / 2 + g.leaf_nw * 0.15

        for ri, sub in enumerate(subsystems):
            lt = g.leaf_top - ri * (cfg.LEAF_H + cfg.LEAF_GAP)
            lny = lt - cfg.LEAF_H

            display = sub.code + (" *" if not sub.is_common else "")
            border = cfg.COL_SPEC_BORDER if not sub.is_common else black

            # Badge: common → "Total × N" if >1
            #        optional → "Present on X of total"
            if sub.is_common:
                n = len(sub.raw_codes)
                badge = f"Total × {n}" if n > 1 else None
            else:
                badge = f"Present on {len(sub.present_in)} of {total_instances}"

            node_box(
                c,
                x=leaf_nx,
                y=lny,
                w=g.leaf_nw,
                h=cfg.LEAF_H,
                code=display,
                description=sub.description,
                code_fs=cfg.TREE_LEAF_CODE_FS,
                desc_fs=cfg.TREE_LEAF_DESC_FS,
                border=border,
                dashed=not sub.is_common,
                count=badge,
            )


# ═════════════════════════════════════════════════════════════════════════════
# Legends
# ═════════════════════════════════════════════════════════════════════════════


def _draw_legend(
    c: rl_canvas.Canvas,
    col_specs: list[_ColSpec],
    group: MainSystem,
    matrix_page: int | None = None,
) -> None:
    """
    Draw legend at bottom of page for exception (non-common) Subsystems.
    If matrix_page is provided, adds "* — see on page N" reference.
    """
    exception_subs: list[Subsystem] = []
    for spec in col_specs:
        subsystems = spec.system.subsystems[
            spec.subsystem_offset : spec.subsystem_offset + spec.subsystem_count
        ]
        for sub in subsystems:
            if not sub.is_common:
                exception_subs.append(sub)

    if not exception_subs:
        return

    legend_x = cfg.USABLE_X
    legend_y = cfg.USABLE_BOT + 0.4 * 28.35
    line_h = 11.0
    fs = 8.0

    c.setFont(cfg.FONT_BOLD, fs)
    c.setFillColor(black)
    c.drawString(legend_x, legend_y + line_h, "NOTES:")

    if matrix_page:
        from utils.pdf_primitives import link_rect
        ref_text = f"* — SEE ON PAGE {matrix_page}"
        ref_y = legend_y
        c.setFont(cfg.FONT_BOLD, fs)
        c.setFillColor(black)
        c.drawString(legend_x, ref_y, ref_text)
        text_w = c.stringWidth(ref_text, cfg.FONT_BOLD, fs)
        link_rect(c, legend_x, ref_y - 2, text_w, fs + 4, matrix_page)


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

    legend_w = box_w + pad_x + 160.0
    legend_x = cfg.USABLE_X + cfg.USABLE_W - legend_w
    legend_y = cfg.USABLE_TOP - 10.0

    for i, (fill, text_col, label) in enumerate(items):
        y = legend_y - i * row_h

        c.setFillColor(fill)
        c.setStrokeColor(black)
        c.setLineWidth(0.7)
        c.roundRect(legend_x, y - box_h, box_w, box_h, cfg.NODE_R, fill=1, stroke=1)

        c.setFont(cfg.FONT_REG, fs)
        c.setFillColor(black)
        c.drawString(legend_x + box_w + pad_x, y - box_h + 4, label)


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════


def _chunk_systems(systems: list[System], max_cols: int) -> list[list[System]]:
    if not systems:
        return [[]]
    return [systems[i : i + max_cols] for i in range(0, len(systems), max_cols)]
