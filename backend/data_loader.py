# backend/data_loader.py
import os
import sqlite3
import pandas as pd
from typing import Optional, Tuple, List, Dict, Any, Iterator
import csv
from io import StringIO

# === Caminhos base ===
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data")

USERS_CSV   = os.path.join(DATA_DIR, "users.csv")
METRICS_CSV = os.path.join(DATA_DIR, "metrics.csv")
DB_PATH     = os.path.join(DATA_DIR, "metrics.db")

# Colunas permitidas para ORDER BY
ALLOWED_SORT = {
    "account_id","campaign_id","cost_micros","clicks","conversions","impressions","interactions","date",
}

# ----------- BOOTSTRAP DO BANCO -----------
def create_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        account_id   TEXT,
        campaign_id  TEXT,
        cost_micros  REAL,
        clicks       REAL,
        conversions  REAL,
        impressions  REAL,
        interactions REAL,
        date         TEXT
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_date ON metrics(date);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_acct ON metrics(account_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_cmp  ON metrics(campaign_id);")
    conn.commit()

def import_csv_chunks(conn: sqlite3.Connection, csv_path: str, read_chunksize: int = 200_000) -> int:
    """
    Importa um CSV para a tabela metrics em blocos de leitura (read_chunksize)
    e com INSERTs em lotes menores para não estourar o limite de variáveis do SQLite.
    Retorna o total de linhas importadas.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV não encontrado: {csv_path}")

    # Limpa a tabela (import idempotente)
    conn.execute("DELETE FROM metrics;")
    conn.commit()

    total = 0
    for chunk in pd.read_csv(
        csv_path,
        dtype={"account_id": str, "campaign_id": str},
        chunksize=read_chunksize,
        low_memory=False
    ):
        # Normaliza numéricos e data
        for col in ["cost_micros","clicks","conversions","impressions","interactions"]:
            if col in chunk.columns:
                chunk[col] = pd.to_numeric(chunk[col], errors="coerce")
        chunk["date"] = pd.to_datetime(chunk["date"], errors="coerce").dt.strftime("%Y-%m-%d")

        # >>> CORREÇÃO: limitar o tamanho do lote no INSERT <<<
        # SQLite geralmente permite 999 variáveis por statement
        SQLITE_MAX_VARS = 999
        n_cols = len(chunk.columns)
        # Quantas linhas cabem por INSERT com method="multi"
        rows_per_insert = max(1, (SQLITE_MAX_VARS // n_cols) - 1)  # margem de segurança
        # Executa a inserção em lotes pequenos
        chunk.to_sql(
            "metrics",
            conn,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=rows_per_insert
        )

        total += len(chunk)

    conn.execute("ANALYZE;")
    conn.commit()
    return total

def import_csv_file(csv_path: str) -> int:
    """Abre conexão e importa um CSV (helper para a rota /api/import)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        create_schema(conn)
        return import_csv_chunks(conn, csv_path)
    finally:
        conn.close()

def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (name,))
    return cur.fetchone() is not None

def ensure_db_ready() -> None:
    """
    Se o DB não existir ou estiver vazio, cria schema e tenta importar do metrics.csv (se existir).
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        create_schema(conn)
        cur = conn.execute("SELECT COUNT(*) FROM metrics;")
        (count,) = cur.fetchone()
        if count == 0 and os.path.exists(METRICS_CSV):
            import_csv_chunks(conn, METRICS_CSV)
    finally:
        conn.close()

# ----------- USUÁRIOS -----------
def load_users() -> Dict[str, Dict[str, str]]:
    """users.csv -> dict indexado por username/email"""
    if not os.path.exists(USERS_CSV):
        return {}
    df = pd.read_csv(USERS_CSV, dtype=str).fillna("")
    users: Dict[str, Dict[str, str]] = {}
    for _, row in df.iterrows():
        key = (row.get("username") or row.get("email") or "").strip()
        if not key:
            continue
        users[key] = {
            "password": str(row.get("password") or ""),
            "role":     str(row.get("role") or "user"),
        }
    return users

# ----------- CONSULTA PAGINADA -----------
def query_metrics_sql(
    date_from: Optional[str],
    date_to: Optional[str],
    sort_by: Optional[str],
    sort_dir: Optional[str],
    page: int,
    page_size: int,
    include_cost: bool,
) -> Tuple[List[Dict[str, Any]], int]:

    ensure_db_ready()

    sort_by  = sort_by if sort_by in ALLOWED_SORT else "date"
    sort_dir = "DESC" if str(sort_dir or "").lower() == "desc" else "ASC"

    try: page = int(page)
    except: page = 1
    page = max(1, page)

    try: page_size = int(page_size)
    except: page_size = 50
    page_size = max(1, min(200, page_size))

    offset = (page - 1) * page_size

    cols = "account_id, campaign_id, clicks, conversions, impressions, interactions, date"
    if include_cost:
        cols = "account_id, campaign_id, cost_micros, clicks, conversions, impressions, interactions, date"

    where = []
    params: List[Any] = []
    if date_from:
        where.append("date >= ?")
        params.append(date_from)
    if date_to:
        where.append("date <= ?")
        params.append(date_to)
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    sql_count = f"SELECT COUNT(*) FROM metrics {where_clause};"
    sql_rows  = f"""
        SELECT {cols}
        FROM metrics
        {where_clause}
        ORDER BY {sort_by} {sort_dir}
        LIMIT ? OFFSET ?;
    """

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(sql_count, params)
        (total,) = cur.fetchone()
        cur = conn.execute(sql_rows, params + [page_size, offset])
        headers = [c[0] for c in cur.description]
        rows = [dict(zip(headers, r)) for r in cur.fetchall()]
    finally:
        conn.close()

    return rows, int(total)

# ----------- EXPORT STREAMING -----------
def _build_export_sql(date_from, date_to, sort_by, sort_dir, include_cost):
    sort_by  = sort_by if sort_by in ALLOWED_SORT else "date"
    sort_dir = "DESC" if str(sort_dir or "").lower() == "desc" else "ASC"

    cols = "account_id, campaign_id, clicks, conversions, impressions, interactions, date"
    if include_cost:
        cols = "account_id, campaign_id, cost_micros, clicks, conversions, impressions, interactions, date"

    where = []
    params: List[Any] = []
    if date_from:
        where.append("date >= ?")
        params.append(date_from)
    if date_to:
        where.append("date <= ?")
        params.append(date_to)
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    sql = f"""
        SELECT {cols}
        FROM metrics
        {where_clause}
        ORDER BY {sort_by} {sort_dir};
    """
    return sql, params

def stream_export_csv(date_from, date_to, sort_by, sort_dir, include_cost) -> Iterator[str]:
    ensure_db_ready()
    sql, params = _build_export_sql(date_from, date_to, sort_by, sort_dir, include_cost)

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(sql, params)
        headers = [c[0] for c in cur.description]

        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)

        for row in cur:
            writer.writerow(row)
            out = buf.getvalue()
            if out:
                yield out
                buf.seek(0); buf.truncate(0)
    finally:
        conn.close()

# ----------- BOUNDS DE DATA -----------
def get_date_bounds() -> Dict[str, Optional[str]]:
    ensure_db_ready()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute("SELECT MIN(date), MAX(date) FROM metrics;")
        row = cur.fetchone() or (None, None)
        return {"min": row[0], "max": row[1]}
    finally:
        conn.close()
