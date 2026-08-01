from __future__ import annotations

"""Version 3.5.2: erster durchgängiger GitHub-Installationsassistent."""

import re
import sqlite3
import urllib.parse

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user
from app.v330 import (
    MAX_MANIFEST,
    REPOSITORY_RE,
    _api_urls,
    _headers,
    _request_bytes,
    _request_json,
    _sync_source,
)
from app.v350 import _create_plan
from app.v351 import app

VERSION = "3.5.2"
base.VERSION = VERSION
app.version = VERSION

SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


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


def _resolve_release_checksum(source_id: int, result: dict) -> None:
    """Liest optional eine *.sha256-Datei aus demselben GitHub-Release."""
    package = result["manifest"].get("package") or {}
    checksum_asset = str(package.get("sha256_asset") or "").strip()
    if not checksum_asset:
        return
    if "/" in checksum_asset or "\\" in checksum_asset or not checksum_asset.endswith(".sha256"):
        raise HTTPException(400, "package.sha256_asset muss ein sicherer .sha256-Dateiname sein")

    with db() as conn:
        source_row = conn.execute(
            "SELECT * FROM project_remote_sources WHERE id=? AND enabled=1", (source_id,)
        ).fetchone()
        release_row = conn.execute(
            """SELECT id,asset_name FROM project_release_assets
               WHERE source_id=? AND manifest_id=(
                   SELECT id FROM project_manifests WHERE project_key=?
               ) ORDER BY id DESC LIMIT 1""",
            (source_id, result["manifest"]["id"]),
        ).fetchone()
    if not source_row or not release_row:
        raise HTTPException(409, "Release-Paket wurde nicht eindeutig erkannt")

    source = dict(source_row)
    _manifest_url, release_url = _api_urls(source)
    headers = _headers(source)
    release_doc = _request_json(release_url, headers, MAX_MANIFEST * 4)
    checksum_url = ""
    for item in release_doc.get("assets") or []:
        if str(item.get("name") or "") == checksum_asset:
            checksum_url = str(item.get("browser_download_url") or item.get("url") or "")
            break
    if not checksum_url.startswith("https://"):
        raise HTTPException(409, f"Prüfsummendatei {checksum_asset} fehlt im GitHub-Release")

    download_headers = dict(headers)
    download_headers["Accept"] = "application/octet-stream"
    text = _request_bytes(checksum_url, download_headers, 4096).decode("utf-8", errors="strict").strip()
    digest = text.split()[0].lower() if text else ""
    if not SHA256_RE.fullmatch(digest):
        raise HTTPException(400, "SHA256-Seitendatei enthält keine gültige Prüfsumme")
    mentioned_name = text.split()[1].lstrip("*") if len(text.split()) > 1 else ""
    if mentioned_name and mentioned_name != release_row["asset_name"]:
        raise HTTPException(409, "SHA256-Seitendatei gehört nicht zum erkannten Debian-Paket")

    with db() as conn:
        conn.execute(
            "UPDATE project_release_assets SET expected_sha256=?,error='' WHERE id=?",
            (digest, release_row["id"]),
        )
    audit("github_install.checksum_resolved", int(release_row["id"]), checksum_asset)


def _prepare_installation(repository: str, secret_name: str, user_id: int) -> tuple[int, int, dict]:
    source_id = _find_or_create_github_source(repository, secret_name, user_id)
    result = _sync_source(source_id)
    _resolve_release_checksum(source_id, result)
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
