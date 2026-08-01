from __future__ import annotations

"""Version 3.5.0: Manifestgesteuerte Installation, Freigaben und Rollback-Planung."""

import json
from typing import Any

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user
from app.v330 import _download_asset
from app.v340 import app

VERSION = "3.5.0"
base.VERSION = VERSION
app.version = VERSION

DANGEROUS_PERMISSIONS = {"systemd", "docker", "compose", "database-write", "filesystem-write"}


def init_manifest_installation_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS manifest_install_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manifest_id INTEGER NOT NULL,
            asset_id INTEGER,
            project_id INTEGER,
            state TEXT NOT NULL DEFAULT 'draft',
            requested_permissions TEXT NOT NULL DEFAULT '[]',
            approved_permissions TEXT NOT NULL DEFAULT '[]',
            dependency_plan TEXT NOT NULL DEFAULT '[]',
            health_type TEXT NOT NULL DEFAULT '',
            health_target TEXT NOT NULL DEFAULT '',
            rollback_enabled INTEGER NOT NULL DEFAULT 1,
            created_by INTEGER,
            approved_by INTEGER,
            installation_job_id INTEGER,
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            approved_at TEXT,
            queued_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(manifest_id) REFERENCES project_manifests(id) ON DELETE CASCADE,
            FOREIGN KEY(asset_id) REFERENCES project_release_assets(id) ON DELETE SET NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
            FOREIGN KEY(installation_job_id) REFERENCES installation_jobs(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_manifest_plans_state ON manifest_install_plans(state,id DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_manifest_plan_active
            ON manifest_install_plans(manifest_id)
            WHERE state IN ('draft','approved','queued','running');
        """)


@app.on_event("startup")
def initialize_v350() -> None:
    init_manifest_installation_db()


def _manifest_row(manifest_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT * FROM project_manifests WHERE id=? AND enabled=1 AND valid=1", (manifest_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Aktives und gültiges Projektmanifest wurde nicht gefunden")
    result = dict(row)
    result["manifest"] = json.loads(result["manifest_json"])
    return result


def _dependency_plan(manifest_id: int) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute("""SELECT d.dependency_key,d.version_constraint,d.optional,
            m.id manifest_id,m.version,p.id project_id,p.version installed_version
            FROM project_manifest_dependencies d
            LEFT JOIN project_manifests m ON m.project_key=d.dependency_key AND m.enabled=1 AND m.valid=1
            LEFT JOIN projects p ON p.slug=d.dependency_key AND p.deleted_at IS NULL
            WHERE d.manifest_id=? ORDER BY d.optional,d.dependency_key""", (manifest_id,)).fetchall()
    plan = []
    for row in rows:
        item = dict(row)
        item["available"] = bool(item.get("manifest_id"))
        item["installed"] = bool(item.get("project_id"))
        item["blocking"] = not bool(item["optional"]) and not item["available"] and not item["installed"]
        plan.append(item)
    return plan


def _permissions(manifest_id: int) -> list[str]:
    with db() as conn:
        return [r["permission"] for r in conn.execute(
            "SELECT permission FROM project_manifest_permissions WHERE manifest_id=? ORDER BY permission", (manifest_id,)
        )]


def _best_asset(manifest_id: int) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute("""SELECT * FROM project_release_assets
            WHERE manifest_id=? AND state IN ('detected','downloaded')
            ORDER BY CASE state WHEN 'downloaded' THEN 0 ELSE 1 END,id DESC LIMIT 1""", (manifest_id,)).fetchone()
    return dict(row) if row else None


def _create_plan(manifest_id: int, user_id: int) -> int:
    manifest_row = _manifest_row(manifest_id)
    manifest = manifest_row["manifest"]
    dependencies = _dependency_plan(manifest_id)
    blocking = [d["dependency_key"] for d in dependencies if d["blocking"]]
    if blocking:
        raise HTTPException(409, "Nicht auflösbare Abhängigkeiten: " + ", ".join(blocking))
    permissions = _permissions(manifest_id)
    asset = _best_asset(manifest_id)
    if manifest.get("type") == "deb" and not asset:
        raise HTTPException(409, "Für dieses Debian-Projekt wurde noch kein Release-Asset erkannt")
    health = manifest.get("health") or {}
    with db() as conn:
        existing = conn.execute("SELECT id FROM manifest_install_plans WHERE manifest_id=? AND state IN ('draft','approved','queued','running')", (manifest_id,)).fetchone()
        if existing:
            return int(existing["id"])
        project = conn.execute("SELECT id FROM projects WHERE slug=? AND deleted_at IS NULL", (manifest["id"],)).fetchone()
        cursor = conn.execute("""INSERT INTO manifest_install_plans(
            manifest_id,asset_id,project_id,requested_permissions,dependency_plan,health_type,health_target,created_by)
            VALUES(?,?,?,?,?,?,?,?)""", (
            manifest_id, asset["id"] if asset else None, project["id"] if project else None,
            json.dumps(permissions), json.dumps(dependencies, ensure_ascii=False),
            str(health.get("type") or ""), str(health.get("url") or health.get("command") or "")[:1000], user_id,
        ))
    audit("manifest_install.plan_created", manifest_id, f"plan={cursor.lastrowid}")
    return int(cursor.lastrowid)


def _plan(plan_id: int) -> dict[str, Any]:
    with db() as conn:
        row = conn.execute("""SELECT p.*,m.project_key,m.name,m.version,m.project_type,m.manifest_json,
            a.asset_name,a.state asset_state,a.local_path
            FROM manifest_install_plans p JOIN project_manifests m ON m.id=p.manifest_id
            LEFT JOIN project_release_assets a ON a.id=p.asset_id WHERE p.id=?""", (plan_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Installationsplan wurde nicht gefunden")
    result = dict(row)
    for key in ("requested_permissions", "approved_permissions", "dependency_plan"):
        result[key] = json.loads(result[key] or "[]")
    return result


def _queue_plan(plan_id: int, user_id: int) -> int:
    plan = _plan(plan_id)
    if plan["state"] != "approved":
        raise HTTPException(409, "Der Installationsplan muss zuerst freigegeben werden")
    requested = set(plan["requested_permissions"])
    approved = set(plan["approved_permissions"])
    if requested - approved:
        raise HTTPException(409, "Nicht alle angeforderten Berechtigungen wurden freigegeben")
    package_file = plan.get("local_path") or ""
    if plan["project_type"] == "deb":
        if plan.get("asset_state") != "downloaded":
            package_file = str(_download_asset(int(plan["asset_id"])))
        if not package_file:
            raise HTTPException(409, "Debian-Paket konnte nicht bereitgestellt werden")
    with db() as conn:
        project = conn.execute("SELECT id FROM projects WHERE slug=? AND deleted_at IS NULL", (plan["project_key"],)).fetchone()
        if not project:
            manifest = json.loads(plan["manifest_json"])
            cursor = conn.execute("""INSERT INTO projects(name,slug,description,category,status,version,project_url,repo_url,package_name)
                VALUES(?,?,?,?,?,?,?,?,?)""", (manifest["name"],manifest["id"],manifest.get("description", ""),manifest.get("category", "Allgemein"),
                "Geplant",manifest["version"],manifest.get("homepage", ""),"",manifest.get("package", {}).get("name", "")))
            project_id = int(cursor.lastrowid)
        else:
            project_id = int(project["id"])
        duplicate = conn.execute("SELECT 1 FROM installation_jobs WHERE project_id=? AND state IN ('queued','running')", (project_id,)).fetchone()
        if duplicate:
            raise HTTPException(409, "Für dieses Projekt läuft bereits ein Installationsauftrag")
        cursor = conn.execute("""INSERT INTO installation_jobs(project_id,job_type,package_file,source,created_by,phase,target_version)
            VALUES(?,'install',?, ?,?,'queued',?)""", (project_id, package_file, f"manifest-plan:{plan_id}", user_id, plan["version"]))
        job_id = int(cursor.lastrowid)
        conn.execute("UPDATE manifest_install_plans SET state='queued',project_id=?,installation_job_id=?,queued_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?", (project_id, job_id, plan_id))
    audit("manifest_install.queued", project_id, f"plan={plan_id},job={job_id}")
    return job_id


def _summary() -> dict[str, Any]:
    with db() as conn:
        manifests = [dict(r) for r in conn.execute("""SELECT m.*,
            (SELECT state FROM manifest_install_plans p WHERE p.manifest_id=m.id ORDER BY p.id DESC LIMIT 1) plan_state
            FROM project_manifests m WHERE m.enabled=1 AND m.valid=1 ORDER BY m.name""")]
        plans = [dict(r) for r in conn.execute("""SELECT p.*,m.name,m.project_key,m.version,u.username created_by_name
            FROM manifest_install_plans p JOIN project_manifests m ON m.id=p.manifest_id
            LEFT JOIN users u ON u.id=p.created_by ORDER BY p.id DESC LIMIT 100""")]
    return {"manifests": manifests, "plans": plans}


@app.get("/manifest-installation", response_class=HTMLResponse)
def manifest_installation_page(request: Request, message: str = "", error: str = ""):
    require_user(request)
    return render("manifest_installation.html", request, title="Manifest-Installation", message=message, error=error, **_summary())


@app.post("/manifest-installation/manifests/{manifest_id}/plan")
def manifest_installation_plan(manifest_id: int, request: Request):
    user = require_admin(request)
    try:
        plan_id = _create_plan(manifest_id, int(user["id"]))
        return RedirectResponse(f"/manifest-installation/plans/{plan_id}", 303)
    except HTTPException as exc:
        return RedirectResponse("/manifest-installation?error=" + str(exc.detail).replace(" ", "+"), 303)


@app.get("/manifest-installation/plans/{plan_id}", response_class=HTMLResponse)
def manifest_installation_plan_page(plan_id: int, request: Request):
    require_user(request)
    return render("manifest_installation_plan.html", request, title=f"Installationsplan #{plan_id}", plan=_plan(plan_id), dangerous_permissions=DANGEROUS_PERMISSIONS)


@app.post("/manifest-installation/plans/{plan_id}/approve")
def approve_manifest_installation(plan_id: int, request: Request, approved_permissions: list[str] = Form(default=[])):
    user = require_admin(request)
    plan = _plan(plan_id)
    requested = set(plan["requested_permissions"])
    approved = set(approved_permissions)
    if not approved <= requested:
        raise HTTPException(400, "Unbekannte Berechtigungsfreigabe")
    if requested - approved:
        raise HTTPException(409, "Alle angeforderten Berechtigungen müssen ausdrücklich freigegeben werden")
    with db() as conn:
        conn.execute("UPDATE manifest_install_plans SET state='approved',approved_permissions=?,approved_by=?,approved_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=? AND state='draft'", (json.dumps(sorted(approved)), user["id"], plan_id))
    audit("manifest_install.approved", plan["manifest_id"], f"plan={plan_id}")
    return RedirectResponse(f"/manifest-installation/plans/{plan_id}", 303)


@app.post("/manifest-installation/plans/{plan_id}/queue")
def queue_manifest_installation(plan_id: int, request: Request):
    user = require_admin(request)
    job_id = _queue_plan(plan_id, int(user["id"]))
    return RedirectResponse(f"/installation/jobs/{job_id}", 303)


@app.get("/api/v1/manifest-installation")
def manifest_installation_api(request: Request):
    require_user(request)
    summary = _summary()
    return {"version": VERSION, "manifests": summary["manifests"], "plans": summary["plans"]}
