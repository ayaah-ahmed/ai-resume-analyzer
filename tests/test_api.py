"""End-to-end API tests (requires fastapi + httpx). Uses a temporary SQLite file."""
import io
import os
import tempfile
from pathlib import Path

import pytest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

SAMPLE = (Path(__file__).resolve().parents[1] / "docs" / "sample_resume.docx").read_bytes()
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/register", json={"name": "Test User", "email": "t@example.com", "password": "secret1"})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_auth_flow(client, auth):
    assert client.get("/api/auth/me", headers=auth).json()["email"] == "t@example.com"
    assert client.post("/api/auth/register", json={"name": "Dup", "email": "t@example.com", "password": "secret1"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "t@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "t@example.com", "password": "secret1"}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_validation_errors_are_readable(client):
    r = client.post("/api/auth/register", json={"name": "A", "email": "bad", "password": "1"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)


def test_resume_upload_and_ai_endpoints(client, auth):
    r = client.post("/api/resumes", headers=auth, files={"file": ("cv.docx", io.BytesIO(SAMPLE), DOCX)})
    assert r.status_code == 201
    rid = r.json()["id"]
    assert "Python" in r.json()["analysis"]["technical_skills"]

    rec = client.get(f"/api/resumes/{rid}/recommendations", headers=auth).json()["recommendations"]
    assert rec and rec[0]["score"] >= rec[-1]["score"]
    imp = client.get(f"/api/resumes/{rid}/improvements?target_role=backend", headers=auth).json()
    assert imp["missing_skills"] and imp["certifications"]
    ans = client.post("/api/career/ask", headers=auth, json={"question": "How do I learn FastAPI?", "resume_id": rid}).json()
    assert ans["sources"]

    assert client.delete(f"/api/resumes/{rid}", headers=auth).status_code == 200
    assert client.get(f"/api/resumes/{rid}", headers=auth).status_code == 404


def test_invalid_uploads(client, auth):
    bad = client.post("/api/resumes", headers=auth, files={"file": ("cv.txt", io.BytesIO(b"hello"), "text/plain")})
    assert bad.status_code == 415
    corrupt = client.post("/api/resumes", headers=auth, files={"file": ("cv.pdf", io.BytesIO(b"junk"), "application/pdf")})
    assert corrupt.status_code == 422
    assert client.post("/api/resumes", files={"file": ("cv.pdf", io.BytesIO(b"x"), "application/pdf")}).status_code == 401


def test_jobs_crud_and_search(client, auth):
    assert len(client.get("/api/jobs").json()) >= 8  # seeded
    job = {"title": "QA Engineer", "company": "TestCo", "location": "Cairo", "job_type": "Full-time",
           "description": "Write automated tests and improve quality across the product.", "required_skills": ["Testing", "Python"]}
    created = client.post("/api/jobs", headers=auth, json=job)
    assert created.status_code == 201
    jid = created.json()["id"]
    assert client.get("/api/jobs?q=QA").json()[0]["id"] == jid
    assert client.get("/api/jobs?skill=Testing").json()
    job["title"] = "Senior QA Engineer"
    assert client.put(f"/api/jobs/{jid}", headers=auth, json=job).json()["title"] == "Senior QA Engineer"
    assert client.post("/api/jobs", json=job).status_code == 401
    assert client.delete(f"/api/jobs/{jid}", headers=auth).status_code == 200
    assert client.get(f"/api/jobs/{jid}").status_code == 404
