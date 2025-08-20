# backend/utils.py : se eu quiser usar depois em usar em melhorias, tipo paginação/export etc.)
from datetime import datetime

def parse_date_safe(value):
    try:
        return datetime.fromisoformat(value).date()
    except Exception:
        return None
