import json
import types
import importlib
from pathlib import Path
import rmap_service as rmap_mod
from flask import Flask
import uuid

# -----------------------------------------------------------------------------------------------
# ------------------------------------ FAKE CLASSES ---------------------------------------------
# -----------------------------------------------------------------------------------------------

# the real one reqs real keys, but here we will only care about the JSON after decryption
class FakeIM:
    """Minimal fake identityManager"""
    def __init__(self, *a, **k):
        pass
    def decrypt_for_server(self, payload_b64: str):
        return getattr(self, "_ret", {})

# same here as with the im, real rmap tracks sessions and build nonces for tests a predictable behaviour is just enough
class FakeRMAP:
    """Minimal fake RMAP"""
    def __init__(self, im):
        self.nonces = {} # dict that can be set to stimulate issues, e.g., {"GroupXX": (nonceClient, nonceServer)}
    def handle_message1(self, obj):
        return {"payload": "OK"} # simply returns ok, so /api/rmap-initiate can return ok
    def handle_message2(self, obj):
        return {"result": "4f" * 16} # returns a token, fixed. so /api/rmap-get-link can get past the last step when nonce check is successfull

# routes expects a row with id, name and path for example
# if i have a dict we can simply fake that behaviour
class _Row:
    def __init__(self, **fields): # copies filed attributes
        self.__dict__.update(fields)


# fake db, return with eiter row if found or none if not found
class FakeConn:
    def __init__(self, row=None):
        self._row = row
    def execute(self, _sql, _params=None):
        return types.SimpleNamespace(first=lambda: self._row)
    def __enter__(self): return self
    def __exit__(self, *a): return False


# call both .connect and .being
# .connect returns a fake connection with said row
# .begin 
class FakeEngine:
    def __init__(self, select_row=None):
        self._row = select_row
    def connect(self):
        return FakeConn(self._row)
    def begin(self):
        class _Tx:
            def __enter__(self_inner): return FakeConn(self._row)
            def __exit__(self_inner, *a): return False
        return _Tx()
    
# -----------------------------------------------------------------------------------------------
# -------------------------------------- THE TESTS ----------------------------------------------
# -----------------------------------------------------------------------------------------------

def make_app(monkeypatch, 
             env: dict, 
             select_row=None, 
             im_ret=None, 
             nonces=None):
    # Arrange environment vars this test needs
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))

    # Swap real deps with fakes
    monkeypatch.setattr(rmap_mod, "IdentityManager", FakeIM, raising=True)
    monkeypatch.setattr(rmap_mod, "RMAP", FakeRMAP, raising=True)

    # Configure fakes (optional: store if you later want to inspect them)
    im_instance = FakeIM()
    im_instance._ret = im_ret if im_ret is not None else {}
    rmap = FakeRMAP(im_instance)
    if nonces is not None:
        rmap.nonces = dict(nonces)

    # Fake engine for DB
    engine = FakeEngine(select_row=select_row)
    def get_engine():
        return engine

    # Build a brand-new bare Flask app (avoid server.create_app)
    app = Flask("testapp_" + uuid.uuid4().hex)

    # Minimal config needed by rmap_service
    # STORAGE_DIR: use provided or a safe default
    app.config["STORAGE_DIR"] = env.get("STORAGE_DIR", "/tmp")

    # Register only the RMAP routes we’re testing
    rmap_mod.register_rmap_routes(app, get_engine)

    return app

def _fresh_app_with(monkeypatch, env, select_row=None, im_ret=None, nonces=None):
    return make_app(monkeypatch, env, select_row=select_row, im_ret=im_ret, nonces=nonces)

# -----------------------------------------------------------------------------------------------
# -------------------------------------- THE TESTS ----------------------------------------------
# -----------------------------------------------------------------------------------------------

def test_rmap_initiate_service_unavailable(monkeypatch):
    # Arrange
    # 1. no env 
    # 2. rmap init 
    # 3. fails -> 503
    app = _fresh_app_with(monkeypatch, env={}, select_row=None)
    client = app.test_client()
    # Act
    resp = client.post("/api/rmap-initiate", json={"payload":"AAAA"})
    # Assert
    assert resp.status_code == 503
    assert "RMAP service unavailable" in resp.get_json().get("error","")

# too many branches
def test_get_link_503_when_missing_env_vars(monkeypatch):
    # Arrange: have RMAP env for creation but miss core vars
    env = {
        "RMAP_CLIENT_KEYS_DIR": "/tmp/clients",
        "RMAP_SERVER_PUB": "/tmp/pub.asc",
        "RMAP_SERVER_PRIV": "/tmp/priv.asc",
        # Missing: RMAP_SOURCE_DOC_ID or RMAP_WM_KEY
    }
    app = _fresh_app_with(monkeypatch, env=env, select_row=None)
    client = app.test_client()
    # Act

    resp = client.post("/api/rmap-get-link", json={"payload":"AAAA"})

    # Assert
    assert resp.status_code == 503
    assert "server misconfigured" in resp.get_json().get("error","")


def test_get_link_500_unknown_method(monkeypatch):
    # Arrange: supply nonsense method
    env = {
        "RMAP_CLIENT_KEYS_DIR": "/tmp/clients",
        "RMAP_SERVER_PUB": "/tmp/pub.asc",
        "RMAP_SERVER_PRIV": "/tmp/priv.asc",
        "RMAP_SOURCE_DOC_ID": "2",
        "RMAP_WM_KEY": "k",
        "RMAP_METHOD": "this-method-dosnt-exist",
    }
    app = _fresh_app_with(monkeypatch, env=env, select_row=None)
    client = app.test_client()

    # Act
    resp = client.post("/api/rmap-get-link", json={"payload":"AAAA"})

    # Assert
    assert resp.status_code == 500
    assert "unknown watermarking method" in resp.get_json().get("error","")


def test_get_link_400_invalid_payload_missing_nonce(monkeypatch):
    # Arrange: 
    # identitymanager decrypt returns
    # no nonceServer key
    env = {
        "RMAP_CLIENT_KEYS_DIR": "/tmp/clients",
        "RMAP_SERVER_PUB": "/tmp/pub.asc",
        "RMAP_SERVER_PRIV": "/tmp/priv.asc",
        "RMAP_SOURCE_DOC_ID": "2",
        "RMAP_WM_KEY": "k",
        "RMAP_METHOD": "anton-eof",
    }
    app = _fresh_app_with(monkeypatch, env=env, im_ret={}, select_row=None)
    client = app.test_client()

    # Act
    resp = client.post("/api/rmap-get-link", json={"payload":"AAAA"})

    # Assert
    assert resp.status_code == 400
    assert "missing nonceServer" in resp.get_json().get("error","")


def test_get_link_400_nonce_not_found(monkeypatch):
    # Arrange: IM returns nonceServer=42 but rmap.nonces empty
    env = {
        "RMAP_CLIENT_KEYS_DIR": "/tmp/clients",
        "RMAP_SERVER_PUB": "/tmp/pub.asc",
        "RMAP_SERVER_PRIV": "/tmp/priv.asc",
        "RMAP_SOURCE_DOC_ID": "1",
        "RMAP_WM_KEY": "k",
        "RMAP_METHOD": "anton-eof",
    }
    app = _fresh_app_with(monkeypatch, env=env, im_ret={"nonceServer": 42}, select_row=None, nonces={})
    client = app.test_client()
    # Act
    resp = client.post("/api/rmap-get-link", json={"payload":"AAAA"})
    # Assert
    assert resp.status_code == 400
    assert "does not match any pending session" in resp.get_json().get("error","")


def test_get_link_404_doc_not_found(monkeypatch, tmp_path):
    # Arrange: Good nonce match, but DB returns no row
    env = {
        "RMAP_CLIENT_KEYS_DIR": "/tmp/clients",
        "RMAP_SERVER_PUB": "/tmp/pub.asc",
        "RMAP_SERVER_PRIV": "/tmp/priv.asc",
        "RMAP_SOURCE_DOC_ID": "1",
        "RMAP_WM_KEY": "k",
        "RMAP_METHOD": "anton-eof",
        "STORAGE_DIR": str(tmp_path),  # used by server app config
    }
    # fake nonces so identity is found (nonceServer=99)
    nonces = {"GroupX": (11, 99)}
    app = _fresh_app_with(monkeypatch, env=env, im_ret={"nonceServer": 99}, select_row=None, nonces=nonces)
    client = app.test_client()
    # Act
    resp = client.post("/api/rmap-get-link", json={"payload":"AAAA"})
    # Assert
    assert resp.status_code == 404
    assert "document id 1 not found" in resp.get_json().get("error","")


def test_get_link_500_path_escape(monkeypatch, tmp_path):
    # Arrange: DB returns a row whose path escapes storage root
    env = {
        "RMAP_CLIENT_KEYS_DIR": "/tmp/clients",
        "RMAP_SERVER_PUB": "/tmp/pub.asc",
        "RMAP_SERVER_PRIV": "/tmp/priv.asc",
        "RMAP_SOURCE_DOC_ID": "1",
        "RMAP_WM_KEY": "k",
        "RMAP_METHOD": "anton-eof",
        "STORAGE_DIR": str(tmp_path),
    }
    nonces = {"GroupX": (11, 99)}
    row = _Row(id=1, name="doc.pdf", path="/etc/passwd")
    app = _fresh_app_with(monkeypatch, env=env, im_ret={"nonceServer": 99}, select_row=row, nonces=nonces)
    client = app.test_client()
    # Act
    resp = client.post("/api/rmap-get-link", json={"payload":"AAAA"})
    # Assert
    assert resp.status_code == 500
    assert "document path invalid" in resp.get_json().get("error","")


def test_get_link_410_missing_file(monkeypatch, tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    env = {
        "RMAP_CLIENT_KEYS_DIR": "/tmp/clients",
        "RMAP_SERVER_PUB": "/tmp/pub.asc",
        "RMAP_SERVER_PRIV": "/tmp/priv.asc",
        "RMAP_SOURCE_DOC_ID": "2",
        "RMAP_WM_KEY": "k",
        "RMAP_METHOD": "anton-eof",
        "STORAGE_DIR": str(storage),
    }
    nonces = {"GroupX": (11, 77)}
    row = _Row(id=2, name="missing.pdf", path="uploads/missing.pdf")
    app = _fresh_app_with(monkeypatch, env=env, im_ret={"nonceServer": 77}, select_row=row, nonces=nonces)
    client = app.test_client()
    # Act
    resp = client.post("/api/rmap-get-link", json={"payload":"AAAA"})
    # Assert
    assert resp.status_code == 410
    assert "file missing on disk" in resp.get_json().get("error","")