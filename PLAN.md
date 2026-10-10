# Project Plan: Text-to-SQL Guarded Assistant (DAI-012)

## 1. Project Objective & Scope

The goal of this project is to build a simple, functional, read-only AI chat assistant that allows users to query a relational SQLite database using natural language.

### Core Workflow
1. **User Query**: The user asks a question in plain English via a Streamlit chat interface (e.g., *"Which five products have the highest total sales?"*).
2. **SQL Generation**: LangChain and Google Gemini convert the natural language question into SQLite-compatible SQL using the database schema and dialect-specific instructions.
3. **Guardrail Validation**: An independent validator using SQLGlot parses the AST, rejects multiple statements, blocks destructive statements (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`), enforces an allowlist of tables and columns, and ensures queries are strictly read-only.
4. **Read-Only Execution**: Approved queries execute against SQLite using a read-only connection handle with a query timeout and row limit.
5. **Results Display**: The Streamlit interface displays the generated SQL, validation status, execution metrics, and the returned data table in the chat stream, along with an optional brief natural language explanation.

> **Key Design Boundary**: The primary objective is a secure, read-only natural-language-to-SQL chat assistant. It is not an autonomous agent or an elaborate data engineering platform. Validation and execution layers remain completely independent of the LLM.

---

## 2. Technology Stack & Environment

| Component | Technology | Role |
|---|---|---|
| **Language** | Python 3.10+ | Core runtime |
| **LLM Orchestration** | LangChain (`langchain-core`, `langchain-google-genai`) | Prompt templating & Gemini model invocation |
| **Foundation Model** | Google Gemini (`gemini-1.5-flash` or configurable) | SQL query generation |
| **SQL Parser & AST Validation** | SQLGlot | AST parsing, dialect checking, structural guardrails |
| **Database** | SQLite3 | Relational storage & read-only execution |
| **Web Interface** | Streamlit | Chat-based user interface |
| **Configuration** | `python-dotenv` | Environment variable management |
| **Testing** | Pytest | Unit and integration test suite |

---

## 3. Architecture & Data Flow

```mermaid
flowchart TD
    User([User Question]) --> ChatUI[Streamlit Chat Interface (app.py)]
    ChatUI --> Generator[SQL Generator (src/sql_generator.py)]
    Generator --> Prompt[LangChain ChatPromptTemplate]
    Prompt --> Gemini[Google Gemini LLM / Mock Generator]
    Gemini --> RawSQL[Generated Raw SQL]
    RawSQL --> Validator{SQL Validator (src/sql_validator.py)\nSQLGlot AST Inspection}
    
    Validator -- "Unsafe / Invalid" --> Blocked[Reject Query + Return Clear Error]
    Blocked --> ChatUI
    
    Validator -- "Approved SELECT" --> Executor[Query Executor (src/query_executor.py)]
    Executor --> ReadOnlyDB[(SQLite Database\nRead-Only Connection)]
    ReadOnlyDB --> QueryResults[Results Table + Execution Metrics]
    QueryResults --> ChatUI
```

### Component Responsibilities
- `src/config.py`: Loads environment variables (`GEMINI_API_KEY`, model names, timeout, row limits) with sensible defaults.
- `src/database.py`: Manages SQLite connections, database initialization from DDL, schema introspection, and read-only connection handles.
- `src/data_generator.py`: Generates deterministic, realistic synthetic datasets for `customers`, `products`, and `orders`.
- `src/ingestion.py`: Cleans, validates, deduplicates, and idempotently populates SQLite tables.
- `src/sql_generator.py`: Uses LangChain's `ChatPromptTemplate` and `ChatGoogleGenerativeAI` to construct the prompt and invoke the model; includes a Mock SQL Generator for offline testing.
- `src/sql_validator.py`: Parses SQL AST with SQLGlot, enforcing read-only rules, single-statement checks, table/column allowlists, and injecting safe `LIMIT` clauses.
- `src/query_executor.py`: Executes validated SQL over a read-only SQLite connection (`file:...db?mode=ro` and `PRAGMA query_only = ON`), enforces execution timeouts, and caps row fetches.
- `app.py`: Streamlit chat UI providing conversational question input, SQL inspection, validation chips, tabular results, and a schema reference sidebar.

---

## 4. Database Schema & Business Rules

### Schema Definition (`sql/schema.sql`)
1. **`customers`**
   - `customer_id` (INTEGER PRIMARY KEY)
   - `name` (TEXT NOT NULL)
   - `city` (TEXT NOT NULL)
   - `signup_date` (DATE NOT NULL)

2. **`products`**
   - `product_id` (INTEGER PRIMARY KEY)
   - `product_name` (TEXT NOT NULL)
   - `category` (TEXT NOT NULL)
   - `unit_price` (REAL NOT NULL CHECK(unit_price > 0))

3. **`orders`**
   - `order_id` (INTEGER PRIMARY KEY)
   - `customer_id` (INTEGER NOT NULL REFERENCES `customers(customer_id)`)
   - `product_id` (INTEGER NOT NULL REFERENCES `products(product_id)`)
   - `quantity` (INTEGER NOT NULL CHECK(quantity > 0))
   - `order_date` (DATE NOT NULL)
   - `status` (TEXT NOT NULL CHECK(status IN ('Completed', 'Pending', 'Cancelled', 'Shipped')))

### Business Assumptions & Calculations
- **Sales Calculation**: Total sales for an order is defined as `quantity * unit_price` (obtained by joining `orders` with `products`).
- **Cancelled Orders**: Queries calculating "total sales" or "revenue" must exclude `status = 'Cancelled'` unless the user explicitly requests all order statuses.
- **Pending Orders**: Orders with `status = 'Pending'` represent unfulfilled orders.
- **Idempotency**: Repeated ingestion runs do not create duplicate records; tables use primary keys and `INSERT OR IGNORE` / unique constraints. Missing non-essential fields are handled gracefully; records with missing foreign keys or primary keys are dropped.

---

## 5. LangChain & Gemini Integration

- **Prompt Construction**: Uses LangChain's `ChatPromptTemplate` with:
  - Exact SQLite schema definitions (tables, columns, types, foreign keys).
  - Business rules (e.g., how to compute total sales, status filters).
  - SQLite dialect rules (e.g., date functions, single statement, `LIMIT` clause).
  - Explicit instruction to output **only valid SQL** without markdown fences or conversational filler.
- **Model Invocation**: `ChatGoogleGenerativeAI` with `temperature=0.0` for deterministic outputs. Model name configurable via `.env` (defaulting to `gemini-1.5-flash`).
- **Sanitization**: Strips any markdown formatting (e.g. ````sql ... ````) before passing the string to the validation layer.
- **Error & Fallback Handling**:
  - Catches missing `GEMINI_API_KEY`, network timeouts, and model rate limits with user-friendly messages.
  - A mock SQL generator is provided for offline testing and test suites, but is never misrepresented as live Gemini output in the user interface.

---

## 6. SQL Guardrails & Security Policy

Security relies on a **defense-in-depth model** combining independent AST analysis and driver-level restrictions:

1. **Strict Read-Only Enforcement**:
   - The query AST must be a single `sqlglot.exp.Select`.
   - Any query containing destructive expressions (`Insert`, `Update`, `Delete`, `Drop`, `Alter`, `Create`, `Truncate`, `Pragma`, `Attach`, `Detach`, `Vacuum`) is rejected immediately.
2. **Single Statement Validation**:
   - Multiple statements (semicolon stacking, e.g., `SELECT 1; DROP TABLE orders;`) are strictly blocked.
3. **Table & Column Allowlisting**:
   - Tables referenced must belong strictly to `{'customers', 'products', 'orders'}` (or internal CTE aliases).
   - System tables (e.g., `sqlite_master`, `sqlite_sequence`, `sqlite_temp_master`) are explicitly rejected.
   - Referenced columns are checked against the active database schema.
4. **Dangerous Construct & Function Blocking**:
   - Disallow external commands, file functions, or extensions (`load_extension`, `eval`).
5. **Execution Limits & Read-Only Connection**:
   - Enforce an automatic `LIMIT 100` if the generated query omits a limit clause.
   - Execute queries via SQLite URI read-only mode (`file:...db?mode=ro`, `PRAGMA query_only = ON;`).
   - Query execution timeout (e.g., max 5 seconds) and row fetch capping (max 1,000 rows).
   - Rejected queries never touch or modify the database.

---

## 7. Streamlit Chat Interface (`app.py`)

A clean, responsive chat-style UI:
- **Chat History**: Displaying user questions and assistant responses in chronological order using `st.chat_message`.
- **Query Details**: Expandable section showing the generated SQL with syntax highlighting.
- **Validation Badge**: Visual indicator showing whether the query was approved or rejected (with specific reasons if rejected).
- **Tabular Results**: Interactive table (`st.dataframe`) showing the actual query results.
- **Metadata**: Row count and query execution time (ms).
- **Sidebar**:
  - Database schema inspector (tables, columns, sample rows).
  - Quick-select buttons/pills for example screening questions:
    - *"How many orders are there?"*
    - *"Which five products have the highest total sales?"*
    - *"Which customers have placed the most orders?"*
    - *"What is the total quantity ordered by product category?"*
    - *"Which cities have the most customers?"*
    - *"How many orders are pending?"*
    - *"Show the ten most recent orders with customer names."*

---

## 8. Repository Structure

```
Text_To_SQL_With_Guarded_Assistant/
├── PLAN.md                     # This plan
├── README.md                   # Comprehensive project documentation
├── requirements.txt            # Dependency list
├── .env.example                # Template environment variables
├── .gitignore                  # Git ignore rules (DB, env, pycache)
├── app.py                      # Streamlit chat interface
├── src/
│   ├── __init__.py
│   ├── config.py               # Settings & environment variables
│   ├── database.py             # SQLite setup, schema retrieval, read-only connections
│   ├── data_generator.py       # Deterministic synthetic data generation
│   ├── ingestion.py            # Data cleaning, deduplication, and DB loading
│   ├── sql_generator.py        # LangChain & Gemini integration (+ mock generator)
│   ├── sql_validator.py        # SQLGlot AST guardrails & allowlist validation
│   └── query_executor.py       # Read-only query execution & timeout handler
├── sql/
│   └── schema.sql              # DDL schema for customers, products, orders
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Test fixtures (temporary DB, mock data)
│   ├── test_ingestion.py       # Duplicate handling, missing data, idempotency
│   ├── test_sql_validator.py   # Guardrails: safe SELECTs, rejects DDL/DML/multi-statement
│   ├── test_query_executor.py  # Read-only execution, timeout, immutability check
│   └── test_sql_generator.py   # LangChain prompt formatting, output cleaning, error handling
└── docs/
    ├── architecture.md         # Architecture diagram and component breakdown
    └── design_decisions.md     # 1-page design decision log and tradeoffs
```

---

## 9. Testing Strategy (Minimum 8 Automated Tests)

Run with `pytest -v`. Tests run completely offline without an API key using temporary SQLite databases and mock SQL generation.

| # | Test Case | Target Module | Objective |
|---|---|---|---|
| 1 | Valid `SELECT` Query | `test_sql_validator.py` | Verify valid queries (joins, aggregations, filters) pass validation |
| 2 | Rejection of `DELETE` | `test_sql_validator.py` | Verify destructive `DELETE` statements are blocked |
| 3 | Rejection of `DROP TABLE` | `test_sql_validator.py` | Verify DDL `DROP` statements are blocked |
| 4 | Rejection of Multi-Statements | `test_sql_validator.py` | Verify stacked queries (`SELECT ...; DROP ...`) are blocked |
| 5 | Rejection of Unauthorized Objects | `test_sql_validator.py` | Verify queries referencing unknown tables or system tables are blocked |
| 6 | Ingestion Deduplication | `test_ingestion.py` | Verify repeated ingestion does not create duplicate records |
| 7 | Missing/Invalid Data Handling | `test_ingestion.py` | Verify null/invalid inputs are handled according to rules |
| 8 | AI Error / Invalid Output | `test_sql_generator.py` | Verify graceful handling when the model fails or outputs invalid text |
| + | Database Immutability | `test_query_executor.py` | Verify the database state is unchanged after rejected query attempts |
| + | Execution Limits | `test_query_executor.py` | Verify queries exceeding row limits or timeouts are handled safely |

---

## 10. Required Deliverables

1. **Runnable Streamlit Chat Assistant**: Functional `app.py` supporting conversational question input, SQL display, validation status, and results.
2. **LangChain & Gemini SQL Generator**: Structured prompt templates, Gemini LLM chain, and output sanitization.
3. **Synthetic Dataset & Ingestion Script**: Reproducible database initialization script populating `customers`, `products`, and `orders`.
4. **SQLGlot Guardrail Engine**: Independent AST validation blocking destructive, multi-statement, and out-of-scope queries.
5. **Read-Only Query Executor**: Sandboxed execution enforcing read-only SQLite mode and resource limits.
6. **Automated Test Suite**: At least 8 passing Pytest tests executable via `pytest -v` without an API key.
7. **Clean Repository**: Properly configured `.gitignore`, `.env.example`, and no committed secrets or pre-generated databases.
8. **Comprehensive README.md**: Problem statement, setup instructions for Windows, architecture diagram, example queries, testing guide, assumptions, and limitations.
9. **Architecture Diagram & Spec**: Documented in `docs/architecture.md`.
10. **Design Decisions Note**: Approximately one-page document in `docs/design_decisions.md` explaining key tradeoffs (e.g., AST validation vs. regex, read-only connections, business logic decisions).
11. **Demo Video Plan & Script**: 5–8 minute video walkthrough demonstrating setup, sample queries, results, and rejection of unsafe SQL.
12. **Submission Summary**: Final summary including GitHub repository link and demo video link.

---

## 11. Implementation Phases

```mermaid
gantt
    title Implementation Phases
    dateFormat X
    axisFormat %s
    section Core
    Phase 1: Foundation, Schema & DDL           :p1, 0, 1
    Phase 2: Synthetic Data & Ingestion Pipeline:p2, 1, 2
    Phase 3: SQLGlot Validator & Guardrails     :p3, 2, 3
    Phase 4: Read-Only Query Executor           :p4, 3, 4
    Phase 5: LangChain & Gemini SQL Generator   :p5, 4, 5
    Phase 6: Streamlit Chat Interface           :p6, 5, 6
    Phase 7: Test Suite & Edge-Case Verification:p7, 6, 7
    Phase 8: Documentation, Design Note & Demo  :p8, 7, 8
```

- **Phase 1: Project Foundation, Assumptions, Architecture, and Database Schema**
  - Create directory structure, `sql/schema.sql`, `src/config.py`, `.env.example`, `.gitignore`, `requirements.txt`.
- **Phase 2: Synthetic Data Generation, Database Initialization, and Ingestion**
  - Implement `src/data_generator.py`, `src/database.py`, and `src/ingestion.py`.
  - Add CLI execution capability (`python -m src.ingestion`) to generate data and populate `data/app_database.db`.
- **Phase 3: SQL Validator and Security Tests**
  - Implement `src/sql_validator.py` with AST-based SQLGlot validation rules.
  - Write `tests/test_sql_validator.py` and verify all security checks pass.
- **Phase 4: Read-Only Query Executor and Execution Limits**
  - Implement `src/query_executor.py` with read-only connection, timeout handler, and row limits.
  - Write `tests/test_query_executor.py` verifying read-only enforcement and DB immutability.
- **Phase 5: LangChain and Gemini SQL Generation**
  - Implement `src/sql_generator.py` with `ChatPromptTemplate`, `ChatGoogleGenerativeAI`, and the mock generator.
  - Write `tests/test_sql_generator.py` verifying prompt formation, markdown stripping, and failure modes.
- **Phase 6: Streamlit Chat Interface and Integration**
  - Build `app.py` with conversational chat messages, SQL viewer, validation status, results table, metrics, and schema browser.
- **Phase 7: Automated Tests and Edge-Case Verification**
  - Implement `tests/test_ingestion.py` and run full test suite with `pytest -v`.
  - Verify all 8+ tests pass offline without an API key.
- **Phase 8: README, Architecture Documentation, Design Note, and Demo Preparation**
  - Complete `README.md`, `docs/architecture.md`, `docs/design_decisions.md`.
  - Outline demo video script and prepare submission summary.

---

## 12. Completion Criteria

The project is considered complete only when:
- [ ] The application installs and runs cleanly on Windows using documented commands.
- [ ] Database is generated during setup via script (not committed as a static binary).
- [ ] Natural language questions generate valid SQLite SQL via LangChain and Gemini.
- [ ] The generated SQL is clearly displayed in the chat interface.
- [ ] Valid queries return real data from SQLite with execution metrics.
- [ ] Unsafe SQL (destructive operations, stacked queries, unauthorized tables/columns) is rejected before execution.
- [ ] Rejected queries leave the database completely unmodified.
- [ ] Synthetic data generation and ingestion can be rerun safely and idempotently.
- [ ] At least eight automated tests pass cleanly via `pytest -v` without requiring a real API key.
- [ ] All required documentation files (`README.md`, `docs/architecture.md`, `docs/design_decisions.md`) are complete.
- [ ] The repository contains no committed secrets or `.env` files.
- [ ] The demo video plan and submission summary are prepared.
