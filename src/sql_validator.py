"""SQL AST Validation and Guardrail Engine using SQLGlot."""

from dataclasses import dataclass, field
from typing import Optional, Set, Dict, List
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from src.config import (
    ALLOWED_TABLES,
    DISALLOWED_SYSTEM_TABLES,
    DISALLOWED_FUNCTIONS,
    DEFAULT_ROW_LIMIT,
    MAX_ROW_LIMIT,
)

DESTRUCTIVE_EXPRESSION_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.Pragma,
    exp.Command,
)


@dataclass
class ValidationResult:
    """Result of SQL validation check."""
    is_valid: bool
    sanitized_sql: Optional[str] = None
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def validate_and_sanitize_sql(
    sql_text: str,
    allowed_tables: Set[str] = ALLOWED_TABLES,
    schema_columns: Optional[Dict[str, Set[str]]] = None,
    default_limit: int = DEFAULT_ROW_LIMIT,
    max_limit: int = MAX_ROW_LIMIT,
) -> ValidationResult:
    """Validates and sanitizes a SQL query using SQLGlot AST inspection.
    
    Enforces:
    1. Single statement only (no semicolon stacking).
    2. Strictly read-only queries (SELECT / UNION / CTE).
    3. No destructive statements (DROP, DELETE, UPDATE, INSERT, ALTER, etc.).
    4. Table allowlisting (only authorized tables or CTEs allowed).
    5. Disallows SQLite system tables (e.g., sqlite_master).
    6. Disallows dangerous functions (e.g., load_extension, eval).
    7. Column validation against schema if provided.
    8. Automatic injection of LIMIT clause if omitted, or clamping if exceeding max_limit.
    """
    if not sql_text or not sql_text.strip():
        return ValidationResult(
            is_valid=False,
            error_message="Query is empty.",
        )

    clean_text = sql_text.strip().rstrip(";")

    # 1. Parse AST with SQLite dialect
    try:
        statements = sqlglot.parse(clean_text, read="sqlite")
    except ParseError as e:
        return ValidationResult(
            is_valid=False,
            error_message=f"SQL syntax error: {str(e)}",
        )

    # 2. Enforce single statement
    valid_statements = [s for s in statements if s is not None]
    if len(valid_statements) == 0:
        return ValidationResult(is_valid=False, error_message="No valid SQL statements found.")
    if len(valid_statements) > 1:
        return ValidationResult(
            is_valid=False,
            error_message="Multi-statement queries (semicolon chaining) are strictly prohibited.",
        )

    expression = valid_statements[0]

    # 3. Check statement type: Must be a Select or Union expression
    if not isinstance(expression, (exp.Select, exp.Union)):
        return ValidationResult(
            is_valid=False,
            error_message=f"Statement type '{expression.key.upper()}' is not permitted. Only SELECT queries are allowed.",
        )

    # 4. Check for destructive nodes anywhere in the AST
    for node in expression.walk():
        if isinstance(node, DESTRUCTIVE_EXPRESSION_TYPES):
            node_name = type(node).__name__.upper()
            return ValidationResult(
                is_valid=False,
                error_message=f"Destructive or non-read-only operation '{node_name}' detected. Only SELECT queries are permitted.",
            )

    # 5. Extract CTE aliases so they are not flagged as unauthorized tables
    cte_aliases = {c.alias_or_name.lower() for c in expression.find_all(exp.CTE)}

    # 6. Table validation
    tables_referenced = expression.find_all(exp.Table)
    for table_node in tables_referenced:
        table_name = table_node.name.lower()

        # Reject system tables explicitly
        if table_name in DISALLOWED_SYSTEM_TABLES:
            return ValidationResult(
                is_valid=False,
                error_message=f"Access to SQLite system catalog table '{table_node.name}' is prohibited.",
            )

        # Allow CTE aliases
        if table_name in cte_aliases:
            continue

        # Check against allowed tables
        if table_name not in allowed_tables:
            allowed_list_str = ", ".join(sorted(allowed_tables))
            return ValidationResult(
                is_valid=False,
                error_message=f"Unauthorized table '{table_node.name}'. Only the following tables are permitted: {allowed_list_str}.",
            )

    # 7. Disallowed functions
    for func_node in expression.find_all((exp.Anonymous, exp.Func)):
        fname = func_node.name.lower() if hasattr(func_node, "name") else ""
        if fname in DISALLOWED_FUNCTIONS:
            return ValidationResult(
                is_valid=False,
                error_message=f"Execution of prohibited function '{fname}()' is not allowed.",
            )

    # 8. Column validation against schema (if provided)
    if schema_columns:
        # Collect table alias mapping within query
        alias_to_table = {}
        for t in tables_referenced:
            tname = t.name.lower()
            if tname in allowed_tables:
                if t.alias:
                    alias_to_table[t.alias.lower()] = tname
                alias_to_table[tname] = tname

        for col_node in expression.find_all(exp.Column):
            col_name = col_node.name.lower()
            col_table = col_node.table.lower() if col_node.table else None

            # If table prefix is explicit and belongs to known tables
            if col_table and col_table in alias_to_table:
                actual_table = alias_to_table[col_table]
                valid_cols = {c.lower() for c in schema_columns.get(actual_table, set())}
                if col_name != "*" and col_name not in valid_cols:
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Column '{col_name}' does not exist on table '{actual_table}'.",
                    )

    # 9. LIMIT clause inspection and enforcement
    warnings = []
    limit_node = expression.args.get("limit")
    if limit_node is None:
        expression = expression.limit(default_limit)
        warnings.append(f"No LIMIT specified; automatically applied LIMIT {default_limit}.")
    else:
        try:
            limit_val = int(limit_node.expression.name)
            if limit_val > max_limit:
                expression.set("limit", exp.Limit(expression=exp.Literal.number(max_limit)))
                warnings.append(f"Requested LIMIT {limit_val} exceeded maximum allowable ({max_limit}); capped to {max_limit}.")
        except (ValueError, AttributeError):
            pass

    sanitized_sql = expression.sql(dialect="sqlite")
    return ValidationResult(
        is_valid=True,
        sanitized_sql=sanitized_sql,
        warnings=warnings,
    )
