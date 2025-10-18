from server import app
from flask import Flask
import rmap_service as rmap_mod
from rmap.rmap import ValidationError
from server import create_app
import os
from pathlib import Path

def test_healthz_route():
    client = app.test_client()
    resp = client.get("/healthz")

    assert resp.status_code == 200
    assert resp.is_json
    
def test__read_payload_b64_from_json():
    app = create_app()
    with app.test_request_context(json={"payload": "AAAA"}):
        assert rmap_mod._read_payload_b64() == "AAAA"


def test__read_payload_b64_from_raw_body():
    app = create_app()
    with app.test_request_context(data="BBBB", content_type="text/plain"):
        assert rmap_mod._read_payload_b64() == "BBBB"


def test__read_payload_b64_missing_raises():
    app = create_app()
    with app.test_request_context():
        try:
            rmap_mod._read_payload_b64()
            assert False, "expected ValidationError"
        except ValidationError:
            pass



def _set_real_rmap_env():
    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    secrets = repo_root / "secrets"
    os.environ["RMAP_CLIENT_KEYS_DIR"] = str(secrets / "clients")
    os.environ["RMAP_SERVER_PUB"] = str(secrets / "server_pub.asc")
    os.environ["RMAP_SERVER_PRIV"] = str(secrets / "server_priv.asc")
    os.environ.pop("RMAP_SERVER_PRIV_PASSPHRASE", None)

def test_initiate_no_payload_400():
    _set_real_rmap_env()
    app = create_app()
    client = app.test_client()
    r = client.post("/api/rmap-initiate")
    assert r.status_code == 400
    assert "payload" in r.get_json().get("error", "").lower()

def test_get_link_misconfig_503():
    _set_real_rmap_env()
    os.environ.pop("RMAP_SOURCE_DOC_ID", None)
    os.environ.pop("RMAP_WM_KEY", None)
    app = create_app()
    client = app.test_client()
    resp = client.post("/api/rmap-get-link", json={"payload": "AAAA"})
    assert resp.status_code == 503
    assert "misconfigured" in resp.get_json().get("error", "").lower()

def test_get_link_bad_method_500():
    _set_real_rmap_env()
    os.environ["RMAP_SOURCE_DOC_ID"] = "1"
    os.environ["RMAP_WM_KEY"] = "k"
    os.environ["RMAP_METHOD"] = "fake"
    app = create_app()
    client = app.test_client()
    resp = client.post("/api/rmap-get-link", json={"payload": "AAAA"})
    assert resp.status_code == 500
    assert "unknown watermarking method" in resp.get_json().get("error", "").lower()
