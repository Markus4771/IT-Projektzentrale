from __future__ import annotations

"""Version 1.9.0: Infrastrukturverwaltung für lokale Debian-Server."""

import json
import re
import shutil
import subprocess
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user
from app.v170 import app, local_snapshot

VERSION = "1.9.0"
base.VERSION = VERSION
app.version = VERSION

SERVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@:-]{0,119}(?:\.service)?$")
CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
ALLOWED_SERVICE_ACTIONS = {"start", "stop", "restart", "enable", "disable"}
ALLOWED_CONTAINER_ACTIONS = {"start", "stop", "restart"}


def init_infrastructure_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS infrastructure_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER,
            task_type TEXT NOT NULL,
            target TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'queued',
            output TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT,
            finished_at TEXT,
            FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE SET NULL,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS infrastructure_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER,
            severity TEXT NOT NULL,
            alert_key TEXT NOT NULL,
            title TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            UNIQUE(server_id, alert_key),
            FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_infra_tasks_created ON infrastructure_tasks(id DESC);
        CREATE INDEX IF NOT EXISTS idx_infra_alerts_active ON infrastructure_alerts(active,severity);
        """)


@app.on_event("startup")
def initialize_v190() -> None:
    init_infrastructure_db()


def _command(args: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def infrastructure_inventory() -> dict[str, Any]:
    services: list[dict[str, str]] = []
    result = _command(["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--no-pager"], 15)
    if result.returncode == 0:
        for line in result.stdout.splitlines()[:250]:
            parts = line.split(None, 4)
            if len(parts) >= 4:
                services.append({"name": parts[0], "load": parts[1], "active": parts[2], "sub": parts[3]})

    containers: list[dict[str, str]] = []
    images: list[dict[str, str]] = []
    if shutil.which("docker"):
        result = _command(["docker", "ps", "-a", "--format", "{{json .}}"], 15)
        if result.returncode == 0:
            for line in result.stdout.splitlines()[:250]:
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        result = _command(["docker", "images", "--format", "{{json .}}"], 15)
        if result.returncode == 0:
            for line in result.stdout.splitlines()[:250]:
                try:
                    images.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    mounts: list[dict[str, Any]] = []
    result = _command(["findmnt", "-J", "-o", "TARGET,SOURCE,FSTYPE,SIZE,USED,AVAIL,USE%"], 10)
    if result.returncode == 0:
        try:
            mounts = json.loads(result.stdout).get("filesystems", [])
        except json.JSONDecodeError:
            pass

    interfaces: list[dict[str, Any]] = []
    result = _command(["ip", "-j", "address"], 10)
    if result.returncode == 0:
        try:
            interfaces = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass

    packages: list[str] = []
    result = _command(["apt", "list", "--upgradable"], 20)
    if result.returncode == 0:
        packages = [line for line in result.stdout.splitlines() if "/" in line][:250]

    return {
        "snapshot": local_snapshot(),
        "services": services,
        "containers": containers,
        "images": images,
        "mounts": mounts,
        "interfaces": interfaces,
        "upgradable_packages": packages,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def refresh_alerts(server_id: int, inventory: dict[str, Any]) -> None:
    snapshot = inventory["snapshot"]
    alerts: dict[str, tuple[str, str, str]] = {}
    for key, label in (("cpu_percent", "CPU"), ("memory_percent", "RAM"), ("disk_percent", "Festplatte")):
        value = snapshot.get(key)
        if isinstance(value, (int, float)) and value >= 90:
            alerts[key] = ("critical", f"{label} kritisch", f"Aktuelle Auslastung: {value} %")
        elif isinstance(value, (int, float)) and value >= 80:
            alerts[key] = ("warning", f"{label} hoch", f"Aktuelle Auslastung: {value} %")
    updates = snapshot.get("package_updates")
    if isinstance(updates, int) and updates > 0:
        alerts["package_updates"] = ("warning", "Updates verfügbar", f"{updates} Debian-Pakete können aktualisiert werden")
    failed = [s["name"] for s in inventory["services"] if s.get("active") == "failed"]
    if failed:
        alerts["failed_services"] = ("critical", "Fehlgeschlagene Dienste", ", ".join(failed[:20]))

    with db() as conn:
        existing = {row["alert_key"] for row in conn.execute("SELECT alert_key FROM infrastructure_alerts WHERE server_id=? AND active=1", (server_id,))}
        for alert_key, (severity, title, details) in alerts.items():
            conn.execute("""INSERT INTO infrastructure_alerts(server_id,severity,alert_key,title,details,active)
                VALUES(?,?,?,?,?,1) ON CONFLICT(server_id,alert_key) DO UPDATE SET severity=excluded.severity,
                title=excluded.title,details=excluded.details,active=1,last_seen_at=CURRENT_TIMESTAMP,resolved_at=NULL""",
                (server_id, severity, alert_key, title, details))
        for alert_key in existing - set(alerts):
            conn.execute("UPDATE infrastructure_alerts SET active=0,resolved_at=CURRENT_TIMESTAMP WHERE server_id=? AND alert_key=?", (server_id, alert_key))


def _run_task(user_id: int, server_id: int, task_type: str, target: str, action: str, command: list[str]) -> int:
    with db() as conn:
        cursor = conn.execute("INSERT INTO infrastructure_tasks(server_id,task_type,target,action,state,created_by,started_at) VALUES(?,?,?,?, 'running',?,CURRENT_TIMESTAMP)",
                              (server_id, task_type, target, action, user_id))
        task_id = int(cursor.lastrowid)
    try:
        result = _command(command, 60)
        output = (result.stdout or "")[-10000:]
        error = (result.stderr or "")[-5000:]
        state = "succeeded" if result.returncode == 0 else "failed"
    except Exception as exc:
        output, error, state = "", str(exc), "failed"
    with db() as conn:
        conn.execute("UPDATE infrastructure_tasks SET state=?,output=?,error=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",
                     (state, output, error, task_id))
    audit("infrastructure.task", None, f"#{task_id} {task_type} {target} {action}: {state}")
    return task_id


@app.get("/infrastructure", response_class=HTMLResponse)
def infrastructure_page(request: Request, message: str = "", error: str = ""):
    require_user(request)
    init_infrastructure_db()
    with db() as conn:
        local_server = conn.execute("SELECT * FROM servers WHERE connection_type='local' ORDER BY id LIMIT 1").fetchone()
        tasks = conn.execute("SELECT * FROM infrastructure_tasks ORDER BY id DESC LIMIT 30").fetchall()
        alerts = conn.execute("SELECT * FROM infrastructure_alerts WHERE active=1 ORDER BY CASE severity WHEN 'critical' THEN 1 ELSE 2 END,id DESC").fetchall()
    inventory = infrastructure_inventory()
    if local_server:
        refresh_alerts(int(local_server["id"]), inventory)
        with db() as conn:
            alerts = conn.execute("SELECT * FROM infrastructure_alerts WHERE active=1 ORDER BY CASE severity WHEN 'critical' THEN 1 ELSE 2 END,id DESC").fetchall()
    return render("infrastructure.html", request, title="Infrastruktur", inventory=inventory,
                  local_server=local_server, tasks=tasks, alerts=alerts, message=message, error=error)


@app.post("/infrastructure/services/{service}/{action}")
def service_action(service: str, action: str, request: Request):
    user = require_admin(request)
    if action not in ALLOWED_SERVICE_ACTIONS or not SERVICE_RE.fullmatch(service):
        raise HTTPException(400, "Ungültige Dienstaktion")
    service = service if service.endswith(".service") else service + ".service"
    with db() as conn:
        server = conn.execute("SELECT id FROM servers WHERE connection_type='local' ORDER BY id LIMIT 1").fetchone()
    task_id = _run_task(int(user["id"]), int(server["id"]) if server else 0, "systemd", service, action,
                        ["sudo", str(base.SYSTEM_HELPER), "service", action, service])
    return RedirectResponse(f"/infrastructure?message=Aufgabe+%23{task_id}+abgeschlossen", 303)


@app.post("/infrastructure/docker/{container}/{action}")
def docker_action(container: str, action: str, request: Request):
    user = require_admin(request)
    if action not in ALLOWED_CONTAINER_ACTIONS or not CONTAINER_RE.fullmatch(container):
        raise HTTPException(400, "Ungültige Containeraktion")
    with db() as conn:
        server = conn.execute("SELECT id FROM servers WHERE connection_type='local' ORDER BY id LIMIT 1").fetchone()
    task_id = _run_task(int(user["id"]), int(server["id"]) if server else 0, "docker", container, action,
                        ["sudo", str(base.SYSTEM_HELPER), "docker", action, container])
    return RedirectResponse(f"/infrastructure?message=Aufgabe+%23{task_id}+abgeschlossen", 303)


@app.post("/infrastructure/packages/upgrade")
def package_upgrade(request: Request, mode: str = Form("safe")):
    user = require_admin(request)
    if mode not in {"safe", "security"}:
        raise HTTPException(400, "Ungültiger Updatemodus")
    with db() as conn:
        server = conn.execute("SELECT id FROM servers WHERE connection_type='local' ORDER BY id LIMIT 1").fetchone()
    task_id = _run_task(int(user["id"]), int(server["id"]) if server else 0, "packages", "apt", mode,
                        ["sudo", str(base.SYSTEM_HELPER), "apt-upgrade", mode])
    return RedirectResponse(f"/infrastructure?message=Update-Aufgabe+%23{task_id}+abgeschlossen", 303)


@app.get("/api/v1/infrastructure")
def infrastructure_api(request: Request):
    require_user(request)
    inventory = infrastructure_inventory()
    with db() as conn:
        inventory["alerts"] = [dict(row) for row in conn.execute("SELECT * FROM infrastructure_alerts WHERE active=1 ORDER BY id DESC")]
        inventory["tasks"] = [dict(row) for row in conn.execute("SELECT * FROM infrastructure_tasks ORDER BY id DESC LIMIT 30")]
    return inventory
