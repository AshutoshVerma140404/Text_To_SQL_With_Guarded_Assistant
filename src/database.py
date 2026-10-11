"""Database connection management, schema initialization, and schema introspection."""

import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Set
from src.config import DATABASE_PATH, SCHEMA_PATH, ALLOWED_TABLES


def get_read_write_connection(db_path: Path | str = DATABASE_PATH) -> sqlite3.Connection:
    """Returns a read-write SQLite connection, ensuring foreign keys are enabled."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def get_read_only_connection(db_path: Path | str = DATABASE_PATH) -> sqlite3.Connection:
    """Returns a strictly read-only SQLite connection using URI mode=ro and PRAGMA query_only."""
    path = Path(db_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Database file not found at {path}")

    # Use SQLite URI read-only mode
    uri_path = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri_path, uri=True)
    conn.execute("PRAGMA query_only = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str = DATABASE_PATH, schema_path: Path | str = SCHEMA_PATH) -> None:
    """Initializes SQLite database tables and indexes from schema DDL file."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    with get_read_write_connection(path) as conn:
        conn.executescript(schema_sql)
        conn.commit()


def get_table_columns_map(db_path: Path | str = DATABASE_PATH) -> Dict[str, Set[str]]:
    """Returns a dictionary mapping each table to its set of column names."""
    table_columns: Dict[str, Set[str]] = {}
    path = Path(db_path)
    if not path.exists():
        return table_columns

    with get_read_only_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row["name"] for row in cursor.fetchall()]
        
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table});")
            cols = {row["name"] for row in cursor.fetchall()}
            table_columns[table] = cols
            
    return table_columns


def get_schema_summary(db_path: Path | str = DATABASE_PATH) -> str:
    """Returns a human-readable and LLM-friendly schema summary including tables and columns."""
    path = Path(db_path)
    if not path.exists():
        return "Database does not exist yet. Please run ingestion to initialize."

    schema_lines = []
    with get_read_only_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
        tables = cursor.fetchall()
        for t in tables:
            schema_lines.append(f"-- Table: {t['name']}")
            schema_lines.append(t["sql"] + ";\n")

    return "\n".join(schema_lines)


def get_table_row_counts(db_path: Path | str = DATABASE_PATH) -> Dict[str, int]:
    """Returns a dictionary with row counts for each allowed table."""
    counts = {}
    path = Path(db_path)
    if not path.exists():
        return counts

    with get_read_only_connection(path) as conn:
        cursor = conn.cursor()
        for table in ALLOWED_TABLES:
            try:
                cursor.execute(f"SELECT COUNT(*) AS count FROM {table};")
                row = cursor.fetchone()
                counts[table] = row["count"] if row else 0
            except sqlite3.Error:
                counts[table] = 0
    return counts


def get_sample_rows(db_path: Path | str = DATABASE_PATH, table_name: str = "customers", limit: int = 3) -> List[Dict[str, Any]]:
    """Fetches sample rows from a specified table."""
    if table_name not in ALLOWED_TABLES:
        return []
    path = Path(db_path)
    if not path.exists():
        return []

    with get_read_only_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit};")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
