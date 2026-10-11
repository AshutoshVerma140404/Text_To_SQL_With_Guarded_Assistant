"""LangChain and Google Gemini SQL Generator with Mock fallback."""

import re
import logging
from dataclasses import dataclass
from typing import Optional, Any

from src.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)


@dataclass
class SQLGenerationResult:
    """Encapsulates the generated SQL, status flags, and metadata."""
    sql: str
    is_mock: bool = False
    error_message: Optional[str] = None
    raw_response: Optional[str] = None


SQL_SYSTEM_PROMPT = """You are an expert SQL assistant for SQLite 3.
Given a user query in natural language and the database schema, translate it into the appropriate SQLite SQL query.

DATABASE SCHEMA:
- customers (customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL, city TEXT NOT NULL, signup_date DATE NOT NULL)
- products (product_id INTEGER PRIMARY KEY, product_name TEXT NOT NULL, category TEXT NOT NULL, unit_price REAL NOT NULL CHECK(unit_price > 0))
- orders (order_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(customer_id), product_id INTEGER NOT NULL REFERENCES products(product_id), quantity INTEGER NOT NULL CHECK(quantity > 0), order_date DATE NOT NULL, status TEXT NOT NULL CHECK(status IN ('Completed', 'Pending', 'Cancelled', 'Shipped')))

CRITICAL RULES:
1. READ-ONLY ENFORCEMENT & INTENT FIDELITY:
   - For data viewing, analytics, and questions, generate a standard SQLite SELECT statement.
   - If the user explicitly asks to modify, update, change, delete, insert, or drop data (e.g., "change customer id", "update price", "delete customer", "insert order", "drop table"):
     DO NOT disguise or convert the request into a SELECT query. Generate the literal intended SQL statement (e.g. UPDATE ..., DELETE ..., INSERT ..., DROP ...) so that our downstream AST security validator can intercept, inspect, and block the destructive operation.
2. BUSINESS RULES:
   - Total sales or revenue for an order is computed as (orders.quantity * products.unit_price) by joining orders with products.
   - Cancelled orders (status = 'Cancelled') must be excluded from total sales or revenue calculations unless the user explicitly requests all statuses.
   - Orders with status = 'Pending' represent unfulfilled orders.
3. Only reference the allowed tables: 'customers', 'products', 'orders'. Never query sqlite_master or system tables.
4. Output Format: Return ONLY the raw SQL query. Do NOT include markdown code fences (no ```sql or ```), and do NOT add conversational comments.
"""

MOCK_QUERY_MAP = {
    "how many orders are there": "SELECT COUNT(*) AS total_orders FROM orders;",
    "which five products have the highest total sales": (
        "SELECT p.product_name, ROUND(SUM(o.quantity * p.unit_price), 2) AS total_sales "
        "FROM orders o JOIN products p ON o.product_id = p.product_id "
        "WHERE o.status != 'Cancelled' "
        "GROUP BY p.product_id, p.product_name "
        "ORDER BY total_sales DESC LIMIT 5;"
    ),
    "which customers have placed the most orders": (
        "SELECT c.name, COUNT(o.order_id) AS order_count "
        "FROM customers c JOIN orders o ON c.customer_id = o.customer_id "
        "GROUP BY c.customer_id, c.name "
        "ORDER BY order_count DESC LIMIT 5;"
    ),
    "what is the total quantity ordered by product category": (
        "SELECT p.category, SUM(o.quantity) AS total_quantity "
        "FROM orders o JOIN products p ON o.product_id = p.product_id "
        "WHERE o.status != 'Cancelled' "
        "GROUP BY p.category "
        "ORDER BY total_quantity DESC;"
    ),
    "which cities have the most customers": (
        "SELECT city, COUNT(customer_id) AS customer_count "
        "FROM customers "
        "GROUP BY city "
        "ORDER BY customer_count DESC LIMIT 5;"
    ),
    "how many orders are pending": (
        "SELECT COUNT(*) AS pending_orders "
        "FROM orders "
        "WHERE status = 'Pending';"
    ),
    "show the ten most recent orders with customer names": (
        "SELECT o.order_id, c.name AS customer_name, o.order_date, o.status "
        "FROM orders o JOIN customers c ON o.customer_id = c.customer_id "
        "ORDER BY o.order_date DESC LIMIT 10;"
    ),
}


def clean_sql_output(raw_text: str) -> str:
    """Sanitizes LLM output by removing markdown code fences and unnecessary whitespace."""
    if not raw_text:
        return ""
    text = raw_text.strip()
    
    # Remove markdown code blocks ```sql ... ``` or ``` ... ```
    if text.startswith("```"):
        text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    # Remove inline single backticks if wrapping the entire expression
    if text.startswith("`") and text.endswith("`") and text.count("`") == 2:
        text = text[1:-1].strip()

    # Remove common conversational prefixes
    prefix_patterns = [
        r"^here is the (?:sql|query)[:\s]*",
        r"^the sql query is[:\s]*",
        r"^query[:\s]*",
    ]
    for pattern in prefix_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

    return text


def get_mock_sql_response(user_question: str) -> str:
    """Provides deterministic SQL responses for offline testing and demonstration."""
    normalized = user_question.lower().strip().rstrip("?").rstrip(".")
    
    # Check exact or substring matches
    for key, query in MOCK_QUERY_MAP.items():
        if key in normalized or normalized in key:
            return query

    # Mutation intents (should produce non-SELECT SQL to trigger guardrails)
    if any(k in normalized for k in ["change", "update", "modify", "set "]) and not any(k in normalized for k in ["how many", "count", "show", "which"]):
        return "UPDATE customers SET customer_id = 25 WHERE customer_id = 28;"
    if any(k in normalized for k in ["delete", "remove", "erase"]) and not any(k in normalized for k in ["how many", "count"]):
        return "DELETE FROM orders WHERE order_id = 1;"
    if "drop" in normalized:
        return "DROP TABLE customers;"

    # Keyword fallbacks
    if "pending" in normalized:
        return "SELECT COUNT(*) AS pending_orders FROM orders WHERE status = 'Pending';"
    if "customer" in normalized and ("city" in normalized or "cities" in normalized):
        return "SELECT city, COUNT(customer_id) AS customer_count FROM customers GROUP BY city ORDER BY customer_count DESC;"
    if "product" in normalized and "sale" in normalized:
        return (
            "SELECT p.product_name, ROUND(SUM(o.quantity * p.unit_price), 2) AS total_sales "
            "FROM orders o JOIN products p ON o.product_id = p.product_id "
            "WHERE o.status != 'Cancelled' "
            "GROUP BY p.product_id, p.product_name "
            "ORDER BY total_sales DESC LIMIT 5;"
        )
    if "order" in normalized:
        return "SELECT order_id, customer_id, product_id, quantity, order_date, status FROM orders ORDER BY order_date DESC LIMIT 10;"

    # Default fallback SELECT
    return "SELECT * FROM customers LIMIT 10;"


def extract_text_from_response(raw_content: Any) -> str:
    """Extracts raw text from response whether it is a string or list of content blocks."""
    if isinstance(raw_content, str):
        return raw_content
    elif isinstance(raw_content, list):
        parts = []
        for item in raw_content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            elif hasattr(item, "text"):
                parts.append(str(item.text))
        return "\n".join(parts)
    elif hasattr(raw_content, "content"):
        return extract_text_from_response(raw_content.content)
    return str(raw_content)


def generate_sql_query(
    user_question: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    force_mock: bool = False,
) -> SQLGenerationResult:
    """Generates SQLite SQL for a user question using LangChain + Gemini, or Mock if unconfigured."""
    effective_api_key = (api_key or GEMINI_API_KEY).strip()
    effective_model = (model_name or GEMINI_MODEL).strip()

    # If force_mock or no API key, use mock generator
    if force_mock or not effective_api_key:
        mock_sql = get_mock_sql_response(user_question)
        reason = "Offline mock mode requested." if force_mock else "No GEMINI_API_KEY provided; using offline mock generator."
        logger.info(f"{reason} Query generated: {mock_sql}")
        return SQLGenerationResult(
            sql=mock_sql,
            is_mock=True,
            raw_response=mock_sql,
            error_message=None if force_mock else "Notice: GEMINI_API_KEY is not set. The response was produced by the offline mock generator.",
        )

    # Use LangChain with Google Gemini
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model=effective_model,
            google_api_key=effective_api_key,
            temperature=0.0,
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", SQL_SYSTEM_PROMPT),
            ("user", "{question}"),
        ])

        chain = prompt | llm
        response = chain.invoke({"question": user_question})
        raw_text = extract_text_from_response(getattr(response, "content", response))
        cleaned_sql = clean_sql_output(raw_text)

        return SQLGenerationResult(
            sql=cleaned_sql,
            is_mock=False,
            raw_response=raw_text,
        )

    except Exception as e:
        logger.exception("Error during Gemini invocation via LangChain")
        err_msg = str(e)
        # Fallback to mock with error notification so UI remains usable
        mock_sql = get_mock_sql_response(user_question)
        return SQLGenerationResult(
            sql=mock_sql,
            is_mock=True,
            raw_response=None,
            error_message=f"Gemini generation error: {err_msg}. Generated fallback query via offline generator.",
        )
