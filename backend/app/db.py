from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
    action_id TEXT PRIMARY KEY,
    run_id TEXT,
    service_id TEXT NOT NULL,
    action TEXT NOT NULL,
    requested_instances INTEGER,
    requested_size TEXT,
    status TEXT NOT NULL,
    error TEXT,
    requested_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS verifications (
    action_id TEXT PRIMARY KEY,
    run_id TEXT,
    status TEXT NOT NULL,
    verified INTEGER NOT NULL,
    summary TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT,
    result_json TEXT,
    input_source_json TEXT,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._ensure_columns()

    def _ensure_columns(self):
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(actions)").fetchall()}
        if "requested_size" not in columns:
            self._conn.execute("ALTER TABLE actions ADD COLUMN requested_size TEXT")
        run_columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(agent_runs)").fetchall()}
        if "result_json" not in run_columns:
            self._conn.execute("ALTER TABLE agent_runs ADD COLUMN result_json TEXT")
        if "input_source_json" not in run_columns:
            self._conn.execute("ALTER TABLE agent_runs ADD COLUMN input_source_json TEXT")
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()):
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    def log_event(self, run_id: str | None, event_type: str, payload: Any, created_at: str):
        self.execute(
            "INSERT INTO audit_events(run_id,event_type,payload,created_at) VALUES(?,?,?,?)",
            (run_id, event_type, json.dumps(payload, default=str), created_at),
        )

    def recent_audit(self, limit: int = 100):
        rows = self.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def save_run(self, run_id: str, provider: str, prompt: str, status: str, summary: str, created_at: str, result: Any = None, input_source: Any = None):
        self.execute(
            "INSERT OR REPLACE INTO agent_runs(run_id,provider,prompt,status,summary,result_json,input_source_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                run_id,
                provider,
                prompt,
                status,
                summary,
                json.dumps(result, default=str) if result is not None else None,
                json.dumps(input_source, default=str) if input_source is not None else None,
                created_at,
            ),
        )

    def save_action(self, execution: dict, run_id: str | None):
        self.execute(
            "INSERT OR REPLACE INTO actions(action_id,run_id,service_id,action,requested_instances,requested_size,status,error,requested_at,completed_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                execution["action_id"], run_id, execution["service_id"], execution["action"],
                execution.get("requested_instances"), execution.get("requested_size"), execution["status"],
                execution.get("error"), execution["requested_at"], execution.get("completed_at"),
            ),
        )

    def get_action(self, action_id: str):
        row = self.execute("SELECT * FROM actions WHERE action_id=?", (action_id,)).fetchone()
        return dict(row) if row else None

    def get_verification(self, action_id: str):
        row = self.execute("SELECT * FROM verifications WHERE action_id=?", (action_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["payload"] = json.loads(data["payload"])
        return data

    def save_verification(self, v: dict, run_id: str | None, created_at: str):
        self.execute(
            "INSERT OR REPLACE INTO verifications(action_id,run_id,status,verified,summary,payload,created_at) VALUES(?,?,?,?,?,?,?)",
            (v["action_id"], run_id, v["status"], int(v["verified"]), v["summary"], json.dumps(v, default=str), created_at),
        )

    def get_run(self, run_id: str):
        row = self.execute("SELECT * FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        for field in ("result_json", "input_source_json"):
            if data.get(field):
                data[field] = json.loads(data[field])
        return data
