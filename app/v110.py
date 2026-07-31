from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.main import (
    app,
    audit,
    db,
    installed_version,
    render,
    require_admin,
    require_user,
    safe_service_name,
    service_state,
    validate_http_url,
    version_is_newer,
)

VERSION = "1.1.0"


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


@app.on_event("startup")
def init_v110_schema() -> None:
    with db() as conn:
        for column, definition in (
            ("icon", "TEXT NOT NULL DEFAULT ''"),
            ("developer", "TEXT NOT NULL DEFAULT ''"),
            ("homepage_url", "TEXT NOT NULL DEFAULT ''"),
            ("license", "TEXT NOT NULL DEFAULT ''"),
            ("port", "INTEGER"),
            ("sort_order", "INTEGER NOT NULL DEFAULT 100"),
            ("tags", "TEXT NOT NULL DEFAULT ''"),
            ("autostart", "INTEGER NOT NULL DEFAULT 1"),
            ("backup_enabled", "INTEGER NOT NULL DEFAULT 0"),
            ("backup_path", "TEXT NOT NULL DEFAULT ''"),
            ("install_path", "TEXT NOT NULL DEFAULT ''"),
        ):
            _ensure_column(conn, "projects", column, definition)
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS project_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            service_name TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 100,
            UNIQUE(project_id, service_name),
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS project_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            setting_key TEXT NOT NULL,
            setting_value TEXT NOT NULL DEFAULT '',
            UNIQUE(project_id, setting_key),
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS project_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            version TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        """)
        conn.execute("""
        INSERT OR IGNORE INTO project_services(project_id, service_name, display_name, sort_order)
        SELECT id, service_name, service_name, 10 FROM projects WHERE service_name <> ''
        """)


def _project(slug: str):
    with db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE slug=? AND deleted_at IS NULL", (slug,)).fetchone()
    if not project:
        raise HTTPException(404, "Projekt nicht gefunden")
    return project


@app.get("/manage/projects/{slug}", response_class=HTMLResponse)
def project_management(slug: str, request: Request, tab: str = "general", message: str = ""):
    require_user(request)
    project = _project(slug)
    with db() as conn:
        services = conn.execute(
            "SELECT * FROM project_services WHERE project_id=? ORDER BY sort_order, display_name, service_name",
            (project["id"],),
        ).fetchall()
        backups = conn.execute(
            "SELECT * FROM backups WHERE project_id=? ORDER BY id DESC LIMIT 30", (project["id"],)
        ).fetchall()
        packages = conn.execute(
            "SELECT * FROM packages WHERE project_id=? ORDER BY id DESC", (project["id"],)
        ).fetchall()
        source = conn.execute("SELECT * FROM package_sources WHERE project_id=?", (project["id"],)).fetchone()
    service_items = [{**dict(row), "state": service_state(row["service_name"])} for row in services]
    installed = installed_version(project["package_name"])
    latest = packages[0]["version"] if packages else None
    return render(
        "project_management.html",
        request,
        project=project,
        services=service_items,
        backups=backups,
        packages=packages,
        source=source,
        installed=installed,
        latest=latest,
        update_available=version_is_newer(latest, installed),
        tab=tab,
        message=message,
        management_version=VERSION,
    )


@app.post("/manage/projects/{slug}/general")
def update_general(
    slug: str,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    category: str = Form("Allgemein"),
    status: str = Form("In Entwicklung"),
    version: str = Form("0.1.0"),
    project_url: str = Form(""),
    repo_url: str = Form(""),
    docs_url: str = Form(""),
    icon: str = Form(""),
    developer: str = Form(""),
    homepage_url: str = Form(""),
    license: str = Form(""),
    port: Optional[int] = Form(None),
    tags: str = Form(""),
    sort_order: int = Form(100),
    visible: Optional[str] = Form(None),
    favorite: Optional[str] = Form(None),
):
    require_admin(request)
    project = _project(slug)
    if port is not None and not 1 <= port <= 65535:
        raise HTTPException(400, "Port muss zwischen 1 und 65535 liegen")
    values = (
        name.strip(), description.strip(), category.strip() or "Allgemein", status.strip(), version.strip(),
        validate_http_url(project_url, "Projektadresse"), validate_http_url(repo_url, "Repository"),
        validate_http_url(docs_url, "Dokumentation"), icon.strip(), developer.strip(),
        validate_http_url(homepage_url, "Homepage"), license.strip(), port, tags.strip(), sort_order,
        1 if visible else 0, 1 if favorite else 0, project["id"],
    )
    with db() as conn:
        conn.execute("""
        UPDATE projects SET name=?,description=?,category=?,status=?,version=?,project_url=?,repo_url=?,docs_url=?,
        icon=?,developer=?,homepage_url=?,license=?,port=?,tags=?,sort_order=?,visible=?,favorite=? WHERE id=?
        """, values)
    audit("project.settings.updated", project["id"], "Allgemeine Projektdaten aktualisiert")
    return RedirectResponse(f"/manage/projects/{slug}?tab=general&message=Gespeichert", status_code=303)


@app.post("/manage/projects/{slug}/runtime")
def update_runtime(
    slug: str,
    request: Request,
    package_name: str = Form(""),
    service_name: str = Form(""),
    install_path: str = Form(""),
    backup_path: str = Form(""),
    autostart: Optional[str] = Form(None),
    backup_enabled: Optional[str] = Form(None),
):
    require_admin(request)
    project = _project(slug)
    service = safe_service_name(service_name) if service_name.strip() else ""
    with db() as conn:
        conn.execute("""
        UPDATE projects SET package_name=?,service_name=?,install_path=?,backup_path=?,autostart=?,backup_enabled=? WHERE id=?
        """, (package_name.strip(), service, install_path.strip(), backup_path.strip(), 1 if autostart else 0,
              1 if backup_enabled else 0, project["id"]))
        if service:
            conn.execute("""
            INSERT INTO project_services(project_id,service_name,display_name,sort_order) VALUES(?,?,?,10)
            ON CONFLICT(project_id,service_name) DO NOTHING
            """, (project["id"], service, service))
    audit("project.runtime.updated", project["id"], "Laufzeitkonfiguration aktualisiert")
    return RedirectResponse(f"/manage/projects/{slug}?tab=settings&message=Gespeichert", status_code=303)


@app.post("/manage/projects/{slug}/services")
def add_service(slug: str, request: Request, service_name: str = Form(...), display_name: str = Form("")):
    require_admin(request)
    project = _project(slug)
    service = safe_service_name(service_name)
    with db() as conn:
        conn.execute("""
        INSERT INTO project_services(project_id,service_name,display_name)
        VALUES(?,?,?) ON CONFLICT(project_id,service_name) DO UPDATE SET display_name=excluded.display_name
        """, (project["id"], service, display_name.strip() or service))
    audit("project.service.added", project["id"], service)
    return RedirectResponse(f"/manage/projects/{slug}?tab=services&message=Dienst+gespeichert", status_code=303)


@app.post("/manage/projects/{slug}/services/{service_id}/delete")
def delete_service(slug: str, service_id: int, request: Request):
    require_admin(request)
    project = _project(slug)
    with db() as conn:
        conn.execute("DELETE FROM project_services WHERE id=? AND project_id=?", (service_id, project["id"]))
    audit("project.service.deleted", project["id"], str(service_id))
    return RedirectResponse(f"/manage/projects/{slug}?tab=services&message=Dienst+entfernt", status_code=303)
