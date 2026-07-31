from __future__ import annotations

"""Kompatibilitätsbrücke für die Serververwaltung aus Version 1.7."""

import json
import urllib.request

import app.v170 as legacy
from app.main import db, validate_http_url


def authenticated_remote_snapshot(agent_url: str) -> dict:
    clean = validate_http_url(agent_url, "Agent-URL").rstrip("/")
    with db() as conn:
        row = conn.execute(
            "SELECT agent_token_hash FROM servers WHERE connection_type='agent' AND rtrim(agent_url,'/')=? LIMIT 1",
            (clean,),
        ).fetchone()
    token = row[0] if row else ""
    if not token:
        raise RuntimeError("Agent ist noch nicht registriert")
    request = urllib.request.Request(
        clean + "/v1/status",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "IT-Projektzentrale/2.2",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"Agent antwortet mit HTTP {response.status}")
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise RuntimeError("Agent-Antwort ist zu groß")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Agent-Antwort ist ungültig")
    data.setdefault("status", "online")
    data.setdefault("services", [])
    return data


legacy.remote_snapshot = authenticated_remote_snapshot
