from __future__ import annotations

"""Produktiver Einstiegspunkt für 1.6.0 mit korrigiertem Plugin-Upsert."""

import json
from typing import Any

import app.v150 as plugin_module
from app.main import db
from app.v160 import app


def upsert_manifest(manifest: dict[str, Any], trusted: bool) -> int:
    install = manifest["install"]
    source = manifest["source"]
    slug = manifest["id"].replace(".", "-").replace("_", "-")
    with db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE slug=?", (slug,)).fetchone()
        values = (
            manifest["name"], manifest["description"], manifest["category"], manifest["version"],
            manifest["repository"], manifest["homepage"], install["package"],
            manifest["services"][0] if manifest["services"] else "", install["type"],
        )
        if project:
            project_id = int(project["id"])
            conn.execute(
                """UPDATE projects SET name=?,description=?,category=?,version=?,repo_url=?,homepage_url=?,
                   package_name=?,service_name=?,install_type=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (*values, project_id),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO projects(name,slug,description,category,status,version,repo_url,homepage_url,
                   package_name,service_name,install_type,install_status)
                   VALUES(?,?,?,?,'In Entwicklung',?,?,?,?,?,?,'not_installed')""",
                (manifest["name"], slug, manifest["description"], manifest["category"], manifest["version"],
                 manifest["repository"], manifest["homepage"], install["package"],
                 manifest["services"][0] if manifest["services"] else "", install["type"]),
            )
            project_id = int(cursor.lastrowid)

        cursor = conn.execute(
            """INSERT INTO plugins(plugin_key,name,version,manifest_version,description,category,author,license,
               icon,homepage_url,repository_url,install_type,package_name,trusted,manifest_json,project_id)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(plugin_key) DO UPDATE SET name=excluded.name,version=excluded.version,
               manifest_version=excluded.manifest_version,description=excluded.description,category=excluded.category,
               author=excluded.author,license=excluded.license,icon=excluded.icon,homepage_url=excluded.homepage_url,
               repository_url=excluded.repository_url,install_type=excluded.install_type,package_name=excluded.package_name,
               trusted=excluded.trusted,manifest_json=excluded.manifest_json,project_id=excluded.project_id,
               updated_at=CURRENT_TIMESTAMP RETURNING id""",
            (manifest["id"], manifest["name"], manifest["version"], manifest["manifest_version"],
             manifest["description"], manifest["category"], manifest["author"], manifest["license"],
             manifest["icon"], manifest["homepage"], manifest["repository"], install["type"], install["package"],
             int(trusted), json.dumps(manifest, ensure_ascii=False, sort_keys=True), project_id),
        )
        plugin_id = int(cursor.fetchone()[0])
        conn.execute("DELETE FROM plugin_capabilities WHERE plugin_id=?", (plugin_id,))
        for capability, configuration in manifest["capabilities"].items():
            conn.execute(
                "INSERT INTO plugin_capabilities(plugin_id,capability,configuration_json) VALUES(?,?,?)",
                (plugin_id, capability, json.dumps(configuration, ensure_ascii=False, sort_keys=True)),
            )
        conn.execute("DELETE FROM project_services WHERE project_id=?", (project_id,))
        for position, service in enumerate(manifest["services"], start=1):
            conn.execute(
                "INSERT INTO project_services(project_id,service_name,display_name,sort_order) VALUES(?,?,?,?)",
                (project_id, service, service, position * 10),
            )
        if source["provider"] and source["repository"]:
            conn.execute(
                """INSERT INTO package_sources(project_id,provider,base_url,repository,token,asset_pattern,enabled)
                   VALUES(?,?,?,?, '',?,1)
                   ON CONFLICT(project_id) DO UPDATE SET provider=excluded.provider,base_url=excluded.base_url,
                   repository=excluded.repository,asset_pattern=excluded.asset_pattern,enabled=1,last_error=''""",
                (project_id, source["provider"], source["base_url"], source["repository"], source["asset_pattern"]),
            )
    return plugin_id


plugin_module._upsert_manifest = upsert_manifest
