from __future__ import annotations

"""Version 3.5.1: vollständige Verwaltung von GitHub- und Gitea-Projektquellen."""

import urllib.parse
from pathlib import Path

from fastapi import Form, HTTPException, Request
from fastapi.responses import RedirectResponse

import app.main as base
from app.main import audit, db, require_admin
from app.v330 import (
    ALLOWED_PROVIDERS,
    MAX_MANIFEST,
    REPOSITORY_RE,
    _api_urls,
    _decode_manifest,
    _headers,
    _parse_manifest_text,
    _request_json,
    _safe_https_base,
)
from app.v350 import app

VERSION = "3.5.1"
base.VERSION = VERSION
app.version = VERSION


def _clean_source_values(
    provider: str,
    base_url: str,
    repository: str,
    branch: str,
    manifest_path: str,
) -> tuple[str, str, str, str, str]:
    clean_provider = provider.strip().lower()
    clean_repository = repository.strip()
    if clean_provider not in ALLOWED_PROVIDERS or not REPOSITORY_RE.fullmatch(clean_repository):
        raise HTTPException(400, "Ungültiger Anbieter oder Repositoryname")
    clean_branch = branch.strip()[:120] or "main"
    clean_path = manifest_path.strip().strip("/")[:240] or "projekt.yaml"
    if ".." in Path(clean_path).parts or not clean_path.endswith((".yaml", ".yml")):
        raise HTTPException(400, "Ungültiger Manifestpfad")
    clean_url = _safe_https_base(base_url, clean_provider)
    return clean_provider, clean_url, clean_repository, clean_branch, clean_path


def _source(source_id: int) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM project_remote_sources WHERE id=?", (source_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Remote-Quelle wurde nicht gefunden")
    return dict(row)


def _test_source(source_id: int) -> dict[str, str]:
    source = _source(source_id)
    manifest_url, release_url = _api_urls(source)
    headers = _headers(source)
    manifest_document = _request_json(manifest_url, headers, MAX_MANIFEST * 2)
    manifest, _digest = _parse_manifest_text(_decode_manifest(manifest_document))
    if manifest["source"]["provider"] != source["provider"]:
        raise HTTPException(409, "Anbieter im Manifest stimmt nicht mit der Quelle überein")
    if manifest["source"]["repository"] != source["repository"]:
        raise HTTPException(409, "Repository im Manifest stimmt nicht mit der Quelle überein")
    release_state = "kein Release"
    try:
        release_document = _request_json(release_url, headers)
        release_state = str(release_document.get("tag_name") or release_document.get("name") or "Release gefunden")[:120]
    except HTTPException as exc:
        if "HTTP 404" not in str(exc.detail):
            raise
    with db() as conn:
        conn.execute(
            "UPDATE project_remote_sources SET last_status='tested',last_error='',updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (source_id,),
        )
    audit("project_remote.source_tested", source_id, f"{manifest['id']}:{manifest['version']}")
    return {"project": manifest["name"], "version": manifest["version"], "release": release_state}


@app.post("/project-framework/remotes/{source_id}/test")
def remote_source_test(source_id: int, request: Request):
    require_admin(request)
    try:
        result = _test_source(source_id)
        message = urllib.parse.quote(
            f"Verbindung erfolgreich: {result['project']} {result['version']} · {result['release']}"
        )
        return RedirectResponse(f"/project-framework/remotes?message={message}", 303)
    except HTTPException as exc:
        with db() as conn:
            conn.execute(
                "UPDATE project_remote_sources SET last_status='failed',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (str(exc.detail)[:2000], source_id),
            )
        return RedirectResponse(
            "/project-framework/remotes?error=" + urllib.parse.quote(str(exc.detail)), 303
        )


@app.post("/project-framework/remotes/{source_id}/edit")
def remote_source_edit(
    source_id: int,
    request: Request,
    name: str = Form(...),
    provider: str = Form(...),
    base_url: str = Form(""),
    repository: str = Form(...),
    branch: str = Form("main"),
    manifest_path: str = Form("projekt.yaml"),
    secret_name: str = Form(""),
    enabled: bool = Form(False),
):
    require_admin(request)
    _source(source_id)
    clean_provider, clean_url, clean_repository, clean_branch, clean_path = _clean_source_values(
        provider, base_url, repository, branch, manifest_path
    )
    with db() as conn:
        conn.execute(
            """UPDATE project_remote_sources SET name=?,provider=?,base_url=?,repository=?,branch=?,
               manifest_path=?,secret_name=?,enabled=?,last_status='changed',last_error='',updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (
                name.strip()[:120], clean_provider, clean_url, clean_repository, clean_branch,
                clean_path, secret_name.strip()[:120], int(enabled), source_id,
            ),
        )
    audit("project_remote.source_edited", source_id, f"{clean_provider}:{clean_repository}")
    return RedirectResponse("/project-framework/remotes?message=Remote-Quelle+wurde+aktualisiert", 303)


@app.post("/project-framework/remotes/{source_id}/delete")
def remote_source_delete(source_id: int, request: Request, confirm: str = Form("")):
    require_admin(request)
    source = _source(source_id)
    if confirm.strip() != source["repository"]:
        raise HTTPException(409, "Zum Löschen muss der Repositoryname bestätigt werden")
    with db() as conn:
        active_job = conn.execute(
            """SELECT 1 FROM installation_jobs j JOIN project_release_assets a
               ON j.source='remote-asset:' || a.id
               WHERE a.source_id=? AND j.state IN ('queued','running') LIMIT 1""",
            (source_id,),
        ).fetchone()
        if active_job:
            raise HTTPException(409, "Quelle kann während eines Installationsauftrags nicht gelöscht werden")
        conn.execute("DELETE FROM project_remote_sources WHERE id=?", (source_id,))
    audit("project_remote.source_deleted", source_id, source["repository"])
    return RedirectResponse("/project-framework/remotes?message=Remote-Quelle+wurde+gelöscht", 303)


@app.post("/project-framework/remotes/sync-all")
def remote_sources_sync_all(request: Request):
    require_admin(request)
    from app.v330 import _sync_source

    with db() as conn:
        source_ids = [row["id"] for row in conn.execute(
            "SELECT id FROM project_remote_sources WHERE enabled=1 ORDER BY id"
        )]
    succeeded = 0
    failed = 0
    for source_id in source_ids:
        try:
            _sync_source(int(source_id))
            succeeded += 1
        except Exception:
            failed += 1
    message = urllib.parse.quote(f"Synchronisierung beendet: {succeeded} erfolgreich, {failed} fehlgeschlagen")
    return RedirectResponse(f"/project-framework/remotes?message={message}", 303)
