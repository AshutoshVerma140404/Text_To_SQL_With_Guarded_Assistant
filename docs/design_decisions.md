# Design Decisions & Tradeoffs Log

## 1. AST Validation (SQLGlot) vs. Regex Pattern Matching

### Decision:
We adopted SQLGlot to parse queries into an Abstract Syntax Tree (AST) rather than relying on regular expressions or keyword blocklists.

### Rationale & Tradeoffs:
- **Security Vulnerabilities in Regex**: Regex-based sanitizers are notoriously brittle and susceptible to bypasses (e.g., nested comments like `/* DROP */`, subqueries, encoded characters, or string literals containing keywords like `'SELECT DELETE FROM'`).
- **Semantic Understanding**: SQLGlot understands SQL syntax context. It distinguishes whether a keyword like `DELETE` appears as an actual AST statement node (`exp.Delete`) versus an innocent column alias or text literal (e.g., `WHERE action = 'delete'`).
- **Allowlisting vs. Blocklisting**: With an AST, we can inspect every referenced table node (`exp.Table`) and confirm it belongs to our allowlist `{'customers', 'products', 'orders'}`, while properly recognizing Common Table Expression (CTE) aliases.

---

## 2. Multi-Layer Defense-in-Depth vs. Single Layer Protection

### Decision:
We implemented defense-in-depth across three separate boundaries:
1. Prompt Engineering: Direct instructions to generate read-only queries.
2. AST Guardrail Engine (`src/sql_validator.py`): Rejects any non-SELECT or destructive statement before it touches SQLite.
3. Driver-Level Restrictions (`src/query_executor.py`): Queries execute exclusively through SQLite URI `mode=ro` and `PRAGMA query_only = ON`.

### Rationale & Tradeoffs:
- Even if an adversarial prompt injection somehow slipped past the LLM and AST parser, the SQLite engine itself physically rejects write operations with `sqlite3.OperationalError: attempt to write a readonly database`.
- This ensures absolute database immutability regardless of input.

---

## 3. SQLite Progress Handler for Timeouts vs. POSIX Signals / OS Threads

### Decision:
We used SQLite's native `sqlite3.Connection.set_progress_handler` callback for query timeouts instead of `signal.alarm` or separate OS threads.

### Rationale & Tradeoffs:
- **Windows Compatibility**: Python's `signal.alarm` is UNIX-only and unavailable on Windows.
- **Thread Safety**: Killing threads in Python can leave SQLite handles in an inconsistent state or leak memory.
- **Native Cancellation**: SQLite's progress handler periodically invokes our Python callback every N virtual machine instructions. Returning `1` from the callback cleanly aborts the executing query within SQLite's C core, raising `sqlite3.OperationalError: interrupted`.

---

## 4. Idempotent Ingestion vs. Drop-and-Recreate

### Decision:
Ingestion utilizes primary keys, foreign key constraints, data validation pipelines, and `INSERT OR IGNORE`.

### Rationale & Tradeoffs:
- Dropping and recreating tables on every run risks downtime, file lock conflicts on Windows, and loss of historical records.
- Idempotency guarantees that ingestion scripts can be safely run multiple times without creating duplicate rows or corrupting relations.

---

## 5. Offline Mock Generator vs. Mandatory API Key

### Decision:
We integrated a deterministic mock generator alongside the Google Gemini LangChain integration.

### Rationale & Tradeoffs:
- Enables full offline operation and automated unit/integration test suites without leaking secrets, hitting rate limits, or incurring costs.
- Transparent UI indication ensures the user always knows whether the active response was produced by live Gemini or the offline mock engine.
