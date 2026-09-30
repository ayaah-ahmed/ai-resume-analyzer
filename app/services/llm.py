"""Optional LLM client: Gemini, OpenAI or Anthropic (via urllib - no extra dependency).

Providers are tried in order (Gemini -> OpenAI -> Anthropic) and the first one that returns
text wins. If none is configured or all fail, complete() returns None and the agents
fall back to their deterministic rule-based + RAG behaviour.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


def _load_dotenv() -> None:
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def is_available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))


def _post(url: str, headers: dict, payload: dict) -> dict | None:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"content-type": "application/json", **headers}
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        print(f"[LLM] HTTP {exc.code}: {exc.read().decode(errors='ignore')[:300]}")
    except Exception as exc:
        print(f"[LLM] request failed: {exc}")
    return None


def _gemini(system: str, prompt: str, max_tokens: int) -> str | None:
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    config = {"maxOutputTokens": max_tokens}
    if "2.5-flash" in model:
        config["thinkingConfig"] = {"thinkingBudget": 0}  # keep the whole token budget for the answer
    data = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        },
    )
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip() or None
    except Exception:
        return None


def _openai(system: str, prompt: str, max_tokens: int) -> str | None:
    data = _post(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        {
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "max_completion_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        },
    )
    try:
        return (data["choices"][0]["message"]["content"] or "").strip() or None
    except Exception:
        return None


def _anthropic(system: str, prompt: str, max_tokens: int) -> str | None:
    data = _post(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
        {
            "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    try:
        text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        return text.strip() or None
    except Exception:
        return None


def complete(system: str, prompt: str, max_tokens: int = 600) -> str | None:
    providers = (
        ("GEMINI_API_KEY", _gemini),
        ("OPENAI_API_KEY", _openai),
        ("ANTHROPIC_API_KEY", _anthropic),
    )
    for env_name, call in providers:
        if os.getenv(env_name):
            text = call(system, prompt, max_tokens)
            if text:
                return text
    return None