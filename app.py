import os
import tempfile

from flask import Flask, render_template, request, jsonify, send_file
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A3, landscape

import config as cfg
from core.validator import validate
from core.excel_parser import parse
from rendering.overview_renderer import draw_overview_pages
from rendering.tree_renderer import draw_tree_pages

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"xlsx"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "empty filename"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "only .xlsx allowed"}), 400

    path = os.path.join(app.config["UPLOAD_FOLDER"], "input.xlsx")
    file.save(path)

    val = validate(path)

    return jsonify({
        "ok": val.ok,
        "errors": val.errors,
        "warnings": val.warnings,
    })


@app.route("/parse", methods=["POST"])
def parse_file():
    path = os.path.join(app.config["UPLOAD_FOLDER"], "input.xlsx")

    if not os.path.exists(path):
        return jsonify({"error": "no file uploaded"}), 400

    main_systems, col_labels = parse(path)

    result = []
    for ms in main_systems:
        systems = []
        for sys in ms.systems:
            subsystems = []
            for sub in sys.subsystems:
                subsystems.append({
                    "code": sub.code,
                    "description": sub.description,
                    "is_common": sub.is_common,
                    "raw_codes": sub.raw_codes,
                    "present_in": sub.present_in,
                })
            systems.append({
                "prefix": sys.prefix,
                "label": sys.label,
                "description": sys.description,
                "subsystems": subsystems,
            })
        result.append({
            "code": ms.code,
            "description": ms.description,
            "instances": ms.instances,
            "count": ms.count,
            "systems": systems,
        })

    return jsonify({"main_systems": result, "col_labels": col_labels})


@app.route("/generate", methods=["POST"])
def generate():
    path = os.path.join(app.config["UPLOAD_FOLDER"], "input.xlsx")

    if not os.path.exists(path):
        return jsonify({"error": "no file uploaded"}), 400

    main_systems, col_labels = parse(path)

    # Plan pages — same logic as main.py
    total_pages, overview_page_nums, f1_first_pages = _plan_pages(main_systems)

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()

    c = rl_canvas.Canvas(tmp.name, pagesize=landscape(A3))
    c.setTitle("Structure Tree")

    # Overview pages
    draw_overview_pages(c, main_systems, overview_page_nums, f1_first_pages, total_pages)
    c.showPage()

    # Tree pages
    for ms in main_systems:
        first_pg = f1_first_pages[ms.code]
        n = draw_tree_pages(c, ms, first_pg, overview_page_nums[0], total_pages, col_labels)
        if first_pg + n <= total_pages:
            c.showPage()

    c.save()

    return send_file(
        tmp.name,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="structure_tree.pdf",
    )


def _plan_pages(main_systems):
    from rendering.tree_renderer import _chunk_systems, _plan_all_pages

    n_overview = 1
    overview_page_nums = [1]

    current = n_overview + 1
    f1_first_pages = {}

    for ms in main_systems:
        f1_first_pages[ms.code] = current
        chunks = _chunk_systems(ms.systems, cfg.MAX_COLS_PER_PAGE)
        pages, _ = _plan_all_pages(chunks)
        current += len(pages)

    total_pages = current - 1
    return total_pages, overview_page_nums, f1_first_pages


def _count_total_pages(main_systems):
    from rendering.tree_renderer import _chunk_systems, _plan_all_pages
    total = 1
    for ms in main_systems:
        chunks = _chunk_systems(ms.systems, cfg.MAX_COLS_PER_PAGE)
        pages, _ = _plan_all_pages(chunks)
        total += len(pages)
    return total


if __name__ == "__main__":
    app.run(debug=True, port=5000)