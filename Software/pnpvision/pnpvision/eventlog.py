"""Append-only SQLite event log. Collect now, analyse later (separate script / dashboard)."""
import json
import sqlite3
import time
import uuid


class EventLog:
    def __init__(self, path="pnp_events.sqlite", run_id=None):
        self.db = sqlite3.connect(path)
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.db.execute("""CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY, ts REAL, run_id TEXT, event TEXT, ok INTEGER, data TEXT)""")
        self.db.commit()

    def log(self, event, ok=None, ts=None, **data):
        """event: 'pick' | 'inspect' | 'place' | 'reject' | ...  ok: True/False/None"""
        self.db.execute("INSERT INTO events(ts,run_id,event,ok,data) VALUES(?,?,?,?,?)",
                        (ts or time.time(), self.run_id, event,
                         None if ok is None else int(ok), json.dumps(data)))
        self.db.commit()

    def cph(self, run_id=None):
        """Components per hour from successful 'place' events in a run."""
        rid = run_id or self.run_id
        rows = self.db.execute("SELECT ts FROM events WHERE run_id=? AND event='place' AND ok=1 "
                               "ORDER BY ts", (rid,)).fetchall()
        if len(rows) < 2:
            return None
        return (len(rows) - 1) / (rows[-1][0] - rows[0][0]) * 3600.0

    def summary(self, run_id=None):
        rid = run_id or self.run_id
        out = {}
        for ev, ok, n in self.db.execute(
                "SELECT event, ok, COUNT(*) FROM events WHERE run_id=? GROUP BY event, ok", (rid,)):
            out[f"{ev}:{ok}"] = n
        return out
