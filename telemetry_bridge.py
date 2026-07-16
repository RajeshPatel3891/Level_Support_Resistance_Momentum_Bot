import os
import sqlite3
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
DB_FILE = os.path.join(CURRENT_DIR, 'harm_telemetry.db')

class TelemetryBridge:
    """
    Unified High-Fidelity Persistence Gateway for HARM.AI.
    Bridges both Live Sentinel Execution (is_live=1) and Offline Simulation runs (is_live=0)
    into the unified database schema including CSO clearance tracking.
    """
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    support_level REAL,
                    spot_price REAL,
                    exit_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    distance REAL,
                    allowed_dist REAL,
                    proximity_score REAL,
                    exit_status TEXT,
                    net_pnl REAL,
                    is_live INTEGER DEFAULT 1,
                    cso_cleared INTEGER DEFAULT 1,
                    cso_notes TEXT
                )
            """)

    def log_trade(self, ticker, strategy, direction, support_level, spot_price, stop_loss, take_profit,
                  exit_price=None, distance=0.0, allowed_dist=2.50, proximity_score=0.0, 
                  exit_status="ACTIVE", net_pnl=0.0, is_live=True, cso_cleared=True, cso_notes=""):
        """
        Commits execution records to the database with CSO context.
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        is_live_flag = 1 if is_live else 0
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO trades (
                    ticker, timestamp, strategy, direction, support_level, spot_price, 
                    exit_price, stop_loss, take_profit, distance, allowed_dist, 
                    proximity_score, exit_status, net_pnl, is_live, cso_cleared, cso_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker, timestamp, strategy, direction, support_level, spot_price,
                exit_price, stop_loss, take_profit, distance, allowed_dist,
                proximity_score, exit_status, net_pnl, is_live_flag, int(cso_cleared), cso_notes
            ))
