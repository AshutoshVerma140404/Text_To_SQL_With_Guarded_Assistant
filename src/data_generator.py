"""Deterministic synthetic data generator for customers, products, and orders."""

import random
from datetime import date, timedelta
from typing import List, Dict, Any


CITIES = [
    "New York", "San Francisco", "Chicago", "Austin", "Seattle",
    "Boston", "Denver", "Atlanta", "Los Angeles", "Miami"
]

CUSTOMER_NAMES = [
    "Alice Johnson", "Bob Smith", "Charlie Brown", "Diana Prince", "Evan Wright",
    "Fiona Gallagher", "George Clark", "Hannah Abbott", "Ian Malcolm", "Julia Roberts",
    "Kevin Bacon", "Laura Croft", "Michael Scott", "Nina Simone", "Oscar Martinez",
    "Pam Beesly", "Quincy Adams", "Rachel Green", "Steve Rogers", "Tina Fey",
    "Uma Thurman", "Victor Stone", "Wanda Maximoff", "Xavier Woods", "Yvonne Strahovski",
    "Zachary Levi", "Arthur Pendragon", "Beth Harmon", "Carlos Santana", "Donna Noble"
]

PRODUCT_CATALOG = [
    # Electronics
    ("Wireless Noise-Canceling Headphones", "Electronics", 199.99),
    ("Mechanical Gaming Keyboard", "Electronics", 129.50),
    ("Ultra-Wide 4K Monitor", "Electronics", 449.00),
    ("Ergonomic Wireless Mouse", "Electronics", 49.99),
    ("USB-C Multi-Port Hub", "Electronics", 39.99),
    ("Smart LED Desk Lamp", "Electronics", 59.95),
    
    # Furniture
    ("Ergonomic Mesh Office Chair", "Furniture", 299.00),
    ("Electric Standing Desk", "Furniture", 499.00),
    ("Solid Oak Bookshelf", "Furniture", 249.50),
    ("Under-Desk Footrest", "Furniture", 34.99),
    
    # Office Supplies
    ("Premium Hardcover Notebook", "Office Supplies", 18.50),
    ("Gel Ink Pens (Set of 12)", "Office Supplies", 14.99),
    ("Desk Cable Management Tray", "Office Supplies", 24.99),
    ("Aluminum Laptop Stand", "Office Supplies", 45.00),
    
    # Accessories
    ("Water-Resistant Laptop Backpack", "Accessories", 79.99),
    ("Leather Desk Pad", "Accessories", 32.50),
    ("Insulated Stainless Travel Mug", "Accessories", 28.00),
    
    # Apparel
    ("Branded Cotton Hoodie", "Apparel", 55.00),
    ("Merino Wool Crewneck Sweater", "Apparel", 85.00),
    ("Embroidered Baseball Cap", "Apparel", 22.50),
]

ORDER_STATUSES = ["Completed", "Pending", "Cancelled", "Shipped"]
STATUS_WEIGHTS = [0.60, 0.15, 0.10, 0.15]  # Most are completed, realistic distribution


def generate_synthetic_data(seed: int = 42) -> Dict[str, List[Dict[str, Any]]]:
    """Generates deterministic, realistic relational dataset for customers, products, and orders."""
    rng = random.Random(seed)
    base_date = date(2025, 1, 1)

    # 1. Customers
    customers = []
    for cid, name in enumerate(CUSTOMER_NAMES, start=1):
        city = rng.choice(CITIES)
        days_ago = rng.randint(60, 365)
        signup_date = (base_date - timedelta(days=days_ago)).isoformat()
        customers.append({
            "customer_id": cid,
            "name": name,
            "city": city,
            "signup_date": signup_date,
        })

    # 2. Products
    products = []
    for pid, (pname, cat, price) in enumerate(PRODUCT_CATALOG, start=1):
        products.append({
            "product_id": pid,
            "product_name": pname,
            "category": cat,
            "unit_price": round(price, 2),
        })

    # 3. Orders
    orders = []
    order_id = 1
    total_orders = 120
    for _ in range(total_orders):
        customer = rng.choice(customers)
        product = rng.choice(products)
        quantity = rng.choices([1, 2, 3, 4, 5], weights=[0.5, 0.25, 0.15, 0.07, 0.03])[0]
        
        # Order date between customer signup date and 2025-06-01
        cust_signup = date.fromisoformat(customer["signup_date"])
        days_after_signup = rng.randint(1, 120)
        order_dt = (cust_signup + timedelta(days=days_after_signup)).isoformat()
        status = rng.choices(ORDER_STATUSES, weights=STATUS_WEIGHTS)[0]

        orders.append({
            "order_id": order_id,
            "customer_id": customer["customer_id"],
            "product_id": product["product_id"],
            "quantity": quantity,
            "order_date": order_dt,
            "status": status,
        })
        order_id += 1

    return {
        "customers": customers,
        "products": products,
        "orders": orders,
    }
