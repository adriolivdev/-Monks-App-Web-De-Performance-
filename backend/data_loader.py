# backend/data_loader.py
# -----------------------------------------------------------------------------
# Camada de dados da aplicação.
#
# Responsabilidades:
# - Criar/garantir schema do SQLite (tabela metrics + índices)
# - Importar CSV (metrics.csv) em chunks, com INSERT em lotes (evita limite do SQLite)
# - Consultas paginadas + totais (para o rodapé do front)
# - Exportação em streaming (CSV) respeitando filtros
# - Bounds de data (min/max) para preencher inputs
# - Autocomplete (valores distintos) de account_id e campaign_id
# - Leitura de users.csv (para autenticação)
#
# Observações de manutenção:
# - Pensado para CSVs grandes (milhões de linhas). Evita "too many SQL variables"
#   calculando o chunk de INSERT com base no limite do SQLite (~999 variáveis).
# - Qualquer alteração de coluna deve ser refletida em:
#   * create_schema
#   * lista ALLOWED_SORT
#   * montagens de SELECT (cols)
#   * totais (query_metrics_sql)
# -----------------------------------------------------------------------------

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

# Colunas permitidas para ORDER BY (sanitização de sort)
ALLOWED_SORT = {
    "account_id", "campaign_id", "cost_micros",
    "clicks", "conversions", "impressions", "interactions", "date",
}

# ----------- SCHEMA / BOOTSTRAP -----------

def create_schema(conn: sqlite3.Connection) -> None:
    """
    Cria a tabela 'metrics' e índices, se ainda não existirem.
    """
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
    Importa o arquivo CSV em blocos de leitura (read_chunksize) e grava no SQLite
    em lotes pequenos (chunksize calculado) para evitar o erro
    'sqlite3.OperationalError: too many SQL variables'.

    Retorna:
        total (int): total de linhas importadas.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV não encontrado: {csv_path}")

    # Limpa a tabela para reimportações (idempotente)
    conn.execute("DELETE FROM metrics;")
    conn.commit()

    total = 0
    for chunk in pd.read_csv(
        csv_path,
        dtype={"account_id": str, "campaign_id": str},
        chunksize=read_chunksize,
        low_memory=False
    ):
        # Normalização de tipos
        for col in ["cost_micros", "clicks", "conversions", "impressions", "interactions"]:
            if col in chunk.columns:
                chunk[col] = pd.to_numeric(chunk[col], errors="coerce")
        # Datas como YYYY-MM-DD (string)
        chunk["date"] = pd.to_datetime(chunk["date"], errors="coerce").dt.strftime("%Y-%m-%d")

        # Evitar "too many SQL variables" no SQLite
        SQLITE_MAX_VARS = 999
        n_cols = len(chunk.columns)
        rows_per_insert = max(1, (SQLITE_MAX_VARS // n_cols) - 1)  # margem de segurança

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
    """
    Helper para a rota /api/import.
    Abre conexão, garante schema e chama import_csv_chunks.
    """
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
    Se o DB estiver vazio, tenta importar automaticamente do METRICS_CSV.
    Usado antes de leituras para garantir que o banco esteja populado.
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
    """
    Lê users.csv e retorna um dict indexado por username/email:
    { "user1": {"password": "xxx", "role": "admin"}, ... }
    """
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


# ----------- HELPERS DE WHERE / SQL DINÂMICO -----------

def _build_where(date_from, date_to, account_id, campaign_id):
    """
    Monta WHERE e lista de parâmetros para filtros. Usa LIKE nos IDs.
    """
    where = []
    params: List[Any] = []
    if date_from:
        where.append("date >= ?")
        params.append(date_from)
    if date_to:
        where.append("date <= ?")
        params.append(date_to)
    if account_id:
        where.append("account_id LIKE ?")
        params.append(f"%{account_id}%")
    if campaign_id:
        where.append("campaign_id LIKE ?")
        params.append(f"%{campaign_id}%")
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    return where_clause, params


# ----------- CONSULTA PAGINADA + TOTAIS -----------

def query_metrics_sql(
    date_from: Optional[str],
    date_to: Optional[str],
    account_id: Optional[str],
    campaign_id: Optional[str],
    sort_by: Optional[str],
    sort_dir: Optional[str],
    page: int,
    page_size: int,
    include_cost: bool,
) -> Tuple[List[Dict[str, Any]], int, Dict[str, float]]:
    """
    Consulta paginada na tabela metrics, com filtros e ordenação.
    Retorna:
      - rows (lista de dicts)
      - total (int) total de linhas do filtro (sem paginação)
      - totals (dict) somatórios do filtro (sem paginação)
    """
    ensure_db_ready()

    sort_by  = sort_by if sort_by in ALLOWED_SORT else "date"
    sort_dir = "DESC" if str(sort_dir or "").lower() == "desc" else "ASC"

    try:
        page = int(page)
    except Exception:
        page = 1
    page = max(1, page)

    try:
        page_size = int(page_size)
    except Exception:
        page_size = 50
    page_size = max(1, min(200, page_size))

    offset = (page - 1) * page_size

    # Seleção de colunas conforme papel (RBAC)
    cols = "account_id, campaign_id, clicks, conversions, impressions, interactions, date"
    if include_cost:
        cols = "account_id, campaign_id, cost_micros, clicks, conversions, impressions, interactions, date"

    where_clause, params = _build_where(date_from, date_to, account_id, campaign_id)

    sql_count = f"SELECT COUNT(*) FROM metrics {where_clause};"
    sql_rows  = f"""
        SELECT {cols}
        FROM metrics
        {where_clause}
        ORDER BY {sort_by} {sort_dir}
        LIMIT ? OFFSET ?;
    """

    # Totais no conjunto filtrado (sem paginação)
    if include_cost:
        sql_totals = f"""
            SELECT
              COALESCE(SUM(clicks),0),
              COALESCE(SUM(conversions),0),
              COALESCE(SUM(impressions),0),
              COALESCE(SUM(interactions),0),
              COALESCE(SUM(cost_micros),0)
            FROM metrics
            {where_clause};
        """
    else:
        sql_totals = f"""
            SELECT
              COALESCE(SUM(clicks),0),
              COALESCE(SUM(conversions),0),
              COALESCE(SUM(impressions),0),
              COALESCE(SUM(interactions),0)
            FROM metrics
            {where_clause};
        """

    conn = sqlite3.connect(DB_PATH)
    try:
        # total
        cur = conn.execute(sql_count, params)
        (total,) = cur.fetchone()

        # página atual
        cur = conn.execute(sql_rows, params + [page_size, offset])
        headers = [c[0] for c in cur.description]
        rows = [dict(zip(headers, r)) for r in cur.fetchall()]

        # totais
        cur = conn.execute(sql_totals, params)
        if include_cost:
            clicks, conv, impr, inter, cost = cur.fetchone()
            totals = {
                "clicks": float(clicks or 0.0),
                "conversions": float(conv or 0.0),
                "impressions": float(impr or 0.0),
                "interactions": float(inter or 0.0),
                "cost_micros": float(cost or 0.0),
            }
        else:
            clicks, conv, impr, inter = cur.fetchone()
            totals = {
                "clicks": float(clicks or 0.0),
                "conversions": float(conv or 0.0),
                "impressions": float(impr or 0.0),
                "interactions": float(inter or 0.0),
            }
    finally:
        conn.close()

    return rows, int(total), totals


# ----------- EXPORT STREAMING -----------

def _build_export_sql(date_from, date_to, account_id, campaign_id, sort_by, sort_dir, include_cost):
    sort_by  = sort_by if sort_by in ALLOWED_SORT else "date"
    sort_dir = "DESC" if str(sort_dir or "").lower() == "desc" else "ASC"

    cols = "account_id, campaign_id, clicks, conversions, impressions, interactions, date"
    if include_cost:
        cols = "account_id, campaign_id, cost_micros, clicks, conversions, impressions, interactions, date"

    where_clause, params = _build_where(date_from, date_to, account_id, campaign_id)
    sql = f"""
        SELECT {cols}
        FROM metrics
        {where_clause}
        ORDER BY {sort_by} {sort_dir};
    """
    return sql, params


def stream_export_csv(date_from, date_to, account_id, campaign_id, sort_by, sort_dir, include_cost) -> Iterator[str]:
    """
    Iterador que vai gerando o CSV linha a linha (baixa memória).
    """
    ensure_db_ready()
    sql, params = _build_export_sql(date_from, date_to, account_id, campaign_id, sort_by, sort_dir, include_cost)

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


# ----------- BOUNDS DE DATA / AUTOCOMPLETE -----------

def get_date_bounds() -> Dict[str, Optional[str]]:
    """
    Retorna as datas mínima e máxima da tabela (para preencher inputs).
    """
    ensure_db_ready()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute("SELECT MIN(date), MAX(date) FROM metrics;")
        row = cur.fetchone() or (None, None)
        return {"min": row[0], "max": row[1]}
    finally:
        conn.close()


def get_distinct_values(column: str, q: str = "", limit: int = 100) -> List[str]:
    """
    Retorna valores distintos de uma coluna (account_id/campaign_id),
    com filtro LIKE %q% e limite configurável (default 100).
    """
    ensure_db_ready()
    if column not in ("account_id", "campaign_id"):
        return []

    where = ""
    params: List[Any] = []
    if q:
        where = f"WHERE {column} LIKE ?"
        params.append(f"%{q}%")

    sql = f"SELECT DISTINCT {column} FROM metrics {where} ORDER BY {column} LIMIT ?;"
    params.append(int(limit))

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(sql, params)
        return [row[0] for row in cur.fetchall() if row and row[0] is not None]
    finally:
        conn.close()
