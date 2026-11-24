"""Append-only trade ledger: SQLite with a hash chain so entries can't be quietly edited."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
"""


def _hash(prev: str, ts: int, kind: str, payload: str) -> str:
    return hashlib.sha256(f"{prev}|{ts}|{kind}|{payload}".encode()).hexdigest()


class Ledger:
    def __init__(self, path: str | Path = "guardrail.db") -> None:
        self.path = str(path)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)

    def append(self, kind: str, **payload) -> str:
        body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        ts = int(time.time())
        prev = self.db.execute("SELECT hash FROM entries ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = prev[0] if prev else "genesis"
        h = _hash(prev_hash, ts, kind, body)
        self.db.execute(
            "INSERT INTO entries (ts, kind, payload, prev_hash, hash) VALUES (?,?,?,?,?)",
            (ts, kind, body, prev_hash, h),
        )
        self.db.commit()
        return h

    def verify(self) -> bool:
        prev = "genesis"
        for ts, kind, payload, prev_hash, h in self.db.execute(
            "SELECT ts, kind, payload, prev_hash, hash FROM entries ORDER BY id"
        ):
            if prev_hash != prev or _hash(prev, ts, kind, payload) != h:
                return False
            prev = h
        return True

    def entries(self) -> list[dict]:
        rows = self.db.execute("SELECT ts, kind, payload, hash FROM entries ORDER BY id").fetchall()
        return [{"ts": r[0], "kind": r[1], **json.loads(r[2]), "hash": r[3]} for r in rows]
