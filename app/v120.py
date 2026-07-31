from __future__ import annotations

import re
import secrets
import sqlite3

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.v110 import app
from app.main import audit, db, hash_password, render, require_admin

VERSION = "1.2.0"
ROLES = {"admin": "Administrator", "manager": "Projektverwalter", "viewer": "Betrachter"}


def _user(user_id: int) -> sqlite3.Row:
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(404, "Benutzer nicht gefunden")
    return user


def _validate_username(username: str) -> str:
    value = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,63}", value):
        raise HTTPException(400, "Benutzername: 3 bis 64 Kleinbuchstaben, Zahlen, Punkt, Unterstrich oder Bindestrich")
    return value


def _validate_role(role: str) -> str:
    if role not in ROLES:
        raise HTTPException(400, "Ungültige Rolle")
    return role


@app.get("/admin/users", response_class=HTMLResponse)
def users_page(request: Request, message: str = "", generated_password: str = ""):
    require_admin(request)
    with db() as conn:
        users = conn.execute(
            "SELECT id,username,role,active,must_change_password,created_at,last_login_at FROM users ORDER BY username"
        ).fetchall()
    return render("users.html", request, users=users, roles=ROLES, message=message,
                  generated_password=generated_password, title="Benutzerverwaltung")


@app.post("/admin/users/create")
def create_user(request: Request, username: str = Form(...), role: str = Form("viewer"),
                password: str = Form("")):
    require_admin(request)
    username = _validate_username(username)
    role = _validate_role(role)
    generated = password.strip() or secrets.token_urlsafe(18)
    try:
        password_hash = hash_password(generated)
        with db() as conn:
            conn.execute(
                "INSERT INTO users(username,password_hash,role,active,must_change_password) VALUES(?,?,?,1,1)",
                (username, password_hash, role),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Dieser Benutzername existiert bereits")
    audit("user.created", None, f"{username} ({role})")
    return RedirectResponse(
        f"/admin/users?message=Benutzer+angelegt&generated_password={generated}", status_code=303
    )


@app.post("/admin/users/{user_id}/update")
def update_user(user_id: int, request: Request, role: str = Form(...), active: str | None = Form(None)):
    actor = require_admin(request)
    target = _user(user_id)
    role = _validate_role(role)
    is_active = 1 if active else 0
    if actor["id"] == user_id and (role != "admin" or not is_active):
        raise HTTPException(400, "Das eigene Administratorkonto darf nicht gesperrt oder herabgestuft werden")
    with db() as conn:
        if target["role"] == "admin" and (role != "admin" or not is_active):
            admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
            if admins <= 1:
                raise HTTPException(400, "Der letzte aktive Administrator darf nicht geändert werden")
        conn.execute("UPDATE users SET role=?,active=? WHERE id=?", (role, is_active, user_id))
    audit("user.updated", None, f"{target['username']} ({role}, active={is_active})")
    return RedirectResponse("/admin/users?message=Benutzer+aktualisiert", status_code=303)


@app.post("/admin/users/{user_id}/reset-password")
def reset_user_password(user_id: int, request: Request):
    require_admin(request)
    target = _user(user_id)
    generated = secrets.token_urlsafe(18)
    with db() as conn:
        conn.execute(
            "UPDATE users SET password_hash=?,must_change_password=1 WHERE id=?",
            (hash_password(generated), user_id),
        )
    audit("user.password_reset", None, target["username"])
    return RedirectResponse(
        f"/admin/users?message=Passwort+zurückgesetzt&generated_password={generated}", status_code=303
    )


@app.post("/admin/users/{user_id}/delete")
def delete_user(user_id: int, request: Request):
    actor = require_admin(request)
    target = _user(user_id)
    if actor["id"] == user_id:
        raise HTTPException(400, "Das eigene Konto kann nicht gelöscht werden")
    with db() as conn:
        if target["role"] == "admin" and target["active"]:
            admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
            if admins <= 1:
                raise HTTPException(400, "Der letzte aktive Administrator darf nicht gelöscht werden")
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    audit("user.deleted", None, target["username"])
    return RedirectResponse("/admin/users?message=Benutzer+gelöscht", status_code=303)
