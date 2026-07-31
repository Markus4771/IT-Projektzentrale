from pathlib import Path


def test_server_management_contract():
    root = Path(__file__).resolve().parents[1]
    source = (root / 'app/v170.py').read_text(encoding='utf-8')
    template = (root / 'templates/servers.html').read_text(encoding='utf-8')

    assert 'CREATE TABLE IF NOT EXISTS servers' in source
    assert 'CREATE TABLE IF NOT EXISTS server_snapshots' in source
    assert "@app.get('/servers'" in source
    assert "@app.get('/api/v1/servers'" in source
    assert "@app.get('/api/v1/agent/status'" in source
    assert 'local_snapshot' in source
    assert 'remote_snapshot' in source
    assert 'Alle Server prüfen' in template
    assert 'CPU' in template and 'RAM' in template and 'Festplatte' in template


def test_remote_agent_has_limits_and_url_validation():
    source = (Path(__file__).resolve().parents[1] / 'app/v170.py').read_text(encoding='utf-8')
    assert 'validate_http_url' in source
    assert 'timeout=10' in source
    assert '1024 * 1024' in source
