import sqlite3

from fastapi import APIRouter, Depends, Query

from ..database import get_db
from ..schemas import AskIn
from ..security import get_current_user
from ..services import llm
from ..services.agents import CareerAdvisorAgent, JobMatchingAgent
from .common import get_analysis, get_owned_resume, job_to_dict

router = APIRouter(prefix="/api", tags=["AI Agents"])
matcher = JobMatchingAgent()
advisor = CareerAdvisorAgent()


@router.get("/resumes/{resume_id}/recommendations", summary="Job Matching Agent: ranked job recommendations")
def recommend_jobs(resume_id: int, top_n: int = Query(5, ge=1, le=50),
                   db: sqlite3.Connection = Depends(get_db), user=Depends(get_current_user)):
    resume = get_owned_resume(db, resume_id, user["id"])
    analysis = get_analysis(db, resume_id)
    jobs = [job_to_dict(r) for r in db.execute("SELECT * FROM jobs").fetchall()]
    results = matcher.match(resume["raw_text"], analysis["technical_skills"] + analysis["soft_skills"], jobs, top_n)
    for r in results:
        db.execute("INSERT INTO recommendations(resume_id, job_id, score, explanation) VALUES (?,?,?,?) "
                   "ON CONFLICT(resume_id, job_id) DO UPDATE SET score=excluded.score, "
                   "explanation=excluded.explanation, created_at=CURRENT_TIMESTAMP",
                   (resume_id, r["job"]["id"], r["score"], r["explanation"]))
    db.commit()
    return {"resume_id": resume_id, "recommendations": results}


@router.get("/resumes/{resume_id}/improvements", summary="Career Advisor Agent: missing skills, weaknesses, courses")
def improvements(resume_id: int, target_role: str | None = None,
                 db: sqlite3.Connection = Depends(get_db), user=Depends(get_current_user)):
    resume = get_owned_resume(db, resume_id, user["id"])
    return advisor.improve(get_analysis(db, resume_id), resume["raw_text"], target_role)


@router.post("/career/ask", summary="Ask the Career Advisor Agent a question (RAG)")
def ask(body: AskIn, db: sqlite3.Connection = Depends(get_db), user=Depends(get_current_user)):
    analysis = None
    if body.resume_id is not None:
        get_owned_resume(db, body.resume_id, user["id"])
        analysis = get_analysis(db, body.resume_id)
    result = advisor.answer(body.question, analysis)
    db.execute("INSERT INTO chat_history(user_id, question, answer) VALUES (?,?,?)",
               (user["id"], body.question, result["answer"]))
    db.commit()
    return result


@router.get("/career/history", summary="My previous career questions")
def history(db: sqlite3.Connection = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute("SELECT question, answer, created_at FROM chat_history WHERE user_id = ? "
                      "ORDER BY id DESC LIMIT 20", (user["id"],)).fetchall()
    return [dict(r) for r in rows]


@router.get("/system/status", summary="Shows whether the optional LLM is enabled")
def status():
    return {"llm_enabled": llm.is_available(), "mode": "llm+rag" if llm.is_available() else "rule-based+rag"}
