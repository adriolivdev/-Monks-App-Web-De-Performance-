# backend/import_csv_to_sqlite.py
import sqlite3
import pandas as pd
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "metrics.csv"
DB_PATH  = Path(__file__).resolve().parents[1] / "data" / "metrics.db"

def create_schema(conn):
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_cmp ON metrics(campaign_id);")
    conn.commit()

def import_csv(conn, chunksize=200_000):
    conn.execute("DELETE FROM metrics;")
    conn.commit()

    total = 0
    for chunk in pd.read_csv(
        CSV_PATH,
        dtype={"account_id": str, "campaign_id": str},
        chunksize=chunksize,
        low_memory=False
    ):
        for col in ["cost_micros","clicks","conversions","impressions","interactions"]:
            if col in chunk.columns:
                chunk[col] = pd.to_numeric(chunk[col], errors="coerce")
        chunk["date"] = pd.to_datetime(chunk["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        chunk.to_sql("metrics", conn, if_exists="append", index=False, method="multi")
        total += len(chunk)
        print(f"+ {len(chunk)} (total {total})")

    conn.execute("VACUUM;")
    conn.execute("ANALYZE;")
    conn.commit()

def main():
    print(f"Lendo CSV: {CSV_PATH}")
    print(f"Criando DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        create_schema(conn)
        import_csv(conn)
    finally:
        conn.close()
    print("OK!")

if __name__ == "__main__":
    main()
