from pathlib import Path


def test_software_center_routes_and_jobs_are_present():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v140.py").read_text(encoding="utf-8")
    template = (root / "templates/software_center.html").read_text(encoding="utf-8")
    navigation = (root / "templates/base.html").read_text(encoding="utf-8")

    for route in (
        '/software-center',
        '/software-center/{project_id}/refresh',
        '/software-center/{project_id}/install',
        '/api/v1/software-center',
    ):
        assert route in source

    assert "latest_deb_asset" in source
    assert "download_asset" in source
    assert "package_metadata" in source
    assert "run_helper(\"install\"" in source
    assert "software.release.refresh" in source
    assert "software.package.install" in source
    assert 'href="/software-center"' in navigation
    assert "Letzte Installationsjobs" in template


def test_software_center_uses_existing_security_boundary():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app/v140.py").read_text(encoding="utf-8")

    assert source.count("require_admin(request)") >= 2
    assert "subprocess.run" not in source
    assert "apt-get" not in source
    assert "sudo" not in source
