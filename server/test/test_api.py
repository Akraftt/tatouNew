import sys, os, json, pytest
from io import BytesIO
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DB_USER"] = "tatou"
os.environ["DB_PASSWORD"] = "tatou"
os.environ["DB_HOST"] = "127.0.0.1"
os.environ["DB_NAME"] = "tatou"

import types
mock_wm = types.ModuleType("watermarking_utils")
mock_wm.METHODS = {}
mock_wm.is_watermarking_applicable = lambda *a, **kw: True
mock_wm.apply_watermark = lambda *a, **kw: b"%PDF-fake"
mock_wm.read_watermark = lambda *a, **kw: "secret"
mock_wm.get_method = lambda name: type("M", (), {"get_usage": lambda self: "Mocked method"})()
mock_wm.explore_pdf = lambda *a, **kw: {"pages": 1, "objects": []}
sys.modules["watermarking_utils"] = mock_wm
sys.modules["watermarking_method"] = MagicMock()
sys.modules["rmap_service"] = MagicMock()
from server import create_app

@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app

@pytest.fixture
def client(app):
    return app.test_client()


from itsdangerous import URLSafeTimedSerializer

@pytest.fixture
def auth_header(app):
    # make a signed token just like the server does
    s = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="tatou-auth")
    token = s.dumps({"uid": 1, "login": "testuser", "email": "test@example.com"})
    return {"Authorization": f"Bearer {token}"}

# tests ------------------

def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code in [200, 503, 500]
    assert r.is_json
    data = r.get_json()
    assert "message" in data

#  --------------------------------------------------------------------------------------------------------
#  ---------------------------------------/api/create-user------------------------------------------------
#  --------------------------------------------------------------------------------------------------------

def test_create_user_missing_email(client):
    #arrange
    payload = {
        "login": "testuser",
        "password": "pass123"
    }
    #act
    response = client.post("/api/create-user", json=payload)

    #assert
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data
    assert "required" in data["error"].lower()

# /api/create-user - no login --------------------------------------------------------------------------------------------------------
def test_create_user_missing_login(client):
    #arrange
    payload = {
        "email": "test@example.com",
        "password": "pass123"
    }
    #act
    response = client.post("/api/create-user", json=payload)

    #assert
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data

# /api/create-user - no password --------------------------------------------------------------------------------------------------------

def test_create_user_missing_password(client):
    # arrange 
    payload = {
        "email": "tes3131231t@example.com",
        "login": "testuser"
    }
    # act 
    response = client.post("/api/create-user", json=payload)
    #assert
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data

# /api/create-user - full input --------------------------------------------------------------------------------------------------------
def test_create_user_all_fields_present(client):
    #arrange
    payload = {
        "email": "test@example.com",
        "login": "testuser",
        "password": "pass123"
    }
    #act
    response = client.post("/api/create-user", json=payload)
    #assert
    assert response.status_code in [201, 409, 503]
    if response.status_code == 201:
        data = response.get_json()
        assert "id" in data
        assert data["email"] == payload["email"]
        assert data["login"] == payload["login"]

#  --------------------------------------------------------------------------------------------------------
#  ---------------------------------------/api/login ------------------------------------------------------
#  --------------------------------------------------------------------------------------------------------
# no email 
def test_login_no_email(client):
    #arrange
    payload = {"password": "pass12356677"}
    #act
    response = client.post("/api/login", json=payload)
    #assert
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data

#  --------------------------------------------------------------------------------------------------------
# no password
def test_login_no_password(client):
    #arrange
    payload = {"email": "test@example.com"}
    #act
    response = client.post("/api/login", json=payload)
    #assert
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data

#  --------------------------------------------------------------------------------------------------------
# no input at all
def test_login_empty_fields(client):
    #arrange
    payload = {"email": "", "password": ""}
    #act
    response = client.post("/api/login", json=payload)
    #assert
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data

#  --------------------------------------------------------------------------------------------------------
# valid input
def test_login_valid_input(client):
    #arrange
    payload = {"email": "testmail@example.com", "password": "pass1235567"}
    #act
    response = client.post("/api/login", json=payload)
    #assert
    # no db test 401
    # db unavaliable 503
    # real db 200 (maybe)
    assert response.status_code in [200, 401, 503]


#  --------------------------------------------------------------------------------------------------------
#  --------------------------------------- /api/list-documents --------------------------------------------
#  --------------------------------------------------------------------------------------------------------
def test_list_documents_requires_auth(client):
    # act
    resp = client.get("/api/list-documents")
    # assert
    assert resp.status_code == 401
    data = resp.get_json()
    assert "error" in data

def test_list_documents_with_auth(client, auth_header):
    # act
    resp = client.get("/api/list-documents", headers=auth_header)
    # assert
    assert resp.status_code in [200, 503]
    if resp.status_code == 200:
        body = resp.get_json()
        assert "documents" in body
        assert isinstance(body["documents"], list)

#  --------------------------------------------------------------------------------------------------------
#  --------------------------------------- /api/list-versions ---------------------------------------------
#  --------------------------------------------------------------------------------------------------------

def test_list_versions_missing_id(client, auth_header):
    # act
    resp = client.get("/api/list-versions", headers=auth_header)
    # assert
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert "document id required" in data["error"].lower()

def test_list_versions_with_path_id(client, auth_header):
    # act
    resp = client.get("/api/list-versions/1", headers=auth_header)
    # assert
    # 200 if DB works, 503 if DB blew up...
    assert resp.status_code in [200, 503]
    if resp.status_code == 200:
        data = resp.get_json()
        assert "versions" in data
        assert isinstance(data["versions"], list)


#  --------------------------------------------------------------------------------------------------------
#  --------------------------------------- /api/get-version/<link> ----------------------------------------
#  --------------------------------------------------------------------------------------------------------
def test_get_version_unknown_link(client):
    # act
    resp = client.get("/api/get-version/some-nonexistent-link-xyz")
    # assert
    assert resp.status_code in [404, 503]  
    # 404 if no link
    # 503 if db says no
    if resp.status_code == 404:
        data = resp.get_json()
        assert "error" in data
        assert "not found" in data["error"].lower()

#  --------------------------------------------------------------------------------------------------------
#  --------------------------------------- /api/get-watermarking-methods ----------------------------------
#  --------------------------------------------------------------------------------------------------------
def test_get_watermarking_methods_public(client):
    # act
    resp = client.get("/api/get-watermarking-methods")
    # assert
    assert resp.status_code == 200
    data = resp.get_json()
    assert "methods" in data
    assert "count" in data
    assert isinstance(data["methods"], list)

#  --------------------------------------------------------------------------------------------------------
#  --------------------------------------- /api/create-watermark ------------------------------------------
#  --------------------------------------------------------------------------------------------------------

def test_create_watermark_missing_document_id(client, auth_header):
    #arrange
    payload = {
        "method": "toy-eof",
        "intended_for": "bob",
        "secret": "123",
        "key": "course-demo-key"
    }
    #act
    resp = client.post("/api/create-watermark", headers=auth_header, json=payload)
    #assert
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    err = data["error"].lower()
    assert (
        "document id required" in err
        or "document_id (int) is required" in err
        or "document_id" in err
    )

def test_create_watermark_missing_key(client, auth_header):
    payload = {
        "method": "",
        "secret": "hi"
        # no key - gone
    }
    # act
    resp = client.post("/api/create-watermark/1", headers=auth_header, json=payload)
    # assert
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data

#  --------------------------------------------------------------------------------------------------------
#  --------------------------------------- /api/read-watermark --------------------------------------------
#  --------------------------------------------------------------------------------------------------------

def test_read_watermark_missing_document_id(client, auth_header):
    #arrange
    payload = {
        "method": "toy-eof",
        "key": "k123"
    }
    #act
    resp = client.post("/api/read-watermark", headers=auth_header, json=payload)
    #assert
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    err = data["error"].lower()
    assert (
        "document id required" in err
        or "document_id (int) is required" in err
        or "document_id" in err
    )

def test_read_watermark_missing_fields(client, auth_header):
    #arrange
    payload = {
        # no method
        "key": "k123"
    }
    #act
    resp = client.post("/api/read-watermark/1", headers=auth_header, json=payload)
    #assert
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data

#  --------------------------------------------------------------------------------------------------------
#  --------------------------------------- /api/delete-document/<id> --------------------------------------
#  --------------------------------------------------------------------------------------------------------

def test_delete_document_not_found(client):
    # act
    resp = client.delete("/api/delete-document/99999")
    # assert
    # 404 if row doesn't exist, 503 if DB error
    assert resp.status_code in [404, 503]
    if resp.status_code == 404:
        data = resp.get_json()
        assert "error" in data
        assert "not found" in data["error"].lower()