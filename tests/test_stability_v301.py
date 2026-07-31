from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v301_release_remains_in_chain():
    source = (ROOT / "app/v301.py").read_text(encoding="utf-8")
    runtime = (ROOT / "app/v301_runtime.py").read_text(encoding="utf-8")
    service = (ROOT / "systemd/it-projektzentrale.service").read_text(encoding="utf-8")
    postinst = (ROOT / "debian/postinst").read_text(encoding="utf-8")
    assert 'VERSION = "3.0.1"' in source
    assert 'VERSION = "3.0.1"' in runtime
    assert "app.v301_runtime:app" in service
    assert "app.v311_runtime:app" in service
    assert "app.v320_runtime:app" in service
    assert "app.v330_runtime:app" in service
    assert '"version":"3.0.1"' in postinst
    assert (ROOT / "version.txt").read_text(encoding="utf-8").strip() == "3.3.0"


def test_marketplace_blocks_ssrf_and_unsafe_versions():
    source = (ROOT / "app/v301.py").read_text(encoding="utf-8")
    assert "ip.is_global" in source
    assert "Private, lokale oder reservierte Zieladressen" in source
    assert "Weiterleitungen sind für Marketplace-Downloads deaktiviert" in source
    assert "VERSION_RE" in source
    assert "Paketsignatur fehlt" in source
    assert "Manifest und Katalogeintrag stimmen nicht überein" in source


def test_plugin_helper_verifies_expected_digest_without_circular_manifest_hash():
    helper = (ROOT / "scripts/itpz-plugin-helper").read_text(encoding="utf-8")
    marketplace = (ROOT / "app/v250.py").read_text(encoding="utf-8")
    assert "expected_sha256" in marketplace
    assert "args.extend([Path(package_file).name, expected_sha256])" in marketplace
    assert "digest!=sys.argv[4]" in helper
    assert "data.get('sha256')" not in helper
    assert "MAX_EXTRACTED_BYTES" in helper
    assert "MAX_MEMBERS" in helper
    assert "member.isfile() or member.isdir()" in helper
    assert "backup.rename(target)" in helper


def test_postinst_preserves_and_validates_master_key():
    postinst = (ROOT / "debian/postinst").read_text(encoding="utf-8")
    assert 'if [ ! -s "$MASTER_KEY" ]' in postinst
    assert "Fernet(Path(sys.argv[1]).read_bytes().strip())" in postinst
    assert "Master-Key ist ungültig" in postinst
