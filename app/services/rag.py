"""Retrieval-Augmented Generation: knowledge base + a from-scratch TF-IDF retriever.

Knowledge base = skill descriptions, career roadmaps, resume-writing guidelines,
learning resources (attached to skills) and job descriptions (seed data + jobs in the DB).
"""
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

STOPWORDS = set(
    "a an and are as at be by for from has have in is it its of on or that the this to was were will with your you our we "
    "i my me using use used can should about into their they them not but if then than also more most such".split()
)


@dataclass
class Doc:
    id: str
    type: str  # skill | roadmap | guideline | job
    title: str
    text: str
    meta: dict = field(default_factory=dict)


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9+#.]*", text.lower())
    tokens = [t.rstrip(".") for t in tokens]
    return [t for t in tokens if t and t not in STOPWORDS]


class TfIdfIndex:
    def __init__(self, docs: list[Doc]):
        self.docs = docs
        token_lists = [tokenize(f"{d.title} {d.title} {d.text}") for d in docs]
        n = len(docs)
        df: Counter = Counter()
        for tokens in token_lists:
            df.update(set(tokens))
        self.idf = {w: math.log((1 + n) / (1 + c)) + 1 for w, c in df.items()}
        self.vectors = [self._vectorize(t) for t in token_lists]

    def _vectorize(self, tokens: list[str]) -> dict[str, float]:
        tf = Counter(t for t in tokens if t in self.idf)
        vec = {w: (1 + math.log(c)) * self.idf[w] for w, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {w: v / norm for w, v in vec.items()}

    @staticmethod
    def _dot(a: dict[str, float], b: dict[str, float]) -> float:
        if len(a) > len(b):
            a, b = b, a
        return sum(v * b.get(w, 0.0) for w, v in a.items())

    def scores(self, query: str) -> list[float]:
        q = self._vectorize(tokenize(query))
        return [self._dot(q, v) for v in self.vectors]

    def search(self, query: str, k: int = 4, types: tuple[str, ...] | None = None) -> list[tuple[Doc, float]]:
        ranked = sorted(zip(self.docs, self.scores(query)), key=lambda x: x[1], reverse=True)
        out = [(d, s) for d, s in ranked if s > 0 and (types is None or d.type in types)]
        return out[:k]


class KnowledgeBase:
    def __init__(self):
        self.skills: list[dict] = json.loads((DATA_DIR / "skills.json").read_text(encoding="utf-8"))
        self.roadmaps: list[dict] = json.loads((DATA_DIR / "roadmaps.json").read_text(encoding="utf-8"))
        self.guidelines: list[dict] = json.loads((DATA_DIR / "guidelines.json").read_text(encoding="utf-8"))
        self.skill_by_name = {s["name"]: s for s in self.skills}
        self.guideline_by_check = {g["check"]: g for g in self.guidelines}
        self._static_docs = self._build_static_docs()
        self._static_index = TfIdfIndex(self._static_docs)

    def _build_static_docs(self) -> list[Doc]:
        docs: list[Doc] = []
        for s in self.skills:
            res = "; ".join(r["title"] for r in s["resources"])
            docs.append(Doc(f"skill:{s['name']}", "skill", s["name"],
                            f"{s['description']} Category: {s['category']}. Learning resources: {res}.", s))
        for r in self.roadmaps:
            text = (f"Career roadmap for {r['role']}. Key skills: {', '.join(r['skills'])}. "
                    f"Certifications: {', '.join(r['certifications'])}. Steps: {r['roadmap']}")
            docs.append(Doc(f"roadmap:{r['role']}", "roadmap", r["role"], text, r))
        for g in self.guidelines:
            docs.append(Doc(f"guideline:{g['id']}", "guideline", "Resume writing guideline", g["text"], g))
        return docs

    @staticmethod
    def job_doc(job: dict) -> Doc:
        text = f"{job['title']} at {job['company']}. {job['description']} Required skills: {', '.join(job['required_skills'])}."
        return Doc(f"job:{job['id']}", "job", job["title"], text, job)

    def retrieve(self, query: str, k: int = 4, types: tuple[str, ...] | None = None,
                 jobs: list[dict] | None = None) -> list[Doc]:
        """Retrieve top-k relevant knowledge-base documents for a query."""
        if jobs:
            index = TfIdfIndex(self._static_docs + [self.job_doc(j) for j in jobs])
        else:
            index = self._static_index
        return [d for d, _ in index.search(query, k, types)]

    def find_roadmap(self, role: str) -> dict | None:
        role_l = role.lower().strip()
        for r in self.roadmaps:
            if role_l == r["role"].lower() or role_l in [a.lower() for a in r["aliases"]]:
                return r
        for r in self.roadmaps:
            if role_l in r["role"].lower() or any(a in role_l for a in r["aliases"]):
                return r
        hits = self.retrieve(role, k=1, types=("roadmap",))
        return hits[0].meta if hits else None


_kb: KnowledgeBase | None = None


def get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb
