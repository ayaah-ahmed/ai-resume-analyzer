import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_db
from ..schemas import JobIn
from ..security import get_current_user
from .common import job_to_dict

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.get("", summary="List / search jobs (q, company, location, job_type, skill)")
def search_jobs(q: str | None = None, company: str | None = None, location: str | None = None,
                job_type: str | None = None, skill: str | None = None,
                limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                db: sqlite3.Connection = Depends(get_db)):
    sql, params = "SELECT * FROM jobs WHERE 1=1", []
    if q:
        sql += " AND (title LIKE ? OR description LIKE ? OR company LIKE ?)"
        params += [f"%{q}%"] * 3
    if company:
        sql += " AND company LIKE ?"; params.append(f"%{company}%")
    if location:
        sql += " AND location LIKE ?"; params.append(f"%{location}%")
    if job_type:
        sql += " AND job_type LIKE ?"; params.append(job_type)
    if skill:
        sql += " AND required_skills_json LIKE ?"; params.append(f'%"{skill}"%')
    rows = db.execute(sql + " ORDER BY id DESC LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
    return [job_to_dict(r) for r in rows]


@router.get("/{job_id}", summary="Get one job")
def get_job(job_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Job not found.")
    return job_to_dict(row)


@router.post("", status_code=201, summary="Add a job")
def add_job(body: JobIn, db: sqlite3.Connection = Depends(get_db), user=Depends(get_current_user)):
    cur = db.execute(
        "INSERT INTO jobs(title, company, location, job_type, description, required_skills_json, created_by) "
        "VALUES (?,?,?,?,?,?,?)",
        (body.title, body.company, body.location, body.job_type, body.description,
         json.dumps(body.required_skills), user["id"]))
    db.commit()
    return get_job(cur.lastrowid, db)


@router.put("/{job_id}", summary="Edit a job")
def edit_job(job_id: int, body: JobIn, db: sqlite3.Connection = Depends(get_db), _user=Depends(get_current_user)):
    get_job(job_id, db)
    db.execute("UPDATE jobs SET title=?, company=?, location=?, job_type=?, description=?, required_skills_json=? "
               "WHERE id=?", (body.title, body.company, body.location, body.job_type, body.description,
                              json.dumps(body.required_skills), job_id))
    db.commit()
    return get_job(job_id, db)


@router.delete("/{job_id}", summary="Delete a job")
def delete_job(job_id: int, db: sqlite3.Connection = Depends(get_db), _user=Depends(get_current_user)):
    get_job(job_id, db)
    db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    db.commit()
    return {"message": "Job deleted."}
