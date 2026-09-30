"""Shared helpers for routers."""
import json
import sqlite3

from fastapi import HTTPException


def job_to_dict(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "title": row["title"], "company": row["company"], "location": row["location"],
            "job_type": row["job_type"], "description": row["description"],
            "required_skills": json.loads(row["required_skills_json"]), "created_at": row["created_at"]}


def analysis_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {"contact": json.loads(row["contact_json"]),
            "technical_skills": json.loads(row["technical_skills_json"]),
            "soft_skills": json.loads(row["soft_skills_json"]),
            "education": json.loads(row["education_json"]),
            "experience": json.loads(row["experience_json"]),
            "summary": row["summary"]}


def get_owned_resume(db: sqlite3.Connection, resume_id: int, user_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM resumes WHERE id = ? AND user_id = ?", (resume_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Resume not found.")
    return row


def get_analysis(db: sqlite3.Connection, resume_id: int) -> dict:
    data = analysis_to_dict(db.execute("SELECT * FROM analyses WHERE resume_id = ?", (resume_id,)).fetchone())
    if data is None:
        raise HTTPException(404, "This resume has not been analyzed yet.")
    return data


def save_analysis(db: sqlite3.Connection, resume_id: int, a: dict) -> None:
    db.execute(
        """INSERT INTO analyses(resume_id, contact_json, technical_skills_json, soft_skills_json,
                                education_json, experience_json, summary)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(resume_id) DO UPDATE SET contact_json=excluded.contact_json,
             technical_skills_json=excluded.technical_skills_json, soft_skills_json=excluded.soft_skills_json,
             education_json=excluded.education_json, experience_json=excluded.experience_json,
             summary=excluded.summary, created_at=CURRENT_TIMESTAMP""",
        (resume_id, json.dumps(a["contact"]), json.dumps(a["technical_skills"]), json.dumps(a["soft_skills"]),
         json.dumps(a["education"]), json.dumps(a["experience"]), a["summary"]))
    db.commit()
