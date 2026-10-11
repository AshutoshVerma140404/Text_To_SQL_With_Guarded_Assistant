"""Sandboxed read-only query execution with timeout and row capping."""

import time
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.config import DATABASE_PATH, QUERY_TIMEOUT_SECONDS, MAX_ROW_LIMIT
from src.database import get_read_only_connection


@dataclass
class QueryExecutionResult:
    """Encapsulates the result and performance metrics of query execution."""
    success: bool
    columns: List[str] = field(default_factory=list)
    rows: List[Dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float = 0.0
    error_message: Optional[str] = None
    truncated: bool = False


class QueryTimeoutError(Exception):
    """Raised when a query exceeds the allotted execution timeout."""
    pass


def execute_read_only_query(
    sql_query: str,
    db_path: Path | str = DATABASE_PATH,
    timeout_seconds: float = QUERY_TIMEOUT_SECONDS,
    max_rows: int = MAX_ROW_LIMIT,
) -> QueryExecutionResult:
    """Executes a sanitized SQL query on a strictly read-only SQLite connection.
    
    Enforces:
    - Connection mode `mode=ro` and `PRAGMA query_only = ON`.
    - SQLite progress handler timeout check.
    - Capped row retrieval up to `max_rows`.
    - Execution timing metrics.
    """
    path = Path(db_path)
    if not path.exists():
        return QueryExecutionResult(
            success=False,
            error_message=f"Database file does not exist at {path}. Please initialize the database first.",
        )

    start_time = time.perf_counter()
    deadline = start_time + timeout_seconds

    def progress_callback():
        # Aborts query by returning non-zero if timeout deadline passed
        if time.perf_counter() > deadline:
            return 1
        return 0

    try:
        conn = get_read_only_connection(path)
        # Register progress handler to interrupt queries that exceed timeout
        conn.set_progress_handler(progress_callback, 1000)
        cursor = conn.cursor()

        try:
            cursor.execute(sql_query)
            columns = [col[0] for col in cursor.description] if cursor.description else []
            
            # Fetch up to max_rows + 1 to detect if truncation occurred
            raw_rows = cursor.fetchmany(max_rows + 1)
            truncated = len(raw_rows) > max_rows
            final_rows = raw_rows[:max_rows]

            rows_as_dict = [dict(zip(columns, row)) for row in final_rows]
            exec_time = (time.perf_counter() - start_time) * 1000.0

            return QueryExecutionResult(
                success=True,
                columns=columns,
                rows=rows_as_dict,
                row_count=len(rows_as_dict),
                execution_time_ms=round(exec_time, 2),
                truncated=truncated,
            )

        except sqlite3.OperationalError as e:
            exec_time = (time.perf_counter() - start_time) * 1000.0
            err_msg = str(e)
            if "interrupted" in err_msg.lower():
                return QueryExecutionResult(
                    success=False,
                    execution_time_ms=round(exec_time, 2),
                    error_message=f"Query execution timed out after {timeout_seconds} seconds.",
                )
            elif "readonly" in err_msg.lower() or "query_only" in err_msg.lower() or "not authorized" in err_msg.lower():
                return QueryExecutionResult(
                    success=False,
                    execution_time_ms=round(exec_time, 2),
                    error_message=f"Database permission error: write operations are strictly disallowed. ({err_msg})",
                )
            return QueryExecutionResult(
                success=False,
                execution_time_ms=round(exec_time, 2),
                error_message=f"SQLite execution error: {err_msg}",
            )

        except sqlite3.Error as e:
            exec_time = (time.perf_counter() - start_time) * 1000.0
            return QueryExecutionResult(
                success=False,
                execution_time_ms=round(exec_time, 2),
                error_message=f"Database error: {str(e)}",
            )
        finally:
            conn.close()

    except Exception as ex:
        exec_time = (time.perf_counter() - start_time) * 1000.0
        return QueryExecutionResult(
            success=False,
            execution_time_ms=round(exec_time, 2),
            error_message=f"Unexpected error: {str(ex)}",
        )
