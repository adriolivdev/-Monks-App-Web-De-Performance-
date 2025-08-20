# backend/app.py
# -----------------------------------------------------------------------------
# API Flask (CORS + Compress)
# - login/logout/me
# - /api/data (paginado + totais)
# - /api/export (CSV do filtro atual)
# - /api/date-range
# - /api/options (autocomplete)
# - /api/compare (períodos A x B)
# - /api/import-start, /api/import, /api/import-progress (progresso de import)
# -----------------------------------------------------------------------------

from flask import Flask, request, jsonify, session, send_from_directory, Response
from flask_cors import CORS
from flask_compress import Compress
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import uuid
from threading import Lock

from auth import authenticate, get_current_user, logout_user
from data_loader import (
    load_users, query_metrics_sql, stream_export_csv, get_date_bounds,
    import_csv_file, METRICS_CSV, get_distinct_values, compute_totals
)

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "..", "frontend"),
    static_url_path=""
)
CORS(app, supports_credentials=True)
Compress(app)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

# -------- progresso em memória (simples) --------
IMPORT_PROGRESS = {}
IMPORT_LOCK = Lock()

def set_progress(job_id: str, stage: str, pct: int | None = None, message: str | None = None):
    with IMPORT_LOCK:
        cur = IMPORT_PROGRESS.get(job_id, {})
        cur["stage"] = stage
        if pct is not None:
            cur["pct"] = int(max(0, min(100, pct)))
        if message is not None:
            cur["message"] = message
        IMPORT_PROGRESS[job_id] = cur

# ---------------- AUTH ----------------

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

# ---------------- DATA ----------------

@app.route("/api/data", methods=["GET"])
def data():
    user = get_current_user(session)
    if not user:
        return jsonify({"error": "Não autenticado"}), 401

    try:
        date_from   = request.args.get("date_from")
        date_to     = request.args.get("date_to")
        account_id  = request.args.get("account_id")
        campaign_id = request.args.get("campaign_id")
        sort_by     = request.args.get("sort_by")
        sort_dir    = request.args.get("sort_dir", "asc")
        page        = int(request.args.get("page", 1))
        page_size   = int(request.args.get("page_size", 50))
        include_cost = (user.get("role") == "admin")

        rows, total, totals = query_metrics_sql(
            date_from=date_from, date_to=date_to,
            account_id=account_id, campaign_id=campaign_id,
            sort_by=sort_by, sort_dir=sort_dir,
            page=page, page_size=page_size,
            include_cost=include_cost,
        )

        return jsonify({
            "rows": rows, "page": page, "page_size": page_size,
            "total": int(total), "totals": totals
        }), 200

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500

@app.route("/api/export", methods=["GET"])
def export_csv():
    user = get_current_user(session)
    if not user:
        return jsonify({"error": "Não autenticado"}), 401

    date_from   = request.args.get("date_from")
    date_to     = request.args.get("date_to")
    account_id  = request.args.get("account_id")
    campaign_id = request.args.get("campaign_id")
    sort_by     = request.args.get("sort_by")
    sort_dir    = request.args.get("sort_dir", "asc")
    include_cost = (user.get("role") == "admin")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    df = (date_from or "all"); dt = (date_to or "all")
    filename = f"metrics_export_{df}_{dt}_{ts}.csv"

    gen = stream_export_csv(date_from, date_to, account_id, campaign_id, sort_by, sort_dir, include_cost)
    return Response(gen, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.route("/api/date-range", methods=["GET"])
def date_range():
    return jsonify(get_date_bounds()), 200

@app.route("/api/options", methods=["GET"])
def options():
    user = get_current_user(session)
    if not user:
        return jsonify({"error": "Não autenticado"}), 401

    field = request.args.get("field", "")
    q     = request.args.get("q", "")
    limit = int(request.args.get("limit", 100))
    vals = get_distinct_values(field, q, limit)
    return jsonify({"values": vals}), 200

# ---- comparação de períodos ----
@app.route("/api/compare", methods=["GET"])
def compare():
    user = get_current_user(session)
    if not user:
        return jsonify({"error": "Não autenticado"}), 401

    include_cost = (user.get("role") == "admin")

    a_from = request.args.get("date_from_a")
    a_to   = request.args.get("date_to_a")
    b_from = request.args.get("date_from_b")
    b_to   = request.args.get("date_to_b")
    account_id  = request.args.get("account_id")
    campaign_id = request.args.get("campaign_id")

    try:
        total_a = compute_totals(a_from, a_to, account_id, campaign_id, include_cost)
        total_b = compute_totals(b_from, b_to, account_id, campaign_id, include_cost)

        diff_abs = {}
        diff_pct = {}
        for k in total_a.keys():
            da = float(total_a.get(k, 0.0))
            db = float(total_b.get(k, 0.0))
            diff_abs[k] = db - da
            diff_pct[k] = None if da == 0 else ((db - da) / da) * 100.0

        return jsonify({"total_a": total_a, "total_b": total_b,
                        "diff_abs": diff_abs, "diff_pct": diff_pct}), 200
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500

# ---------------- IMPORT (com progresso) ----------------

@app.route("/api/import-start", methods=["POST"])
def import_start():
    user = get_current_user(session)
    if not user:
        return jsonify({"error": "Não autenticado"}), 401
    if user.get("role") != "admin":
        return jsonify({"error": "Acesso negado (apenas admin)"}), 403

    job_id = uuid.uuid4().hex
    set_progress(job_id, "ready", 0, "Aguardando upload")
    return jsonify({"job_id": job_id}), 200

@app.route("/api/import-progress", methods=["GET"])
def import_progress():
    user = get_current_user(session)
    if not user:
        return jsonify({"error": "Não autenticado"}), 401
    job_id = request.args.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id é obrigatório"}), 400
    with IMPORT_LOCK:
        return jsonify(IMPORT_PROGRESS.get(job_id, {"stage": "unknown", "pct": 0})), 200

@app.route("/api/import", methods=["POST"])
def import_metrics():
    user = get_current_user(session)
    if not user:
        return jsonify({"error": "Não autenticado"}), 401
    if user.get("role") != "admin":
        return jsonify({"error": "Acesso negado (apenas admin)"}), 403

    job_id = request.args.get("job_id") or request.form.get("job_id") or uuid.uuid4().hex
    set_progress(job_id, "uploading", 0, "Recebendo arquivo")

    if "file" not in request.files:
        set_progress(job_id, "error", 0, "Arquivo ausente (campo 'file')")
        return jsonify({"error": "Envie um arquivo em form-data com campo 'file'"}), 400

    f = request.files["file"]
    if not f.filename.lower().endswith(".csv"):
        set_progress(job_id, "error", 0, "Apenas .csv é aceito")
        return jsonify({"error": "Apenas .csv é aceito"}), 400

    filename = secure_filename(f.filename) or f"metrics_{uuid.uuid4().hex}.csv"
    os.makedirs(os.path.dirname(METRICS_CSV), exist_ok=True)
    temp_path = os.path.join(os.path.dirname(METRICS_CSV), f"__upload_{uuid.uuid4().hex}.csv")

    f.save(temp_path)
    set_progress(job_id, "importing", 0, "Importando CSV")

    try:
        def _cb(stage: str, pct: int, message: str | None = None):
            set_progress(job_id, stage, pct, message)

        imported_rows = import_csv_file(temp_path, progress_cb=_cb)
        os.replace(temp_path, METRICS_CSV)
        set_progress(job_id, "finalizing", 100, "Finalizando")
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        set_progress(job_id, "error", 0, str(e))
        return jsonify({"error": f"Falha ao importar CSV: {e}"}), 400

    set_progress(job_id, "done", 100, f"Importação concluída ({imported_rows} linhas)")
    return jsonify({"ok": True, "message": f"Importação concluída ({imported_rows} linhas).", "job_id": job_id}), 200

# ---------------- FRONT ----------------

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
