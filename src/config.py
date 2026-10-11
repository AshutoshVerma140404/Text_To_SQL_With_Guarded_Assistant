"""Configuration settings and environment variable management."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Find workspace root (parent of src)
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env if present
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# Google Gemini Configuration
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

# Database Configuration
DEFAULT_DB_PATH = BASE_DIR / "data" / "app_database.db"
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH)))

# Schema path
SCHEMA_PATH = BASE_DIR / "sql" / "schema.sql"

# Safety and Execution Limits
QUERY_TIMEOUT_SECONDS = int(os.getenv("QUERY_TIMEOUT_SECONDS", "5"))
MAX_ROW_LIMIT = int(os.getenv("MAX_ROW_LIMIT", "1000"))
DEFAULT_ROW_LIMIT = int(os.getenv("DEFAULT_ROW_LIMIT", "100"))

# Security Allowlists and Blocklists
ALLOWED_TABLES = {"customers", "products", "orders"}
DISALLOWED_SYSTEM_TABLES = {
    "sqlite_master",
    "sqlite_temp_master",
    "sqlite_sequence",
    "sqlite_stat1",
    "sqlite_stat4",
}

DISALLOWED_FUNCTIONS = {
    "load_extension",
    "eval",
    "randomblob",
}
