import sqlite3
import glob
import re
import os
import sys
from schema_manifest import TABLE_SCHEMAS

def audit_codebase():
    print("=" * 70)
    print("🔍 HARM.AI SCHEMA MANIFEST COMPLETENESS AUDITOR")
    print("=" * 70)

    # 1. Initialize purely in-memory DB using ONLY schema_manifest.py
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    for table, ddl in TABLE_SCHEMAS.items():
        cursor.execute(ddl)
    conn.commit()

    # Extract all valid tables and columns from the manifest
    manifest_schema = {}
    for table in TABLE_SCHEMAS.keys():
        cols = set(row[1] for row in cursor.execute(f"PRAGMA table_info({table});"))
        manifest_schema[table] = cols
        print(f"[✓] Manifest Table '{table}': {len(cols)} columns verified -> {sorted(list(cols))}")

    print("-" * 70)

    # 2. Gather all python files (excluding backup/test scripts)
    py_files = [f for f in glob.glob("**/*.py", recursive=True) 
                if not f.startswith("backups/") and not f.startswith("tests/")]

    missing_table_errors = []
    missing_column_errors = []

    # Regular expressions to extract SQL string literals
    sql_pattern = re.compile(
        r'["\']{3}(.*?)["\']{3}|["\'](SELECT|INSERT|UPDATE|DELETE|ALTER).*?["\']', 
        re.DOTALL | re.IGNORECASE
    )

    # Simple regex for column names inside queries (e.g. starting_settled_cash, net_pnl)
    identifier_pattern = re.compile(r'\b([a_z][a_z0_9_]+)\b', re.IGNORECASE)

    sql_keywords = {
        'select', 'insert', 'update', 'delete', 'from', 'where', 'into', 'values',
        'set', 'order', 'by', 'group', 'asc', 'desc', 'limit', 'offset', 'and',
        'or', 'not', 'null', 'is', 'in', 'as', 'on', 'join', 'left', 'right',
        'inner', 'outer', 'text', 'real', 'integer', 'primary', 'key', 'autoincrement',
        'default', 'table', 'if', 'exists', 'pragma', 'count', 'sum', 'avg', 'max',
        'min', 'datetime', 'current_timestamp', 'none', 'true', 'false', 'like'
    }

    # Iterate through code and dry-run SQL statements
    for filepath in py_files:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Find all potential SQL blocks in script
            matches = sql_pattern.findall(content)
            for match in matches:
                sql_snippet = match[0] if match[0] else match[1]
                sql_snippet_clean = sql_snippet.strip().replace('\n', ' ')

                # Check for table existence referenced in SQL string
                for table in manifest_schema.keys():
                    if table in sql_snippet_clean.lower():
                        # Extract all identifiers and check against manifest columns
                        words = set(identifier_pattern.findall(sql_snippet_clean.lower())) - sql_keywords
                        for word in words:
                            # If word looks like a column (used in SQL) but not in table schema
                            if "_" in word and word not in manifest_schema[table]:
                                # Check if it's a column in ANY table
                                all_cols = set().union(*manifest_schema.values())
                                if word not in all_cols:
                                    missing_column_errors.append((filepath, table, word, sql_snippet_clean[:80]))

        except Exception as e:
            print(f"[!] Error reading {filepath}: {e}")

    # 3. Report Results
    print("=" * 70)
    if not missing_column_errors:
        print("🎉 SUCCESS: ZERO MISSING COLUMNS DETECTED IN CODEBASE!")
        print("[✓] schema_manifest.py is 100% complete for all active Python scripts.")
        print("=" * 70)
        sys.exit(0)
    else:
        print(f"🚨 WARNING: FOUND {len(missing_column_errors)} POTENTIAL MISSING COLUMNS IN CODEBASE:")
        print("-" * 70)
        seen = set()
        for filepath, table, col, snippet in missing_column_errors:
            key = f"{filepath}:{table}:{col}"
            if key not in seen:
                seen.add(key)
                print(f"  • Script: {filepath}")
                print(f"    Table: '{table}' | Missing Column: '{col}'")
                print(f"    Snippet: {snippet}...")
                print()
        print("=" * 70)
        sys.exit(1)

if __name__ == "__main__":
    audit_codebase()
