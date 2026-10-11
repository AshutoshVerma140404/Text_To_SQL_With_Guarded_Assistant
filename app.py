"""Streamlit Chat Application for Text-to-SQL Guarded Assistant."""

import time
import pandas as pd
import streamlit as st
from pathlib import Path

from src.config import (
    DATABASE_PATH,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    ALLOWED_TABLES,
    DEFAULT_ROW_LIMIT,
    MAX_ROW_LIMIT,
)
from src.database import (
    init_db,
    get_schema_summary,
    get_table_columns_map,
    get_table_row_counts,
    get_sample_rows,
)
from src.ingestion import populate_default_database
from src.sql_generator import generate_sql_query
from src.sql_validator import validate_and_sanitize_sql
from src.query_executor import execute_read_only_query

# Page Configuration
st.set_page_config(
    page_title="Text-to-SQL Guarded Assistant",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished, premium styling
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #4F46E5, #06B6D4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .badge-approved {
        background-color: #DCFCE7;
        color: #166534;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
        border: 1px solid #BBF7D0;
    }
    .badge-blocked {
        background-color: #FEE2E2;
        color: #991B1B;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
        border: 1px solid #FECACA;
    }
    .badge-info {
        background-color: #E0F2FE;
        color: #0369A1;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
        display: inline-block;
        border: 1px solid #BAE6FD;
    }
    .metric-chip {
        background-color: #F1F5F9;
        color: #334155;
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.82rem;
        font-weight: 500;
        margin-right: 6px;
        display: inline-block;
    }
    .query-box {
        background-color: #0F172A;
        border-radius: 8px;
        padding: 12px;
        color: #F8FAFC;
        font-family: monospace;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def ensure_database_ready():
    """Ensures database is created and populated on first run."""
    if not DATABASE_PATH.exists():
        with st.spinner("Initializing SQLite database with synthetic dataset..."):
            populate_default_database(seed=42, db_path=DATABASE_PATH)


ensure_database_ready()

# Session State Initialization
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "👋 Hello! I am your **Guarded Text-to-SQL Assistant**.\n\n"
                "Ask questions in natural English about **customers**, **products**, or **orders**. "
                "I will generate SQLite queries, validate them against strict AST security guardrails, "
                "and execute them securely on a read-only database."
            ),
            "sql": None,
            "validation": None,
            "results": None,
            "metrics": None,
        }
    ]

if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None

# Sidebar Setup
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Model Configuration
    api_key_input = st.text_input(
        "Gemini API Key (optional override):",
        value=GEMINI_API_KEY,
        type="password",
        help="Leave blank to use .env or offline mock mode.",
    )
    
    force_mock = st.toggle(
        "Force Offline Mock Mode",
        value=not bool(api_key_input),
        help="Use deterministic mock queries without calling Google Gemini API.",
    )
    
    model_choice = st.selectbox(
        "Gemini Model:",
        options=["gemini-3.8-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"],
        index=0,
    )

    st.markdown("---")
    st.header("💡 Example Questions")
    example_questions = [
        "How many orders are there?",
        "Which five products have the highest total sales?",
        "Which customers have placed the most orders?",
        "What is the total quantity ordered by product category?",
        "Which cities have the most customers?",
        "How many orders are pending?",
        "Show the ten most recent orders with customer names.",
        "DROP TABLE customers;",  # Security test prompt
        "DELETE FROM orders WHERE order_id = 1;",  # Security test prompt
    ]

    for q in example_questions:
        if st.button(f"💬 {q}", use_container_width=True, key=f"ex_{q}"):
            st.session_state.pending_prompt = q

    st.markdown("---")
    st.header("📊 Database Schema")
    row_counts = get_table_row_counts(DATABASE_PATH)
    for tbl, cnt in row_counts.items():
        st.caption(f"• **{tbl}**: {cnt} rows")

    with st.expander("🔍 View Table Samples & DDL"):
        table_selected = st.selectbox("Inspect table:", options=list(ALLOWED_TABLES))
        sample_rows = get_sample_rows(DATABASE_PATH, table_name=table_selected, limit=3)
        if sample_rows:
            st.dataframe(pd.DataFrame(sample_rows), use_container_width=True)
        st.markdown("**DDL Schema:**")
        st.code(get_schema_summary(DATABASE_PATH), language="sql")

    if st.button("🔄 Reset / Re-seed Database", use_container_width=True):
        populate_default_database(seed=42, db_path=DATABASE_PATH)
        st.success("Database re-seeded successfully!")
        time.sleep(1)
        st.rerun()

# Main Header
st.markdown('<div class="main-title">🛡️ Text-to-SQL Guarded Assistant</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Natural language queries with independent SQLGlot AST guardrails and read-only SQLite execution.</div>',
    unsafe_allow_html=True,
)

# Display Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        # Display SQL section if available
        if msg.get("sql"):
            with st.expander("🔍 Generated SQL Query", expanded=True):
                st.code(msg["sql"], language="sql")
                
                # Validation status
                val = msg.get("validation")
                if val:
                    if val.get("is_valid"):
                        st.markdown(
                            '<span class="badge-approved">✅ Passed AST Guardrails</span> '
                            '<span class="badge-info">Strictly Read-Only SELECT</span>',
                            unsafe_allow_html=True,
                        )
                        if val.get("warnings"):
                            for w in val["warnings"]:
                                st.caption(f"⚠️ {w}")
                    else:
                        st.markdown(
                            f'<span class="badge-blocked">🚫 Blocked by Guardrail</span>',
                            unsafe_allow_html=True,
                        )
                        st.error(f"Reason: {val.get('error_message')}")

        # Display Results Table and Metrics
        if msg.get("results") is not None and msg.get("validation", {}).get("is_valid"):
            results = msg["results"]
            metrics = msg.get("metrics", {})
            
            # Metric chips
            chips_html = (
                f'<div style="margin: 8px 0;">'
                f'<span class="metric-chip">⚡ {metrics.get("execution_time_ms", 0)} ms</span>'
                f'<span class="metric-chip">📋 {metrics.get("row_count", 0)} rows returned</span>'
                f'<span class="metric-chip">🔒 Read-Only Connection</span>'
                f'</div>'
            )
            st.markdown(chips_html, unsafe_allow_html=True)

            if results:
                df = pd.DataFrame(results)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Query executed successfully, but returned 0 rows.")


# Handle User Input
user_input = st.chat_input("Ask a question about customers, products, or orders...")
if st.session_state.pending_prompt:
    user_input = st.session_state.pending_prompt
    st.session_state.pending_prompt = None

if user_input:
    # 1. Append and render user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # 2. Process query in Assistant turn
    with st.chat_message("assistant"):
        with st.spinner("Generating SQL query..."):
            # Check if user directly entered a raw SQL query or natural language
            is_direct_sql = user_input.strip().upper().startswith(("SELECT", "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE"))
            
            if is_direct_sql:
                generated_sql = user_input.strip()
                gen_is_mock = False
                gen_error = None
            else:
                gen_result = generate_sql_query(
                    user_question=user_input,
                    api_key=api_key_input,
                    model_name=model_choice,
                    force_mock=force_mock,
                )
                generated_sql = gen_result.sql
                gen_is_mock = gen_result.is_mock
                gen_error = gen_result.error_message

        # 3. Guardrail AST Validation
        with st.spinner("Validating SQL against AST guardrails..."):
            schema_cols = get_table_columns_map(DATABASE_PATH)
            val_result = validate_and_sanitize_sql(
                sql_text=generated_sql,
                schema_columns=schema_cols,
                default_limit=DEFAULT_ROW_LIMIT,
                max_limit=MAX_ROW_LIMIT,
            )

        # 4. Display generated SQL and validation
        with st.expander("🔍 Generated SQL Query", expanded=True):
            st.code(generated_sql, language="sql")
            if val_result.is_valid:
                st.markdown(
                    '<span class="badge-approved">✅ Passed AST Guardrails</span> '
                    '<span class="badge-info">Strictly Read-Only SELECT</span>',
                    unsafe_allow_html=True,
                )
                if val_result.warnings:
                    for w in val_result.warnings:
                        st.caption(f"⚠️ {w}")
            else:
                st.markdown(
                    '<span class="badge-blocked">🚫 Blocked by Guardrail</span>',
                    unsafe_allow_html=True,
                )
                st.error(f"Reason: {val_result.error_message}")

        # 5. Execute if valid, or block
        query_results = None
        metrics_dict = None
        reply_text = ""

        if not val_result.is_valid:
            reply_text = (
                f"🛑 **Query Blocked for Safety**: {val_result.error_message}\n\n"
                "The query violated our security policy and was **not** executed on the database."
            )
            st.warning(reply_text)
        else:
            with st.spinner("Executing read-only query on SQLite..."):
                exec_result = execute_read_only_query(
                    sql_query=val_result.sanitized_sql,
                    db_path=DATABASE_PATH,
                )

            if exec_result.success:
                query_results = exec_result.rows
                metrics_dict = {
                    "execution_time_ms": exec_result.execution_time_ms,
                    "row_count": exec_result.row_count,
                    "truncated": exec_result.truncated,
                }
                
                chips_html = (
                    f'<div style="margin: 8px 0;">'
                    f'<span class="metric-chip">⚡ {exec_result.execution_time_ms} ms</span>'
                    f'<span class="metric-chip">📋 {exec_result.row_count} rows returned</span>'
                    f'<span class="metric-chip">🔒 Read-Only Connection</span>'
                    f'</div>'
                )
                st.markdown(chips_html, unsafe_allow_html=True)

                if query_results:
                    df = pd.DataFrame(query_results)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    reply_text = f"Retrieved **{exec_result.row_count}** rows in **{exec_result.execution_time_ms} ms**."
                else:
                    reply_text = "Query executed successfully, but returned 0 rows."
                    st.info(reply_text)

                if gen_is_mock and not is_direct_sql:
                    st.caption("ℹ️ *Generated via offline mock engine.*")
            else:
                reply_text = f"⚠️ Execution error: {exec_result.error_message}"
                st.error(reply_text)

        # 6. Save message to session state
        st.session_state.messages.append({
            "role": "assistant",
            "content": reply_text,
            "sql": generated_sql,
            "validation": {
                "is_valid": val_result.is_valid,
                "error_message": val_result.error_message,
                "warnings": val_result.warnings,
            },
            "results": query_results,
            "metrics": metrics_dict,
        })
