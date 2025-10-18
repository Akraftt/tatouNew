from server import app
from flask import Flask
import rmap_service as rmap_mod
from rmap.rmap import ValidationError
from server import create_app

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
    with app.test_request_context():  # no JSON and no raw body
        try:
            rmap_mod._read_payload_b64()
            assert False, "expected ValidationError"
        except ValidationError:
            pass

def test_rmap_initiate_returns_503_when_rmap_unavailable():
    app = create_app()
    client = app.test_client()
    resp = client.post("/api/rmap-initiate", json={"payload": "AAAA"})
    assert resp.status_code == 503
    assert "RMAP service unavailable" in resp.get_json().get("error", "")


def test_rmap_get_link_returns_503_when_rmap_unavailable():
    app = create_app()
    client = app.test_client()
    resp = client.post("/api/rmap-get-link", json={"payload": "AAAA"})
    assert resp.status_code == 503