"""AI Resume Analyzer - FastAPI application entry point.

Run:  uvicorn app.main:app --reload      then open http://127.0.0.1:8000
API docs (Swagger): http://127.0.0.1:8000/docs
"""
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .database import connect, init_db
from .routers import ai, auth, jobs, resumes

ROOT = Path(__file__).resolve().parents[1]


def seed_jobs() -> None:
    conn = connect()
    try:
        if conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0:
            for j in json.loads((ROOT / "data" / "jobs_seed.json").read_text(encoding="utf-8")):
                conn.execute(
                    "INSERT INTO jobs(title, company, location, job_type, description, required_skills_json) "
                    "VALUES (?,?,?,?,?,?)",
                    (j["title"], j["company"], j["location"], j["job_type"], j["description"],
                     json.dumps(j["required_skills"])))
            conn.commit()
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_jobs()
    yield


app = FastAPI(title="AI Resume Analyzer", version="1.0.0", lifespan=lifespan,
              description="Analyze resumes, match jobs and get career advice using AI agents + RAG.")


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    """Turn Pydantic errors into one readable message."""
    msgs = []
    for e in exc.errors():
        field = ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path"))
        msgs.append(f"{field}: {e['msg']}" if field else e["msg"])
    return JSONResponse(status_code=422, content={"detail": "; ".join(msgs)})


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Unexpected server error. Please try again."})


for r in (auth.router, resumes.router, jobs.router, ai.router):
    app.include_router(r)

# Frontend (plain HTML/CSS/JS) served from the same origin; must be mounted last.
app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
