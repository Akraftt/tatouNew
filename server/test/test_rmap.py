import sys, types, os
import pytest
from flask import Flask, json

# Rmap has:
#from rmap.identity_manager import IdentityManager, IdentityManagerError, DecryptionError, EncryptionError
#from rmap.rmap import RMAP, ValidationError
# which comes from rmap @ https://github.com/nharrand/RMAP-Server/releases/download/v2.0.0/rmap-2.0.0-py3-none-any.whl
# therefore fake modules are created 
rmap_mod = types.ModuleType("rmap")
rmap_identity = types.ModuleType("rmap.identity_manager")

class DummyError(Exception): ...
class IdentityManager: ...
class RMAP: ...
class ValidationError(Exception): ...

# linking the lcasses to the fake modules
rmap_identity.IdentityManager = IdentityManager
rmap_identity.IdentityManagerError = DummyError
rmap_identity.DecryptionError = DummyError
rmap_identity.EncryptionError = DummyError
rmap_mod.RMAP = RMAP
rmap_mod.ValidationError = ValidationError

# register fake modules
sys.modules["rmap"] = rmap_mod
sys.modules["rmap.identity_manager"] = rmap_identity
sys.modules["rmap.rmap"] = rmap_mod

sys.path.append(os.path.abspath("src"))
from rmap_service import _read_payload_b64, ValidationError

app = Flask(__name__)

def test_read_payload_from_json():
    with app.test_request_context(
        "/api/rmap-initiate",
        method="POST",
        data=json.dumps({"payload": "SGVsbG8h"}),
        content_type="application/json",
    ):
        result = _read_payload_b64()
        assert result == "SGVsbG8h"

def test_read_payload_from_raw_text():
    with app.test_request_context(
        "/api/rmap-initiate",
        method="POST",
        data="U29tZUJhc2U2NA==",
        content_type="text/plain",
    ):
        result = _read_payload_b64()
        assert result == "U29tZUJhc2U2NA=="

def test_read_payload_raises_on_empty_request():
    with app.test_request_context(
        "/api/rmap-initiate",
        method="POST",
        data="",
        content_type="application/json",
    ):
        with pytest.raises(ValidationError):
            _read_payload_b64()


from flask import Flask
import types

# ------------------------------------------------------------------------------------

def test_rmap_initiate_service_unavailable(tmp_path):
    app = Flask(__name__)

    # delete variables to force except block
    for var in ["RMAP_CLIENT_KEYS_DIR", "RMAP_SERVER_PUB", "RMAP_SERVER_PRIV"]:
        if var in os.environ:
            del os.environ[var]

    fake_rmap = types.SimpleNamespace()
    fake_identity = types.SimpleNamespace()
    sys.modules["rmap"] = fake_rmap
    sys.modules["rmap.identity_manager"] = fake_identity
    sys.modules["rmap.rmap"] = fake_rmap

    # lambda : none since this test dosnt use a database
    from rmap_service import register_rmap_routes
    register_rmap_routes(app, lambda: None)

    client = app.test_client()
    resp = client.post("/api/rmap-initiate", json={"payload": "SGVsbG8="})

    assert resp.status_code == 503
    assert "RMAP service unavailable" in resp.text

# ------------------------------------------------------------------------------------
# test /api/rmap-initiate
def test_rmap_initiate_with_valid_payload(monkeypatch):
    app = Flask(__name__)

    # fake/stimulate sucess
    class DummyRMAP:
        def handle_message1(self, data):
            return {"payload": "ok"}

    # not used but is a req for constructor
    class DummyIdentity:
        pass

    # patch environment for successful init
    os.environ["RMAP_CLIENT_KEYS_DIR"] = "fake"
    os.environ["RMAP_SERVER_PUB"] = "fake"
    os.environ["RMAP_SERVER_PRIV"] = "fake"

    # fake constructor returns dummy
    # normal im expect arguments and dummy class dosnt have any
    # then use lambda ** to "eat them"
    monkeypatch.setattr("rmap_service.IdentityManager", lambda **kw: DummyIdentity())
    monkeypatch.setattr("rmap_service.RMAP", lambda im: DummyRMAP())

    # lambda : none since this test dosnt use a database
    from rmap_service import register_rmap_routes
    register_rmap_routes(app, lambda: None)
    client = app.test_client()

    resp = client.post("/api/rmap-initiate", json={"payload": "SGVsbG8="})

    assert resp.status_code == 200
    assert "payload" in resp.text

# ------------------------------------------------------------------------------------

def test_rmap_initiate_returns_400_when_payload_missing(monkeypatch):
    app = Flask(__name__)

    # 1. dummy classes
    class DummyRMAP:
        def handle_message1(self, data):
            return {"something_else": "oops"}
    class DummyIdentity:
        pass

    # 2. env vars
    # neeed env vars otherwise register_rmap_routes() throw keyerror
    os.environ["RMAP_CLIENT_KEYS_DIR"] = "dummy"
    os.environ["RMAP_SERVER_PUB"] = "dummy"
    os.environ["RMAP_SERVER_PRIV"] = "dummy"

    # 3. Inject dummy classes with env vars
    monkeypatch.setattr("rmap_service.IdentityManager", lambda **kw: DummyIdentity())
    monkeypatch.setattr("rmap_service.RMAP", lambda im: DummyRMAP())

    from rmap_service import register_rmap_routes
    register_rmap_routes(app, lambda: None)
    client = app.test_client()

    resp = client.post("/api/rmap-initiate", json={"payload": "SGVsbG8="})

    assert resp.status_code == 400
    data = resp.get_json()
    assert "something_else" in data

# ------------------------------------------------------------------------------------

def test_rmap_get_link_unavailable(monkeypatch):
    from flask import Flask
    app = Flask(__name__)

    def bad_identity_manager(**kwargs):
        raise RuntimeError("init fail")

    monkeypatch.setattr("rmap_service.IdentityManager", bad_identity_manager)

    from rmap_service import register_rmap_routes
    register_rmap_routes(app, lambda: None)
    client = app.test_client()

    resp = client.post("/api/rmap-get-link", json={"payload": "SGVsbG8="})
    assert resp.status_code == 503
    data = resp.get_json()
    assert "RMAP service unavailable" in data.get("error", "")

# ------------------------------------------------------------------------------------

def test_rmap_get_link_server_misconfigured(monkeypatch):
    """When RMAP_SOURCE_DOC_ID or RMAP_WM_KEY is missing, it should return 503."""
    from flask import Flask
    app = Flask(__name__)

    # Dummy classes to simulate a valid RMAP init
    class DummyIdentity:
        pass

    class DummyRMAP:
        pass

    # Ensure RMAP initializes fine
    os.environ["RMAP_CLIENT_KEYS_DIR"] = "dummy"
    os.environ["RMAP_SERVER_PUB"] = "dummy"
    os.environ["RMAP_SERVER_PRIV"] = "dummy"

    monkeypatch.setattr("rmap_service.IdentityManager", lambda **kw: DummyIdentity())
    monkeypatch.setattr("rmap_service.RMAP", lambda im: DummyRMAP())

    # Now register routes
    from rmap_service import register_rmap_routes
    register_rmap_routes(app, lambda: None)
    client = app.test_client()

    # Ensure environment lacks required config
    if "RMAP_SOURCE_DOC_ID" in os.environ:
        del os.environ["RMAP_SOURCE_DOC_ID"]
    if "RMAP_WM_KEY" in os.environ:
        del os.environ["RMAP_WM_KEY"]

    # Act
    resp = client.post("/api/rmap-get-link", json={"payload": "SGVsbG8="})

    # Assert
    assert resp.status_code == 503
    data = resp.get_json()
    assert "server misconfigured" in data.get("error", "")

def test_rmap_get_link_unknown_watermark_method(monkeypatch):
    """If WM.get_method raises KeyError, return 500 with proper message."""
    from flask import Flask
    app = Flask(__name__)

    # Dummy replacements for successful init
    class DummyIdentity:
        pass
    class DummyRMAP:
        pass

    os.environ["RMAP_CLIENT_KEYS_DIR"] = "dummy"
    os.environ["RMAP_SERVER_PUB"] = "dummy"
    os.environ["RMAP_SERVER_PRIV"] = "dummy"
    os.environ["RMAP_SOURCE_DOC_ID"] = "123"
    os.environ["RMAP_WM_KEY"] = "secretkey"
    os.environ["RMAP_METHOD"] = "unknown-method"

    monkeypatch.setattr("rmap_service.IdentityManager", lambda **kw: DummyIdentity())
    monkeypatch.setattr("rmap_service.RMAP", lambda im: DummyRMAP())
    monkeypatch.setattr("rmap_service.WM.get_method", lambda name: (_ for _ in ()).throw(KeyError("unknown method")))

    from rmap_service import register_rmap_routes
    register_rmap_routes(app, lambda: None)
    client = app.test_client()

    resp = client.post("/api/rmap-get-link", json={"payload": "SGVsbG8="})

    assert resp.status_code == 500
    data = resp.get_json()
    assert "unknown watermarking method" in data.get("error", "")

# ------------------------------------------------------------------------------------

def test_rmap_get_link_invalid_payload_missing_nonce(monkeypatch, tmp_path):
    """If decrypted payload is missing nonceServer, it should return 400."""
    from flask import Flask
    app = Flask(__name__)

    # Dummy classes and environment
    class DummyIdentity:
        def decrypt_for_server(self, payload):
            return {"wrong": "structure"}  # Missing nonceServer

    class DummyRMAP:
        nonces = {}

        def handle_message2(self, obj):
            return {"result": "fake-result"}

    os.environ["RMAP_CLIENT_KEYS_DIR"] = "dummy"
    os.environ["RMAP_SERVER_PUB"] = "dummy"
    os.environ["RMAP_SERVER_PRIV"] = "dummy"
    os.environ["RMAP_SOURCE_DOC_ID"] = "123"
    os.environ["RMAP_WM_KEY"] = "secretkey"
    os.environ["RMAP_METHOD"] = "toy-eof"

    monkeypatch.setattr("rmap_service.IdentityManager", lambda **kw: DummyIdentity())
    monkeypatch.setattr("rmap_service.RMAP", lambda im: DummyRMAP())
    monkeypatch.setattr("rmap_service.WM.get_method", lambda name: True)

    from rmap_service import register_rmap_routes
    register_rmap_routes(app, lambda: None)
    client = app.test_client()

    resp = client.post("/api/rmap-get-link", json={"payload": "SGVsbG8="})

    assert resp.status_code == 400
    data = resp.get_json()
    assert "invalid payload" in data.get("error", "")

# ------------------------------------------------------------------------------------

def test_rmap_get_link_nonce_mismatch(monkeypatch):
    """If nonceServer does not match any pending session, return 400."""
    from flask import Flask
    app = Flask(__name__)

    class DummyIdentity:
        def decrypt_for_server(self, payload):
            return {"nonceServer": 42}  # valid-looking payload

    class DummyRMAP:
        nonces = {"userA": ("clientNonce", 99)}  # does NOT match 42

        def handle_message2(self, obj):
            return {"result": "fake-result"}

    os.environ["RMAP_CLIENT_KEYS_DIR"] = "dummy"
    os.environ["RMAP_SERVER_PUB"] = "dummy"
    os.environ["RMAP_SERVER_PRIV"] = "dummy"
    os.environ["RMAP_SOURCE_DOC_ID"] = "123"
    os.environ["RMAP_WM_KEY"] = "secretkey"
    os.environ["RMAP_METHOD"] = "toy-eof"

    monkeypatch.setattr("rmap_service.IdentityManager", lambda **kw: DummyIdentity())
    monkeypatch.setattr("rmap_service.RMAP", lambda im: DummyRMAP())
    monkeypatch.setattr("rmap_service.WM.get_method", lambda name: True)

    from rmap_service import register_rmap_routes
    register_rmap_routes(app, lambda: None)
    client = app.test_client()

    resp = client.post("/api/rmap-get-link", json={"payload": "SGVsbG8="})

    assert resp.status_code == 400
    data = resp.get_json()
    assert "nonceServer does not match" in data.get("error", "")

# ------------------------------------------------------------------------------------

def test_rmap_get_link_missing_document_returns_404(monkeypatch, tmp_path):
    """If the source document ID is not found in DB, return 404."""
    from flask import Flask

    app = Flask(__name__)
    app.config["STORAGE_DIR"] = str(tmp_path)

    # Dummy identity manager and rmap
    class DummyIdentity:
        def decrypt_for_server(self, payload):
            return {"nonceServer": 123}

    class DummyRMAP:
        nonces = {"alice": ("n1", 123)}

        def handle_message2(self, obj):
            return {"result": "tok123"}

    # Fake DB connection and engine
    class DummyConn:
        def execute(self, q, params):
            class NoRow:
                def first(self_inner): return None
            return NoRow()

        def __enter__(self): return self
        def __exit__(self, *a): pass

    class DummyEngine:
        def connect(self):  # simulate SQLAlchemy engine.connect()
            return DummyConn()

    def fake_engine():
        return DummyEngine()

    # Set env vars
    os.environ["RMAP_CLIENT_KEYS_DIR"] = "dummy"
    os.environ["RMAP_SERVER_PUB"] = "dummy"
    os.environ["RMAP_SERVER_PRIV"] = "dummy"
    os.environ["RMAP_SOURCE_DOC_ID"] = "999"
    os.environ["RMAP_WM_KEY"] = "key123"
    os.environ["RMAP_METHOD"] = "toy-eof"

    # Monkeypatch dependencies
    monkeypatch.setattr("rmap_service.IdentityManager", lambda **kw: DummyIdentity())
    monkeypatch.setattr("rmap_service.RMAP", lambda im: DummyRMAP())
    monkeypatch.setattr("rmap_service.WM.get_method", lambda name: True)

    from rmap_service import register_rmap_routes
    register_rmap_routes(app, fake_engine)
    client = app.test_client()

    resp = client.post("/api/rmap-get-link", json={"payload": "SGVsbG8="})
    data = resp.get_json()

    assert resp.status_code == 404
    assert "not found" in data["error"]

# ------------------------------------------------------------------------------------

def test_rmap_get_link_file_missing_returns_410(monkeypatch, tmp_path):
    """Return 410 if the source file is missing on disk."""
    from flask import Flask

    app = Flask(__name__)
    app.config["STORAGE_DIR"] = str(tmp_path)

    class DummyIdentity:
        def decrypt_for_server(self, payload):
            return {"nonceServer": 111}

    class DummyRMAP:
        nonces = {"alice": ("c", 111)}

        def handle_message2(self, obj):
            return {"result": "ok"}

    # Simulate SQLAlchemy row-like object
    class DummyRow:
        id = 999
        name = "doc.pdf"
        path = "missing.pdf"

    class DummyResult:
        def first(self): return DummyRow()

    class DummyConn:
        def execute(self, q, params):
            return DummyResult()

        def __enter__(self): return self
        def __exit__(self, *a): pass

    class DummyEngine:
        def connect(self): return DummyConn()

    # Env vars
    os.environ["RMAP_CLIENT_KEYS_DIR"] = "d"
    os.environ["RMAP_SERVER_PUB"] = "d"
    os.environ["RMAP_SERVER_PRIV"] = "d"
    os.environ["RMAP_SOURCE_DOC_ID"] = "999"
    os.environ["RMAP_WM_KEY"] = "key"
    os.environ["RMAP_METHOD"] = "toy-eof"

    # Monkeypatch minimal dependencies
    monkeypatch.setattr("rmap_service.IdentityManager", lambda **kw: DummyIdentity())
    monkeypatch.setattr("rmap_service.RMAP", lambda im: DummyRMAP())
    monkeypatch.setattr("rmap_service.WM.get_method", lambda n: True)

    from rmap_service import register_rmap_routes
    register_rmap_routes(app, lambda: DummyEngine())
    client = app.test_client()

    resp = client.post("/api/rmap-get-link", json={"payload": "SGVsbG8="})
    data = resp.get_json()

    assert resp.status_code == 410
    assert "file" in data["error"]

