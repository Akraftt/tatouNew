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



def _set_rmap_env_and_check_readable() -> bool:
    here = Path(__file__).resolve()
    root = here.parents[2]
    sec = root / "secrets"
    os.environ["RMAP_CLIENT_KEYS_DIR"] = str(sec / "clients")
    os.environ["RMAP_SERVER_PUB"] = str(sec / "server_pub.asc")
    os.environ["RMAP_SERVER_PRIV"] = str(sec / "server_priv.asc")
    os.environ.pop("RMAP_SERVER_PRIV_PASSPHRASE", None)
    return os.access(sec / "server_priv.asc", os.R_OK)

def test_initiate_no_payload():
    readable = _set_rmap_env_and_check_readable()
    app = create_app()
    c = app.test_client()
    r = c.post("/api/rmap-initiate")
    if not readable:
        assert r.status_code == 503
        assert "unavailable" in r.get_json().get("error", "").lower()
    else:
        assert r.status_code == 400
        assert "payload" in r.get_json().get("error", "").lower()

def test_get_link_misconfig():
    readable = _set_rmap_env_and_check_readable()
    os.environ.pop("RMAP_SOURCE_DOC_ID", None)
    os.environ.pop("RMAP_WM_KEY", None)
    app = create_app()
    c = app.test_client()
    r = c.post("/api/rmap-get-link", json={"payload": "AAAA"})
    if not readable:
        assert r.status_code == 503
        assert "unavailable" in r.get_json().get("error", "").lower()
    else:
        assert r.status_code == 503
        assert "misconfigured" in r.get_json().get("error", "").lower()

def test_get_link_bad_method():
    readable = _set_rmap_env_and_check_readable()
    os.environ["RMAP_SOURCE_DOC_ID"] = "1"
    os.environ["RMAP_WM_KEY"] = "k"
    os.environ["RMAP_METHOD"] = "no-such-method"
    app = create_app()
    c = app.test_client()
    r = c.post("/api/rmap-get-link", json={"payload": "AAAA"})
    if not readable:
        assert r.status_code == 503
        assert "unavailable" in r.get_json().get("error", "").lower()
    else:
        assert r.status_code == 500
        assert "unknown watermarking method" in r.get_json().get("error", "").lower()
