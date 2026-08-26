"""Local SQLite-backed server for The Edwards Experience tracker."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "one_on_ones.db"

SEED_EMPLOYEES = [
    ("jordan", "Jordan Lee", "Product Designer", "weekly", "2026-08-25", 0),
    ("maya", "Maya Chen", "Software Engineer", "biweekly", "2026-08-27", 1),
    ("elena", "Elena Ruiz", "Customer Success", "weekly", "2026-08-31", 2),
    ("sam", "Sam Wright", "Data Analyst", "biweekly", "2026-09-02", 3),
]
SEED_SESSIONS = [
    ("s1", "jordan", "2026-08-18", "Reviewed the onboarding flow research. Jordan is excited to test a simpler first-run experience with the new cohort."),
    ("s2", "maya", "2026-08-13", "Talked through the API migration plan and where Maya would like more support from the platform team."),
    ("s3", "elena", "2026-08-24", "Celebrated a strong renewal month. Discussed setting clearer expectations with two newer accounts."),
]
SEED_ACTIONS = [
    ("a1", "jordan", "Share first-run research plan with the team", "employee", "2026-08-25", 0, None),
    ("a2", "maya", "Connect Maya with the platform API owner", "manager", "2026-08-27", 0, None),
    ("a3", "elena", "Draft a template for account expectation setting", "employee", "2026-08-31", 0, None),
    ("a4", "sam", "Review Q3 dashboard priorities", "employee", "2026-08-20", 1, None),
]


def connect():
    database = sqlite3.connect(DATABASE)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")
    return database


def setup_database():
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS employees (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL DEFAULT '',
              cadence TEXT NOT NULL CHECK(cadence IN ('weekly', 'biweekly')),
              next_meeting TEXT NOT NULL, color INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY, employee_id TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
              meeting_date TEXT NOT NULL, notes TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS actions (
              id TEXT PRIMARY KEY, employee_id TEXT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
              text TEXT NOT NULL, owner TEXT NOT NULL CHECK(owner IN ('employee', 'manager')),
              due_date TEXT, done INTEGER NOT NULL DEFAULT 0, created_session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS discussion_points (
              id TEXT PRIMARY KEY, employee_id TEXT REFERENCES employees(id) ON DELETE CASCADE,
              text TEXT NOT NULL, shared_group TEXT, done INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        columns = {column[1] for column in db.execute("PRAGMA table_info(discussion_points)")}
        if "shared_group" not in columns:
            db.execute("ALTER TABLE discussion_points ADD COLUMN shared_group TEXT")
        if not db.execute("SELECT 1 FROM employees LIMIT 1").fetchone():
            db.executemany("INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?)", SEED_EMPLOYEES)
            db.executemany("INSERT INTO sessions (id, employee_id, meeting_date, notes) VALUES (?, ?, ?, ?)", SEED_SESSIONS)
            db.executemany("INSERT INTO actions VALUES (?, ?, ?, ?, ?, ?, ?)", SEED_ACTIONS)


def state():
    with connect() as db:
        employees = [dict(row) for row in db.execute("SELECT id, name, role, cadence, next_meeting AS next, color FROM employees ORDER BY name")]
        sessions = [dict(row) for row in db.execute("SELECT id, employee_id AS employeeId, meeting_date AS date, notes FROM sessions")]
        actions = [dict(row) for row in db.execute("SELECT id, employee_id AS employeeId, text, owner, due_date AS due, done, created_session_id AS createdAt FROM actions")]
        discussion_points = [dict(row) for row in db.execute("SELECT id, employee_id AS employeeId, text, shared_group AS sharedGroup, done FROM discussion_points ORDER BY created_at DESC")]
    for action in actions:
        action["done"] = bool(action["done"])
    for point in discussion_points:
        point["done"] = bool(point["done"])
    return {"employees": employees, "sessions": sessions, "actions": actions, "discussionPoints": discussion_points}


def reset_database():
    with connect() as db:
        db.execute("DELETE FROM actions")
        db.execute("DELETE FROM discussion_points")
        db.execute("DELETE FROM sessions")
        db.execute("DELETE FROM employees")
        db.executemany("INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?)", SEED_EMPLOYEES)
        db.executemany("INSERT INTO sessions (id, employee_id, meeting_date, notes) VALUES (?, ?, ?, ?)", SEED_SESSIONS)
        db.executemany("INSERT INTO actions VALUES (?, ?, ?, ?, ?, ?, ?)", SEED_ACTIONS)


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, content, status=HTTPStatus.OK):
        payload = json.dumps(content).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def body(self):
        size = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(size) or b"{}")

    def do_GET(self):
        if urlparse(self.path).path == "/api/state":
            return self.send_json(state())
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self.body()
            if path == "/api/employees":
                employee_id = f"e{int(datetime.now().timestamp() * 1000)}"
                with connect() as db:
                    db.execute("INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?)", (
                        employee_id, payload["name"].strip(), payload.get("role", "").strip(), payload["cadence"],
                        date.today().isoformat(), payload.get("color", 0),
                    ))
            elif path == "/api/sessions":
                session_id = f"s{int(datetime.now().timestamp() * 1000)}"
                with connect() as db:
                    employee = db.execute("SELECT cadence FROM employees WHERE id = ?", (payload["employeeId"],)).fetchone()
                    if not employee:
                        raise ValueError("Employee not found")
                    db.execute("INSERT INTO sessions (id, employee_id, meeting_date, notes) VALUES (?, ?, ?, ?)", (session_id, payload["employeeId"], payload["date"], payload["notes"].strip()))
                    if payload.get("actionText", "").strip():
                        db.execute("INSERT INTO actions VALUES (?, ?, ?, ?, ?, 0, ?)", (f"a{int(datetime.now().timestamp() * 1000)}", payload["employeeId"], payload["actionText"].strip(), payload["owner"], payload.get("dueDate") or None, session_id))
                    next_date = datetime.strptime(payload["date"], "%Y-%m-%d").date() + timedelta(days=7 if employee["cadence"] == "weekly" else 14)
                    db.execute("UPDATE employees SET next_meeting = ? WHERE id = ?", (next_date.isoformat(), payload["employeeId"]))
            elif path == "/api/reset":
                reset_database()
            elif path == "/api/discussion-points":
                employee_id = payload.get("employeeId") or None
                point_text = payload["text"].strip()
                stamp = int(datetime.now().timestamp() * 1000)
                if employee_id:
                    if not db.execute("SELECT 1 FROM employees WHERE id = ?", (employee_id,)).fetchone():
                        raise ValueError("Employee not found")
                    db.execute("INSERT INTO discussion_points (id, employee_id, text) VALUES (?, ?, ?)", (f"d{stamp}", employee_id, point_text))
                else:
                    employees = db.execute("SELECT id FROM employees ORDER BY name").fetchall()
                    if not employees:
                        raise ValueError("Add an employee before adding a shared discussion point")
                    shared_group = f"g{stamp}"
                    db.executemany("INSERT INTO discussion_points (id, employee_id, text, shared_group) VALUES (?, ?, ?, ?)", [(f"d{stamp}{index}", row["id"], point_text, shared_group) for index, row in enumerate(employees)])
            else:
                return self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return self.send_json(state(), HTTPStatus.CREATED)
        except (KeyError, ValueError, json.JSONDecodeError) as error:
            return self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    def do_PATCH(self):
        path = urlparse(self.path).path
        try:
            payload = self.body()
            with connect() as db:
                if path == "/api/employees":
                    cadence = payload["cadence"]
                    if cadence not in ("weekly", "biweekly"):
                        raise ValueError("Cadence must be weekly or biweekly")
                    result = db.execute(
                        "UPDATE employees SET name = ?, role = ?, cadence = ?, next_meeting = ? WHERE id = ?",
                        (payload["name"].strip(), payload.get("role", "").strip(), cadence, payload["next"], payload["id"]),
                    )
                    if result.rowcount == 0:
                        return self.send_json({"error": "Employee not found"}, HTTPStatus.NOT_FOUND)
                elif path in ("/api/actions", "/api/discussion-points"):
                    table = "actions" if path == "/api/actions" else "discussion_points"
                    db.execute(f"UPDATE {table} SET done = ? WHERE id = ?", (int(bool(payload["done"])), payload["id"]))
                else:
                    return self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return self.send_json(state())
        except (KeyError, ValueError, json.JSONDecodeError) as error:
            return self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    def do_DELETE(self):
        prefix = "/api/employees/"
        path = urlparse(self.path).path
        if not path.startswith(prefix) or not path[len(prefix):]:
            return self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        employee_id = path[len(prefix):]
        with connect() as db:
            result = db.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
            if result.rowcount == 0:
                return self.send_json({"error": "Employee not found"}, HTTPStatus.NOT_FOUND)
        return self.send_json(state())


if __name__ == "__main__":
    setup_database()
    print(f"The Edwards Experience is running at http://127.0.0.1:4173 (database: {DATABASE.name})")
    ThreadingHTTPServer(("127.0.0.1", 4173), AppHandler).serve_forever()
