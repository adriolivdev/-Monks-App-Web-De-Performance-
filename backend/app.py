# backend/app.py
from flask import Flask, request, jsonify, session, send_from_directory, Response
from flask_cors import CORS
from flask_compress import Compress
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import uuid

from auth import authenticate, get_current_user, logout_user
from data_loader import (
    load_users,
    query_metrics_sql,
    stream_export_csv,
    get_date_bounds,
    import_csv_file,
    METRICS_CSV,
)

# --- Flask app (serve o frontend em ../frontend) ---
app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "..", "frontend"),
    static_url_path=""
)

# CORS + compressão (gzip)
CORS(app, supports_credentials=True)
Compress(app)

# Chave de sessão (use variável de ambiente em produção)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")


# ==========================
#         AUTH
# ==========================
@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True, silent=True) or {}
    email_or_user = (data.get("email") or data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    users = load_users()
    user = authenticate(users, email_or_user, password)
    if not user:
        return jsonify({"ok": False, "error": "Credenciais inválidas"}), 401

    session["user"] = {"username": email_or_user, "role": user["role"]}
    return jsonify({"ok": True, "user": session["user"]}), 200


@app.route("/api/me", methods=["GET"])
def me():
    return jsonify({"user": get_current_user(session)}), 200


@app.route("/api/logout", methods=["POST"])
def logout():
    logout_user(session)
    return jsonify({"ok": True}), 200


# ==========================
#          DATA
# ==========================
@app.route("/api/data", methods=["GET"])
def data():
    user = get_current_user(session)
    if not user:
        return jsonify({"error": "Não autenticado"}), 401

    # Query params
    date_from = request.args.get("date_from")
    date_to   = request.args.get("date_to")
    sort_by   = request.args.get("sort_by")
    sort_dir  = request.args.get("sort_dir", "asc")
    page      = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 50))

    include_cost = (user.get("role") == "admin")

    rows, total = query_metrics_sql(
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
        include_cost=include_cost,
    )

    return jsonify({
        "rows": rows,
        "page": page,
        "page_size": page_size,
        "total": int(total)
    })


@app.route("/api/export", methods=["GET"])
def export_csv():
    user = get_current_user(session)
    if not user:
        return jsonify({"error": "Não autenticado"}), 401

    date_from = request.args.get("date_from")
    date_to   = request.args.get("date_to")
    sort_by   = request.args.get("sort_by")
    sort_dir  = request.args.get("sort_dir", "asc")
    include_cost = (user.get("role") == "admin")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    df = (date_from or "all"); dt = (date_to or "all")
    filename = f"metrics_export_{df}_{dt}_{ts}.csv"

    gen = stream_export_csv(date_from, date_to, sort_by, sort_dir, include_cost)
    return Response(
        gen,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.route("/api/date-range", methods=["GET"])
def date_range():
    return jsonify(get_date_bounds()), 200


@app.route("/api/import", methods=["POST"])
def import_metrics():
    """
    Upload de CSV (apenas admin). O CSV enviado substitui o metrics.csv
    e é importado para o SQLite (metrics.db).
    """
    user = get_current_user(session)
    if not user:
        return jsonify({"error": "Não autenticado"}), 401
    if user.get("role") != "admin":
        return jsonify({"error": "Acesso negado (apenas admin pode importar)"}), 403

    if "file" not in request.files:
        return jsonify({"error": "Envie um arquivo em form-data com campo 'file'"}), 400

    f = request.files["file"]
    if not f.filename.lower().endswith(".csv"):
        return jsonify({"error": "Apenas .csv é aceito"}), 400

    # salvar temporário e substituir
    filename = secure_filename(f.filename) or f"metrics_{uuid.uuid4().hex}.csv"
    os.makedirs(os.path.dirname(METRICS_CSV), exist_ok=True)
    temp_path = os.path.join(os.path.dirname(METRICS_CSV), f"__upload_{uuid.uuid4().hex}.csv")
    f.save(temp_path)

    try:
        # importa para o DB e substitui o CSV oficial
        imported_rows = import_csv_file(temp_path)
        os.replace(temp_path, METRICS_CSV)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"error": f"Falha ao importar CSV: {e}"}), 500

    return jsonify({"ok": True, "message": f"Importação concluída ({imported_rows} linhas)."}), 200


# ==========================
#        FRONTEND
# ==========================
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ==========================
#         MAIN
# ==========================
if __name__ == "__main__":
    # debug=False para medir performance real
    app.run(host="0.0.0.0", port=8000, debug=False)
    # (opcional no Windows)
    # waitress-serve --listen=0.0.0.0:8000 backend.app:app
