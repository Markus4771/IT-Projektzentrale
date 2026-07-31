from __future__ import annotations

"""Version 1.7.0: Serverinventar, Statusabfragen und Monitoring-API."""

import json
import os
import platform
import shutil
import socket
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.main as base
from app.main import audit, db, render, require_admin, require_user, validate_http_url
from app.v160_runtime import app

VERSION = "1.7.0"
base.VERSION = VERSION
app.version = VERSION


def init_server_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            hostname TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL DEFAULT 'Allgemein',
            environment TEXT NOT NULL DEFAULT 'Produktion',
            connection_type TEXT NOT NULL DEFAULT 'local',
            agent_url TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            last_status TEXT NOT NULL DEFAULT 'unknown',
            last_error TEXT NOT NULL DEFAULT '',
            last_seen_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS server_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            cpu_percent REAL,
            memory_percent REAL,
            disk_percent REAL,
            uptime_seconds INTEGER,
            os_name TEXT NOT NULL DEFAULT '',
            kernel TEXT NOT NULL DEFAULT '',
            package_updates INTEGER,
            docker_available INTEGER NOT NULL DEFAULT 0,
            docker_containers INTEGER NOT NULL DEFAULT 0,
            services_json TEXT NOT NULL DEFAULT '[]',
            raw_json TEXT NOT NULL DEFAULT '{}',
            collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_server_snapshots_server ON server_snapshots(server_id,id DESC);
        """)
        hostname = socket.gethostname()
        conn.execute(
            """INSERT OR IGNORE INTO servers(name,hostname,role,connection_type,description)
               VALUES(?,?,'Projektzentrale','local','Lokaler Server der IT-Projektzentrale')""",
            (hostname, hostname),
        )


@app.on_event("startup")
def initialize_v170() -> None:
    init_server_db()


def _read_mem() -> float | None:
    values: dict[str, int] = {}
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            key, raw = line.split(':', 1)
            values[key] = int(raw.strip().split()[0])
        total, available = values['MemTotal'], values['MemAvailable']
        return round((total - available) * 100 / total, 1)
    except (OSError, ValueError, KeyError, ZeroDivisionError):
        return None


def _cpu_sample() -> tuple[int, int]:
    fields = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    return sum(fields), idle


def _cpu_percent() -> float | None:
    try:
        first_total, first_idle = _cpu_sample()
        import time
        time.sleep(0.1)
        second_total, second_idle = _cpu_sample()
        delta = second_total - first_total
        return round((1 - (second_idle - first_idle) / delta) * 100, 1) if delta else 0.0
    except (OSError, ValueError, IndexError):
        return None


def _command(args: list[str], timeout: int = 5) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def local_snapshot() -> dict[str, Any]:
    disk = shutil.disk_usage('/')
    uptime = None
    try:
        uptime = int(float(Path('/proc/uptime').read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        pass
    services = []
    for service in ('it-projektzentrale.service', 'nginx.service', 'docker.service', 'ssh.service'):
        result = _command(['systemctl', 'is-active', service])
        services.append({'name': service, 'state': result.stdout.strip() or 'unknown'})
    docker_available = shutil.which('docker') is not None
    containers = 0
    if docker_available:
        result = _command(['docker', 'ps', '-q'])
        if result.returncode == 0:
            containers = len([line for line in result.stdout.splitlines() if line.strip()])
    updates = None
    if shutil.which('apt'):
        result = _command(['apt', 'list', '--upgradable'], timeout=15)
        if result.returncode == 0:
            updates = max(0, len([line for line in result.stdout.splitlines() if '/' in line]))
    return {
        'status': 'online', 'cpu_percent': _cpu_percent(), 'memory_percent': _read_mem(),
        'disk_percent': round(disk.used * 100 / disk.total, 1), 'uptime_seconds': uptime,
        'os_name': platform.platform(), 'kernel': platform.release(), 'package_updates': updates,
        'docker_available': docker_available, 'docker_containers': containers, 'services': services,
        'collected_at': datetime.now(timezone.utc).isoformat(),
    }


def remote_snapshot(agent_url: str) -> dict[str, Any]:
    url = validate_http_url(agent_url, 'Agent-URL')
    if not url:
        raise ValueError('Agent-URL fehlt')
    request = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'IT-Projektzentrale/1.7'})
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f'Agent antwortet mit HTTP {response.status}')
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise RuntimeError('Agent-Antwort ist zu groß')
    data = json.loads(raw.decode('utf-8'))
    if not isinstance(data, dict):
        raise RuntimeError('Agent-Antwort ist ungültig')
    data.setdefault('status', 'online')
    data.setdefault('services', [])
    return data


def store_snapshot(server_id: int, data: dict[str, Any]) -> None:
    status = str(data.get('status') or 'online')[:30]
    with db() as conn:
        conn.execute(
            """INSERT INTO server_snapshots(server_id,status,cpu_percent,memory_percent,disk_percent,
               uptime_seconds,os_name,kernel,package_updates,docker_available,docker_containers,services_json,raw_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (server_id, status, data.get('cpu_percent'), data.get('memory_percent'), data.get('disk_percent'),
             data.get('uptime_seconds'), str(data.get('os_name') or '')[:300], str(data.get('kernel') or '')[:120],
             data.get('package_updates'), int(bool(data.get('docker_available'))), int(data.get('docker_containers') or 0),
             json.dumps(data.get('services') or [], ensure_ascii=False), json.dumps(data, ensure_ascii=False)),
        )
        conn.execute(
            "UPDATE servers SET last_status=?,last_error='',last_seen_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, server_id),
        )


def collect_server(server_id: int) -> None:
    with db() as conn:
        server = conn.execute('SELECT * FROM servers WHERE id=?', (server_id,)).fetchone()
    if not server:
        raise HTTPException(404, 'Server nicht gefunden')
    try:
        data = local_snapshot() if server['connection_type'] == 'local' else remote_snapshot(server['agent_url'])
        store_snapshot(server_id, data)
    except Exception as exc:
        with db() as conn:
            conn.execute("UPDATE servers SET last_status='offline',last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (str(exc)[:900], server_id))
        raise


@app.get('/servers', response_class=HTMLResponse)
def servers_page(request: Request, message: str = '', error: str = ''):
    require_user(request)
    with db() as conn:
        rows = conn.execute("""SELECT s.*,ss.cpu_percent,ss.memory_percent,ss.disk_percent,ss.uptime_seconds,
            ss.os_name,ss.package_updates,ss.docker_available,ss.docker_containers,ss.services_json,ss.collected_at
            FROM servers s LEFT JOIN server_snapshots ss ON ss.id=(SELECT id FROM server_snapshots x WHERE x.server_id=s.id ORDER BY x.id DESC LIMIT 1)
            ORDER BY s.environment,s.role,s.name""").fetchall()
    servers = []
    for row in rows:
        item = dict(row)
        item['services'] = json.loads(item.get('services_json') or '[]')
        servers.append(item)
    return render('servers.html', request, title='Serververwaltung', servers=servers, message=message, error=error)


@app.post('/servers/add')
def add_server(request: Request, name: str = Form(...), hostname: str = Form(...), role: str = Form('Allgemein'),
               environment: str = Form('Produktion'), connection_type: str = Form('agent'),
               agent_url: str = Form(''), description: str = Form('')):
    require_admin(request)
    connection_type = connection_type if connection_type in {'local', 'agent'} else 'agent'
    clean_host = hostname.strip().lower()
    if not clean_host or len(clean_host) > 253 or any(ch not in 'abcdefghijklmnopqrstuvwxyz0123456789.-' for ch in clean_host):
        return RedirectResponse('/servers?error=Ungültiger+Hostname', 303)
    clean_url = validate_http_url(agent_url, 'Agent-URL') if connection_type == 'agent' else ''
    try:
        with db() as conn:
            conn.execute("INSERT INTO servers(name,hostname,role,environment,connection_type,agent_url,description) VALUES(?,?,?,?,?,?,?)",
                         (name.strip()[:120], clean_host, role.strip()[:80], environment.strip()[:50], connection_type, clean_url, description.strip()[:1000]))
    except Exception as exc:
        return RedirectResponse('/servers?error=' + urllib.parse.quote(str(exc)[:500]), 303)
    audit('server.added', None, clean_host)
    return RedirectResponse('/servers?message=Server+wurde+angelegt', 303)


@app.post('/servers/{server_id}/collect')
def collect_server_route(server_id: int, request: Request):
    require_admin(request)
    try:
        collect_server(server_id)
        audit('server.collected', None, f'Server #{server_id}')
        return RedirectResponse('/servers?message=Serverstatus+wurde+aktualisiert', 303)
    except Exception as exc:
        return RedirectResponse('/servers?error=' + urllib.parse.quote(str(exc)[:700]), 303)


@app.post('/servers/collect-all')
def collect_all(request: Request):
    require_admin(request)
    with db() as conn:
        ids = [int(row[0]) for row in conn.execute('SELECT id FROM servers WHERE enabled=1')]
    failures = 0
    for server_id in ids:
        try:
            collect_server(server_id)
        except Exception:
            failures += 1
    audit('server.collect_all', None, f'{len(ids)} Server, {failures} Fehler')
    target = '/servers?message=' + urllib.parse.quote(f'{len(ids)} Server geprüft, {failures} Fehler')
    return RedirectResponse(target, 303)


@app.get('/api/v1/servers')
def servers_api(request: Request):
    require_user(request)
    with db() as conn:
        rows = conn.execute("""SELECT s.*,ss.cpu_percent,ss.memory_percent,ss.disk_percent,ss.uptime_seconds,
            ss.os_name,ss.kernel,ss.package_updates,ss.docker_available,ss.docker_containers,ss.services_json,ss.collected_at
            FROM servers s LEFT JOIN server_snapshots ss ON ss.id=(SELECT id FROM server_snapshots x WHERE x.server_id=s.id ORDER BY x.id DESC LIMIT 1)
            ORDER BY s.name""").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item['services'] = json.loads(item.pop('services_json') or '[]')
        result.append(item)
    return result


@app.get('/api/v1/agent/status')
def local_agent_status(request: Request):
    require_user(request)
    return local_snapshot()
