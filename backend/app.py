# backend/app.py
# -----------------------------------------------------------------------------
# API Flask
#
# Rotas:
# - /api/login, /api/logout, /api/me               → sessão/usuário
# - /api/data                                      → dados paginados + totais (filtros/ordenação)
# - /api/export                                    → exportação CSV do filtro atual
# - /api/date-range                                → bounds de data (min/max)
# - /api/options?field=account_id|campaign_id&q=   → autocomplete
# - /api/import (POST, admin)                      → upload de CSV e reimport
# - / (static)                                     → entrega o frontend
#
# Observações:
# - RBAC simples via session: role=admin habilita cost_micros
# - Em produção, rodar com waitress/uwsgi/gunicorn e SECRET_KEY via ambiente.
# -----------------------------------------------------------------------------

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
    get_distinct_values,
)

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "..", "frontend"),
    static_url_path=""
)
CORS(app, supports_credentials=True)
Compress(app)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

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
    """
    Retorna dados paginados + totais do filtro atual.
    Query params aceitos:
      - date_from, date_to (YYYY-MM-DD)
      - account_id, campaign_id (contém)
      - sort_by, sort_dir (asc|desc)
      - page, page_size
    """
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
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
            campaign_id=campaign_id,
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
            "total": int(total),
            "totals": totals
        }), 200

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/export", methods=["GET"])
def export_csv():
    """
    Exporta o filtro atual em CSV (todas as linhas, sem paginação).
    Respeita RBAC (cost_micros apenas para admin).
    """
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
    """
    Retorna {min, max} de date na tabela. Útil para preencher inputs do front.
    """
    return jsonify(get_date_bounds()), 200


@app.route("/api/options", methods=["GET"])
def options():
    """
    Autocomplete de valores distintos:
      /api/options?field=account_id&q=8181&limit=20
      /api/options?field=campaign_id&q=6320&limit=20
    """
    user = get_current_user(session)
    if not user:
        return jsonify({"error": "Não autenticado"}), 401

    field = request.args.get("field", "")
    q     = request.args.get("q", "")
    limit = int(request.args.get("limit", 100))
    vals = get_distinct_values(field, q, limit)
    return jsonify({"values": vals}), 200


@app.route("/api/import", methods=["POST"])
def import_metrics():
    """
    Upload de CSV (apenas admin). Salva temporário, importa para o DB,
    e substitui o metrics.csv “oficial”.
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

    filename = secure_filename(f.filename) or f"metrics_{uuid.uuid4().hex}.csv"
    os.makedirs(os.path.dirname(METRICS_CSV), exist_ok=True)
    temp_path = os.path.join(os.path.dirname(METRICS_CSV), f"__upload_{uuid.uuid4().hex}.csv")
    f.save(temp_path)

    try:
        imported_rows = import_csv_file(temp_path)
        os.replace(temp_path, METRICS_CSV)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"error": f"Falha ao importar CSV: {e}"}), 500

    return jsonify({"ok": True, "message": f"Importação concluída ({imported_rows} linhas)."}), 200


# ---------------- FRONT ----------------

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    # Em produção, prefira waitress/uwsgi/gunicorn (ex.: waitress-serve backend.app:app)
    app.run(host="0.0.0.0", port=8000, debug=False)
