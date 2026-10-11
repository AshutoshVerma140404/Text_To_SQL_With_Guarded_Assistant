"""Unit tests for AST-based SQL guardrail validation (SQLGlot)."""

import pytest
from src.sql_validator import validate_and_sanitize_sql


def test_valid_select_query():
    """Test 1: Valid SELECT query with JOIN, aggregations, and filters passes validation."""
    query = (
        "SELECT p.product_name, SUM(o.quantity * p.unit_price) AS total_sales "
        "FROM orders o JOIN products p ON o.product_id = p.product_id "
        "WHERE o.status != 'Cancelled' "
        "GROUP BY p.product_name "
        "ORDER BY total_sales DESC;"
    )
    result = validate_and_sanitize_sql(query)
    assert result.is_valid is True
    assert result.error_message is None
    assert "LIMIT 100" in result.sanitized_sql.upper()  # Auto-injected LIMIT


def test_rejection_of_delete():
    """Test 2: Destructive DELETE statements are blocked."""
    query = "DELETE FROM orders WHERE status = 'Cancelled';"
    result = validate_and_sanitize_sql(query)
    assert result.is_valid is False
    assert "DELETE" in result.error_message or "Only SELECT" in result.error_message


def test_rejection_of_drop_table():
    """Test 3: DDL DROP TABLE statements are blocked."""
    query = "DROP TABLE customers;"
    result = validate_and_sanitize_sql(query)
    assert result.is_valid is False
    assert "DROP" in result.error_message or "Only SELECT" in result.error_message


def test_rejection_of_multi_statements():
    """Test 4: Stacked queries with semicolon separation are strictly blocked."""
    query = "SELECT * FROM products; DROP TABLE orders;"
    result = validate_and_sanitize_sql(query)
    assert result.is_valid is False
    assert "Multi-statement" in result.error_message


def test_rejection_of_unauthorized_tables():
    """Test 5: Queries referencing unknown or unauthorized tables are blocked."""
    query = "SELECT * FROM secret_financials;"
    result = validate_and_sanitize_sql(query)
    assert result.is_valid is False
    assert "Unauthorized table 'secret_financials'" in result.error_message


def test_rejection_of_system_tables():
    """Test: Queries referencing sqlite_master or sqlite system tables are blocked."""
    query = "SELECT * FROM sqlite_master WHERE type='table';"
    result = validate_and_sanitize_sql(query)
    assert result.is_valid is False
    assert "sqlite_master" in result.error_message


def test_rejection_of_update_and_insert():
    """Test: UPDATE and INSERT statements are blocked."""
    q_insert = "INSERT INTO customers (customer_id, name, city, signup_date) VALUES (999, 'Hacker', 'NY', '2025-01-01');"
    res_insert = validate_and_sanitize_sql(q_insert)
    assert res_insert.is_valid is False

    q_update = "UPDATE products SET unit_price = 0.01 WHERE product_id = 1;"
    res_update = validate_and_sanitize_sql(q_update)
    assert res_update.is_valid is False


def test_rejection_of_prohibited_functions():
    """Test: Execution of disallowed functions like load_extension is blocked."""
    query = "SELECT load_extension('malicious.dll') FROM customers;"
    result = validate_and_sanitize_sql(query)
    assert result.is_valid is False
    assert "load_extension" in result.error_message


def test_cte_aliases_permitted():
    """Test: Common Table Expressions (WITH clauses) with internal aliases are permitted."""
    query = (
        "WITH high_orders AS ("
        "  SELECT customer_id, COUNT(*) AS cnt FROM orders GROUP BY customer_id"
        ") "
        "SELECT c.name, h.cnt FROM high_orders h JOIN customers c ON h.customer_id = c.customer_id;"
    )
    result = validate_and_sanitize_sql(query)
    assert result.is_valid is True
    assert result.error_message is None


def test_limit_clamping():
    """Test: A requested LIMIT higher than max_limit is clamped to max_limit."""
    query = "SELECT * FROM orders LIMIT 5000;"
    result = validate_and_sanitize_sql(query, max_limit=1000)
    assert result.is_valid is True
    assert "LIMIT 1000" in result.sanitized_sql.upper()
    assert len(result.warnings) > 0
