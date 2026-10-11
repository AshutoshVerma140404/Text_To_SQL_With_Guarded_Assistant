"""Data ingestion pipeline: cleaning, validation, deduplication, and database loading."""

import logging
from typing import Dict, List, Any, Tuple
from pathlib import Path
from src.config import DATABASE_PATH, SCHEMA_PATH
from src.database import init_db, get_read_write_connection, get_table_row_counts
from src.data_generator import generate_synthetic_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def clean_and_validate_customers(raw_customers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cleans and validates customer records, filtering out invalid or missing primary keys."""
    valid_customers = []
    seen_ids = set()

    for item in raw_customers:
        cid = item.get("customer_id")
        name = item.get("name")
        city = item.get("city")
        signup_date = item.get("signup_date")

        # Must have valid positive integer customer_id and non-empty name
        if cid is None or not isinstance(cid, int) or cid <= 0:
            logger.warning(f"Dropping customer with invalid customer_id: {item}")
            continue

        if not name or not str(name).strip():
            logger.warning(f"Dropping customer with missing name: {item}")
            continue

        if cid in seen_ids:
            logger.warning(f"Deduplicating customer_id {cid}")
            continue

        seen_ids.add(cid)
        valid_customers.append({
            "customer_id": cid,
            "name": str(name).strip(),
            "city": str(city).strip() if city else "Unknown",
            "signup_date": str(signup_date) if signup_date else "2025-01-01",
        })

    return valid_customers


def clean_and_validate_products(raw_products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cleans and validates product records, enforcing positive prices and required fields."""
    valid_products = []
    seen_ids = set()

    for item in raw_products:
        pid = item.get("product_id")
        pname = item.get("product_name")
        cat = item.get("category")
        price = item.get("unit_price")

        if pid is None or not isinstance(pid, int) or pid <= 0:
            logger.warning(f"Dropping product with invalid product_id: {item}")
            continue

        if not pname or not str(pname).strip():
            logger.warning(f"Dropping product with missing product_name: {item}")
            continue

        try:
            price_val = float(price)
            if price_val <= 0:
                logger.warning(f"Dropping product with non-positive price: {item}")
                continue
        except (ValueError, TypeError):
            logger.warning(f"Dropping product with invalid price value: {item}")
            continue

        if pid in seen_ids:
            logger.warning(f"Deduplicating product_id {pid}")
            continue

        seen_ids.add(pid)
        valid_products.append({
            "product_id": pid,
            "product_name": str(pname).strip(),
            "category": str(cat).strip() if cat else "General",
            "unit_price": round(price_val, 2),
        })

    return valid_products


def clean_and_validate_orders(
    raw_orders: List[Dict[str, Any]],
    valid_customer_ids: set,
    valid_product_ids: set,
) -> List[Dict[str, Any]]:
    """Cleans orders, enforcing valid foreign keys, positive quantities, and allowed statuses."""
    valid_orders = []
    seen_ids = set()
    allowed_statuses = {"Completed", "Pending", "Cancelled", "Shipped"}

    for item in raw_orders:
        oid = item.get("order_id")
        cid = item.get("customer_id")
        pid = item.get("product_id")
        qty = item.get("quantity")
        odate = item.get("order_date")
        status = item.get("status")

        if oid is None or not isinstance(oid, int) or oid <= 0:
            logger.warning(f"Dropping order with invalid order_id: {item}")
            continue

        if cid not in valid_customer_ids:
            logger.warning(f"Dropping order with invalid foreign key customer_id {cid}")
            continue

        if pid not in valid_product_ids:
            logger.warning(f"Dropping order with invalid foreign key product_id {pid}")
            continue

        try:
            qty_val = int(qty)
            if qty_val <= 0:
                logger.warning(f"Dropping order with invalid quantity {qty}")
                continue
        except (ValueError, TypeError):
            logger.warning(f"Dropping order with non-integer quantity {qty}")
            continue

        if status not in allowed_statuses:
            status = "Pending"  # Fallback to Pending if unknown status

        if oid in seen_ids:
            logger.warning(f"Deduplicating order_id {oid}")
            continue

        seen_ids.add(oid)
        valid_orders.append({
            "order_id": oid,
            "customer_id": cid,
            "product_id": pid,
            "quantity": qty_val,
            "order_date": str(odate) if odate else "2025-01-01",
            "status": status,
        })

    return valid_orders


def ingest_data(
    data: Dict[str, List[Dict[str, Any]]],
    db_path: Path | str = DATABASE_PATH,
    schema_path: Path | str = SCHEMA_PATH,
) -> Tuple[int, int, int]:
    """Idempotently ingests cleaned and validated datasets into the SQLite database.
    
    Returns:
        Tuple of (inserted_customers, inserted_products, inserted_orders)
    """
    init_db(db_path=db_path, schema_path=schema_path)

    # Clean and validate
    clean_customers = clean_and_validate_customers(data.get("customers", []))
    customer_ids = {c["customer_id"] for c in clean_customers}

    clean_products = clean_and_validate_products(data.get("products", []))
    product_ids = {p["product_id"] for p in clean_products}

    clean_orders = clean_and_validate_orders(data.get("orders", []), customer_ids, product_ids)

    with get_read_write_connection(db_path) as conn:
        cursor = conn.cursor()

        # Idempotent insert with INSERT OR IGNORE
        cursor.executemany(
            """
            INSERT OR IGNORE INTO customers (customer_id, name, city, signup_date)
            VALUES (:customer_id, :name, :city, :signup_date);
            """,
            clean_customers,
        )

        cursor.executemany(
            """
            INSERT OR IGNORE INTO products (product_id, product_name, category, unit_price)
            VALUES (:product_id, :product_name, :category, :unit_price);
            """,
            clean_products,
        )

        cursor.executemany(
            """
            INSERT OR IGNORE INTO orders (order_id, customer_id, product_id, quantity, order_date, status)
            VALUES (:order_id, :customer_id, :product_id, :quantity, :order_date, :status);
            """,
            clean_orders,
        )

        conn.commit()

    logger.info(
        f"Ingestion completed. Processed {len(clean_customers)} customers, "
        f"{len(clean_products)} products, {len(clean_orders)} orders."
    )
    return len(clean_customers), len(clean_products), len(clean_orders)


def populate_default_database(seed: int = 42, db_path: Path | str = DATABASE_PATH) -> None:
    """Generates synthetic data and ingests it into the target database."""
    logger.info(f"Generating synthetic dataset (seed={seed})...")
    raw_data = generate_synthetic_data(seed=seed)
    logger.info(f"Ingesting dataset into {db_path}...")
    ingest_data(raw_data, db_path=db_path)
    
    counts = get_table_row_counts(db_path)
    logger.info(f"Current row counts in {db_path}: {counts}")


if __name__ == "__main__":
    populate_default_database()
