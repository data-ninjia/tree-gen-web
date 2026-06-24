# rendering/matrix_renderer.py
from __future__ import annotations

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.colors import black, white, HexColor

import config as cfg
from core.data_models import RootNode, Node
from utils.pdf_primitives import bookmark, page_footer, back_button


def has_optional(group: RootNode) -> bool:
    """Return True if this RootNode has any OPTIONAL nodes."""
    return any(
        not node.is_static
        for sec in group.sections
        for node in sec.nodes
    )


def draw_matrix_page(
    c: rl_canvas.Canvas,
    group: RootNode,
    pg: int,
    overview_page: int,
    total_pages: int,
) -> None:
    _draw_header(c, group)
    bookmark(c, pg)
    back_button(c, overview_page)
    page_footer(c, pg, total_pages)
    _draw_matrix(c, group)


def _draw_header(c: rl_canvas.Canvas, group: RootNode) -> None:
    c.setFillColor(cfg.COL_HEADER)
    c.rect(0, cfg.PAGE_H - cfg.HEADER_H, cfg.PAGE_W, cfg.HEADER_H, fill=1, stroke=0)

    code = group.code if group.code.startswith("=") else f"={group.code}"
    text = f"{code}  —  Optional Subsystems Matrix"

    c.setFont(cfg.FONT_BOLD, cfg.TREE_HEADER_FS)
    c.setFillColor(white)
    c.drawString(cfg.MARGIN, cfg.PAGE_H - cfg.HEADER_H + 0.55 * 28.35, text)


def _draw_matrix(c: rl_canvas.Canvas, group: RootNode) -> None:
    instances = group.instances
    n_inst    = len(instances)

    # Collect all optional nodes grouped by section
    rows: list[tuple[str, str, str, set[str]]] = []
    section_breaks: set[int] = set()

    for sec in group.sections:
        optional_nodes = [node for node in sec.nodes if not node.is_static]
        if not optional_nodes:
            continue

        section_start = len(rows)
        section_breaks.add(section_start)

        for node in optional_nodes:
            for raw_code in node.raw_codes:
                desc    = node.raw_descriptions.get(raw_code, node.description)
                present = set(node.raw_present_in.get(raw_code, node.present_in))
                rows.append((sec.prefix, raw_code, desc, present))

    if not rows:
        return

    n_rows = len(rows)

    # ── Layout ────────────────────────────────────────────────────────────
    margin_x = cfg.USABLE_X
    top_y    = cfg.USABLE_TOP - 8
    bottom_y = cfg.USABLE_BOT + 20

    usable_w = cfg.USABLE_W
    usable_h = top_y - bottom_y

    prefix_w = 36.0
    code_w   = 52.0
    desc_w   = min(160.0, usable_w * 0.22)
    fixed_w  = prefix_w + code_w + desc_w

    inst_area  = usable_w - fixed_w
    inst_col_w = max(14.0, inst_area / n_inst)

    header_h  = 28.0
    ms_row_h  = 14.0
    fs_header = 7.0
    fs_code   = 7.5
    fs_desc   = 6.5
    fs_inst   = 6.5

    row_h = max(14.0, (usable_h - header_h - ms_row_h) / n_rows)
    row_h = min(row_h, 20.0)

    # Colors — neutral black palette
    col_header_bg   = HexColor("#F0F0F0")
    col_header_text = black
    col_section_bg  = HexColor("#F7F7F7")
    col_present_bg  = HexColor("#E8E8E8")
    col_present_mark = black
    col_absent_bg   = white
    col_border      = HexColor("#CCCCCC")
    col_code        = black
    col_desc        = black
    col_prefix      = HexColor("#555555")

    def col_x(i: int) -> float:
        return margin_x + fixed_w + i * inst_col_w

    # ── Header rows ───────────────────────────────────────────────────────
    hx   = margin_x
    ms_y = top_y - ms_row_h
    hy   = ms_y - header_h

    # "MAIN SYSTEMS" spanning row
    c.setFillColor(col_header_bg)
    c.setStrokeColor(col_border)
    c.setLineWidth(0.4)
    c.rect(hx, ms_y, fixed_w, ms_row_h, fill=1, stroke=1)

    inst_total_w = inst_col_w * n_inst
    c.setFillColor(col_header_bg)
    c.setStrokeColor(col_border)
    c.rect(hx + fixed_w, ms_y, inst_total_w, ms_row_h, fill=1, stroke=1)
    c.setFont(cfg.FONT_BOLD, fs_header)
    c.setFillColor(col_header_text)
    c.drawCentredString(hx + fixed_w + inst_total_w / 2, ms_y + (ms_row_h - fs_header) / 2, "MAIN SYSTEMS")

    # Fixed header cells
    for x, w, label in [
        (hx, prefix_w, "Sys"),
        (hx + prefix_w, code_w, "Code"),
        (hx + prefix_w + code_w, desc_w, "Description"),
    ]:
        c.setFillColor(col_header_bg)
        c.setStrokeColor(col_border)
        c.setLineWidth(0.4)
        c.rect(x, hy, w, header_h, fill=1, stroke=1)
        c.setFont(cfg.FONT_BOLD, fs_header)
        c.setFillColor(col_header_text)
        c.drawCentredString(x + w / 2, hy + (header_h - fs_header) / 2, label)

    # Instance header cells — rotated with = prefix
    for i, inst in enumerate(instances):
        ix = col_x(i)
        c.setFillColor(col_header_bg)
        c.setStrokeColor(col_border)
        c.setLineWidth(0.4)
        c.rect(ix, hy, inst_col_w, header_h, fill=1, stroke=1)

        c.saveState()
        cx_inst = ix + inst_col_w / 2
        cy_inst = hy + header_h / 2
        c.translate(cx_inst, cy_inst)
        c.rotate(90)
        c.setFont(cfg.FONT_REG, fs_inst)
        c.setFillColor(col_header_text)
        c.drawCentredString(0, -fs_inst / 2, f"={inst}")
        c.restoreState()

    # ── Data rows ─────────────────────────────────────────────────────────
    for ri, (prefix, raw_code, desc, present) in enumerate(rows):
        ry               = top_y - ms_row_h - header_h - (ri + 1) * row_h
        is_section_start = ri in section_breaks
        row_bg           = col_section_bg if is_section_start else white

        # Prefix cell
        c.setFillColor(col_section_bg)
        c.setStrokeColor(col_border)
        c.setLineWidth(0.4)
        c.rect(margin_x, ry, prefix_w, row_h, fill=1, stroke=1)
        if is_section_start:
            c.setFont(cfg.FONT_BOLD, fs_code - 1)
            c.setFillColor(col_prefix)
            c.drawCentredString(margin_x + prefix_w / 2, ry + (row_h - fs_code + 1) / 2, f"={prefix}")

        # Code cell
        c.setFillColor(row_bg)
        c.setStrokeColor(col_border)
        c.rect(margin_x + prefix_w, ry, code_w, row_h, fill=1, stroke=1)
        c.setFont(cfg.FONT_BOLD, fs_code)
        c.setFillColor(col_code)
        c.drawCentredString(margin_x + prefix_w + code_w / 2, ry + (row_h - fs_code) / 2, f"={raw_code}")

        # Description cell
        c.setFillColor(row_bg)
        c.setStrokeColor(col_border)
        c.rect(margin_x + prefix_w + code_w, ry, desc_w, row_h, fill=1, stroke=1)
        c.setFont(cfg.FONT_REG, fs_desc)
        c.setFillColor(col_desc)
        short_desc = desc.split(",")[0].strip() if "," in desc else desc
        max_chars  = int(desc_w / (fs_desc * 0.52))
        label      = short_desc[:max_chars] + "…" if len(short_desc) > max_chars else short_desc
        c.drawString(margin_x + prefix_w + code_w + 3, ry + (row_h - fs_desc) / 2, label)

        # Instance cells
        for i, inst in enumerate(instances):
            ix         = col_x(i)
            is_present = inst in present

            c.setFillColor(col_present_bg if is_present else col_absent_bg)
            c.setStrokeColor(col_border)
            c.setLineWidth(0.4)
            c.rect(ix, ry, inst_col_w, row_h, fill=1, stroke=1)

            if is_present:
                c.setFont(cfg.FONT_BOLD, fs_inst + 1)
                c.setFillColor(col_present_mark)
                c.drawCentredString(ix + inst_col_w / 2, ry + (row_h - fs_inst) / 2, "✕")

    # ── Legend ────────────────────────────────────────────────────────────
    leg_x   = margin_x
    leg_y   = bottom_y - 2
    leg_box = 8.0
    leg_fs  = 7.0
    leg_gap = 60.0

    for j, (bg, label) in enumerate([
        (col_present_bg, "present"),
        (col_absent_bg,  "not present"),
    ]):
        lx = leg_x + j * leg_gap
        c.setFillColor(bg)
        c.setStrokeColor(col_border)
        c.setLineWidth(0.4)
        c.rect(lx, leg_y, leg_box, leg_box, fill=1, stroke=1)
        if bg == col_present_bg:
            c.setFont(cfg.FONT_BOLD, leg_fs)
            c.setFillColor(col_present_mark)
            c.drawCentredString(lx + leg_box / 2, leg_y + 1, "✕")
        c.setFont(cfg.FONT_REG, leg_fs)
        c.setFillColor(col_desc)
        c.drawString(lx + leg_box + 3, leg_y + 1, label)
