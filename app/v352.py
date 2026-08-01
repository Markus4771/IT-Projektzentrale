from __future__ import annotations

"""Version 3.5.2: erster durchgängiger GitHub-Installationsassistent."""

import sqlite3
import urllib.parse

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user
from app.v330 import REPOSITORY_RE, _sync_source
from app.v350 import _create_plan
from app.v351 import app

VERSION = "3.5.2"
base.VERSION = VERSION
app.version = VERSION


def _find_or_create_github_source(repository: str, secret_name: str, user_id: int) -> int:
    clean_repository = repository.strip()
    if not REPOSITORY_RE.fullmatch(clean_repository):
        raise HTTPException(400, "Repository muss im Format Eigentümer/Repository angegeben werden")
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM project_remote_sources WHERE provider='github' AND repository=? ORDER BY id LIMIT 1",
            (clean_repository,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE project_remote_sources SET enabled=1,secret_name=?,last_error='',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (secret_name.strip()[:120], row["id"]),
            )
            return int(row["id"])
        try:
            cursor = conn.execute(
                """INSERT INTO project_remote_sources(
                    name,provider,base_url,repository,branch,manifest_path,secret_name,enabled,created_by
                ) VALUES(?, 'github', 'https://api.github.com', ?, 'main', 'projekt.yaml', ?, 1, ?)""",
                (clean_repository, clean_repository, secret_name.strip()[:120], user_id),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "Diese GitHub-Quelle ist bereits vorhanden") from exc
    audit("github_install.source_ready", int(cursor.lastrowid), clean_repository)
    return int(cursor.lastrowid)


def _prepare_installation(repository: str, secret_name: str, user_id: int) -> tuple[int, int, dict]:
    source_id = _find_or_create_github_source(repository, secret_name, user_id)
    result = _sync_source(source_id)
    with db() as conn:
        row = conn.execute(
            """SELECT m.id FROM project_manifests m
               WHERE m.source_ref=? AND m.enabled=1 AND m.valid=1
               ORDER BY m.id DESC LIMIT 1""",
            (f"remote:github:{repository.strip()}",),
        ).fetchone()
    if not row:
        raise HTTPException(409, "Das Repository wurde synchronisiert, aber kein gültiges projekt.yaml übernommen")
    manifest_id = int(row["id"])
    plan_id = _create_plan(manifest_id, user_id)
    audit("github_install.plan_ready", manifest_id, f"source={source_id},plan={plan_id}")
    return source_id, plan_id, result


@app.get("/github-install", response_class=HTMLResponse)
def github_install_page(request: Request, message: str = "", error: str = ""):
    require_user(request)
    with db() as conn:
        secret_names = [row["name"] for row in conn.execute("SELECT name FROM encrypted_secrets ORDER BY name")]
    return render(
        "github_install.html",
        request,
        title="Aus GitHub installieren",
        message=message,
        error=error,
        secret_names=secret_names,
    )


@app.post("/github-install/prepare")
def github_install_prepare(
    request: Request,
    repository: str = Form(...),
    secret_name: str = Form(""),
):
    user = require_admin(request)
    try:
        _source_id, plan_id, result = _prepare_installation(repository, secret_name, int(user["id"]))
        message = urllib.parse.quote(
            f"GitHub-Projekt erkannt: {result['manifest']['name']} {result['manifest']['version']}"
        )
        return RedirectResponse(f"/manifest-installation/plans/{plan_id}?message={message}", 303)
    except HTTPException as exc:
        return RedirectResponse("/github-install?error=" + urllib.parse.quote(str(exc.detail)), 303)
    except Exception as exc:
        return RedirectResponse(
            "/github-install?error=" + urllib.parse.quote(f"GitHub-Prüfung fehlgeschlagen: {exc}"), 303
        )


@app.get("/api/v1/github-install")
def github_install_api(request: Request):
    require_user(request)
    return {
        "version": VERSION,
        "workflow": [
            "Repository registrieren",
            "projekt.yaml validieren",
            "Release und SHA256 prüfen",
            "Installationsplan erstellen",
            "Berechtigungen freigeben",
            "Installation starten",
        ],
    }
