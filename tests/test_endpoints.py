import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.routers.documents import sanitize_filename
from app.security import create_access_token


@pytest.fixture
def client():
    # Use TestClient with explicit base_url matching allowed hosts
    with TestClient(app, base_url="http://localhost") as c:
        yield c


@pytest.fixture
def auth_header():
    token = create_access_token(data={"sub": "test_operator"})
    return {"Authorization": f"Bearer {token}"}


def test_security_headers_present(client):
    response = client.get("/health")
    assert response.status_code == 200
    headers = response.headers

    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert "Strict-Transport-Security" in headers
    assert "Content-Security-Policy" in headers
    assert "X-Process-Time" in headers


def test_sanitize_filename():
    assert sanitize_filename("../../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32.dll") == "system32.dll"
    assert sanitize_filename("my document (1) #final.pdf") == "my_document__1___final.pdf"


def test_unauthorized_upload(client):
    response = client.post(
        "/upload",
        files={"file": ("test.pdf", b"%PDF-1.4 dummy", "application/pdf")},
        data={"reference_id": "REF_123"},
    )
    # Must fail without JWT
    assert response.status_code == 401


def test_unauthorized_documents_fetch(client):
    response = client.get("/documents/REF_123")
    assert response.status_code == 401


def test_unauthorized_status_fetch(client):
    response = client.get("/documents/REF_123/status")
    assert response.status_code == 401
