from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import subprocess
import shutil
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.middleware.sessions import SessionMiddleware

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = Path(os.getenv("ITPZ_STATE_DIR", "/var/lib/it-projektzentrale"))
DB_PATH = STATE_DIR / "data" / "projektzentrale.db"
PACKAGE_DIR = STATE_DIR / "uploads" / "packages"
BACKUP_DIR = STATE_DIR / "backups"
EXPORT_DIR = STATE_DIR / "exports"
TEMPLATES = Environment(loader=FileSystemLoader(BASE_DIR / "templates"), autoescape=select_autoescape(["html", "xml"]))
VERSION = "1.0.0-beta.2"
MAX_UPLOAD_BYTES = int(os.getenv("ITPZ_MAX_UPLOAD_BYTES", str(256 * 1024 * 1024)))
SYSTEM_HELPER = Path(os.getenv("ITPZ_SYSTEM_HELPER", "/usr/lib/it-projektzentrale/itpz-helper"))
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_FAILURES = 5
LOGIN_FAILURES: dict[str, list[float]] = {}

app = FastAPI(title="IT-Projektzentrale", version=VERSION)
session_secret = os.getenv("ITPZ_SECRET")
if not session_secret or len(session_secret) < 32:
    raise RuntimeError("ITPZ_SECRET fehlt oder ist zu kurz")
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    same_site="strict",
    https_only=os.getenv("ITPZ_HTTPS_ONLY", "0") == "1",
    max_age=8 * 60 * 60,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'Allgemein',
            status TEXT NOT NULL DEFAULT 'In Entwicklung',
            version TEXT NOT NULL DEFAULT '0.1.0',
            project_url TEXT NOT NULL DEFAULT '',
            repo_url TEXT NOT NULL DEFAULT '',
            docs_url TEXT NOT NULL DEFAULT '',
            package_name TEXT NOT NULL DEFAULT '',
            service_name TEXT NOT NULL DEFAULT '',
            visible INTEGER NOT NULL DEFAULT 1,
            archived INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT,
            favorite INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            version TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'upload',
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS package_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL UNIQUE,
            provider TEXT NOT NULL,
            base_url TEXT NOT NULL,
            repository TEXT NOT NULL,
            token TEXT NOT NULL DEFAULT '',
            asset_pattern TEXT NOT NULL DEFAULT '*.deb',
            enabled INTEGER NOT NULL DEFAULT 1,
            last_checked_at TEXT,
            last_error TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            filename TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'project',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            project_id INTEGER,
            details TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            active INTEGER NOT NULL DEFAULT 1,
            must_change_password INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login_at TEXT
        );
        """)
        ensure_column(conn, "projects", "archived", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "projects", "deleted_at", "TEXT")
        ensure_column(conn, "projects", "favorite", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "packages", "source", "TEXT NOT NULL DEFAULT 'upload'")
        if not conn.execute("SELECT id FROM users LIMIT 1").fetchone():
            username = os.getenv("ITPZ_ADMIN_USER", "admin").strip() or "admin"
            password = os.getenv("ITPZ_ADMIN_PASSWORD", "")
            if len(password) < 12:
                raise RuntimeError("ITPZ_ADMIN_PASSWORD muss mindestens 12 Zeichen lang sein")
            conn.execute(
                "INSERT INTO users(username,password_hash,role,must_change_password) VALUES(?,?,?,1)",
                (username, hash_password(password), "admin"),
            )
        # Ab Version 0.4.0 werden bei einer frischen Installation bewusst keine Beispielprojekte angelegt.


def render(name: str, request: Request, **context) -> HTMLResponse:
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    user = current_user(request)
    template = TEMPLATES.get_template(name)
    return HTMLResponse(template.render(
        request=request,
        logged_in=bool(user),
        current_user=user,
        csrf_token=request.session["csrf_token"],
        app_version=VERSION,
        **context,
    ))


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Das Passwort muss mindestens 12 Zeichen lang sein")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(digest_hex)),
        )
        return hmac.compare_digest(actual, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


def current_user(request: Request) -> Optional[sqlite3.Row]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    with db() as conn:
        return conn.execute("SELECT * FROM users WHERE id=? AND active=1", (user_id,)).fetchone()


def verify_csrf(request: Request) -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    expected = request.session.get("csrf_token", "")
    supplied = request.headers.get("x-csrf-token", "")
    if not expected or not supplied or not hmac.compare_digest(str(expected), supplied):
        raise HTTPException(status_code=403, detail="Ungültiger CSRF-Schutz")


def require_user(request: Request, allow_password_change: bool = False) -> sqlite3.Row:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Anmeldung erforderlich")
    if user["must_change_password"] and not allow_password_change:
        raise HTTPException(status_code=403, detail="Zuerst muss das Initialpasswort geändert werden")
    verify_csrf(request)
    return user


def require_admin(request: Request) -> sqlite3.Row:
    user = require_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Administrator-Berechtigung erforderlich")
    return user


def installed_version(package_name: str) -> Optional[str]:
    if not package_name or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", package_name):
        return None
    result = subprocess.run(["dpkg-query", "-W", "-f=${Version}", "--", package_name], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def service_state(service_name: str) -> str:
    if not service_name:
        return "unbekannt"
    try:
        service_name = safe_service_name(service_name)
    except HTTPException:
        return "unbekannt"
    result = subprocess.run(["systemctl", "is-active", "--", service_name], capture_output=True, text=True)
    state = result.stdout.strip().lower()
    if state == "active":
        return "läuft"
    if state in {"inactive", "failed", "activating", "deactivating"}:
        return state
    return "unbekannt"


def version_is_newer(candidate: Optional[str], current: Optional[str]) -> bool:
    if not candidate or not current:
        return False
    return subprocess.run(["dpkg", "--compare-versions", candidate, "gt", current]).returncode == 0


def validate_slug(slug: str) -> str:
    slug = slug.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", slug):
        raise HTTPException(400, "Kurzname: nur Kleinbuchstaben, Zahlen und Bindestriche")
    return slug


def validate_source(provider: str, base_url: str, repository: str) -> tuple[str, str, str]:
    provider = provider.lower().strip()
    if provider not in {"github", "gitea"}:
        raise HTTPException(400, "Anbieter muss GitHub oder Gitea sein")
    base_url = base_url.strip().rstrip("/")
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(400, "Die Serveradresse muss mit http:// oder https:// beginnen")
    repository = repository.strip().strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise HTTPException(400, "Repository im Format Eigentümer/Projekt eintragen")
    return provider, base_url, repository


def validate_http_url(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise HTTPException(400, f"{label} muss eine gültige HTTP- oder HTTPS-Adresse sein")
    return value


def package_metadata(path: Path) -> dict[str, str]:
    if not path.is_file() or path.suffix.lower() != ".deb":
        raise ValueError("Ungültiger DEB-Dateipfad")
    fields = {}
    for field in ("Package", "Version", "Architecture", "Depends"):
        result = subprocess.run(
            ["dpkg-deb", "--field", str(path), field], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise ValueError("Die Datei ist kein gültiges Debian-Paket")
        fields[field.lower()] = result.stdout.strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", fields["package"]):
        raise ValueError("Das Paket enthält einen ungültigen Paketnamen")
    host_arch = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True, timeout=10).stdout.strip()
    if fields["architecture"] not in {"all", host_arch}:
        raise ValueError(f"Paketarchitektur {fields['architecture']} passt nicht zu {host_arch}")
    return fields


def run_helper(*arguments: str) -> subprocess.CompletedProcess[str]:
    command = ["sudo", str(SYSTEM_HELPER), *arguments]
    return subprocess.run(command, capture_output=True, text=True, timeout=1800)


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        old_origin = urllib.parse.urlparse(req.full_url)
        new_origin = urllib.parse.urlparse(newurl)
        if new_origin.scheme not in {"http", "https"}:
            return None
        if redirected and (old_origin.scheme, old_origin.netloc) != (new_origin.scheme, new_origin.netloc):
            redirected.remove_header("Authorization")
        return redirected


URL_OPENER = urllib.request.build_opener(SafeRedirectHandler)


def api_request_json(url: str, token: str, provider: str) -> dict:
    headers = {"Accept": "application/json", "User-Agent": f"IT-Projektzentrale/{VERSION}"}
    if token:
        headers["Authorization"] = f"Bearer {token}" if provider == "github" else f"token {token}"
    try:
        with URL_OPENER.open(urllib.request.Request(url, headers=headers), timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(str(exc)) from exc


def latest_deb_asset(source: sqlite3.Row) -> tuple[str, str, str]:
    provider, base_url, repository = source["provider"], source["base_url"].rstrip("/"), source["repository"]
    if provider == "github":
        api_base = "https://api.github.com" if urllib.parse.urlparse(base_url).netloc.lower() == "github.com" else f"{base_url}/api/v3"
        data = api_request_json(f"{api_base}/repos/{repository}/releases/latest", source["token"], provider)
    else:
        data = api_request_json(f"{base_url}/api/v1/repos/{repository}/releases/latest", source["token"], provider)
    version = str(data.get("tag_name") or data.get("name") or "unbekannt").lstrip("v")
    pattern = source["asset_pattern"] or "*.deb"
    suffix = pattern.replace("*", "")
    for asset in data.get("assets") or []:
        name = str(asset.get("name") or "")
        url = asset.get("browser_download_url") or asset.get("download_url")
        if name.endswith(".deb") and (not suffix or name.endswith(suffix)) and url:
            return name, version, str(url)
    raise RuntimeError(f"Im neuesten Release wurde kein passendes DEB-Paket ({pattern}) gefunden")


def download_asset(url: str, target: Path, token: str, provider: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("Die Release-Datei besitzt keine gültige Downloadadresse")
    headers = {"Accept": "application/octet-stream", "User-Agent": f"IT-Projektzentrale/{VERSION}"}
    if token:
        headers["Authorization"] = f"Bearer {token}" if provider == "github" else f"token {token}"
    digest = hashlib.sha256()
    try:
        with URL_OPENER.open(urllib.request.Request(url, headers=headers), timeout=120) as response, target.open("wb") as output:
            declared_size = int(response.headers.get("Content-Length") or 0)
            if declared_size > MAX_UPLOAD_BYTES:
                raise RuntimeError("Die Release-Datei überschreitet die erlaubte Größe")
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise RuntimeError("Die Release-Datei überschreitet die erlaubte Größe")
                digest.update(chunk)
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    try:
        package_metadata(target)
    except ValueError as exc:
        target.unlink(missing_ok=True)
        raise RuntimeError(str(exc)) from exc
    return digest.hexdigest()



def audit(action: str, project_id: Optional[int] = None, details: str = "") -> None:
    with db() as conn:
        conn.execute("INSERT INTO audit_log(action,project_id,details) VALUES(?,?,?)", (action, project_id, details[:1000]))


def system_metrics() -> dict:
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    mem_total = mem_available = 0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) * 1024
            elif line.startswith("MemAvailable:"):
                mem_available = int(line.split()[1]) * 1024
    except OSError:
        pass
    usage = shutil.disk_usage("/")
    temperature = None
    for path in (Path("/sys/class/thermal/thermal_zone0/temp"), Path("/sys/class/hwmon/hwmon0/temp1_input")):
        try:
            temperature = round(int(path.read_text().strip()) / 1000, 1)
            break
        except (OSError, ValueError):
            continue
    return {
        "load": [round(v, 2) for v in load],
        "memory_total": mem_total,
        "memory_used": max(0, mem_total - mem_available),
        "memory_percent": round((mem_total - mem_available) * 100 / mem_total, 1) if mem_total else 0,
        "disk_total": usage.total,
        "disk_used": usage.used,
        "disk_percent": round(usage.used * 100 / usage.total, 1) if usage.total else 0,
        "temperature": temperature,
        "hostname": os.uname().nodename,
        "uptime_seconds": int(float(Path("/proc/uptime").read_text().split()[0])) if Path("/proc/uptime").exists() else 0,
    }


def safe_service_name(name: str) -> str:
    name = name.strip()
    if not name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@:-]*", name):
        raise HTTPException(400, "Ungültiger systemd-Dienstname")
    if not name.endswith(".service"):
        name += ".service"
    return name


def project_manifest(project: sqlite3.Row) -> dict:
    return {
        "schema": "it-projektzentrale/v1",
        "name": project["name"], "slug": project["slug"], "description": project["description"],
        "category": project["category"], "status": project["status"], "version": project["version"],
        "project_url": project["project_url"], "repo_url": project["repo_url"], "docs_url": project["docs_url"],
        "package_name": project["package_name"], "service_name": project["service_name"],
    }

@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    if not current_user(request):
        return RedirectResponse("/admin/login", status_code=303)
    require_user(request)
    with db() as conn:
        rows = conn.execute("""SELECT p.*,
        (SELECT version FROM packages x WHERE x.project_id=p.id ORDER BY x.id DESC LIMIT 1) latest_version
        FROM projects p
        WHERE p.visible=1 AND p.archived=0 AND p.deleted_at IS NULL
        ORDER BY p.favorite DESC,p.name""").fetchall()
        news = conn.execute("SELECT * FROM news ORDER BY id DESC LIMIT 5").fetchall()
        package_count = conn.execute("SELECT COUNT(*) FROM packages p JOIN projects x ON x.id=p.project_id WHERE x.deleted_at IS NULL").fetchone()[0]

    projects = []
    for row in rows:
        current = installed_version(row["package_name"])
        if not current:
            continue
        item = dict(row)
        item["installed_version"] = current
        item["service_state"] = service_state(row["service_name"])
        item["update_available"] = version_is_newer(row["latest_version"], current)
        projects.append(item)

    active_services = sum(1 for p in projects if p["service_state"] == "läuft")
    updates = sum(1 for p in projects if p["update_available"])
    return render("dashboard.html", request, projects=projects, news=news, system=system_metrics(), stats={
        "installed": len(projects),
        "updates": updates,
        "active_services": active_services,
        "packages": package_count,
    })


@app.get("/projects", response_class=HTMLResponse)
def projects(request: Request, archived: int = 0):
    require_user(request)
    where = "deleted_at IS NULL AND archived=?"
    with db() as conn:
        rows = conn.execute(f"SELECT * FROM projects WHERE {where} ORDER BY name", (1 if archived else 0,)).fetchall()
    return render("projects.html", request, projects=rows, archived=bool(archived))


@app.get("/projects/{slug}", response_class=HTMLResponse)
def project_detail(slug: str, request: Request, message: str = ""):
    require_user(request)
    with db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE slug=? AND deleted_at IS NULL", (slug,)).fetchone()
        if not project:
            raise HTTPException(404)
        packages = conn.execute("SELECT * FROM packages WHERE project_id=? ORDER BY id DESC", (project["id"],)).fetchall()
    return render("project_detail.html", request, project=project, packages=packages, installed=installed_version(project["package_name"]), service=service_state(project["service_name"]), message=message)


@app.get("/installation", response_class=HTMLResponse)
def installation(request: Request, message: str = "", error: str = ""):
    require_user(request)
    with db() as conn:
        rows = conn.execute("""SELECT p.*,
        (SELECT filename FROM packages x WHERE x.project_id=p.id ORDER BY x.id DESC LIMIT 1) latest_file,
        (SELECT version FROM packages x WHERE x.project_id=p.id ORDER BY x.id DESC LIMIT 1) latest_version,
        (SELECT source FROM packages x WHERE x.project_id=p.id ORDER BY x.id DESC LIMIT 1) latest_source,
        s.provider source_provider, s.repository source_repository, s.last_error source_error
        FROM projects p LEFT JOIN package_sources s ON s.project_id=p.id
        WHERE p.visible=1 AND p.archived=0 AND p.deleted_at IS NULL ORDER BY p.name""").fetchall()
    enriched = [{**dict(r), "installed_version": installed_version(r["package_name"])} for r in rows]
    return render("installation.html", request, projects=enriched, message=message, error=error)


@app.post("/installation/{project_id}/refresh")
def refresh_package(project_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        source = conn.execute("SELECT s.* FROM package_sources s JOIN projects p ON p.id=s.project_id WHERE s.project_id=? AND s.enabled=1 AND p.deleted_at IS NULL", (project_id,)).fetchone()
    if not source:
        return RedirectResponse("/installation?error=Keine+aktive+Paketquelle+eingerichtet", status_code=303)
    try:
        filename, version, url = latest_deb_asset(source)
        safe_name = Path(filename).name
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+~-]*\.deb", safe_name):
            raise RuntimeError("Das Release enthält keinen sicheren DEB-Dateinamen")
        target = PACKAGE_DIR / safe_name
        temporary = PACKAGE_DIR / f".release-{secrets.token_hex(16)}.deb"
        digest = download_asset(url, temporary, source["token"], source["provider"])
        metadata = package_metadata(temporary)
        with db() as conn:
            project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if project and project["package_name"] and project["package_name"] != metadata["package"]:
                temporary.unlink(missing_ok=True)
                raise RuntimeError("Der Paketname des Releases stimmt nicht mit dem Projekt überein")
            temporary.replace(target)
            if not conn.execute("SELECT id FROM packages WHERE project_id=? AND filename=? AND sha256=?", (project_id, safe_name, digest)).fetchone():
                conn.execute("INSERT INTO packages(project_id,filename,version,sha256,source) VALUES(?,?,?,?,?)", (project_id, safe_name, metadata["version"] or version, digest, source["provider"]))
            conn.execute("UPDATE package_sources SET last_checked_at=CURRENT_TIMESTAMP,last_error='' WHERE project_id=?", (project_id,))
        return RedirectResponse("/installation?message=Paketquelle+wurde+erfolgreich+abgerufen", status_code=303)
    except Exception as exc:
        if "temporary" in locals():
            temporary.unlink(missing_ok=True)
        error = str(exc)[:900]
        with db() as conn:
            conn.execute("UPDATE package_sources SET last_checked_at=CURRENT_TIMESTAMP,last_error=? WHERE project_id=?", (error, project_id))
        return RedirectResponse(f"/installation?error={urllib.parse.quote(error)}", status_code=303)


@app.post("/installation/{project_id}/install")
def install_package(project_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        pkg = conn.execute("SELECT x.* FROM packages x JOIN projects p ON p.id=x.project_id WHERE x.project_id=? AND p.deleted_at IS NULL ORDER BY x.id DESC LIMIT 1", (project_id,)).fetchone()
    if not pkg:
        raise HTTPException(404, "Kein DEB-Paket vorhanden")
    package_path = PACKAGE_DIR / Path(pkg["filename"]).name
    try:
        package_metadata(package_path)
    except ValueError as exc:
        return RedirectResponse(f"/installation?error={urllib.parse.quote(str(exc))}", status_code=303)
    result = run_helper("install", str(package_path))
    audit("package.install", project_id, result.stderr or result.stdout)
    if result.returncode != 0:
        return RedirectResponse(f"/installation?error={urllib.parse.quote(result.stderr[-900:])}", status_code=303)
    return RedirectResponse("/installation?message=Installation+wurde+erfolgreich+abgeschlossen", status_code=303)


@app.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = ""):
    if current_user(request):
        return RedirectResponse("/", status_code=303)
    return render("login.html", request, error=error)


@app.post("/admin/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    verify_csrf(request)
    client = request.client.host if request.client else "unbekannt"
    now = time.time()
    failures = [stamp for stamp in LOGIN_FAILURES.get(client, []) if now - stamp < LOGIN_WINDOW_SECONDS]
    if len(failures) >= LOGIN_MAX_FAILURES:
        raise HTTPException(status_code=429, detail="Zu viele Anmeldeversuche. Bitte später erneut versuchen.")
    authenticated_user = None
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username=? AND active=1", (username.strip(),)).fetchone()
        if user and verify_password(password, user["password_hash"]):
            authenticated_user = dict(user)
            conn.execute("UPDATE users SET last_login_at=CURRENT_TIMESTAMP WHERE id=?", (user["id"],))
    if authenticated_user:
        LOGIN_FAILURES.pop(client, None)
        request.session.clear()
        request.session["user_id"] = authenticated_user["id"]
        request.session["csrf_token"] = secrets.token_urlsafe(32)
        audit("auth.login", details=f"Benutzer {authenticated_user['username']}")
        target = "/account/password" if authenticated_user["must_change_password"] else "/"
        return RedirectResponse(target, status_code=303)
    failures.append(now)
    LOGIN_FAILURES[client] = failures
    audit("auth.login_failed", details=f"Benutzer {username.strip()[:100]}")
    return RedirectResponse("/admin/login?error=Anmeldedaten+sind+nicht+korrekt", status_code=303)


@app.post("/admin/logout")
def logout(request: Request):
    user = require_user(request, allow_password_change=True)
    audit("auth.logout", details=f"Benutzer {user['username']}")
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.get("/account/password", response_class=HTMLResponse)
def password_page(request: Request, error: str = ""):
    require_user(request, allow_password_change=True)
    return render("password_change.html", request, error=error)


@app.post("/account/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirmation: str = Form(...),
):
    user = require_user(request, allow_password_change=True)
    if not verify_password(current_password, user["password_hash"]):
        return RedirectResponse("/account/password?error=Das+aktuelle+Passwort+ist+falsch", status_code=303)
    if new_password != confirmation:
        return RedirectResponse("/account/password?error=Die+neuen+Passwörter+stimmen+nicht+überein", status_code=303)
    try:
        encoded = hash_password(new_password)
    except ValueError as exc:
        return RedirectResponse(f"/account/password?error={urllib.parse.quote(str(exc))}", status_code=303)
    if verify_password(new_password, user["password_hash"]):
        return RedirectResponse("/account/password?error=Das+neue+Passwort+muss+sich+unterscheiden", status_code=303)
    with db() as conn:
        conn.execute("UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?", (encoded, user["id"]))
    audit("auth.password_changed", details=f"Benutzer {user['username']}")
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    return RedirectResponse("/?message=Passwort+wurde+geändert", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, message: str = "", error: str = ""):
    require_admin(request)
    with db() as conn:
        projects = conn.execute("SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY archived,name").fetchall()
        sources = {row["project_id"]: row for row in conn.execute("SELECT * FROM package_sources").fetchall()}
    return render("admin.html", request, projects=projects, sources=sources, message=message, error=error)


@app.post("/admin/projects")
def add_project(request: Request, name: str = Form(...), slug: str = Form(...), description: str = Form(""), category: str = Form("Allgemein"), status: str = Form("In Entwicklung"), version: str = Form("0.1.0"), package_name: str = Form(""), service_name: str = Form("")):
    require_admin(request)
    package_name = package_name.strip()
    service_name = service_name.strip()
    if package_name and not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", package_name):
        raise HTTPException(400, "Ungültiger Debian-Paketname")
    if service_name:
        safe_service_name(service_name)
    try:
        with db() as conn:
            conn.execute("INSERT INTO projects(name,slug,description,category,status,version,package_name,service_name) VALUES(?,?,?,?,?,?,?,?)", (name.strip(), validate_slug(slug), description.strip(), category.strip() or "Allgemein", status, version.strip() or "0.1.0", package_name.strip(), service_name.strip()))
    except sqlite3.IntegrityError:
        return RedirectResponse("/admin?error=Der+Kurzname+ist+bereits+vergeben", status_code=303)
    return RedirectResponse("/admin?message=Projekt+wurde+angelegt", status_code=303)


@app.post("/admin/projects/{project_id}/edit")
def edit_project(project_id: int, request: Request, name: str = Form(...), slug: str = Form(...), description: str = Form(""), category: str = Form("Allgemein"), status: str = Form("In Entwicklung"), version: str = Form("0.1.0"), project_url: str = Form(""), repo_url: str = Form(""), docs_url: str = Form(""), package_name: str = Form(""), service_name: str = Form(""), favorite: Optional[str] = Form(None)):
    require_admin(request)
    project_url = validate_http_url(project_url, "Projekt-Webseite")
    repo_url = validate_http_url(repo_url, "Repository-Link")
    docs_url = validate_http_url(docs_url, "Dokumentationsadresse")
    package_name = package_name.strip()
    service_name = service_name.strip()
    if package_name and not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", package_name):
        raise HTTPException(400, "Ungültiger Debian-Paketname")
    if service_name:
        safe_service_name(service_name)
    try:
        with db() as conn:
            conn.execute("""UPDATE projects SET name=?,slug=?,description=?,category=?,status=?,version=?,project_url=?,repo_url=?,docs_url=?,package_name=?,service_name=?,favorite=? WHERE id=? AND deleted_at IS NULL""", (name.strip(), validate_slug(slug), description.strip(), category.strip() or "Allgemein", status, version.strip() or "0.1.0", project_url.strip(), repo_url.strip(), docs_url.strip(), package_name.strip(), service_name.strip(), 1 if favorite else 0, project_id))
    except sqlite3.IntegrityError:
        return RedirectResponse("/admin?error=Der+Kurzname+ist+bereits+vergeben", status_code=303)
    return RedirectResponse("/admin?message=Projekt+wurde+gespeichert", status_code=303)


@app.post("/admin/projects/{project_id}/archive")
def archive_project(project_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        conn.execute("UPDATE projects SET archived=1,status='Archiviert' WHERE id=? AND deleted_at IS NULL", (project_id,))
    return RedirectResponse("/admin?message=Projekt+wurde+archiviert", status_code=303)


@app.post("/admin/projects/{project_id}/unarchive")
def unarchive_project(project_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        conn.execute("UPDATE projects SET archived=0,status=CASE WHEN status='Archiviert' THEN 'In Entwicklung' ELSE status END WHERE id=? AND deleted_at IS NULL", (project_id,))
    return RedirectResponse("/admin?message=Projekt+wurde+reaktiviert", status_code=303)


@app.post("/projects/{project_id}/favorite")
def toggle_favorite(project_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        project = conn.execute("SELECT favorite FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
        if not project:
            raise HTTPException(404)
        conn.execute("UPDATE projects SET favorite=? WHERE id=?", (0 if project["favorite"] else 1, project_id))
    return RedirectResponse("/", status_code=303)


@app.post("/admin/projects/{project_id}/trash")
def trash_project(project_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        conn.execute("UPDATE projects SET deleted_at=CURRENT_TIMESTAMP,visible=0 WHERE id=?", (project_id,))
    return RedirectResponse("/admin?message=Projekt+wurde+in+den+Papierkorb+verschoben", status_code=303)


@app.get("/admin/trash", response_class=HTMLResponse)
def trash(request: Request, message: str = ""):
    require_admin(request)
    with db() as conn:
        projects = conn.execute("SELECT * FROM projects WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC").fetchall()
    return render("trash.html", request, projects=projects, message=message)


@app.post("/admin/projects/{project_id}/restore")
def restore_project(project_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        conn.execute("UPDATE projects SET deleted_at=NULL,visible=1 WHERE id=?", (project_id,))
    return RedirectResponse("/admin/trash?message=Projekt+wurde+wiederhergestellt", status_code=303)


@app.post("/admin/projects/{project_id}/delete")
def permanently_delete_project(project_id: int, request: Request, confirmation: str = Form(...), remove_package_files: Optional[str] = Form(None)):
    require_admin(request)
    with db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NOT NULL", (project_id,)).fetchone()
        if not project:
            raise HTTPException(404)
        if confirmation.strip() != project["name"]:
            return RedirectResponse("/admin/trash?message=Der+Projektname+stimmt+nicht+überein", status_code=303)
        filenames = [row["filename"] for row in conn.execute("SELECT filename FROM packages WHERE project_id=?", (project_id,)).fetchall()]
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        if remove_package_files:
            for filename in filenames:
                still_used = conn.execute("SELECT 1 FROM packages WHERE filename=? LIMIT 1", (filename,)).fetchone()
                if not still_used:
                    (PACKAGE_DIR / Path(filename).name).unlink(missing_ok=True)
    return RedirectResponse("/admin/trash?message=Projekt+wurde+endgültig+gelöscht", status_code=303)


@app.post("/admin/sources")
def save_source(request: Request, project_id: int = Form(...), provider: str = Form(...), base_url: str = Form(...), repository: str = Form(...), token: str = Form(""), asset_pattern: str = Form("*.deb")):
    require_admin(request)
    provider, base_url, repository = validate_source(provider, base_url, repository)
    with db() as conn:
        if not conn.execute("SELECT id FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone():
            raise HTTPException(404, "Projekt wurde nicht gefunden")
        current = conn.execute("SELECT token FROM package_sources WHERE project_id=?", (project_id,)).fetchone()
        saved_token = token.strip() if token.strip() else (current["token"] if current else "")
        conn.execute("""INSERT INTO package_sources(project_id,provider,base_url,repository,token,asset_pattern,enabled) VALUES(?,?,?,?,?,?,1)
        ON CONFLICT(project_id) DO UPDATE SET provider=excluded.provider,base_url=excluded.base_url,repository=excluded.repository,token=excluded.token,asset_pattern=excluded.asset_pattern,enabled=1,last_error=''""", (project_id, provider, base_url, repository, saved_token, asset_pattern.strip() or "*.deb"))
    return RedirectResponse("/admin?message=Paketquelle+wurde+gespeichert", status_code=303)


@app.post("/admin/packages")
async def upload_package(request: Request, project_id: int = Form(...), package: UploadFile = File(...)):
    require_admin(request)
    if not package.filename or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+~-]*\.deb", Path(package.filename).name):
        raise HTTPException(400, "Nur .deb-Dateien mit sicherem Dateinamen sind erlaubt")
    safe_name = Path(package.filename).name
    target = PACKAGE_DIR / safe_name
    temporary = PACKAGE_DIR / f".upload-{secrets.token_hex(16)}.deb"
    digest = hashlib.sha256()
    total = 0
    with temporary.open("wb") as output:
        while chunk := await package.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                output.close()
                temporary.unlink(missing_ok=True)
                raise HTTPException(413, "Das DEB-Paket ist zu groß")
            digest.update(chunk)
            output.write(chunk)
    try:
        metadata = package_metadata(temporary)
    except ValueError as exc:
        temporary.unlink(missing_ok=True)
        raise HTTPException(400, str(exc)) from exc
    with db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
        if not project:
            temporary.unlink(missing_ok=True)
            raise HTTPException(404, "Projekt wurde nicht gefunden")
        if project["package_name"] and project["package_name"] != metadata["package"]:
            temporary.unlink(missing_ok=True)
            raise HTTPException(400, "Der Paketname stimmt nicht mit dem Projekt überein")
        temporary.replace(target)
        conn.execute(
            "INSERT INTO packages(project_id,filename,version,sha256,source) VALUES(?,?,?,?,?)",
            (project_id, safe_name, metadata["version"], digest.hexdigest(), "upload"),
        )
    return RedirectResponse("/admin?message=DEB-Paket+wurde+hochgeladen", status_code=303)


@app.get("/packages/{filename}")
def download_package(filename: str, request: Request):
    require_user(request)
    path = PACKAGE_DIR / Path(filename).name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, filename=path.name)


@app.get("/health")
def health():
    return {"status": "ok", "version": VERSION}


@app.get("/system", response_class=HTMLResponse)
def system_page(request: Request, message: str = "", error: str = ""):
    require_admin(request)
    with db() as conn:
        audits = conn.execute("SELECT a.*,p.name project_name FROM audit_log a LEFT JOIN projects p ON p.id=a.project_id ORDER BY a.id DESC LIMIT 100").fetchall()
    return render("system.html", request, system=system_metrics(), audits=audits, message=message, error=error)


@app.post("/projects/{project_id}/service/{action}")
def service_action(project_id: int, action: str, request: Request):
    require_admin(request)
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(400, "Unbekannte Aktion")
    with db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
    if not project:
        raise HTTPException(404)
    service = safe_service_name(project["service_name"])
    result = run_helper("service", action, service)
    audit(f"service.{action}", project_id, result.stderr or result.stdout)
    msg = "Dienstaktion ausgeführt" if result.returncode == 0 else "Dienstaktion fehlgeschlagen: " + (result.stderr[-500:] or result.stdout[-500:])
    return RedirectResponse(f"/projects/{project['slug']}?message={urllib.parse.quote(msg)}", status_code=303)


@app.get("/projects/{project_id}/logs", response_class=HTMLResponse)
def project_logs(project_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
    if not project:
        raise HTTPException(404)
    service = safe_service_name(project["service_name"])
    result = subprocess.run(["/usr/bin/journalctl", f"--unit={service}", "-n", "200", "--no-pager"], capture_output=True, text=True)
    return render("logs.html", request, project=project, logs=(result.stdout or result.stderr))


@app.post("/projects/{project_id}/uninstall")
def uninstall_project_package(project_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
    if not project or not project["package_name"]:
        raise HTTPException(404, "Kein Paketname hinterlegt")
    package = project["package_name"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", package):
        raise HTTPException(400, "Ungültiger Paketname")
    result = run_helper("remove", package)
    audit("package.uninstall", project_id, result.stderr or result.stdout)
    message = "Anwendung wurde deinstalliert" if result.returncode == 0 else "Deinstallation fehlgeschlagen: " + result.stderr[-500:]
    return RedirectResponse(f"/projects/{project['slug']}?message={urllib.parse.quote(message)}", status_code=303)


@app.post("/projects/{project_id}/backup")
def create_project_backup(project_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
        packages = conn.execute("SELECT * FROM packages WHERE project_id=?", (project_id,)).fetchall() if project else []
        source = conn.execute("SELECT * FROM package_sources WHERE project_id=?", (project_id,)).fetchone() if project else None
    if not project:
        raise HTTPException(404)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"{project['slug']}-{stamp}.tar.gz"
    target = BACKUP_DIR / filename
    tmp = EXPORT_DIR / f"{project['slug']}-{stamp}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        (tmp / "projekt.json").write_text(json.dumps(project_manifest(project), ensure_ascii=False, indent=2))
        (tmp / "packages.json").write_text(json.dumps([dict(x) for x in packages], ensure_ascii=False, indent=2))
        if source:
            clean_source = dict(source); clean_source["token"] = ""
            (tmp / "source.json").write_text(json.dumps(clean_source, ensure_ascii=False, indent=2))
        with tarfile.open(target, "w:gz") as tar:
            tar.add(tmp, arcname=project["slug"])
            for pkg in packages:
                pkg_path = PACKAGE_DIR / pkg["filename"]
                if pkg_path.exists():
                    tar.add(pkg_path, arcname=f"{project['slug']}/packages/{pkg_path.name}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    with db() as conn:
        conn.execute("INSERT INTO backups(project_id,filename,kind,size_bytes) VALUES(?,?,?,?)", (project_id, filename, "project", target.stat().st_size))
    audit("backup.create", project_id, filename)
    return RedirectResponse(f"/backups?message={urllib.parse.quote('Backup wurde erstellt')}", status_code=303)


@app.get("/backups", response_class=HTMLResponse)
def backups_page(request: Request, message: str = ""):
    require_admin(request)
    with db() as conn:
        backups = conn.execute("SELECT b.*,p.name project_name FROM backups b LEFT JOIN projects p ON p.id=b.project_id ORDER BY b.id DESC").fetchall()
        projects = conn.execute("SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY name").fetchall()
    return render("backups.html", request, backups=backups, projects=projects, message=message)


@app.get("/backups/{backup_id}/download")
def download_backup(backup_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        backup = conn.execute("SELECT * FROM backups WHERE id=?", (backup_id,)).fetchone()
    if not backup:
        raise HTTPException(404)
    path = BACKUP_DIR / Path(backup["filename"]).name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, filename=path.name)


@app.post("/backups/{backup_id}/delete")
def delete_backup(backup_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        backup = conn.execute("SELECT * FROM backups WHERE id=?", (backup_id,)).fetchone()
        if backup:
            conn.execute("DELETE FROM backups WHERE id=?", (backup_id,))
    if backup:
        (BACKUP_DIR / Path(backup["filename"]).name).unlink(missing_ok=True)
    return RedirectResponse("/backups?message=Backup+wurde+gelöscht", status_code=303)


@app.get("/projects/{project_id}/export")
def export_project(project_id: int, request: Request):
    require_admin(request)
    with db() as conn:
        project = conn.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)).fetchone()
    if not project:
        raise HTTPException(404)
    target = EXPORT_DIR / f"{project['slug']}.projekt.json"
    target.write_text(json.dumps(project_manifest(project), ensure_ascii=False, indent=2))
    audit("project.export", project_id, target.name)
    return FileResponse(target, filename=target.name, media_type="application/json")


@app.post("/admin/projects/import")
async def import_project_manifest(request: Request, manifest: UploadFile = File(...)):
    require_admin(request)
    try:
        content = await manifest.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise ValueError("Das Projektmanifest ist zu groß")
        data = json.loads(content.decode("utf-8"))
        slug = validate_slug(str(data.get("slug") or ""))
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("Projektname fehlt")
        project_url = validate_http_url(str(data.get("project_url") or ""), "Projekt-Webseite")
        repo_url = validate_http_url(str(data.get("repo_url") or ""), "Repository-Link")
        docs_url = validate_http_url(str(data.get("docs_url") or ""), "Dokumentationsadresse")
        package_name = str(data.get("package_name") or "").strip()
        service_name = str(data.get("service_name") or "").strip()
        if package_name and not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", package_name):
            raise ValueError("Ungültiger Debian-Paketname")
        if service_name:
            service_name = safe_service_name(service_name)
        with db() as conn:
            conn.execute("""INSERT INTO projects(name,slug,description,category,status,version,project_url,repo_url,docs_url,package_name,service_name)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (name, slug, str(data.get("description") or ""), str(data.get("category") or "Allgemein"), str(data.get("status") or "In Entwicklung"), str(data.get("version") or "0.1.0"), project_url, repo_url, docs_url, package_name, service_name))
        audit("project.import", None, slug)
        return RedirectResponse("/admin?message=Projektmanifest+wurde+importiert", status_code=303)
    except (ValueError, json.JSONDecodeError, sqlite3.IntegrityError) as exc:
        return RedirectResponse(f"/admin?error={urllib.parse.quote(str(exc))}", status_code=303)


@app.get("/api/v1/projects")
def api_projects(request: Request):
    require_user(request)
    with db() as conn:
        rows = conn.execute("SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY name").fetchall()
    return JSONResponse([{**dict(r), "installed_version": installed_version(r["package_name"]), "service_state": service_state(r["service_name"])} for r in rows])


@app.get("/api/v1/system")
def api_system(request: Request):
    require_admin(request)
    return system_metrics()
