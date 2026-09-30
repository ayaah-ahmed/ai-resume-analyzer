# 📄 AI Resume Analyzer

Web application that analyzes uploaded resumes (PDF/DOCX), recommends jobs, and gives career advice using **three AI agents** and **Retrieval-Augmented Generation (RAG)**.

**Stack (as required):** Python · FastAPI · SQLite · HTML / CSS / Vanilla JavaScript (no frameworks).

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

* App: http://127.0.0.1:8000  ·  Swagger / OpenAPI docs: http://127.0.0.1:8000/docs
* The SQLite database is created and seeded with 8 sample jobs on first start.
* Try it with `docs/sample_resume.docx`.
* Tests: `pytest -q`

### Optional: LLM mode
Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`. Agents then let an LLM write the final text (summary, match explanation, advice, answers) **using the retrieved RAG context**. Without a key, a deterministic rule-based composer is used and every feature still works (`GET /api/system/status` shows the active mode).

## Architecture

```
static/ (HTML+CSS+JS)  ──REST/JSON──▶  app/routers  ──▶  app/services (agents, RAG, parsing)  ──▶  SQLite
```

| Path | Responsibility |
|---|---|
| `app/main.py` | App factory, DB init + seeding, error handlers, static frontend |
| `app/routers/` | `auth`, `resumes`, `jobs`, `ai` REST endpoints |
| `app/schemas.py` | Pydantic input validation |
| `app/security.py` | PBKDF2 password hashing, bearer-token sessions |
| `app/services/parsing.py` | File validation (type, size, magic bytes, corrupt/encrypted/scanned files) and text extraction |
| `app/services/rag.py` | Knowledge base + from-scratch TF-IDF / cosine retriever |
| `app/services/agents.py` | The three agents |
| `data/` | Knowledge base: skills (+ learning resources), roadmaps (+ certifications), resume guidelines, seed jobs |

## AI agents

| Agent | What it does | How RAG is used |
|---|---|---|
| **Resume Analyzer Agent** | Extracts contact info, technical & soft skills (alias dictionary with word-boundary matching), education, experience (date ranges merged, study periods excluded), and writes a summary | Retrieves roadmap/skill docs to infer best-fit role and ground the summary |
| **Job Matching Agent** | Score = **65 % skill overlap + 35 % TF-IDF cosine similarity** between resume and job description; ranks jobs and explains matched / missing skills | Retrieves learning resources for the first missing skill |
| **Career Advisor Agent** | Missing skills for a target role, resume weaknesses & fixes, certifications, learning resources, roadmap, free-form Q&A | Retrieves top-k documents from the knowledge base **before** generating any answer; sources are returned to the user |

## RAG pipeline
`question/resume → tokenize → TF-IDF vector → cosine similarity over knowledge-base documents (skills, roadmaps, guidelines, jobs) → top-k context → agent composes answer (LLM if configured, otherwise rule-based) → answer + sources`.

## REST API
All endpoints except `register`, `login`, `GET /api/jobs*` and `system/status` need `Authorization: Bearer <token>`. Errors use `{"detail": "<readable message>"}`.

| Method | Endpoint | Description | FR |
|---|---|---|---|
| POST | `/api/auth/register` | Create account → token | FR-1 |
| POST | `/api/auth/login` | Login → token | FR-1 |
| POST | `/api/auth/logout` | Invalidate token | FR-1 |
| GET | `/api/auth/me` | Current user | FR-1 |
| POST | `/api/resumes` | Upload PDF/DOCX (multipart `file`), analysis runs automatically | FR-2, FR-3 |
| GET | `/api/resumes` | List my resumes | FR-2 |
| GET | `/api/resumes/{id}` | Resume + analysis | FR-3 |
| POST | `/api/resumes/{id}/analyze` | Re-run analysis | FR-3 |
| DELETE | `/api/resumes/{id}` | Delete resume | FR-2 |
| GET | `/api/resumes/{id}/recommendations?top_n=5` | Ranked jobs with score + explanation | FR-4 |
| GET | `/api/resumes/{id}/improvements?target_role=` | Missing skills, weaknesses, improvements, certifications, resources | FR-5 |
| POST | `/api/career/ask` | `{question, resume_id?}` → RAG answer + sources | AI |
| GET | `/api/career/history` | My previous questions | AI |
| GET | `/api/jobs` | List / search: `q`, `company`, `location`, `job_type`, `skill`, `limit`, `offset` | FR-6, FR-7 |
| GET | `/api/jobs/{id}` | View job | FR-6 |
| POST | `/api/jobs` | Add job | FR-6 |
| PUT | `/api/jobs/{id}` | Edit job | FR-6 |
| DELETE | `/api/jobs/{id}` | Delete job | FR-6 |
| GET | `/api/system/status` | LLM enabled? | – |

Status codes: `400` empty file · `401` not authenticated · `404` not found · `409` duplicate email · `413` file > 5 MB · `415` unsupported type · `422` invalid input / corrupt file.

## Database
See [`docs/ER_DIAGRAM.md`](docs/ER_DIAGRAM.md): `users`, `sessions`, `resumes`, `analyses`, `jobs`, `recommendations`, `chat_history` (foreign keys with cascade deletes, unique constraints, indexes).

## Requirement coverage

| SRS item | Where |
|---|---|
| FR-1 … FR-7 | `app/routers/*`, UI tabs in `static/` |
| 3 AI agents | `app/services/agents.py` |
| RAG + knowledge base | `app/services/rag.py`, `data/` |
| Input validation / invalid files / error messages | `app/schemas.py`, `app/services/parsing.py`, global handlers in `main.py` |
| Modular code, REST principles | routers / services / schemas separation, resource-based URLs |
| Tests | `tests/` |

## Limitations
* Skill detection uses a curated dictionary (~45 skills); extend `data/skills.json` to add more.
* Scanned (image-only) PDFs are rejected with a clear message; OCR is not included.
* Sessions never expire automatically (kept simple for the course scope).
