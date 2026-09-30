"""Unit tests for parsing, RAG and the three agents (no web server needed)."""
import json
from pathlib import Path

import pytest

from app.services.agents import CareerAdvisorAgent, JobMatchingAgent, ResumeAnalyzerAgent
from app.services.parsing import ResumeParseError, extract_text
from app.services.rag import get_kb

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = (ROOT / "docs" / "sample_resume.docx").read_bytes()


@pytest.fixture(scope="module")
def text():
    return extract_text("sample_resume.docx", SAMPLE)


@pytest.fixture(scope="module")
def analysis(text):
    return ResumeAnalyzerAgent().analyze(text)


@pytest.fixture(scope="module")
def jobs():
    data = json.loads((ROOT / "data" / "jobs_seed.json").read_text(encoding="utf-8"))
    for i, j in enumerate(data, 1):
        j["id"] = i
    return data


@pytest.mark.parametrize("name,data,status", [
    ("cv.txt", b"hello", 415), ("cv.pdf", b"not a pdf", 422), ("cv.docx", b"", 400),
    ("cv.docx", b"PK-broken-zip", 422), ("cv.pdf", b"%PDF-1.4 broken", 422),
])
def test_invalid_files_rejected(name, data, status):
    with pytest.raises(ResumeParseError) as exc:
        extract_text(name, data)
    assert exc.value.status == status


def test_file_too_large():
    with pytest.raises(ResumeParseError) as exc:
        extract_text("cv.pdf", b"%PDF" + b"0" * (5 * 1024 * 1024 + 1))
    assert exc.value.status == 413


def test_analysis_extracts_information(analysis):
    assert analysis["contact"]["email"] == "ahmed.hassan@example.com"
    assert {"Python", "SQL", "Git"} <= set(analysis["technical_skills"])
    assert "Teamwork" in analysis["soft_skills"]
    assert any("Cairo University" in e for e in analysis["education"])
    assert analysis["experience"]["estimated_years"] >= 3  # study years are not counted as experience
    assert analysis["summary"]


def test_ambiguous_words_do_not_create_false_skills():
    a = ResumeAnalyzerAgent().analyze("I will take the rest of the day to relax. " * 5 + "Worked with Java and JavaScript.")
    assert "REST API" not in a["technical_skills"]
    assert {"Java", "JavaScript"} <= set(a["technical_skills"])


def test_rag_retrieves_relevant_docs():
    kb = get_kb()
    top = kb.retrieve("how to become a data scientist", k=3)
    assert any(d.type == "roadmap" and d.title == "Data Scientist" for d in top)
    assert kb.retrieve("fastapi tutorial", k=1)[0].title == "FastAPI"


def test_job_matching_scores_and_orders(text, analysis, jobs):
    results = JobMatchingAgent().match(text, analysis["technical_skills"] + analysis["soft_skills"], jobs)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= s <= 100 for s in scores)
    assert results[0]["explanation"] and results[0]["matched_skills"]
    assert results[-1]["job"]["title"] in ("DevOps Engineer", "Data Analyst")  # least related jobs rank last


def test_career_advisor_improvements(text, analysis):
    out = CareerAdvisorAgent().improve(analysis, text, "backend developer")
    assert out["target_role"] == "Backend Developer"
    assert "FastAPI" in out["missing_skills"]
    assert out["certifications"] and out["learning_resources"] and out["ai_advice"]


def test_career_advisor_answers_from_knowledge_base(analysis):
    out = CareerAdvisorAgent().answer("Which certifications help a DevOps engineer?", analysis)
    assert out["sources"] and out["answer"]
