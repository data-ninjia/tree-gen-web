import os
import tempfile
import copy
import math
from datetime import datetime
import pandas as pd

from flask import Flask, render_template, request, jsonify, send_file
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A3, landscape

import config as cfg
from core.validator import validate
from core.excel_parser import parse
from core.data_models import Node
from rendering.overview_renderer import draw_overview_pages
from rendering.tree_renderer import draw_tree_pages, _chunk_sections, _plan_all_pages
from rendering.matrix_renderer import draw_matrix_page, has_optional

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
    return jsonify({"ok": True})


@app.route("/columns", methods=["POST"])
def get_columns():
    path = os.path.join(app.config["UPLOAD_FOLDER"], "input.xlsx")
    if not os.path.exists(path):
        return jsonify({"error": "no file uploaded"}), 400
    df = pd.read_excel(path, dtype=str, nrows=5)
    df = df.fillna("").apply(lambda col: col.str.strip() if col.dtype == "object" else col)
    columns = []
    for col in df.columns:
        examples = [v for v in df[col].tolist() if v][:3]
        columns.append({"name": col.strip(), "examples": examples})
    return jsonify({"columns": columns})


@app.route("/parse", methods=["POST"])
def parse_file():
    path = os.path.join(app.config["UPLOAD_FOLDER"], "input.xlsx")
    if not os.path.exists(path):
        return jsonify({"error": "no file uploaded"}), 400

    body       = request.get_json(silent=True) or {}
    column_map = body.get("column_map") or None

    val = validate(path, column_map=column_map)
    if not val.ok:
        return jsonify({"errors": val.errors, "warnings": val.warnings}), 400

    roots, col_labels = parse(path, column_map=column_map)

    result = []
    for root in roots:
        sections = []
        for sec in root.sections:
            nodes = []
            for node in sec.nodes:
                nodes.append({
                    "code":             node.code,
                    "description":      node.description,
                    "is_static":        node.is_static,
                    "raw_codes":        node.raw_codes,
                    "raw_descriptions": node.raw_descriptions,
                    "raw_present_in":   node.raw_present_in,
                    "present_in":       node.present_in,
                })
            sections.append({
                "prefix":      sec.prefix,
                "label":       sec.label,
                "description": sec.description,
                "nodes":       nodes,
            })
        result.append({
            "code":        root.code,
            "description": root.description,
            "instances":   root.instances,
            "count":       root.count,
            "sections":    sections,
        })

    return jsonify({"main_systems": result, "col_labels": col_labels, "warnings": val.warnings})


@app.route("/generate", methods=["POST"])
def generate():
    path = os.path.join(app.config["UPLOAD_FOLDER"], "input.xlsx")
    if not os.path.exists(path):
        return jsonify({"error": "no file uploaded"}), 400

    body       = request.get_json(silent=True) or {}
    ungroup    = body.get("ungroup", {})
    column_map = body.get("column_map") or None

    roots, col_labels = parse(path, column_map=column_map)
    roots = _apply_ungroup(roots, ungroup)

    total_pages, overview_page_nums, f1_first_pages, matrix_pages = _plan_pages(roots)

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()

    c = rl_canvas.Canvas(tmp.name, pagesize=landscape(A3))
    c.setTitle("Structure Tree")

    draw_overview_pages(c, roots, overview_page_nums, f1_first_pages, total_pages)

    for i, root in enumerate(roots):
        c.showPage()
        ov_pg  = overview_page_nums[i // cfg.CARDS_PER_PAGE]
        mat_pg = matrix_pages.get(root.code)

        draw_tree_pages(
            c, root,
            first_page=f1_first_pages[root.code],
            overview_page=ov_pg,
            total_pages=total_pages,
            col_labels=col_labels,
            matrix_page=mat_pg,
        )

        if mat_pg is not None:
            c.showPage()
            draw_matrix_page(c, root, pg=mat_pg, overview_page=ov_pg, total_pages=total_pages)

    c.save()

    return send_file(
        tmp.name,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"structure_tree_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
    )


def _apply_ungroup(roots, ungroup: dict):
    if not ungroup:
        return roots

    roots = copy.deepcopy(roots)

    for key, is_ungrouped in ungroup.items():
        if not is_ungrouped:
            continue

        parts = key.split("|")
        if len(parts) != 3:
            continue

        root_idx, prefix, node_idx = int(parts[0]), parts[1], int(parts[2])

        try:
            root = roots[root_idx]
            sec  = next((s for s in root.sections if s.prefix == prefix), None)
            if sec is None:
                continue
            node = sec.nodes[node_idx]
        except (IndexError, StopIteration):
            continue

        if len(node.raw_codes) <= 1:
            continue

        expanded = [
            Node(
                code=f"={c}",
                description=node.raw_descriptions.get(c, ""),
                is_static=node.is_static,
                raw_codes=[c],
                raw_descriptions={c: node.raw_descriptions.get(c, "")},
                raw_present_in={c: node.raw_present_in.get(c, node.present_in)},
                present_in=node.raw_present_in.get(c, node.present_in),
            )
            for c in node.raw_codes
        ]

        sec.nodes = sec.nodes[:node_idx] + expanded + sec.nodes[node_idx + 1:]

    return roots


def _plan_pages(roots):
    n_ov_pages         = math.ceil(len(roots) / cfg.CARDS_PER_PAGE)
    overview_page_nums = list(range(1, n_ov_pages + 1))

    f1_first_pages: dict[str, int] = {}
    matrix_pages:   dict[str, int] = {}
    cursor = n_ov_pages + 1

    for root in roots:
        f1_first_pages[root.code] = cursor
        chunks = _chunk_sections(root.sections, cfg.MAX_COLS_PER_PAGE)
        pages, _ = _plan_all_pages(chunks)
        cursor += len(pages)
        if has_optional(root):
            matrix_pages[root.code] = cursor
            cursor += 1

    total_pages = cursor - 1
    return total_pages, overview_page_nums, f1_first_pages, matrix_pages


if __name__ == "__main__":
    app.run(debug=True, port=5000)