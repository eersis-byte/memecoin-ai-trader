"""Transactional per-account persistence. SQLite is development-only on ephemeral hosts."""
import json
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from config import STARTING_CASH

SCHEMA = [
 "CREATE TABLE IF NOT EXISTS accounts (user_id VARCHAR(128) PRIMARY KEY, state_json TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0)",
 "CREATE TABLE IF NOT EXISTS cycles (cycle_id VARCHAR(128) PRIMARY KEY, user_id VARCHAR(128) NOT NULL, created_at TEXT NOT NULL, report_json TEXT NOT NULL)",
 "CREATE TABLE IF NOT EXISTS snapshots (id VARCHAR(128) PRIMARY KEY, user_id VARCHAR(128) NOT NULL, recorded_at TEXT NOT NULL, profile VARCHAR(64) NOT NULL, tokens_json TEXT NOT NULL)",
 "CREATE TABLE IF NOT EXISTS decisions (id VARCHAR(128) PRIMARY KEY, user_id VARCHAR(128) NOT NULL, cycle_id VARCHAR(128) NOT NULL, time TEXT NOT NULL, address TEXT NOT NULL, decision TEXT NOT NULL, reason TEXT NOT NULL)",
]


def default_state():
    return {"cash": STARTING_CASH, "positions": {}, "trades": [], "equity_history": [],
            "day_start": {}, "last_cycle": None, "halted": False}


class Store:
    def __init__(self, url=None):
        url = url or os.environ.get("DATABASE_URL") or "sqlite:///paper_v15.db"
        if url.startswith("postgres://"): url = "postgresql+psycopg://" + url[len("postgres://"):]
        if url.startswith("postgresql://"): url = "postgresql+psycopg://" + url[len("postgresql://"):]
        self.durable = not url.startswith("sqlite:")
        self.engine = create_engine(url, pool_pre_ping=True)
        with self.engine.begin() as connection:
            for statement in SCHEMA: connection.execute(text(statement))

    def load(self, user_id):
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT state_json,version FROM accounts WHERE user_id=:u"), {"u": user_id}).first()
        return (json.loads(row[0]), row[1]) if row else (default_state(), None)

    def commit_cycle(self, user_id, expected_version, cycle_id, state, report, decisions, tokens=None, profile=None):
        """Optimistic concurrency: one cycle commits or none do; duplicate cycles rejected."""
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        with self.engine.begin() as conn:
            if expected_version is None:
                # Competing first-writers: insert only if account is absent.
                result = conn.execute(text("INSERT INTO accounts(user_id,state_json,version) VALUES (:u,:s,1) ON CONFLICT (user_id) DO NOTHING"), {"u": user_id, "s": json.dumps(state)})
            else:
                result = conn.execute(text("UPDATE accounts SET state_json=:s,version=version+1 WHERE user_id=:u AND version=:v"), {"s": json.dumps(state), "u": user_id, "v": expected_version})
            if result.rowcount != 1: raise RuntimeError("Concurrent update detected; refresh and retry")
            conn.execute(text("INSERT INTO cycles(cycle_id,user_id,created_at,report_json) VALUES(:id,:u,:t,:r)"),
                         {"id": cycle_id, "u": user_id, "t": now, "r": json.dumps(report)})
            for item in decisions:
                conn.execute(text("INSERT INTO decisions(id,user_id,cycle_id,time,address,decision,reason) VALUES(:id,:u,:c,:t,:a,:d,:r)"),
                             {"id": str(uuid.uuid4()), "u": user_id, "c": cycle_id, "t": now,
                              "a": item.get("address", ""), "d": item["decision"], "r": item["reason"]})
            if tokens is not None:
                conn.execute(text("INSERT INTO snapshots(id,user_id,recorded_at,profile,tokens_json) VALUES(:id,:u,:t,:p,:j)"),
                             {"id": str(uuid.uuid4()), "u": user_id, "t": now, "p": profile or "", "j": json.dumps(tokens)})

    def record_scan(self, user_id, tokens, profile):
        import uuid
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO snapshots(id,user_id,recorded_at,profile,tokens_json) VALUES(:id,:u,:t,:p,:j)"),
                         {"id": str(uuid.uuid4()), "u": user_id, "t": datetime.now(timezone.utc).isoformat(), "p": profile, "j": json.dumps(tokens)})

    def snapshots(self, user_id, limit=250):
        with self.engine.begin() as conn:
            rows = conn.execute(text("SELECT recorded_at,tokens_json FROM snapshots WHERE user_id=:u ORDER BY recorded_at DESC LIMIT :n"), {"u": user_id, "n": limit}).fetchall()
        return [(row[0], json.loads(row[1])) for row in reversed(rows)]

    def journal(self, user_id, limit=250):
        with self.engine.begin() as conn:
            rows = conn.execute(text("SELECT time,decision,address,reason FROM decisions WHERE user_id=:u ORDER BY time DESC LIMIT :n"), {"u": user_id, "n": limit}).fetchall()
        return [dict(zip(("time", "decision", "address", "reason"), row)) for row in rows]
