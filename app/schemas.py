"""Pydantic request models (input validation)."""
import re

from pydantic import BaseModel, Field, field_validator

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(max_length=120)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("must be a valid email address")
        return v

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class LoginIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def norm_email(cls, v: str) -> str:
        return v.strip().lower()


class JobIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    company: str = Field(min_length=2, max_length=120)
    location: str = Field(default="", max_length=120)
    job_type: str = Field(default="Full-time", max_length=40)
    description: str = Field(min_length=20, max_length=5000)
    required_skills: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("required_skills")
    @classmethod
    def clean_skills(cls, v: list[str]) -> list[str]:
        seen, out = set(), []
        for s in v:
            s = s.strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s)
        return out


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    resume_id: int | None = None
