"""
HARM.AI ATOMIC DATABASE SCHEMA MANIFEST
========================================
Single source of truth for all SQLite tables across the trading engine.
"""

TABLE_SCHEMAS = {
    "account_ledger": """
        CREATE TABLE IF NOT EXISTS account_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            date TEXT DEFAULT '',
            balance REAL DEFAULT 10000.0,
            available_cash REAL DEFAULT 10000.0,
            starting_settled_cash REAL DEFAULT 10000.0,
            settled_cash REAL DEFAULT 10000.0,
            available_settled_cash REAL DEFAULT 10000.0,
            unsettled_cash REAL DEFAULT 0.0,
            deployed_capital REAL DEFAULT 0.0,
            net_pnl REAL DEFAULT 0.0,
            realized_pnl REAL DEFAULT 0.0,
            unrealized_pnl REAL DEFAULT 0.0
        );
    """,
    "trades": """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT DEFAULT 'COMPANY_A',
            ticker TEXT,
            timestamp TEXT,
            exit_timestamp TEXT,
            strategy TEXT,
            direction TEXT,
            execution_origin TEXT DEFAULT 'BOT',
            support_level REAL,
            spot_price REAL,
            entry_price REAL DEFAULT 0.0,
            exit_price REAL,
            stop_loss REAL,
            take_profit REAL,
            distance REAL,
            allowed_dist REAL,
            proximity_score REAL DEFAULT 0.0,
            peak_pnl REAL DEFAULT 0.0,
            shares INTEGER DEFAULT 0,
            exit_status TEXT,
            net_pnl REAL,
            is_live INTEGER DEFAULT 1,
            cso_cleared INTEGER DEFAULT 0,
            cso_notes TEXT DEFAULT '',
            occ_symbol TEXT DEFAULT ''
        );
    """,
    "harmonized_trades": """
        CREATE TABLE IF NOT EXISTS harmonized_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT DEFAULT 'COMPANY_A',
            ticker TEXT,
            timestamp TEXT,
            exit_timestamp TEXT,
            strategy TEXT,
            direction TEXT,
            execution_origin TEXT DEFAULT 'BOT',
            support_level REAL,
            spot_price REAL,
            entry_price REAL DEFAULT 0.0,
            exit_price REAL,
            stop_loss REAL,
            take_profit REAL,
            distance REAL,
            allowed_dist REAL,
            proximity_score REAL DEFAULT 0.0,
            peak_pnl REAL DEFAULT 0.0,
            shares INTEGER DEFAULT 0,
            exit_status TEXT,
            net_pnl REAL,
            is_live INTEGER DEFAULT 1,
            cso_cleared INTEGER DEFAULT 0,
            cso_notes TEXT DEFAULT '',
            occ_symbol TEXT DEFAULT ''
        );
    """,
    "gex_telemetry": """
        CREATE TABLE IF NOT EXISTS gex_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            ticker TEXT,
            underlying_price REAL DEFAULT 0.0,
            gamma_flip REAL,
            zero_gamma REAL,
            net_gex REAL
        );
    """,
    "tick_history": """
        CREATE TABLE IF NOT EXISTS tick_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            ticker TEXT,
            price REAL,
            volume INTEGER
        );
    """,
    "backtest_runs": """
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            ticker TEXT,
            test_date TEXT,
            strategy TEXT,
            net_pnl REAL
        );
    """
}

COLUMN_TYPES = {
    "account_ledger": {
        "date": "TEXT DEFAULT ''",
        "balance": "REAL DEFAULT 10000.0",
        "available_cash": "REAL DEFAULT 10000.0",
        "starting_settled_cash": "REAL DEFAULT 10000.0",
        "settled_cash": "REAL DEFAULT 10000.0",
        "available_settled_cash": "REAL DEFAULT 10000.0",
        "unsettled_cash": "REAL DEFAULT 0.0",
        "deployed_capital": "REAL DEFAULT 0.0",
        "net_pnl": "REAL DEFAULT 0.0",
        "realized_pnl": "REAL DEFAULT 0.0",
        "unrealized_pnl": "REAL DEFAULT 0.0"
    },
    "trades": {
        "company_id": "TEXT DEFAULT 'COMPANY_A'",
        "exit_timestamp": "TEXT DEFAULT ''",
        "execution_origin": "TEXT DEFAULT 'BOT'",
        "entry_price": "REAL DEFAULT 0.0",
        "shares": "INTEGER DEFAULT 0",
        "proximity_score": "REAL DEFAULT 0.0",
        "peak_pnl": "REAL DEFAULT 0.0",
        "cso_notes": "TEXT DEFAULT ''",
        "cso_cleared": "INTEGER DEFAULT 0",
        "is_live": "INTEGER DEFAULT 1",
        "occ_symbol": "TEXT DEFAULT ''"
    }
}
