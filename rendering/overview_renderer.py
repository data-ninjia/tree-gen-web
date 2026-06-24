from __future__ import annotations

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.utils import simpleSplit

import config as cfg
from core.data_models import RootNode
from utils.pdf_primitives import bookmark, link_rect, page_footer


def draw_overview_pages(
    c: rl_canvas.Canvas,
    groups: list[RootNode],
    page_nums: list[int],
    f1_first_pages: dict[str, int],
    total_pages: int,
) -> None:
    pages = _split_into_pages(groups)

    for page_i, page_groups in enumerate(pages):
        pg = page_nums[page_i]
        bookmark(c, pg)
        _draw_title(c, page_i, len(pages))
        _draw_cards(c, page_groups, f1_first_pages, pg)
        page_footer(c, pg, total_pages)

        if page_i < len(pages) - 1:
            c.showPage()


def _split_into_pages(groups: list[RootNode]) -> list[list[RootNode]]:
    return [
        groups[i : i + cfg.CARDS_PER_PAGE]
        for i in range(0, max(len(groups), 1), cfg.CARDS_PER_PAGE)
    ]


def _card_geometry() -> tuple[float, float, float, float, float]:
    h_gap = 0.6 * 28.35
    v_gap = 0.8 * 28.35
    title_h = 3.4 * 28.35
    margin = cfg.MARGIN

    usable_w = cfg.PAGE_W - 2 * margin
    usable_h = cfg.PAGE_H - margin - title_h - margin - 1.5 * 28.35

    card_w = (usable_w - (cfg.GRID_COLS - 1) * h_gap) / cfg.GRID_COLS
    card_h = (usable_h - (cfg.GRID_ROWS - 1) * v_gap) / cfg.GRID_ROWS
    card_r = min(10.0, card_h * 0.06)

    grid_x = margin
    grid_top = cfg.PAGE_H - margin - title_h

    return card_w, card_h, card_r, grid_x, grid_top, h_gap, v_gap


def _draw_title(c: rl_canvas.Canvas, page_i: int, total_ov_pages: int) -> None:
    title_fs = cfg.OVERVIEW_TITLE_FS
    margin = cfg.MARGIN

    text = (
        cfg.DEFAULT_TITLE
        if total_ov_pages == 1
        else f"{cfg.DEFAULT_TITLE}  —  {page_i + 1} / {total_ov_pages}"
    )

    title_y = cfg.PAGE_H - margin - title_fs + 6
    c.setFont(cfg.FONT_BOLD, title_fs)
    c.setFillColor(black)
    c.drawCentredString(cfg.PAGE_W / 2, title_y, text)

    if cfg.DEFAULT_SUBTITLE:
        sub_fs = title_fs * 0.42
        c.setFont(cfg.FONT_REG, sub_fs)
        c.setFillColor(HexColor("#555555"))
        c.drawCentredString(
            cfg.PAGE_W / 2,
            title_y - title_fs * 0.9,
            cfg.DEFAULT_SUBTITLE,
        )


def _draw_cards(
    c: rl_canvas.Canvas,
    groups: list[RootNode],
    f1_first_pages: dict[str, int],
    page_num: int,
) -> None:
    card_w, card_h, card_r, grid_x, grid_top, h_gap, v_gap = _card_geometry()

    code_fs = cfg.OVERVIEW_CODE_FS
    desc_fs = cfg.OVERVIEW_DESC_FS
    cnt_fs  = cfg.OVERVIEW_CNT_FS

    for slot, group in enumerate(groups):
        col_i = slot % cfg.GRID_COLS
        row_i = slot // cfg.GRID_COLS

        x = grid_x + col_i * (card_w + h_gap)
        y = grid_top - (row_i + 1) * card_h - row_i * v_gap

        _draw_single_card(
            c, x, y, card_w, card_h, card_r, group,
            code_fs, desc_fs, cnt_fs,
            f1_first_pages.get(group.code),
        )


def _draw_single_card(
    c: rl_canvas.Canvas,
    x: float, y: float, card_w: float, card_h: float, card_r: float,
    group: RootNode,
    code_fs: float, desc_fs: float, cnt_fs: float,
    f1_page: int | None,
) -> None:
    pad_x   = card_w * 0.06
    pad_y   = card_h * 0.07
    inner_w = card_w - 2 * pad_x

    c.setFillColor(white)
    c.setStrokeColor(black)
    c.setLineWidth(1.3)
    c.roundRect(x, y, card_w, card_h, card_r, fill=1, stroke=1)

    code_y    = y + card_h - pad_y - code_fs
    card_code = group.code if group.code.startswith("=") else f"={group.code}"
    c.setFont(cfg.FONT_BOLD, code_fs)
    c.setFillColor(black)
    c.drawCentredString(x + card_w / 2, code_y, card_code)

    div_y = code_y - code_fs * 0.38
    c.setStrokeColor(HexColor("#CCCCCC"))
    c.setLineWidth(0.5)
    c.line(x + pad_x * 2, div_y, x + card_w - pad_x * 2, div_y)

    cnt_area  = (cnt_fs + pad_y) if group.count > 1 else 0
    desc_area = div_y - y - pad_y - cnt_area
    max_lines = max(1, int(desc_area / (desc_fs * 1.3)))
    lines     = simpleSplit(group.description, cfg.FONT_REG, desc_fs, inner_w)
    lines     = lines[:max_lines]

    c.setFont(cfg.FONT_REG, desc_fs)
    c.setFillColor(HexColor("#2C2C2C"))
    block_h = len(lines) * desc_fs * 1.3
    desc_y  = div_y - (desc_area - block_h) / 2 - desc_fs * 1.05
    for ln in lines:
        c.drawCentredString(x + card_w / 2, desc_y, ln)
        desc_y -= desc_fs * 1.3

    if group.count > 1:
        c.setFont(cfg.FONT_REG, cnt_fs)
        c.setFillColor(HexColor("#999999"))
        c.drawCentredString(x + card_w / 2, y + pad_y * 0.55, f"× {group.count}")

    if f1_page is not None:
        link_rect(c, x, y, card_w, card_h, f1_page)
