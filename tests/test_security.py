import os
import re
import tempfile

os.environ["ITPZ_SECRET"] = "test-session-secret-" + "x" * 48
os.environ["ITPZ_ADMIN_USER"] = "admin"
os.environ["ITPZ_ADMIN_PASSWORD"] = "Initial-Test-Passwort-123!"
os.environ["ITPZ_STATE_DIR"] = tempfile.mkdtemp(prefix="itpz-test-")
os.environ["ITPZ_SYSTEM_HELPER"] = "/bin/false"

from fastapi.testclient import TestClient

from app.main import app, hash_password, verify_password


def csrf_token(response) -> str:
    match = re.search(r'<meta name="csrf-token" content="([^"]+)">', response.text)
    assert match
    return match.group(1)


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("Ein-langes-Testpasswort-123")
    second = hash_password("Ein-langes-Testpasswort-123")
    assert first != second
    assert verify_password("Ein-langes-Testpasswort-123", first)
    assert not verify_password("falsch", first)


def test_first_login_requires_csrf_and_password_change():
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        anonymous = client.get("/", follow_redirects=False)
        assert anonymous.status_code == 303
        assert anonymous.headers["location"] == "/admin/login"

        login_page = client.get("/admin/login")
        token = csrf_token(login_page)

        rejected = client.post(
            "/admin/login",
            data={"username": "admin", "password": "Initial-Test-Passwort-123!"},
            follow_redirects=False,
        )
        assert rejected.status_code == 403

        accepted = client.post(
            "/admin/login",
            data={"username": "admin", "password": "Initial-Test-Passwort-123!"},
            headers={"X-CSRF-Token": token},
            follow_redirects=False,
        )
        assert accepted.status_code == 303
        assert accepted.headers["location"] == "/account/password"

        password_page = client.get("/account/password")
        password_token = csrf_token(password_page)
        changed = client.post(
            "/account/password",
            data={
                "current_password": "Initial-Test-Passwort-123!",
                "new_password": "Neues-sicheres-Passwort-456!",
                "confirmation": "Neues-sicheres-Passwort-456!",
            },
            headers={"X-CSRF-Token": password_token},
            follow_redirects=False,
        )
        assert changed.status_code == 303
        assert client.get("/").status_code == 200
