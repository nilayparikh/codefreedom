"""LiteLLM proxy client for generating commit messages and PR descriptions."""

from __future__ import annotations

import re
from pathlib import Path

import httpx

from codefreedom.log import eprint, tag


def _load_proxy_settings(work_dir: Path | None = None) -> tuple[str, str]:
    """Load proxy URL and API key using the canonical env loader.

    Returns (proxy_url, api_key).
    """
    from codefreedom.env_loader import get_env

    if work_dir is None:
        work_dir = Path.cwd()

    env = get_env(work_dir, component=None, verbose=False)

    proxy_url = env.get("LITELLM_BASE_URL", "http://localhost:4000")
    api_key = env.get("LITELLM_MASTER_KEY", "")

    return proxy_url.rstrip("/"), api_key


def generate_message(
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 500,
    temperature: float = 0.3,
    work_dir: Path | None = None,
) -> str | None:
    """Call the LiteLLM proxy and return the response text, or None on failure."""
    proxy_url, api_key = _load_proxy_settings(work_dir)
    chat_url = proxy_url + "/v1/chat/completions"

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = httpx.post(
            chat_url,
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        message = data["choices"][0]["message"]
        content = message.get("content")
        if not content:
            eprint(f"{tag('ERROR')} LLM returned empty response. Try a different model.")
            return None
        return content.strip()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            eprint(
                f"{tag('ERROR')} Proxy authentication failed. "
                "Check your profile has LITELLM_MASTER_KEY set."
            )
        else:
            eprint(f"{tag('ERROR')} LLM call failed: {e}")
        return None
    except Exception as e:
        error_str = str(e).lower()
        if "connect" in error_str or "connection" in error_str:
            eprint(
                f"{tag('ERROR')} LiteLLM proxy not running at {proxy_url}. "
                "Start it with: cf r px start"
            )
        else:
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
