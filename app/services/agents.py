"""The three AI agents required by the SRS.

Each agent follows the same loop:  perceive (input) -> retrieve (RAG tool) -> reason -> respond.
If an LLM key is configured, the final wording is produced by the LLM using the retrieved
context; otherwise a deterministic rule-based composer produces the answer, so the app always works.
"""
import re
from datetime import date

from . import llm
from .rag import KnowledgeBase, TfIdfIndex, Doc, get_kb

MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
# Short/ambiguous aliases must match with an exact case to avoid false positives ("the rest of ...").
CASE_SENSITIVE = {"rest": "REST", "ml": "ML", "js": "JS", "rag": "RAG", "llm": "LLM", "llms": "LLMs",
                  "cnn": "CNN", "rnn": "RNN", "s3": "S3", "ec2": "EC2", "node": "Node", "k8s": "k8s"}
DEGREE_RE = re.compile(
    r"\b(b\.?sc\.?|bachelor|b\.?eng\.?|m\.?sc\.?|master|m\.?eng\.?|mba|ph\.?d\.?|doctorate|diploma|associate degree)\b", re.I)
INSTITUTION_RE = re.compile(r"\b(university|faculty|institute|college|academy|school of)\b", re.I)
ROLE_RE = re.compile(
    r"\b(developer|engineer|analyst|intern|manager|designer|scientist|consultant|administrator|specialist|architect|"
    r"lead|trainee|teaching assistant|researcher)\b", re.I)
RANGE_RE = re.compile(
    rf"(?:(?:{MONTHS})[a-z]*\.?\s+)?((?:19|20)\d{{2}})\s*(?:-|–|—|to)\s*"
    rf"(?:(?:{MONTHS})[a-z]*\.?\s+)?((?:19|20)\d{{2}}|present|current|now)", re.I)
WEAK_VERBS_RE = re.compile(r"\b(responsible for|worked on|helped with|duties included)\b", re.I)
METRIC_RE = re.compile(r"\d+\s?%|\$\s?\d|\b\d+\+?\s+(users|customers|clients|requests|projects|members|students|reports)\b", re.I)


# ----------------------------------------------------------------------------- helpers
def _pattern(alias: str) -> re.Pattern:
    if alias in CASE_SENSITIVE:
        return re.compile(r"(?<![A-Za-z0-9+#])" + re.escape(CASE_SENSITIVE[alias]) + r"(?![A-Za-z0-9+#])")
    return re.compile(r"(?<![A-Za-z0-9+#])" + re.escape(alias) + r"(?![A-Za-z0-9+#])", re.I)


def extract_skills(text: str, kb: KnowledgeBase) -> tuple[list[str], list[str]]:
    technical, soft = [], []
    for skill in kb.skills:
        if any(_pattern(a).search(text) for a in skill["aliases"]):
            (technical if skill["category"] == "technical" else soft).append(skill["name"])
    return technical, soft


def resume_signals(text: str) -> dict:
    """Structural signals used to judge resume quality."""
    lower = text.lower()
    return {
        "words": len(text.split()),
        "has_summary": bool(re.search(r"\b(summary|profile|objective|about me)\b", lower)),
        "has_projects": bool(re.search(r"\bprojects?\b", lower)),
        "has_metrics": bool(METRIC_RE.search(text)),
        "weak_verbs": len(WEAK_VERBS_RE.findall(text)),
        "has_links": bool(re.search(r"github\.com|linkedin\.com", lower)),
        "has_email": bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)),
        "has_phone": bool(re.search(r"\+?\d[\d\s\-()]{8,}\d", text)),
    }


class Agent:
    name = "agent"

    def __init__(self, kb: KnowledgeBase | None = None):
        self.kb = kb or get_kb()

    def _llm(self, system: str, prompt: str, max_tokens: int = 500) -> str | None:
        return llm.complete(system, prompt, max_tokens)

    @staticmethod
    def _context(docs: list[Doc]) -> str:
        return "\n".join(f"- [{d.type}] {d.title}: {d.text}" for d in docs)


# ----------------------------------------------------------------------------- Agent 1
class ResumeAnalyzerAgent(Agent):
    """Extracts structured information from resume text and writes a summary."""
    name = "Resume Analyzer Agent"

    def analyze(self, text: str) -> dict:
        technical, soft = extract_skills(text, self.kb)
        result = {
            "contact": self._contact(text),
            "technical_skills": technical,
            "soft_skills": soft,
            "education": self._education(text),
            "experience": self._experience(text),
        }
        result["summary"] = self._summary(text, result)
        return result

    # -- extraction tools
    @staticmethod
    def _contact(text: str) -> dict:
        email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
        phone = re.search(r"\+?\d[\d\s\-()]{8,}\d", text)
        github = re.search(r"(?:https?://)?(?:www\.)?github\.com/[\w\-./]+", text, re.I)
        linkedin = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/[\w\-./]+", text, re.I)
        first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        name = first if 0 < len(first.split()) <= 5 and not re.search(r"[@\d]", first) else None
        return {"name": name, "email": email.group(0) if email else None,
                "phone": phone.group(0).strip() if phone else None,
                "github": github.group(0) if github else None,
                "linkedin": linkedin.group(0) if linkedin else None}

    @staticmethod
    def _education(text: str) -> list[str]:
        found: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if 4 < len(line) <= 250 and (DEGREE_RE.search(line) or INSTITUTION_RE.search(line)):
                if line not in found:
                    found.append(line)
        return found[:5]

    @staticmethod
    def _experience(text: str) -> dict:
        this_year = date.today().year
        intervals, ranges = [], []
        for line in text.splitlines():
            if DEGREE_RE.search(line) or INSTITUTION_RE.search(line):
                continue  # study periods are not work experience
            for m in RANGE_RE.finditer(line):
                start = int(m.group(1))
                end_raw = m.group(2).lower()
                end = this_year if end_raw in ("present", "current", "now") else int(end_raw)
                if start <= end <= this_year + 1:
                    intervals.append((start, end))
                    ranges.append(m.group(0).strip())
        years = 0
        last_end = None
        for s, e in sorted(intervals):  # union of intervals so overlapping jobs are not double counted
            if last_end is None or s > last_end:
                years += max(e - s, 0)
                last_end = e
            elif e > last_end:
                years += e - last_end
                last_end = e
        stated = re.search(r"(\d{1,2})\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+)?(?:experience|exp)", text, re.I)
        if stated:
            years = max(years, int(stated.group(1)))
        roles: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if 3 < len(line) <= 120 and ROLE_RE.search(line) and not line.endswith(".") and line not in roles:
                roles.append(line)
        return {"estimated_years": years, "date_ranges": ranges[:8], "roles": roles[:6]}

    # -- summary (LLM with RAG context, or template)
    def _best_fit_role(self, skills: list[str]) -> tuple[str | None, int]:
        best, best_score = None, 0
        for r in self.kb.roadmaps:
            score = len(set(r["skills"]) & set(skills))
            if score > best_score:
                best, best_score = r["role"], score
        return best, best_score

    def _summary(self, text: str, data: dict) -> str:
        skills = data["technical_skills"]
        role, _ = self._best_fit_role(skills + data["soft_skills"])
        years = data["experience"]["estimated_years"]
        name = data["contact"]["name"] or "The candidate"
        exp = f"about {years} year(s) of experience" if years else "no clearly stated work experience"
        edu = data["education"][0] if data["education"] else "education details not clearly listed"
        template = (f"{name} has {exp} and {len(skills)} technical skill(s) detected"
                    f"{' (' + ', '.join(skills[:8]) + ')' if skills else ''}. "
                    f"Education: {edu}. "
                    f"{'The profile is closest to a ' + role + ' path.' if role else 'No clear target role could be inferred.'}")
        context = self.kb.retrieve(" ".join(skills[:10]) or text[:300], k=3, types=("roadmap", "skill"))
        generated = self._llm(
            "You are an expert technical recruiter. Write a concise 3-4 sentence professional summary of the resume. "
            "Be factual; do not invent details.",
            f"Resume text:\n{text[:6000]}\n\nRelevant knowledge:\n{self._context(context)}", 300)
        return generated or template


# ----------------------------------------------------------------------------- Agent 2
class JobMatchingAgent(Agent):
    """Compares a resume with job descriptions and recommends the best matches."""
    name = "Job Matching Agent"
    SKILL_WEIGHT, TEXT_WEIGHT = 0.65, 0.35

    def _job_skills(self, job: dict) -> list[str]:
        if job["required_skills"]:
            return job["required_skills"]
        tech, soft = extract_skills(job["description"], self.kb)
        return tech + soft

    def match(self, resume_text: str, resume_skills: list[str], jobs: list[dict], top_n: int | None = None) -> list[dict]:
        if not jobs:
            return []
        docs = [self.kb.job_doc(j) for j in jobs]
        index = TfIdfIndex(docs)
        similarities = index.scores(resume_text)
        have = {s.lower() for s in resume_skills}
        results = []
        for job, sim in zip(jobs, similarities):
            required = self._job_skills(job)
            matched = [s for s in required if s.lower() in have]
            missing = [s for s in required if s.lower() not in have]
            skill_score = len(matched) / len(required) if required else 0.0
            text_score = min(1.0, sim / 0.6)  # normalise cosine similarity to 0..1
            score = round(100 * (self.SKILL_WEIGHT * skill_score + self.TEXT_WEIGHT * text_score), 1)
            results.append({
                "job": job, "score": score, "matched_skills": matched, "missing_skills": missing,
                "text_similarity": round(sim * 100, 1),
                "explanation": self._explain(job, score, matched, missing, sim),
            })
        results.sort(key=lambda r: r["score"], reverse=True)
        results = results[:top_n] if top_n else results
        for r in results[:3]:  # LLM rewrite only for the top matches (keeps latency low)
            better = self._llm(
                "You are a career coach. In 2-3 sentences explain why this job is or is not a good match. "
                "Use only the facts provided.",
                f"Job: {r['job']['title']} at {r['job']['company']}\nScore: {r['score']}%\n"
                f"Matched skills: {r['matched_skills']}\nMissing skills: {r['missing_skills']}", 200)
            if better:
                r["explanation"] = better
        return results

    def _explain(self, job: dict, score: float, matched: list[str], missing: list[str], sim: float) -> str:
        level = "Strong" if score >= 70 else "Moderate" if score >= 45 else "Low"
        parts = [f"{level} match ({score}%)."]
        if matched:
            parts.append(f"You already have {len(matched)} required skill(s): {', '.join(matched)}.")
        if missing:
            hint = self.kb.retrieve(missing[0], k=1, types=("skill",))
            tip = f" Start with {missing[0]}" + (f" ({hint[0].meta['resources'][0]['title']})." if hint else ".")
            parts.append(f"Missing: {', '.join(missing)}.{tip}")
        else:
            parts.append("You cover all listed requirements.")
        parts.append(f"Resume/job-description text similarity: {round(sim * 100, 1)}%.")
        return " ".join(parts)


# ----------------------------------------------------------------------------- Agent 3
class CareerAdvisorAgent(Agent):
    """Suggests missing skills, certifications, courses and answers career questions."""
    name = "Career Advisor Agent"

    def improve(self, analysis: dict, resume_text: str, target_role: str | None = None) -> dict:
        have = set(analysis["technical_skills"]) | set(analysis["soft_skills"])
        if target_role:
            roadmap = self.kb.find_roadmap(target_role)
        else:
            roadmap = max(self.kb.roadmaps, key=lambda r: len(set(r["skills"]) & have))
        if roadmap is None:
            roadmap = self.kb.roadmaps[0]
        required = roadmap["skills"]
        missing = [s for s in required if s not in have]
        match_pct = round(100 * (len(required) - len(missing)) / len(required), 1)

        weaknesses, improvements = self._review(resume_text, analysis)
        resources = []
        for skill in missing[:6]:
            entry = self.kb.skill_by_name.get(skill)
            if entry:
                resources.append({"skill": skill, "resources": entry["resources"]})

        retrieved = self.kb.retrieve(f"{roadmap['role']} {' '.join(missing)}", k=4)
        fallback = (f"To become a stronger {roadmap['role']} candidate, focus on: {', '.join(missing[:4]) or 'polishing your projects'}. "
                    f"Roadmap: {roadmap['roadmap']}")
        advice = self._llm(
            "You are a friendly career advisor. Give a short, actionable plan (max 6 sentences).",
            f"Target role: {roadmap['role']}\nCandidate skills: {sorted(have)}\nMissing skills: {missing}\n"
            f"Resume weaknesses: {weaknesses}\nKnowledge base:\n{self._context(retrieved)}", 450)
        return {
            "target_role": roadmap["role"], "match_percent": match_pct,
            "missing_skills": missing, "weaknesses": weaknesses, "improvements": improvements,
            "certifications": roadmap["certifications"], "learning_resources": resources,
            "roadmap": roadmap["roadmap"], "ai_advice": advice or fallback,
            "sources": [d.title for d in retrieved],
        }

    def _review(self, text: str, analysis: dict) -> tuple[list[str], list[str]]:
        s = resume_signals(text)
        g = self.kb.guideline_by_check
        weaknesses: list[str] = []
        improvements: list[str] = []

        def flag(problem: str, check: str):
            weaknesses.append(problem)
            improvements.append(g[check]["text"])

        if s["words"] > 900: flag(f"Resume is long ({s['words']} words).", "length")
        elif s["words"] < 150: flag(f"Resume is very short ({s['words']} words) and may lack detail.", "length")
        if not s["has_summary"]: flag("No professional summary/profile section found.", "summary")
        if not s["has_metrics"]: flag("Achievements are not quantified with numbers or percentages.", "metrics")
        if s["weak_verbs"]: flag(f"Weak phrasing found {s['weak_verbs']} time(s), e.g. 'responsible for'.", "verbs")
        if not s["has_projects"]: flag("No projects section found.", "projects")
        if not s["has_links"]: flag("No GitHub or LinkedIn link found.", "links")
        if not (s["has_email"] and s["has_phone"]): flag("Contact details (email and/or phone) are missing.", "contact")
        if not analysis["education"]: flag("Education section could not be detected.", "education")
        if len(analysis["technical_skills"]) < 5: flag("Fewer than 5 technical skills detected; add a clear Skills section.", "keywords")
        if not analysis["experience"]["estimated_years"] and not analysis["experience"]["roles"]:
            weaknesses.append("No work experience detected.")
            improvements.append("Add internships, freelance work, open-source contributions or academic projects to show practical experience.")
        return weaknesses, improvements

    def answer(self, question: str, analysis: dict | None = None) -> dict:
        docs = self.kb.retrieve(question, k=4)
        profile = ""
        if analysis:
            profile = (f"Candidate skills: {', '.join(analysis['technical_skills'] + analysis['soft_skills'])}. "
                       f"Experience: ~{analysis['experience']['estimated_years']} years.")
        generated = self._llm(
            "You are a career advisor. Answer using ONLY the knowledge base context and candidate profile; "
            "if the context is insufficient say so. Keep it under 8 sentences.",
            f"Question: {question}\n{profile}\nKnowledge base:\n{self._context(docs)}", 500)
        if generated:
            answer, mode = generated, "llm+rag"
        elif docs:
            lines = [f"• {d.title}: {d.text}" for d in docs[:3]]
            answer = ("Here is what the knowledge base says about your question:\n" + "\n".join(lines)
                      + (f"\n\nPersonalised note: {profile}" if profile else ""))
            mode = "rag-only"
        else:
            answer = ("I couldn't find anything relevant in my knowledge base. Try asking about a skill, "
                      "a role (e.g. Backend Developer), certifications or resume writing tips.")
            mode = "rag-only"
        return {"answer": answer, "mode": mode, "sources": [{"type": d.type, "title": d.title} for d in docs]}
