import os
from flask import Flask, render_template, request, jsonify
from core.validator import validate
from core.excel_parser import parse


app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'no file'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'empty filename'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'invalid file type'}), 400

    path = os.path.join(app.config['UPLOAD_FOLDER'], 'input.xlsx')
    file.save(path)

    val = validate(path)

    return jsonify({
        'ok': val.ok,
        'errors': val.errors,
        'warnings': val.warnings,
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
