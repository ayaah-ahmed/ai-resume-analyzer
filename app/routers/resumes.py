import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..database import get_db
from ..security import get_current_user
from ..services.agents import ResumeAnalyzerAgent
from ..services.parsing import ResumeParseError, extract_text
from .common import analysis_to_dict, get_owned_resume, save_analysis

router = APIRouter(prefix="/api/resumes", tags=["Resumes"])
analyzer = ResumeAnalyzerAgent()


def _resume_dict(row: sqlite3.Row, analysis: dict | None = None, include_text: bool = False) -> dict:
    d = {"id": row["id"], "filename": row["filename"], "uploaded_at": row["uploaded_at"], "analysis": analysis}
    if include_text:
        d["raw_text"] = row["raw_text"]
    return d


@router.post("", status_code=201, summary="Upload a PDF/DOCX resume (analysis runs automatically)")
async def upload_resume(file: UploadFile = File(...), db: sqlite3.Connection = Depends(get_db),
                        user=Depends(get_current_user)):
    content = await file.read()
    try:
        text = extract_text(file.filename or "", content)
    except ResumeParseError as exc:
        raise HTTPException(exc.status, str(exc))
    cur = db.execute("INSERT INTO resumes(user_id, filename, raw_text) VALUES (?,?,?)",
                     (user["id"], file.filename, text))
    db.commit()
    analysis = analyzer.analyze(text)
    save_analysis(db, cur.lastrowid, analysis)
    return _resume_dict(get_owned_resume(db, cur.lastrowid, user["id"]), analysis)


@router.get("", summary="List my resumes")
def list_resumes(db: sqlite3.Connection = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute("SELECT * FROM resumes WHERE user_id = ? ORDER BY id DESC", (user["id"],)).fetchall()
    return [_resume_dict(r) for r in rows]


@router.get("/{resume_id}", summary="Resume details with analysis")
def get_resume(resume_id: int, db: sqlite3.Connection = Depends(get_db), user=Depends(get_current_user)):
    row = get_owned_resume(db, resume_id, user["id"])
    a = analysis_to_dict(db.execute("SELECT * FROM analyses WHERE resume_id = ?", (resume_id,)).fetchone())
    return _resume_dict(row, a, include_text=True)


@router.post("/{resume_id}/analyze", summary="Re-run the Resume Analyzer Agent")
def reanalyze(resume_id: int, db: sqlite3.Connection = Depends(get_db), user=Depends(get_current_user)):
    row = get_owned_resume(db, resume_id, user["id"])
    analysis = analyzer.analyze(row["raw_text"])
    save_analysis(db, resume_id, analysis)
    return _resume_dict(row, analysis)


@router.delete("/{resume_id}", summary="Delete a resume")
def delete_resume(resume_id: int, db: sqlite3.Connection = Depends(get_db), user=Depends(get_current_user)):
    get_owned_resume(db, resume_id, user["id"])
    db.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
    db.commit()
    return {"message": "Resume deleted."}
