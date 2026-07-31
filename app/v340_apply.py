from __future__ import annotations

"""Kompatible Manifestübernahme für den Repository-Katalog 3.4.0."""

from typing import Any

import app.v320 as framework
from app.main import audit, db


def apply_manifest(manifest: dict[str, Any]) -> int:
    repository = manifest["source"]["repository"]
    provider = manifest["source"]["provider"]
    repo_url = f"https://github.com/{repository}" if provider == "github" and repository else ""
    with db() as conn:
        project = conn.execute("SELECT id FROM projects WHERE slug=? AND deleted_at IS NULL", (manifest["id"],)).fetchone()
        if project:
            project_id = int(project["id"])
            conn.execute(
                """UPDATE projects SET name=?,description=?,category=?,version=?,project_url=?,repo_url=?,
                   package_name=?,service_name=?,health_url=?,latest_version=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (manifest["name"], manifest["description"], manifest["category"], manifest["version"],
                 manifest["homepage"], repo_url, manifest["package"]["name"],
                 str(manifest.get("install", {}).get("service") or "")[:255],
                 str(manifest.get("health", {}).get("url") or "")[:1000],
                 manifest["version"], project_id),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO projects(name,slug,description,category,status,version,project_url,repo_url,
                   package_name,service_name,health_url,latest_version,installation_status)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (manifest["name"], manifest["id"], manifest["description"], manifest["category"],
                 "Geplant", manifest["version"], manifest["homepage"], repo_url,
                 manifest["package"]["name"], str(manifest.get("install", {}).get("service") or "")[:255],
                 str(manifest.get("health", {}).get("url") or "")[:1000], manifest["version"], "available"),
            )
            project_id = int(cursor.lastrowid)
        if provider in {"github", "gitea"}:
            base_url = "https://github.com" if provider == "github" else str(manifest["source"].get("base_url") or "")[:500]
            pattern = str(manifest["package"].get("asset") or "*.deb")[:200]
            conn.execute(
                """INSERT INTO package_sources(project_id,provider,base_url,repository,token,asset_pattern,enabled)
                   VALUES(?,?,?,?, '',?,1) ON CONFLICT(project_id) DO UPDATE SET
                   provider=excluded.provider,base_url=excluded.base_url,repository=excluded.repository,
                   asset_pattern=excluded.asset_pattern,enabled=1,last_error='',updated_at=CURRENT_TIMESTAMP""",
                (project_id, provider, base_url, repository, pattern),
            )
    audit("project_manifest.applied", project_id, manifest["id"])
    return project_id


# v340 ruft aus Kompatibilitätsgründen diese Funktion über app.v320 auf.
framework._apply_manifest = apply_manifest
