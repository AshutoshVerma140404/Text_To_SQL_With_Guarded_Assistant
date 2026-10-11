"""Unit tests for SQL generation, output cleaning, and mock generator."""

import pytest
from src.sql_generator import (
    clean_sql_output,
    generate_sql_query,
    get_mock_sql_response,
)
from src.sql_validator import validate_and_sanitize_sql


def test_markdown_stripping():
    """Test: Markdown code fences and conversational filler are stripped cleanly."""
    raw_response_1 = "```sql\nSELECT * FROM customers;\n```"
    assert clean_sql_output(raw_response_1) == "SELECT * FROM customers;"

    raw_response_2 = "```\nSELECT name, city FROM customers\n```"
    assert clean_sql_output(raw_response_2) == "SELECT name, city FROM customers"

    raw_response_3 = "Here is the SQL query:\nSELECT COUNT(*) FROM orders;"
    assert clean_sql_output(raw_response_3) == "SELECT COUNT(*) FROM orders;"


def test_offline_mock_generation_without_api_key():
    """Test 8: Generator works offline without API key and returns valid SQL."""
    question = "Which five products have the highest total sales?"
    res = generate_sql_query(question, api_key="", force_mock=True)

    assert res.is_mock is True
    assert "SELECT" in res.sql.upper()
    assert "products" in res.sql.lower()

    # Verify that the generated mock SQL passes the validator
    val_res = validate_and_sanitize_sql(res.sql)
    assert val_res.is_valid is True


def test_mock_query_sample_questions():
    """Test: All sample screening questions produce valid executable SQL in mock mode."""
    sample_questions = [
        "How many orders are there?",
        "Which five products have the highest total sales?",
        "Which customers have placed the most orders?",
        "What is the total quantity ordered by product category?",
        "Which cities have the most customers?",
        "How many orders are pending?",
        "Show the ten most recent orders with customer names.",
    ]

    for q in sample_questions:
        res = generate_sql_query(q, force_mock=True)
        assert res.is_mock is True
        val_res = validate_and_sanitize_sql(res.sql)
        assert val_res.is_valid is True, f"Question '{q}' produced invalid SQL: {res.sql} - Error: {val_res.error_message}"
