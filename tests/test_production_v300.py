from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v300_release_remains_in_release_chain():
    source = (ROOT / "app/v300.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app/v300_runtime.py").read_text(encoding="utf-8")
    current = (ROOT / "app/v301.py").read_text(encoding="utf-8")
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (ROOT / "debian/postinst").read_text(encoding="utf-8")
    assert 'VERSION = "3.0.0"' in source
    assert "from app.v250 import app" in source
    assert "import app.v300 as v300" in current
    assert "app.v301_runtime:app" in service
    assert "IT-Projektzentrale 3.0.1 wurde erfolgreich eingerichtet" in postinst
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.0.1"
    assert "app.version = VERSION" in runtime


def test_v300_has_real_crypto_and_secret_storage():
    source = (ROOT / "app/v300.py").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    postinst = (ROOT / "debian/postinst").read_text(encoding="utf-8")
    assert "Ed25519PublicKey" in source
    assert ".verify(" in source
    assert "Fernet" in source
    assert "encrypted_secrets" in source
    assert "revoked_artifacts" in source
    assert "cryptography==" in requirements
    assert "Fernet.generate_key" in postinst
    assert "chmod 0640" in postinst


def test_marketplace_sync_and_download_are_guarded():
    source = (ROOT / "app/v300.py").read_text(encoding="utf-8")
    stability = (ROOT / "app/v301.py").read_text(encoding="utf-8")
    template = (ROOT / "templates/marketplace.html").read_text(encoding="utf-8")
    assert "Nur HTTPS-Quellen" in source
    assert "MAX_PACKAGE" in source
    assert "hashlib.sha256" in source
    assert "Signaturprüfung fehlgeschlagen" in source
    assert "marketplace_sync_runs" in source
    assert "/marketplace/catalogs/{catalog_id}/sync" in source
    assert "/marketplace/packages/{package_id}/download" in source
    assert "ip.is_global" in stability
    assert "Signiert synchronisieren" in template
    assert "Prüfen & herunterladen" in template


def test_security_center_is_admin_only():
    source = (ROOT / "app/v300.py").read_text(encoding="utf-8")
    template = (ROOT / "templates/base.html").read_text(encoding="utf-8")
    assert '@app.get("/security"' in source
    assert '@app.get("/api/v1/security")' in source
    assert source.count("require_admin(request)") >= 7
    assert 'href="/security"' in template
