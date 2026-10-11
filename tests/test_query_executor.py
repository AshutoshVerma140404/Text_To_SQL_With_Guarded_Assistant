"""Unit tests for sandboxed read-only query execution and limits."""

import sqlite3
import pytest
from pathlib import Path
from src.query_executor import execute_read_only_query
from src.database import get_table_row_counts, get_read_only_connection


def test_read_only_query_execution_success(temp_db: Path):
    """Test: Executing a valid SELECT query successfully returns columns, rows, and timing."""
    sql = "SELECT customer_id, name, city FROM customers ORDER BY customer_id ASC LIMIT 5;"
    result = execute_read_only_query(sql, db_path=temp_db)

    assert result.success is True
    assert result.error_message is None
    assert result.columns == ["customer_id", "name", "city"]
    assert len(result.rows) == 5
    assert result.row_count == 5
    assert result.execution_time_ms >= 0.0


def test_database_immutability(temp_db: Path):
    """Test: Database state is unchanged and write attempts fail under read-only mode."""
    initial_counts = get_table_row_counts(temp_db)

    # Attempting to execute an INSERT or UPDATE directly via read-only executor
    write_sql = "INSERT INTO customers (customer_id, name, city, signup_date) VALUES (9999, 'Test', 'Nowhere', '2025-01-01');"
    result = execute_read_only_query(write_sql, db_path=temp_db)

    # Must fail
    assert result.success is False
    assert result.error_message is not None

    # Verify counts remain identical
    after_counts = get_table_row_counts(temp_db)
    assert initial_counts == after_counts


def test_execution_row_capping(temp_db: Path):
    """Test: Queries returning more rows than max_rows are properly capped and flagged."""
    sql = "SELECT * FROM orders;"
    result = execute_read_only_query(sql, db_path=temp_db, max_rows=10)

    assert result.success is True
    assert len(result.rows) == 10
    assert result.truncated is True


def test_nonexistent_database():
    """Test: Query executor handles missing database gracefully without unhandled exception."""
    result = execute_read_only_query("SELECT 1;", db_path="nonexistent_db_path.db")
    assert result.success is False
    assert "does not exist" in result.error_message
