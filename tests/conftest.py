"""Pytest fixtures for offline and isolated testing."""

import pytest
import tempfile
from pathlib import Path
from src.database import init_db, get_table_columns_map
from src.ingestion import ingest_data
from src.data_generator import generate_synthetic_data
from src.config import SCHEMA_PATH


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Creates and returns an isolated temporary SQLite database populated with synthetic data."""
    db_file = tmp_path / "test_app_database.db"
    raw_data = generate_synthetic_data(seed=99)
    ingest_data(raw_data, db_path=db_file, schema_path=SCHEMA_PATH)
    return db_file


@pytest.fixture
def empty_temp_db(tmp_path: Path) -> Path:
    """Creates and returns an empty initialized temporary SQLite database schema."""
    db_file = tmp_path / "test_empty.db"
    init_db(db_path=db_file, schema_path=SCHEMA_PATH)
    return db_file


@pytest.fixture
def schema_columns(temp_db: Path):
    """Returns mapping of table names to columns for the temporary database."""
    return get_table_columns_map(temp_db)
