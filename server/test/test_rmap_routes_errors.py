import pytest
from server import create_app


@pytest.fixture
def client(monkeypatch):
    """Simple test client using the real app, no faking bullshit"""
    for k in [
        "RMAP_CLIENT_KEYS_DIR", "RMAP_SERVER_PUB", "RMAP_SERVER_PRIV",
        "RMAP_SERVER_PRIV_PASSPHRASE", "RMAP_METHOD", "RMAP_WM_KEY",
        "RMAP_SOURCE_DOC_ID", "STORAGE_DIR"
    ]:
        monkeypatch.delenv(k, raising=False)

    app = create_app()
    return app.test_client()

def test_initiate_no_env_returns_503(client):
    resp = client.post("/api/rmap-initiate", json={"payload": "AAAA"})
    assert resp.status_code in (400, 503)

def test_get_link_no_env_returns_503(client):
    resp = client.post("/api/rmap-get-link", json={"payload": "AAAA"})
    assert resp.status_code in (400, 503)

def test_get_link_missing_core_vars(monkeypatch):
    env = {
        "RMAP_CLIENT_KEYS_DIR": "/tmp/clients",
        "RMAP_SERVER_PUB": "/tmp/pub.asc",
        "RMAP_SERVER_PRIV": "/tmp/priv.asc",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    app = create_app()
    client = app.test_client()

    resp = client.post("/api/rmap-get-link", json={"payload": "AAAA"})
    assert resp.status_code in (400, 503)

def test_get_link_invalid_payload(monkeypatch):
    monkeypatch.setenv("RMAP_CLIENT_KEYS_DIR", "/tmp/clients")
    monkeypatch.setenv("RMAP_SERVER_PUB", "/tmp/pub.asc")
    monkeypatch.setenv("RMAP_SERVER_PRIV", "/tmp/priv.asc")
    monkeypatch.setenv("RMAP_SOURCE_DOC_ID", "10")
    monkeypatch.setenv("RMAP_WM_KEY", "abc")
    monkeypatch.setenv("RMAP_METHOD", "anton-eof")

    app = create_app()
    client = app.test_client()

    resp = client.post("/api/rmap-get-link", json={"payload": "bad_payload"})
    assert resp.status_code in (400, 500)