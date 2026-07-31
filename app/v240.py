from __future__ import annotations

"""Version 2.4.0: Monitoring, Alarmregeln und Benachrichtigungen."""

import json
import re
import urllib.parse
from datetime import datetime, timezone

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user
from app.v230 import app

VERSION = "2.4.0"
base.VERSION = VERSION
app.version = VERSION
METRICS = {"cpu_percent", "memory_percent", "disk_percent", "package_updates", "availability"}
OPERATORS = {">", ">=", "<", "<=", "=="}
CHANNELS = {"none", "webhook", "email"}


def init_monitoring_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS monitoring_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            server_id INTEGER,
            metric TEXT NOT NULL,
            operator TEXT NOT NULL,
            threshold REAL NOT NULL,
            severity TEXT NOT NULL DEFAULT 'warning',
            consecutive_failures INTEGER NOT NULL DEFAULT 2,
            enabled INTEGER NOT NULL DEFAULT 1,
            notification_channel TEXT NOT NULL DEFAULT 'none',
            notification_target TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS monitoring_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER NOT NULL,
            server_id INTEGER,
            state TEXT NOT NULL DEFAULT 'open',
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            observed_value REAL,
            opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            acknowledged_at TEXT,
            acknowledged_by INTEGER,
            resolved_at TEXT,
            last_notification_at TEXT,
            FOREIGN KEY(rule_id) REFERENCES monitoring_rules(id) ON DELETE CASCADE,
            FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE,
            FOREIGN KEY(acknowledged_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS monitoring_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER,
            status TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS maintenance_windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            server_id INTEGER,
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_monitoring_alerts_state ON monitoring_alerts(state,updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_monitoring_runs_server ON monitoring_runs(server_id,id DESC);
        """)


@app.on_event("startup")
def initialize_v240() -> None:
    init_monitoring_db()


@app.get("/monitoring", response_class=HTMLResponse)
def monitoring_page(request: Request, message: str = "", error: str = ""):
    require_user(request)
    with db() as conn:
        servers = [dict(r) for r in conn.execute("SELECT id,name,hostname,last_status FROM servers ORDER BY name")]
        rules = [dict(r) for r in conn.execute("""SELECT r.*,s.name server_name FROM monitoring_rules r LEFT JOIN servers s ON s.id=r.server_id ORDER BY r.enabled DESC,r.name""")]
        alerts = [dict(r) for r in conn.execute("""SELECT a.*,r.name rule_name,s.name server_name,u.username acknowledged_by_name FROM monitoring_alerts a JOIN monitoring_rules r ON r.id=a.rule_id LEFT JOIN servers s ON s.id=a.server_id LEFT JOIN users u ON u.id=a.acknowledged_by ORDER BY CASE a.state WHEN 'open' THEN 0 WHEN 'acknowledged' THEN 1 ELSE 2 END,a.updated_at DESC LIMIT 200""")]
        windows = [dict(r) for r in conn.execute("""SELECT w.*,s.name server_name FROM maintenance_windows w LEFT JOIN servers s ON s.id=w.server_id WHERE datetime(w.ends_at)>=datetime('now') ORDER BY w.starts_at""")]
        runs = [dict(r) for r in conn.execute("""SELECT m.*,s.name server_name FROM monitoring_runs m LEFT JOIN servers s ON s.id=m.server_id ORDER BY m.id DESC LIMIT 100""")]
    return render("monitoring.html", request, title="Monitoring", servers=servers, rules=rules, alerts=alerts, windows=windows, runs=runs, metrics=sorted(METRICS), message=message, error=error)


@app.post("/monitoring/rules/add")
def monitoring_rule_add(request: Request, name: str = Form(...), server_id: str = Form(""), metric: str = Form(...), operator: str = Form(...), threshold: float = Form(...), severity: str = Form("warning"), consecutive_failures: int = Form(2), notification_channel: str = Form("none"), notification_target: str = Form("")):
    require_admin(request)
    if metric not in METRICS or operator not in OPERATORS or notification_channel not in CHANNELS:
        raise HTTPException(400, "Ungültige Alarmregel")
    if severity not in {"info", "warning", "critical"}:
        severity = "warning"
    target_server = int(server_id) if server_id.isdigit() else None
    failures = max(1, min(20, consecutive_failures))
    if notification_channel == "webhook" and not re.match(r"^https://", notification_target.strip()):
        return RedirectResponse("/monitoring?error=Webhook+muss+HTTPS+verwenden", 303)
    with db() as conn:
        conn.execute("INSERT INTO monitoring_rules(name,server_id,metric,operator,threshold,severity,consecutive_failures,notification_channel,notification_target) VALUES(?,?,?,?,?,?,?,?,?)", (name.strip()[:120], target_server, metric, operator, threshold, severity, failures, notification_channel, notification_target.strip()[:500]))
    audit("monitoring.rule_added", target_server, name[:120])
    return RedirectResponse("/monitoring?message=Alarmregel+wurde+angelegt", 303)


@app.post("/monitoring/rules/{rule_id}/toggle")
def monitoring_rule_toggle(rule_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        conn.execute("UPDATE monitoring_rules SET enabled=CASE enabled WHEN 1 THEN 0 ELSE 1 END,updated_at=CURRENT_TIMESTAMP WHERE id=?", (rule_id,))
    return RedirectResponse("/monitoring?message=Alarmregel+wurde+geändert", 303)


@app.post("/monitoring/alerts/{alert_id}/ack")
def monitoring_alert_ack(alert_id: int, request: Request):
    user = require_admin(request)
    with db() as conn:
        conn.execute("UPDATE monitoring_alerts SET state='acknowledged',acknowledged_at=CURRENT_TIMESTAMP,acknowledged_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND state='open'", (user["id"], alert_id))
    audit("monitoring.alert_acknowledged", alert_id, user["username"])
    return RedirectResponse("/monitoring?message=Alarm+wurde+bestätigt", 303)


@app.post("/monitoring/windows/add")
def monitoring_window_add(request: Request, name: str = Form(...), server_id: str = Form(""), starts_at: str = Form(...), ends_at: str = Form(...), reason: str = Form("")):
    user = require_admin(request)
    try:
        start = datetime.fromisoformat(starts_at)
        end = datetime.fromisoformat(ends_at)
    except ValueError as exc:
        raise HTTPException(400, "Ungültiger Zeitraum") from exc
    if end <= start:
        raise HTTPException(400, "Das Ende muss nach dem Beginn liegen")
    target_server = int(server_id) if server_id.isdigit() else None
    with db() as conn:
        conn.execute("INSERT INTO maintenance_windows(name,server_id,starts_at,ends_at,reason,created_by) VALUES(?,?,?,?,?,?)", (name.strip()[:120], target_server, start.isoformat(), end.isoformat(), reason.strip()[:1000], user["id"]))
    audit("monitoring.maintenance_window", target_server, name[:120])
    return RedirectResponse("/monitoring?message=Wartungsfenster+wurde+angelegt", 303)


@app.get("/api/v1/monitoring")
def monitoring_api(request: Request):
    require_user(request)
    with db() as conn:
        rules = [dict(r) for r in conn.execute("SELECT * FROM monitoring_rules ORDER BY id")]
        alerts = [dict(r) for r in conn.execute("SELECT * FROM monitoring_alerts ORDER BY id DESC LIMIT 200")]
        runs = [dict(r) for r in conn.execute("SELECT * FROM monitoring_runs ORDER BY id DESC LIMIT 200")]
    return {"version": VERSION, "rules": rules, "alerts": alerts, "runs": runs}
