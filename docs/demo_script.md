# Demo Video Plan & Script (5–8 Minutes)

## Objective
Demonstrate the end-to-end functionality, security guardrails, and read-only execution of the Text-to-SQL Guarded Assistant on Windows.

---

## Video Outline & Timestamp Breakdown

| Segment | Duration | Topic | Key Actions / Talking Points |
|---|---|---|---|
| **1. Introduction** | 0:00 – 1:00 | Project Overview | • Introduce the problem statement: safely querying relational databases using natural language.<br>• Explain the core philosophy: multi-layered defense-in-depth, AST guardrails, and read-only execution. |
| **2. Architecture Walkthrough** | 1:00 – 2:00 | System Design | • Present the Mermaid architecture diagram.<br>• Walk through the components: Streamlit UI, LangChain + Gemini, SQLGlot AST validator, SQLite read-only executor. |
| **3. Setup & Ingestion** | 2:00 – 3:00 | Environment & Data | • Show environment configuration (`.env.example`).<br>• Run `python -m src.ingestion` in terminal to show deterministic, idempotent database creation.<br>• Show row counts for customers, products, orders. |
| **4. Live Assistant Demo** | 3:00 – 5:00 | Natural Language Queries | • Launch application via `streamlit run app.py`.<br>• Show the sidebar schema inspector and sample rows.<br>• Test queries:<br>  - *"How many orders are there?"*<br>  - *"Which five products have the highest total sales?"*<br>  - *"Which customers have placed the most orders?"*<br>• Highlight the generated SQL, AST approval badge, execution time (ms), and interactive dataframe. |
| **5. Security & Guardrail Testing** | 5:00 – 6:30 | Malicious Query Defense | • Demonstrate attempt to run destructive SQL:<br>  - `DROP TABLE customers;`<br>  - `DELETE FROM orders WHERE order_id = 1;`<br>  - `SELECT * FROM secret_financials;`<br>  - Semicolon chaining: `SELECT * FROM products; DROP TABLE orders;`<br>• Show that the AST validator blocks them immediately before execution.<br>• Show that database remains completely unchanged. |
| **6. Automated Test Suite** | 6:30 – 7:30 | Testing & Verification | • Run `pytest -v` in terminal.<br>• Highlight all 21 unit and integration tests passing offline without requiring an API key. |
| **7. Conclusion & Wrap-up** | 7:30 – 8:00 | Summary | • Reiterate design decisions (AST vs regex, read-only driver handle).<br>• Conclude walkthrough. |

---

## Step-by-Step Recording Instructions

1. **Pre-requisites**:
   - Ensure `app_database.db` is generated (`python -m src.ingestion`).
   - Open two terminal windows: one for the Streamlit app, one for running tests and commands.
2. **Terminal 1**:
   ```powershell
   streamlit run app.py
   ```
3. **Terminal 2**:
   ```powershell
   pytest -v
   ```
4. **Browser**:
   - Navigate to `http://localhost:8501`.
   - Interact with the sidebar example pills.
   - Enter malicious prompts to demonstrate guardrails blocking unsafe operations.
