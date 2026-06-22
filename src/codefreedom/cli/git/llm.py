"""LiteLLM proxy client for generating commit messages and PR descriptions."""

from __future__ import annotations

import re

import httpx

from codefreedom.log import eprint, tag

_PROXY_URL = "http://localhost:4000/v1/chat/completions"


def generate_message(
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 500,
    temperature: float = 0.3,
) -> str | None:
    """Call the LiteLLM proxy and return the response text, or None on failure."""
    try:
        resp = httpx.post(
            _PROXY_URL,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except httpx.ConnectError:
        eprint(
            f"{tag('ERROR')} LiteLLM proxy not running. "
            "Start it with: cf r px start"
        )
        return None
    except Exception as e:
        eprint(f"{tag('ERROR')} LLM call failed: {e}")
        return None


_COMMIT_TYPE_RE = re.compile(
    r"^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)"
    r"(?:\((\w+)\))?\s*:\s*(.+)$",
    re.MULTILINE,
)


def parse_commit_response(text: str) -> dict[str, str]:
    """Parse LLM response into {type, scope, description}."""
    m = _COMMIT_TYPE_RE.search(text.strip())
    if m:
        return {
            "type": m.group(1),
            "scope": m.group(2) or "",
            "description": m.group(3).strip(),
        }
    lines = text.strip().split("\n")
    first_line = lines[0].strip() if lines else text.strip()
    return {
        "type": "chore",
        "scope": "",
        "description": first_line[:72],
    }


_PR_TITLE_RE = re.compile(
    r"^TITLE:\s*(.+)$",
    re.MULTILINE,
)

_PR_BODY_RE = re.compile(
    r"^BODY:\s*\n(.+)",
    re.MULTILINE | re.DOTALL,
)


def parse_pr_response(text: str) -> dict[str, str]:
    """Parse LLM response into {title, body}."""
    title = ""
    body = text.strip()

    m_title = _PR_TITLE_RE.search(text)
    if m_title:
        title = m_title.group(1).strip()

    m_body = _PR_BODY_RE.search(text)
    if m_body:
        body = m_body.group(1).strip()

    if not title:
        lines = text.strip().split("\n")
        title = lines[0].strip() if lines else "Update"

    return {"title": title, "body": body}
