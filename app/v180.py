from __future__ import annotations

"""Version 1.8.0: zentrales Backup-, Restore- und Update-Center."""

import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Form, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

import app.main as base
from app.main import (
    BACKUP_DIR,
    DB_PATH,
    PACKAGE_DIR,
    STATE_DIR,
    audit,
    db,
    download_asset,
    installed_version,
    latest_deb_asset,
    package_metadata,
    render,
    require_admin,
    require_user,
    run_helper,
    version_is_newer,
)
from app.v170 import app

VERSION = "1.8.0"
base.VERSION = VERSION
app.version = VERSION
MAX_RESTORE_BYTES = 2 * 1024 * 1024 * 1024
BACKUP_KINDS = {"platform", "project", "database"}


def init_maintenance_db() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS backup_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                project_id INTEGER,
                kind TEXT NOT NULL DEFAULT 'platform',
                schedule TEXT NOT NULL DEFAULT 'manual',
                retention_count INTEGER NOT NULL DEFAULT 10,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_run_at TEXT,
                next_run_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS maintenance_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                project_id INTEGER,
                state TEXT NOT NULL DEFAULT 'queued',
                progress INTEGER NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                result_json TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT '',
                created_by INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                finished_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
                FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS backup_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER,
                project_id INTEGER,
                kind TEXT NOT NULL,
                filename TEXT NOT NULL UNIQUE,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'ready',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(plan_id) REFERENCES backup_plans(id) ON DELETE SET NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_maintenance_jobs_created ON maintenance_jobs(id DESC);
            CREATE INDEX IF NOT EXISTS idx_backup_artifacts_created ON backup_artifacts(id DESC);
            """
        )


@app.on_event("startup")
def initialize_v180() -> None:
    init_maintenance_db()


def _job(job_type: str, user_id: int, project_id: int | None = None) -> int:
    with db() as conn:
        cursor = conn.execute(
            "INSERT INTO maintenance_jobs(job_type,project_id,created_by) VALUES(?,?,?)",
            (job_type, project_id, user_id),
        )
        return int(cursor.lastrowid)


def _job_update(job_id: int, state: str, progress: int, message: str = "", *, result: dict | None = None, error: str = "") -> None:
    with db() as conn:
        conn.execute(
            """UPDATE maintenance_jobs SET state=?,progress=?,message=?,result_json=?,error=?,
               started_at=CASE WHEN ?='running' AND started_at IS NULL THEN CURRENT_TIMESTAMP ELSE started_at END,
               finished_at=CASE WHEN ? IN ('succeeded','failed','cancelled') THEN CURRENT_TIMESTAMP ELSE finished_at END
               WHERE id=?""",
            (state, max(0, min(100, progress)), message[:500], json.dumps(result or {}, ensure_ascii=False), error[:2000], state, state, job_id),
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_backup_name(kind: str, project_slug: str = "") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = f"-{project_slug}" if project_slug else ""
    return f"itpz-{kind}{suffix}-{stamp}.tar.gz"


def _database_copy(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(DB_PATH)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def create_backup(kind: str, project_id: int | None, plan_id: int | None, job_id: int) -> dict[str, Any]:
    if kind not in BACKUP_KINDS:
        raise ValueError("Unbekannte Sicherungsart")
    project = None
    if project_id:
        with db() as conn:
            project = conn.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
        if not project:
            raise ValueError("Projekt nicht gefunden")
    slug = project["slug"] if project else ""
    filename = _safe_backup_name(kind, slug)
    final_path = BACKUP_DIR / filename
    temporary = BACKUP_DIR / (filename + ".tmp")
    staging = BACKUP_DIR / (filename + ".work")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(mode=0o750)
    try:
        _job_update(job_id, "running", 15, "Datenbank wird konsistent kopiert")
        _database_copy(staging / "projektzentrale.db")
        metadata = {
            "format": "itpz-backup-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "application_version": VERSION,
            "kind": kind,
            "project": dict(project) if project else None,
        }
        (staging / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        if kind == "platform":
            _job_update(job_id, "running", 40, "Plattformdaten werden gesammelt")
            for directory in ("uploads", "exports"):
                source = STATE_DIR / directory
                if source.exists():
                    shutil.copytree(source, staging / directory, dirs_exist_ok=True)
        elif kind == "project" and project:
            _job_update(job_id, "running", 40, "Projektmetadaten werden gesichert")
            with db() as conn:
                payload = {
                    "project": dict(project),
                    "services": [dict(row) for row in conn.execute("SELECT * FROM project_services WHERE project_id=?", (project_id,))],
                    "source": [dict(row) for row in conn.execute("SELECT * FROM package_sources WHERE project_id=?", (project_id,))],
                    "packages": [dict(row) for row in conn.execute("SELECT * FROM packages WHERE project_id=?", (project_id,))],
                }
            (staging / "project.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _job_update(job_id, "running", 70, "Archiv wird erstellt")
        with tarfile.open(temporary, "w:gz") as archive:
            for item in staging.iterdir():
                archive.add(item, arcname=item.name, recursive=True)
        temporary.replace(final_path)
        digest = _sha256(final_path)
        with db() as conn:
            cursor = conn.execute(
                """INSERT INTO backup_artifacts(plan_id,project_id,kind,filename,sha256,size_bytes,metadata_json)
                   VALUES(?,?,?,?,?,?,?)""",
                (plan_id, project_id, kind, filename, digest, final_path.stat().st_size, json.dumps(metadata, ensure_ascii=False)),
            )
            artifact_id = int(cursor.lastrowid)
            if plan_id:
                conn.execute("UPDATE backup_plans SET last_run_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?", (plan_id,))
        return {"artifact_id": artifact_id, "filename": filename, "sha256": digest, "size_bytes": final_path.stat().st_size}
    finally:
        temporary.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)


def _prune(plan_id: int, retention: int) -> None:
    if retention < 1:
        return
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM backup_artifacts WHERE plan_id=? ORDER BY id DESC LIMIT -1 OFFSET ?",
            (plan_id, retention),
        ).fetchall()
        for row in rows:
            (BACKUP_DIR / Path(row["filename"]).name).unlink(missing_ok=True)
            conn.execute("DELETE FROM backup_artifacts WHERE id=?", (row["id"],))


def _validate_restore_archive(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_RESTORE_BYTES:
        raise ValueError("Sicherungsdatei ist zu groß")
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 10000:
            raise ValueError("Sicherungsarchiv enthält zu viele Dateien")
        for member in members:
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts or member.issym() or member.islnk():
                raise ValueError("Sicherungsarchiv enthält unsichere Pfade")
        metadata_member = archive.getmember("metadata.json")
        extracted = archive.extractfile(metadata_member)
        if not extracted:
            raise ValueError("Metadaten fehlen")
        metadata = json.loads(extracted.read(1024 * 1024).decode("utf-8"))
    if metadata.get("format") != "itpz-backup-v1":
        raise ValueError("Unbekanntes Sicherungsformat")
    return metadata


@app.get("/maintenance", response_class=HTMLResponse)
def maintenance_page(request: Request, message: str = "", error: str = ""):
    require_user(request)
    with db() as conn:
        plans = conn.execute("SELECT bp.*,p.name project_name FROM backup_plans bp LEFT JOIN projects p ON p.id=bp.project_id ORDER BY bp.name").fetchall()
        artifacts = conn.execute("SELECT ba.*,p.name project_name FROM backup_artifacts ba LEFT JOIN projects p ON p.id=ba.project_id ORDER BY ba.id DESC LIMIT 40").fetchall()
        jobs = conn.execute("SELECT mj.*,p.name project_name FROM maintenance_jobs mj LEFT JOIN projects p ON p.id=mj.project_id ORDER BY mj.id DESC LIMIT 40").fetchall()
        projects = conn.execute("SELECT id,name,slug,package_name FROM projects WHERE deleted_at IS NULL AND archived=0 ORDER BY name").fetchall()
        updates = conn.execute(
            """SELECT p.id,p.name,p.package_name,
               (SELECT version FROM packages x WHERE x.project_id=p.id ORDER BY x.id DESC LIMIT 1) latest_version
               FROM projects p WHERE p.deleted_at IS NULL AND p.archived=0 ORDER BY p.name"""
        ).fetchall()
    update_rows = []
    for row in updates:
        item = dict(row)
        item["installed_version"] = installed_version(row["package_name"])
        item["update_available"] = version_is_newer(row["latest_version"], item["installed_version"])
        update_rows.append(item)
    return render("maintenance.html", request, title="Backup & Updates", plans=plans, artifacts=artifacts, jobs=jobs, projects=projects, updates=update_rows, message=message, error=error)


@app.post("/maintenance/backups/create")
def backup_now(request: Request, kind: str = Form("platform"), project_id: int | None = Form(None)):
    user = require_admin(request)
    if kind != "project":
        project_id = None
    job_id = _job("backup.create", user["id"], project_id)
    try:
        result = create_backup(kind, project_id, None, job_id)
        _job_update(job_id, "succeeded", 100, "Sicherung erfolgreich", result=result)
        audit("backup.created", project_id, result["filename"])
        return RedirectResponse("/maintenance?message=Sicherung+wurde+erstellt", 303)
    except Exception as exc:
        _job_update(job_id, "failed", 100, "Sicherung fehlgeschlagen", error=str(exc))
        return RedirectResponse("/maintenance?error=" + urllib.parse.quote(str(exc)[:900]), 303)


@app.post("/maintenance/plans/add")
def add_backup_plan(request: Request, name: str = Form(...), kind: str = Form("platform"), project_id: int | None = Form(None), schedule: str = Form("daily"), retention_count: int = Form(10)):
    require_admin(request)
    if kind not in BACKUP_KINDS:
        raise HTTPException(400, "Ungültige Sicherungsart")
    if schedule not in {"manual", "daily", "weekly", "monthly"}:
        raise HTTPException(400, "Ungültiger Zeitplan")
    if kind != "project":
        project_id = None
    with db() as conn:
        conn.execute(
            "INSERT INTO backup_plans(name,project_id,kind,schedule,retention_count) VALUES(?,?,?,?,?)",
            (name.strip()[:120], project_id, kind, schedule, max(1, min(365, retention_count))),
        )
    return RedirectResponse("/maintenance?message=Sicherungsplan+wurde+angelegt", 303)


@app.post("/maintenance/plans/{plan_id}/run")
def run_backup_plan(plan_id: int, request: Request):
    user = require_admin(request)
    with db() as conn:
        plan = conn.execute("SELECT * FROM backup_plans WHERE id=? AND enabled=1", (plan_id,)).fetchone()
    if not plan:
        raise HTTPException(404, "Sicherungsplan nicht gefunden")
    job_id = _job("backup.plan.run", user["id"], plan["project_id"])
    try:
        result = create_backup(plan["kind"], plan["project_id"], plan_id, job_id)
        _prune(plan_id, int(plan["retention_count"]))
        _job_update(job_id, "succeeded", 100, "Sicherungsplan erfolgreich", result=result)
        return RedirectResponse("/maintenance?message=Sicherungsplan+wurde+ausgeführt", 303)
    except Exception as exc:
        _job_update(job_id, "failed", 100, "Sicherungsplan fehlgeschlagen", error=str(exc))
        return RedirectResponse("/maintenance?error=" + urllib.parse.quote(str(exc)[:900]), 303)


@app.get("/maintenance/backups/{artifact_id}/download")
def download_backup(artifact_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        artifact = conn.execute("SELECT * FROM backup_artifacts WHERE id=?", (artifact_id,)).fetchone()
    if not artifact:
        raise HTTPException(404, "Sicherung nicht gefunden")
    path = BACKUP_DIR / Path(artifact["filename"]).name
    if not path.is_file() or _sha256(path) != artifact["sha256"]:
        raise HTTPException(409, "Sicherungsdatei fehlt oder Prüfsumme stimmt nicht")
    return FileResponse(path, filename=artifact["filename"], media_type="application/gzip")


@app.post("/maintenance/restore/validate")
async def validate_restore(request: Request, backup: UploadFile = File(...)):
    require_admin(request)
    name = Path(backup.filename or "backup.tar.gz").name
    if not name.endswith((".tar.gz", ".tgz")):
        return RedirectResponse("/maintenance?error=Nur+tar.gz-Sicherungen+sind+erlaubt", 303)
    target = BACKUP_DIR / ("restore-candidate-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + ".tar.gz")
    size = 0
    with target.open("wb") as handle:
        while chunk := await backup.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_RESTORE_BYTES:
                target.unlink(missing_ok=True)
                return RedirectResponse("/maintenance?error=Sicherungsdatei+ist+zu+groß", 303)
            handle.write(chunk)
    try:
        metadata = _validate_restore_archive(target)
        sidecar = target.with_suffix(target.suffix + ".validated.json")
        sidecar.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        audit("restore.validated", None, target.name)
        return RedirectResponse("/maintenance?message=Wiederherstellung+wurde+geprüft+und+bereitgestellt", 303)
    except Exception as exc:
        target.unlink(missing_ok=True)
        return RedirectResponse("/maintenance?error=" + urllib.parse.quote(str(exc)[:900]), 303)


def _refresh_and_install(project_id: int, job_id: int) -> dict[str, Any]:
    with db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
        source = conn.execute("SELECT * FROM package_sources WHERE project_id=? AND enabled=1", (project_id,)).fetchone()
    if not project or not source:
        raise ValueError("Projekt oder Paketquelle fehlt")
    _job_update(job_id, "running", 15, "Release wird gesucht")
    filename, release_version, url = latest_deb_asset(source)
    temporary = PACKAGE_DIR / f".maintenance-{job_id}.deb"
    try:
        digest = download_asset(url, temporary, source["token"], source["provider"])
        metadata = package_metadata(temporary)
        if project["package_name"] and metadata["package"] != project["package_name"]:
            raise ValueError("Paketname stimmt nicht mit dem Projekt überein")
        current = installed_version(metadata["package"])
        if current and not version_is_newer(metadata["version"], current):
            return {"status": "current", "version": current}
        _job_update(job_id, "running", 45, "Sicherheitsbackup wird erstellt")
        backup_job = _job("backup.pre-update", 0, project_id)
        backup_result = create_backup("project", project_id, None, backup_job)
        _job_update(backup_job, "succeeded", 100, "Vor-Update-Sicherung erfolgreich", result=backup_result)
        target = PACKAGE_DIR / Path(filename).name
        temporary.replace(target)
        _job_update(job_id, "running", 70, "Paket wird installiert")
        install = run_helper("install", str(target))
        if install.returncode != 0:
            raise RuntimeError((install.stderr or install.stdout or "Installation fehlgeschlagen")[-1800:])
        installed = installed_version(metadata["package"]) or metadata["version"]
        with db() as conn:
            conn.execute("UPDATE projects SET version=?,install_status='installed',updated_at=CURRENT_TIMESTAMP WHERE id=?", (installed, project_id))
            conn.execute(
                "INSERT INTO packages(project_id,filename,version,sha256,source) VALUES(?,?,?,?,?)",
                (project_id, target.name, metadata["version"], digest, source["provider"]),
            )
        return {"status": "updated", "version": installed, "release_version": release_version, "backup": backup_result["filename"]}
    finally:
        temporary.unlink(missing_ok=True)


@app.post("/maintenance/updates/{project_id}/install")
def install_project_update(project_id: int, request: Request):
    user = require_admin(request)
    job_id = _job("update.install", user["id"], project_id)
    try:
        result = _refresh_and_install(project_id, job_id)
        _job_update(job_id, "succeeded", 100, "Update abgeschlossen", result=result)
        audit("update.completed", project_id, json.dumps(result, ensure_ascii=False))
        return RedirectResponse("/maintenance?message=Update+wurde+abgeschlossen", 303)
    except Exception as exc:
        _job_update(job_id, "failed", 100, "Update fehlgeschlagen", error=str(exc))
        return RedirectResponse("/maintenance?error=" + urllib.parse.quote(str(exc)[:900]), 303)


@app.get("/api/v1/maintenance")
def maintenance_api(request: Request):
    require_user(request)
    with db() as conn:
        plans = [dict(row) for row in conn.execute("SELECT * FROM backup_plans ORDER BY id")]
        artifacts = [dict(row) for row in conn.execute("SELECT * FROM backup_artifacts ORDER BY id DESC LIMIT 100")]
        jobs = [dict(row) for row in conn.execute("SELECT * FROM maintenance_jobs ORDER BY id DESC LIMIT 100")]
    return {"version": VERSION, "plans": plans, "artifacts": artifacts, "jobs": jobs}
