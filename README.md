# Structure Tree Generator

A web-based tool that converts Excel-formatted system lists into professional A3 PDF tree diagrams — complete with hierarchy visualization, static/optional grouping, and an interactive matrix page.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-black?logo=flask)
![ReportLab](https://img.shields.io/badge/ReportLab-PDF-red)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What it does

- Parses structured Excel files with 3-level hierarchies (Main System → System → Subsystem)
- Groups repeated codes into ranges (e.g. `=MQA01..20`)
- Automatically detects **STATIC** subsystems (present in all installations) and **OPTIONAL** ones (present in some)
- Generates A3 landscape PDFs with:
  - Overview page with clickable cards per Main System
  - Tree diagram pages with navigation
  - Optional subsystems matrix page
- Interactive web UI with column mapper, preview, UNGROUP toggle, and warnings panel

---

## Screenshots

> Upload → Map columns → Preview → Generate PDF

---

## Getting started

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
git clone https://github.com/your-username/structure-tree-generator.git
cd structure-tree-generator
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### Run

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

### Share on local network

```python
# app.py — already configured
app.run(host="0.0.0.0", port=5000)
```

Other devices on the same network can access it at `http://<your-ip>:5000`.

---

## Excel file format

Your `.xlsx` file must contain at least 3 columns:

| Column                 | Content                                 | Example                           |
| ---------------------- | --------------------------------------- | --------------------------------- |
| **Main System**        | Installation or site code               | `G001`, `=T001`                   |
| **System / Subsystem** | System header or subsystem code         | `MQA`, `MQA01`                    |
| **Description**        | Short name for each item (max 60 chars) | `Photovoltaic Generator System 1` |

### Key rules

- **System headers** — letters only, 3 chars (e.g. `MQA`, `MSE`) — group title rows
- **Subsystems** — 3 letters + exactly 2 digits (e.g. `MQA01`) — individual items
- Each installation must have a description row (Main System filled, System/Subsystem empty)
- Each installation must have the System header row before its subsystems

### Example structure

```
=G001 |        | Photovoltaic Field 1
=G001 | MQA    | Photovoltaic Generator System
=G001 | MQA01  | Photovoltaic Generator System 1
=G001 | MQA02  | Photovoltaic Generator System 2
=G001 | MSE    | Inverter System
=G001 | MSE01  | Inverter System 1
=G002 |        | Photovoltaic Field 2
=G002 | MQA    | Photovoltaic Generator System
=G002 | MQA01  | Photovoltaic Generator System 1
```

Column names don't matter — you map them in the UI.

---

## Project structure

```
structure-tree-generator/
├── app.py                      # Flask application
├── config.py                   # PDF layout constants
├── requirements.txt
├── uploads/                    # Temporary uploaded files
├── assets/
│   └── logo.png                # Optional company logo (shown in PDF footer)
├── core/
│   ├── data_models.py          # RootNode, Section, Node dataclasses
│   ├── excel_parser.py         # Excel → data model
│   └── validator.py            # Input validation
├── rendering/
│   ├── overview_renderer.py    # Overview cards page
│   ├── tree_renderer.py        # Tree diagram pages
│   └── matrix_renderer.py      # Optional subsystems matrix
├── utils/
│   └── pdf_primitives.py       # Low-level drawing helpers
└── templates/
    └── index.html              # Single-page web UI
```

---

## How it works

1. **Upload** — file is saved server-side, no validation yet
2. **Column mapper** — user assigns roles to columns; validation runs here with the correct column context
3. **Parse** — Excel is parsed into `RootNode → Section → Node` hierarchy; codes are grouped into ranges, static/optional split is determined
4. **Preview** — serialized tree is rendered in the UI; user can expand raw codes, toggle UNGROUP
5. **Generate** — PDF is rendered with ReportLab and downloaded

### Static vs Optional

A subsystem is **STATIC** if it appears in **all** instances of its Main System group.
It is **OPTIONAL** if it appears in only some — these get an asterisk `*` in the PDF and appear in the matrix page.

---

## Configuration

Edit `config.py` to customize:

```python
DEFAULT_TITLE    = "RDS-PP Structure"   # PDF title on overview page
DEFAULT_SUBTITLE = ""                   # Optional subtitle
LOGO_PATH        = "assets/logo.png"   # Company logo (leave file out to skip)
LOGO_WIDTH       = 60                  # Logo width in points
MAX_COLS_PER_PAGE = 6                  # Max system columns per tree page
```

---

## Requirements

```
flask
pandas
openpyxl
reportlab
```

---

## License

MIT — free to use, modify and distribute.
