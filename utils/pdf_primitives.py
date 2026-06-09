from __future__ import annotations

from typing import Optional

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.utils import simpleSplit

import config as cfg


# === LINES & CONNECTORS ===
def line(
    c: rl_canvas.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color=None,
    width: float = 0.8,
) -> None:
    c.setStrokeColor(color or cfg.COL_CONNECTOR)
    c.setLineWidth(width)
    c.setDash([])
    c.line(x1, y1, x2, y2)


def hline(
    c: rl_canvas.Canvas, x1: float, x2: float, y: float, color=None, width: float = 0.5
) -> None:
    c.setStrokeColor(color or cfg.COL_RULE)
    c.setLineWidth(width)
    c.line(x1, y, x2, y)


def elbow(c: rl_canvas.Canvas, px: float, py: float, cx: float, cy: float) -> None:
    """
    L-shaped connector: vertical from (px,py) to midpoint,
    then horizontal to (cx,cy).
    """
    mid_y = (py + cy) / 2
    c.setStrokeColor(cfg.COL_CONNECTOR)
    c.setLineWidth(0.8)
    c.setDash([])
    path = c.beginPath()
    path.moveTo(px, py)
    path.lineTo(px, mid_y)
    path.lineTo(cx, mid_y)
    path.lineTo(cx, cy)
    c.drawPath(path, stroke=1, fill=0)


# === LINKS & BOOKMARKS ===
def bookmark(c: rl_canvas.Canvas, page_num: int) -> None:
    c.bookmarkPage(f"page_{page_num}")


def link_rect(
    c: rl_canvas.Canvas, x: float, y: float, w: float, h: float, target_page: int
) -> None:
    c.linkAbsolute(
        "", f"page_{target_page}", Rect=(x, y, x + w, y + h), Border="[0 0 0]"
    )


# === NODE BOX ===
def node_box(
    c: rl_canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    code: str,
    description: str = "",
    code_fs: float = cfg.TREE_LEAF_CODE_FS,
    desc_fs: float = cfg.TREE_LEAF_DESC_FS,
    fill=white,
    text_color=black,
    border=black,
    dashed: bool = False,
    link_page: Optional[int] = None,
    count=1,
) -> None:
    """
    Draw a rounded-rect node with code (bold) + optional description.
    """
    c.saveState()

    c.setFillColor(fill)
    c.setStrokeColor(border)
    c.setLineWidth(1.3 if dashed else 0.9)
    if dashed:
        c.setDash([5, 3])

    c.roundRect(x, y, w, h, cfg.NODE_R, fill=1, stroke=1)

    code_y = y + h - code_fs - 6
    c.setFont(cfg.FONT_BOLD, code_fs)
    c.setFillColor(text_color)
    c.drawCentredString(x + w / 2, code_y, code)

    # Separator Line
    if description:
        sep_y = code_y - 5
        c.setStrokeColor(HexColor("#CCCCCC"))
        c.setLineWidth(0.4)
        c.line(x + 8, sep_y, x + w - 8, sep_y)

        # Description wrapped up to 3 lines
        c.setFont(cfg.FONT_REG, desc_fs)
        c.setFillColor(text_color)
        lines = simpleSplit(description, cfg.FONT_REG, desc_fs, w - 12)
        ly = sep_y - desc_fs - 2
        for ln in lines[:3]:
            if ly > y + 2:
                c.drawCentredString(x + w / 2, ly, ln)
            ly -= desc_fs + 2

    if link_page is not None:
        link_rect(c, x, y, w, h, link_page)

    if isinstance(count, str):
        # String badge (e.g. "27/28" for optional subsystems)
        c.setFont(cfg.FONT_REG, 7)
        c.setFillColor(HexColor("#999999"))
        c.drawCentredString(x + w / 2, y + 5, count)
    elif count is not None and count > 1:
        c.setFont(cfg.FONT_REG, 7)
        c.setFillColor(HexColor("#999999"))
        c.drawCentredString(x + w / 2, y + 5, f"× {count}")

    c.restoreState()


# === PAGE HEADER & FOOTER ===
def page_footer(c: rl_canvas.Canvas, page_num: int, total_pages: int) -> None:
    hline(c, cfg.MARGIN, cfg.PAGE_W - cfg.MARGIN, cfg.USABLE_BOT - 2)
    c.setFont(cfg.FONT_REG, 7)
    c.setFillColor(cfg.COL_PAGE_NUM)
    c.drawCentredString(
        cfg.PAGE_W / 2,
        cfg.MARGIN + 1,
        f"Page {page_num} of {total_pages}",
    )


def back_button(c: rl_canvas.Canvas, target_page: int) -> None:
    btn_w = 2.4 * 28.35
    btn_h = 0.7 * 28.35
    btn_x = cfg.USABLE_X
    btn_y = cfg.USABLE_BOT - btn_h - 0.15 * 28.35

    c.setFillColor(white)
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    c.roundRect(btn_x, btn_y, btn_w, btn_h, 3, fill=1, stroke=1)

    c.setFont(cfg.FONT_BOLD, 9)
    c.setFillColor(black)
    c.drawCentredString(
        btn_x + btn_w / 2,
        btn_y + (btn_h - 9) / 2,
        "← Overview",
    )
    link_rect(c, btn_x, btn_y, btn_w, btn_h, target_page)


def nav_badge(
    c: rl_canvas.Canvas,
    y_mid: float,
    label: str,
    target_page: int,
    align: str = "right",
) -> None:
    """
    Draw a small navigation badge (← N/M or N/M →).
    align: 'left' or 'right'
    """
    badge_w = 42.0
    badge_h = 20.0
    badge_r = 3.0
    pad = 8.0

    x = (
        cfg.USABLE_X + pad
        if align == "left"
        else cfg.USABLE_X + cfg.USABLE_W - pad - badge_w
    )
    by = y_mid - badge_h / 2

    c.setFillColor(white)
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    c.roundRect(x, by, badge_w, badge_h, badge_r, fill=1, stroke=1)

    c.setFont(cfg.FONT_BOLD, 8)
    c.setFillColor(black)
    c.drawCentredString(x + badge_w / 2, by + (badge_h - 8) / 2, label)

    link_rect(c, x, by, badge_w, badge_h, target_page)


def section_nav_button(
    c: rl_canvas.Canvas,
    cx: float,
    y: float,
    label: str,
    target_page: int,
    direction: str = "down",
) -> None:
    """
    Small navigation button attached to an L1 section node.
    direction: 'down' (→ continuation) drawn below the node,
               'up'   (← back) drawn above the node.
    """
    btn_w = 52.0
    btn_h = 16.0
    btn_r = 3.0

    bx = cx - btn_w / 2
    by = y - btn_h - 4 if direction == "down" else y + 4

    c.setFillColor(HexColor("#EAF3FB"))
    c.setStrokeColor(HexColor("#2C5F8A"))
    c.setLineWidth(0.8)
    c.roundRect(bx, by, btn_w, btn_h, btn_r, fill=1, stroke=1)

    c.setFont(cfg.FONT_BOLD, 7)
    c.setFillColor(HexColor("#2C5F8A"))
    c.drawCentredString(cx, by + (btn_h - 7) / 2, label)

    link_rect(c, bx, by, btn_w, btn_h, target_page)
