from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import cm

# === PAGE ===
PAGE_W, PAGE_H = landscape(A3)

MARGIN = 2.0 * cm
HEADER_H = 2.2 * cm
FOOTER_H = 1.0 * cm
BAND_TAG_W = 1.6 * cm

USABLE_X = MARGIN
USABLE_W = PAGE_W - 2 * MARGIN
USABLE_TOP = PAGE_H - HEADER_H - 0.4 * cm
USABLE_BOT = MARGIN + FOOTER_H

# === FONTS ===
FONT_BOLD = "Helvetica-Bold"
FONT_REG = "Helvetica"

# === DEFAULT CONTENT ===
DEFAULT_TITLE = "Main Systems Overview"
DEFAULT_SUBTITLE = ""

# === OVERVIEW CARDS ===
CARDS_PER_PAGE = 10
GRID_COLS = 5
GRID_ROWS = 2

# === F1 TREE - NODE GEOMETRY ===
F0_W = 210
F0_H = 76
L1_W = 160
L1_H = 58
LEAF_W = 168
LEAF_H = 82
LEAF_GAP = 14  # vertical gap between stacked leaves
NODE_R = 4  # corner radius for all nodes

MAX_COLS_PER_PAGE = 4  # F1 tree columns per page before continuation

# === FONT SIZES ===
OVERVIEW_TITLE_FS = 42.0
OVERVIEW_CODE_FS = 22.0
OVERVIEW_DESC_FS = 14.0
OVERVIEW_CNT_FS = 9.0

TREE_HEADER_FS = 22.0
TREE_F0_CODE_FS = 14.0
TREE_F0_DESC_FS = 10.5
TREE_L1_FS = 11.0
TREE_LEAF_CODE_FS = 11.0
TREE_LEAF_DESC_FS = 9.0

# === COLORS ===
COL_HEADER = HexColor("#3D5A6C")
COL_F0_FILL = HexColor("#B5D4F4")
COL_F0_TEXT = black
COL_L1_FILL = HexColor("#E6F1FB")
COL_L1_TEXT = black
COL_LEAF_FILL = white
COL_LEAF_TEXT = black
COL_SPEC_BORDER = HexColor("#A0522D")
COL_CONNECTOR = black
COL_RULE = HexColor("#C0CCDA")
COL_BACK = HexColor("#2C5F8A")
COL_OVERVIEW_DESC = HexColor("#2C2C2C")
COL_OVERVIEW_CNT = HexColor("#999999")
COL_PAGE_NUM = HexColor("#8090A0")
COL_TOC_LINK = HexColor("#2C5F8A")

LOGO_PATH = "assets/logo.png"
LOGO_WIDTH = 60
LOGO_HEIGHT = 15
LOGO_MARGIN = 20