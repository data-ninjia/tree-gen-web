# rendering/l2_renderer.py
from __future__ import annotations

from typing import Optional

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.colors import white, black, HexColor

import config as cfg
from core.data_models import Node, Section
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


def has_l2(node: Node) -> bool:
    """Return True if node has L2 children sections."""
    return bool(node.children)


def draw_l2_pages(
    c: rl_canvas.Canvas,
    parent_node: Node,
    first_page: int,
    parent_tree_page: int,
    total_pages: int,
    matrix_page: int | None = None,
) -> int:
    """
    Draw all L2 tree pages for one static Node onto canvas c.
    Returns number of pages drawn.
    """
    h_chunks = _chunk_sections(parent_node.children, cfg.MAX_COLS_PER_PAGE)
    pages, section_pages = _plan_all_pages(h_chunks)
    n_pages = len(pages)

    for page_i, page_spec in enumerate(pages):
        pg      = first_page + page_i
        prev_pg = (first_page + page_i - 1) if page_i > 0 else None
        next_pg = (first_page + page_i + 1) if page_i < n_pages - 1 else None

        _draw_page(
            c,
            parent_node=parent_node,
            page_spec=page_spec,
            pg=pg,
            parent_tree_page=parent_tree_page,
            prev_pg=prev_pg,
            next_pg=next_pg,
            page_i=page_i,
            n_pages=n_pages,
            total_pages=total_pages,
            section_pages=section_pages,
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
    def __init__(self, section: Section, node_offset: int, node_count: int):
        self.section     = section
        self.node_offset = node_offset
        self.node_count  = node_count


class _PageSpec:
    def __init__(self, col_specs: list[_ColSpec], is_continuation: bool = False):
        self.col_specs       = col_specs
        self.is_continuation = is_continuation


# ═════════════════════════════════════════════════════════════════════════════
# Page planning
# ═════════════════════════════════════════════════════════════════════════════


def _nodes_per_col() -> int:
    f0_area = cfg.F0_H + 40
    l1_area = cfg.L1_H + 30
    avail   = cfg.USABLE_TOP - cfg.USABLE_BOT - f0_area - l1_area - 20
    return max(1, int(avail // (cfg.LEAF_H + cfg.LEAF_GAP)))


def _plan_all_pages(
    h_chunks: list[list[Section]],
) -> tuple[list[_PageSpec], dict[int, list[int]]]:
    pages: list[_PageSpec]              = []
    section_pages: dict[int, list[int]] = {}
    capacity = _nodes_per_col()

    for chunk in h_chunks:
        first_specs = [
            _ColSpec(sec, 0, min(capacity, len(sec.nodes))) for sec in chunk
        ]
        page_i = len(pages)
        pages.append(_PageSpec(first_specs, is_continuation=False))
        for spec in first_specs:
            section_pages.setdefault(id(spec.section), []).append(page_i)

        offsets = [min(capacity, len(sec.nodes)) for sec in chunk]

        while True:
            overflow_specs = []
            for sec, off in zip(chunk, offsets):
                remaining = len(sec.nodes) - off
                if remaining > 0:
                    show = min(capacity, remaining)
                    overflow_specs.append(_ColSpec(sec, off, show))

            if not overflow_specs:
                break

            page_i = len(pages)
            pages.append(_PageSpec(overflow_specs, is_continuation=True))
            for spec in overflow_specs:
                section_pages.setdefault(id(spec.section), []).append(page_i)

            new_offsets = list(offsets)
            for i, sec in enumerate(chunk):
                for spec in overflow_specs:
                    if spec.section is sec:
                        new_offsets[i] = spec.node_offset + spec.node_count
            offsets = new_offsets

    return pages, section_pages


# ═════════════════════════════════════════════════════════════════════════════
# Single page renderer
# ═════════════════════════════════════════════════════════════════════════════


def _draw_page(
    c: rl_canvas.Canvas,
    parent_node: Node,
    page_spec: _PageSpec,
    pg: int,
    parent_tree_page: int,
    prev_pg: Optional[int],
    next_pg: Optional[int],
    page_i: int,
    n_pages: int,
    total_pages: int,
    section_pages: dict[int, list[int]] | None = None,
    first_page: int = 1,
    matrix_page: int | None = None,
) -> None:
    _draw_header(c, parent_node, page_i, n_pages)
    bookmark(c, pg)
    back_button(c, parent_tree_page)
    page_footer(c, pg, total_pages)

    col_specs = page_spec.col_specs
    if not col_specs:
        return

    n_cols = len(col_specs)
    geom   = _compute_geometry(n_cols)

    _draw_connectors(c, col_specs, geom)
    _draw_parent_node(c, parent_node, geom, parent_tree_page)
    _draw_nav_badges(c, geom, prev_pg, next_pg, page_i, n_pages)
    _draw_section_nodes(c, col_specs, geom, section_pages=section_pages,
                        page_i=page_i, first_page=first_page)
    _draw_nodes(c, col_specs, geom, total_instances=len(parent_node.present_in))
    _draw_legend(c, col_specs, parent_node, matrix_page=matrix_page)


# ═════════════════════════════════════════════════════════════════════════════
# Header
# ═════════════════════════════════════════════════════════════════════════════


def _draw_header(c: rl_canvas.Canvas, node: Node, page_i: int, n_pages: int) -> None:
    c.setFillColor(cfg.COL_HEADER)
    c.rect(0, cfg.PAGE_H - cfg.HEADER_H, cfg.PAGE_W, cfg.HEADER_H, fill=1, stroke=0)

    cont = f"  ({page_i + 1}/{n_pages})" if n_pages > 1 else ""
    text = f"{node.code}  —  {node.description}{cont}"

    c.setFont(cfg.FONT_BOLD, cfg.TREE_HEADER_FS)
    c.setFillColor(white)
    c.drawString(cfg.MARGIN, cfg.PAGE_H - cfg.HEADER_H + 0.55 * 28.35, text)


# ═════════════════════════════════════════════════════════════════════════════
# Geometry
# ═════════════════════════════════════════════════════════════════════════════


class _Geom:
    def __init__(self):
        self.f0_y: float      = 0.0
        self.f0_cx: float     = 0.0
        self.bus_y: float     = 0.0
        self.l1_y: float      = 0.0
        self.l1_top_y: float  = 0.0
        self.leaf_top: float  = 0.0
        self.col_w: float     = 0.0
        self.node_w: float    = 0.0
        self.leaf_nw: float   = 0.0
        self.col_xs: list[float] = []


def _compute_geometry(n_cols: int) -> _Geom:
    g = _Geom()
    g.f0_cx    = cfg.PAGE_W / 2
    g.f0_y     = cfg.USABLE_TOP - cfg.F0_H
    g.l1_top_y = g.f0_y - 40
    g.l1_y     = g.l1_top_y - cfg.L1_H
    g.leaf_top = g.l1_y - 30
    g.bus_y    = (g.f0_y + g.l1_top_y) / 2
    g.col_w    = cfg.USABLE_W / n_cols
    g.node_w   = max(90.0, min(float(cfg.L1_W), g.col_w - 14))
    g.leaf_nw  = max(90.0, min(float(cfg.LEAF_W), g.col_w - 10))
    g.col_xs   = [cfg.USABLE_X + g.col_w * (i + 0.5) for i in range(n_cols)]
    return g


# ═════════════════════════════════════════════════════════════════════════════
# Connectors
# ═════════════════════════════════════════════════════════════════════════════


def _draw_connectors(c: rl_canvas.Canvas, col_specs: list[_ColSpec], g: _Geom) -> None:
    n_cols = len(col_specs)
    line(c, g.f0_cx, g.f0_y, g.f0_cx, g.bus_y)
    if n_cols > 1:
        line(c, g.col_xs[0], g.bus_y, g.col_xs[-1], g.bus_y)

    for spec, cx in zip(col_specs, g.col_xs):
        nodes = spec.section.nodes[spec.node_offset : spec.node_offset + spec.node_count]
        line(c, cx, g.bus_y, cx, g.l1_top_y)
        if not nodes:
            continue

        n_nodes = len(nodes)
        leaf_nx = cx - g.leaf_nw / 2 + g.leaf_nw * 0.15
        spine_x = leaf_nx - 12
        last_top = g.leaf_top - (n_nodes - 1) * (cfg.LEAF_H + cfg.LEAF_GAP)
        last_mid = last_top - cfg.LEAF_H / 2

        line(c, cx, g.l1_y, spine_x, g.l1_y)
        line(c, spine_x, g.l1_y, spine_x, last_mid)
        for ri in range(n_nodes):
            lt   = g.leaf_top - ri * (cfg.LEAF_H + cfg.LEAF_GAP)
            lny  = lt - cfg.LEAF_H
            lmid = lny + cfg.LEAF_H / 2
            line(c, spine_x, lmid, leaf_nx, lmid)


# ═════════════════════════════════════════════════════════════════════════════
# Nodes
# ═════════════════════════════════════════════════════════════════════════════


def _draw_parent_node(
    c: rl_canvas.Canvas, node: Node, g: _Geom, parent_tree_page: int
) -> None:
    node_box(
        c,
        x=g.f0_cx - cfg.F0_W / 2, y=g.f0_y,
        w=cfg.F0_W, h=cfg.F0_H,
        code=node.code, description=node.description,
        code_fs=cfg.TREE_F0_CODE_FS, desc_fs=cfg.TREE_F0_DESC_FS,
        fill=cfg.COL_F0_FILL, text_color=cfg.COL_F0_TEXT,
        border=black, link_page=parent_tree_page,
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


def _draw_section_nodes(
    c: rl_canvas.Canvas,
    col_specs: list[_ColSpec],
    g: _Geom,
    section_pages: dict[int, list[int]] | None = None,
    page_i: int = 0,
    first_page: int = 1,
) -> None:
    for spec, cx in zip(col_specs, g.col_xs):
        sec   = spec.section
        label = f"={sec.label}" if not sec.label.startswith("=") else sec.label
        node_box(
            c,
            x=cx - g.node_w / 2, y=g.l1_y,
            w=g.node_w, h=cfg.L1_H,
            code=label, description=sec.description,
            code_fs=cfg.TREE_L1_FS, desc_fs=cfg.TREE_LEAF_DESC_FS,
            fill=cfg.COL_L1_FILL, text_color=cfg.COL_L1_TEXT,
            border=black,
        )

        if section_pages is None:
            continue
        pages_for_sec = section_pages.get(id(sec), [])
        if len(pages_for_sec) <= 1:
            continue

        pos_in_sec = pages_for_sec.index(page_i) if page_i in pages_for_sec else -1
        if pos_in_sec < 0:
            continue

        n_sec = len(pages_for_sec)

        if pos_in_sec > 0:
            prev_pg = first_page + pages_for_sec[pos_in_sec - 1]
            section_nav_button(c, cx, g.leaf_top,
                label=f"← {pos_in_sec}/{n_sec} back",
                target_page=prev_pg, direction="up")

        if pos_in_sec < n_sec - 1:
            next_pg     = first_page + pages_for_sec[pos_in_sec + 1]
            n_subs      = spec.node_count
            last_bottom = g.leaf_top - (n_subs - 1) * (cfg.LEAF_H + cfg.LEAF_GAP) - cfg.LEAF_H
            section_nav_button(c, cx, last_bottom,
                label=f"cont. {pos_in_sec + 2}/{n_sec} →",
                target_page=next_pg, direction="down")


def _draw_nodes(
    c: rl_canvas.Canvas,
    col_specs: list[_ColSpec],
    g: _Geom,
    total_instances: int = 1,
) -> None:
    for spec, cx in zip(col_specs, g.col_xs):
        nodes   = spec.section.nodes[spec.node_offset : spec.node_offset + spec.node_count]
        leaf_nx = cx - g.leaf_nw / 2 + g.leaf_nw * 0.15

        for ri, node in enumerate(nodes):
            lt  = g.leaf_top - ri * (cfg.LEAF_H + cfg.LEAF_GAP)
            lny = lt - cfg.LEAF_H

            display = node.code + (" *" if not node.is_static else "")
            border  = cfg.COL_SPEC_BORDER if not node.is_static else black

            if node.is_static:
                n     = len(node.raw_codes)
                badge = f"Total × {n}" if n > 1 else None
            else:
                badge = f"Present on {len(node.present_in)} of {total_instances}"

            node_box(
                c,
                x=leaf_nx, y=lny,
                w=g.leaf_nw, h=cfg.LEAF_H,
                code=display, description=node.description,
                code_fs=cfg.TREE_LEAF_CODE_FS, desc_fs=cfg.TREE_LEAF_DESC_FS,
                border=border, dashed=not node.is_static,
                count=badge,
            )


# ═════════════════════════════════════════════════════════════════════════════
# Legend
# ═════════════════════════════════════════════════════════════════════════════


def _draw_legend(
    c: rl_canvas.Canvas,
    col_specs: list[_ColSpec],
    parent_node: Node,
    matrix_page: int | None = None,
) -> None:
    optional_nodes = [
        node
        for spec in col_specs
        for node in spec.section.nodes[spec.node_offset : spec.node_offset + spec.node_count]
        if not node.is_static
    ]

    if not optional_nodes and not matrix_page:
        return

    legend_x = cfg.USABLE_X
    legend_y  = cfg.USABLE_BOT + 0.4 * 28.35
    line_h    = 11.0
    fs        = 8.0

    c.setFont(cfg.FONT_BOLD, fs)
    c.setFillColor(black)
    c.drawString(legend_x, legend_y + line_h, "NOTES:")

    if matrix_page:
        from utils.pdf_primitives import link_rect
        ref_text = f"* — SEE ON PAGE {matrix_page}"
        c.setFont(cfg.FONT_BOLD, fs)
        c.setFillColor(black)
        c.drawString(legend_x, legend_y, ref_text)
        text_w = c.stringWidth(ref_text, cfg.FONT_BOLD, fs)
        link_rect(c, legend_x, legend_y - 2, text_w, fs + 4, matrix_page)


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════


def _chunk_sections(sections: list[Section], max_cols: int) -> list[list[Section]]:
    if not sections:
        return [[]]
    return [sections[i : i + max_cols] for i in range(0, len(sections), max_cols)]
