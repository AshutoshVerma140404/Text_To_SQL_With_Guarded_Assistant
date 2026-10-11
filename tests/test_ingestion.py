"""Unit tests for synthetic data ingestion, deduplication, and edge cases."""

import pytest
from pathlib import Path
from src.ingestion import ingest_data, clean_and_validate_customers, clean_and_validate_products, clean_and_validate_orders
from src.database import get_table_row_counts


def test_ingestion_deduplication(empty_temp_db: Path):
    """Test 6: Repeated ingestion runs do not create duplicate records."""
    data = {
        "customers": [
            {"customer_id": 1, "name": "Alice", "city": "NYC", "signup_date": "2025-01-01"},
            {"customer_id": 2, "name": "Bob", "city": "SF", "signup_date": "2025-01-02"},
        ],
        "products": [
            {"product_id": 1, "product_name": "Keyboard", "category": "Electronics", "unit_price": 50.0},
        ],
        "orders": [
            {"order_id": 1, "customer_id": 1, "product_id": 1, "quantity": 2, "order_date": "2025-02-01", "status": "Completed"},
        ],
    }

    # First run
    c1, p1, o1 = ingest_data(data, db_path=empty_temp_db)
    counts1 = get_table_row_counts(empty_temp_db)
    assert counts1["customers"] == 2
    assert counts1["products"] == 1
    assert counts1["orders"] == 1

    # Second run with exact same data
    c2, p2, o2 = ingest_data(data, db_path=empty_temp_db)
    counts2 = get_table_row_counts(empty_temp_db)
    assert counts2["customers"] == 2
    assert counts2["products"] == 1
    assert counts2["orders"] == 1


def test_missing_or_invalid_customer_handling():
    """Test 7a: Records with missing/invalid primary keys or missing names are dropped."""
    raw = [
        {"customer_id": None, "name": "No ID"},          # missing ID -> drop
        {"customer_id": -5, "name": "Negative ID"},       # negative ID -> drop
        {"customer_id": 1, "name": ""},                   # empty name -> drop
        {"customer_id": 2, "name": "Valid", "city": ""},  # missing city -> keep with default
    ]
    cleaned = clean_and_validate_customers(raw)
    assert len(cleaned) == 1
    assert cleaned[0]["customer_id"] == 2
    assert cleaned[0]["city"] == "Unknown"


def test_invalid_product_handling():
    """Test 7b: Products with non-positive price or missing name are dropped."""
    raw = [
        {"product_id": 1, "product_name": "Free item", "category": "Promo", "unit_price": 0.0},
        {"product_id": 2, "product_name": "Negative item", "category": "Promo", "unit_price": -10.0},
        {"product_id": 3, "product_name": "", "category": "Promo", "unit_price": 15.0},
        {"product_id": 4, "product_name": "Good item", "category": "Hardware", "unit_price": 49.99},
    ]
    cleaned = clean_and_validate_products(raw)
    assert len(cleaned) == 1
    assert cleaned[0]["product_id"] == 4
    assert cleaned[0]["unit_price"] == 49.99


def test_invalid_order_foreign_keys_and_quantities():
    """Test 7c: Orders with missing/dangling foreign keys or zero/negative quantities are dropped."""
    valid_customers = {1, 2}
    valid_products = {10}

    raw = [
        {"order_id": 1, "customer_id": 999, "product_id": 10, "quantity": 1, "status": "Completed"},  # Invalid customer
        {"order_id": 2, "customer_id": 1, "product_id": 888, "quantity": 1, "status": "Completed"},   # Invalid product
        {"order_id": 3, "customer_id": 1, "product_id": 10, "quantity": 0, "status": "Completed"},    # Invalid quantity <= 0
        {"order_id": 4, "customer_id": 2, "product_id": 10, "quantity": 3, "status": "InvalidStatus"},# Valid order, fallback status
    ]
    cleaned = clean_and_validate_orders(raw, valid_customers, valid_products)
    assert len(cleaned) == 1
    assert cleaned[0]["order_id"] == 4
    assert cleaned[0]["status"] == "Pending"
