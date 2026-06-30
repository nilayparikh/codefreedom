"""LiteLLM proxy client for generating commit messages and PR descriptions."""

from __future__ import annotations

import os
import re
from pathlib import Path

import httpx

from codefreedom.log import eprint, tag


def _load_proxy_settings(work_dir: Path | None = None) -> tuple[str, str]:
    """Load proxy URL and API key using the canonical env loader.

    Returns (proxy_url, api_key).
    """
    from codefreedom.config.runtime import apply_cf_cli_overrides

    if work_dir is None:
        work_dir = Path.cwd()

    env = apply_cf_cli_overrides(dict(os.environ))

    from codefreedom.core.agent_runtime import resolve_proxy_api_key

    proxy_url = env.get("PROXY_BASE_URL", "http://localhost:4000")
    api_key = resolve_proxy_api_key(env)

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
                "Check your profile has PROXY_API_KEY set."
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
    r"(?:\(([a-zA-Z0-9_\-/]+)\))?\s*:\s*(.+)$",
    re.MULTILINE,
)

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_UNCLOSED_THINK_RE = re.compile(r"<think>[^\n]*\n?", re.MULTILINE)
_STRAY_CLOSE_RE = re.compile(r"</think>", re.MULTILINE)
_CHAT_TOKEN_RE = re.compile(
    r"^\s*\[?(user|assistant|system|human|ai)\]?\s*[:>]\s*",
    re.IGNORECASE | re.MULTILINE,
)
_LEADING_LABELS_RE = re.compile(
    r"^\s*(commit message|here'?s?\s+(the|my)\s+commit(\s+message)?|"
    r"here'?s?\s+the\s+suggested\s+message|"
    r"suggested\s+commit(\s+message)?|"
    r"output|response|answer)\s*[:>]\s*\n?",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_think_blocks(text: str) -> str:
    """Remove `` blocks (and stray close tags) from a model response.

    Reasoning models like Qwen3 emit their chain-of-thought inside
    `` tags, and some of those tags leak into the ``content``
    field. The parser needs the bare commit message / PR body.
    """
    if not text:
        return text
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _UNCLOSED_THINK_RE.sub("", cleaned)
    cleaned = _STRAY_CLOSE_RE.sub("", cleaned)
    return cleaned.strip()


def _strip_chat_tokens(text: str) -> str:
    """Strip stray chat-format tokens like ``[user]:`` or ``[assistant]:``.

    Some chat-tuned models emit the role tag as a prefix when the
    upstream system prompt leaks. Removing the prefix lets the parser
    see the actual answer.
    """
    if not text:
        return text
    return _CHAT_TOKEN_RE.sub("", text)


def _strip_leading_labels(text: str) -> str:
    """Strip conversational prefixes like ``Commit message:`` from a response.

    The model is told to output only the message, but a chat-tuned
    model will sometimes wrap the answer in a label.
    """
    if not text:
        return text
    cleaned = _LEADING_LABELS_RE.sub("", text, count=1)
    return cleaned.strip()


def clean_response(text: str) -> str:
    """Apply all response cleanups: think blocks, chat tokens, labels.

    Returns the bare answer text. Idempotent and safe to call on
    already-clean input.
    """
    cleaned = _strip_think_blocks(text)
    cleaned = _strip_chat_tokens(cleaned)
    cleaned = _strip_leading_labels(cleaned)
    return cleaned.strip()


def parse_commit_response(text: str) -> dict[str, str]:
    """Parse LLM response into {type, scope, description}.

    The response is first cleaned of `` reasoning blocks,
    stray chat tokens, and conversational prefixes before parsing.
    """
    cleaned = clean_response(text)
    if not cleaned:
        return {"type": "chore", "scope": "", "description": ""}
    cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?|```$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\$(?=(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)\b)", "", cleaned)
    cleaned = re.sub(r"(?<=\()\$", "", cleaned)
    cleaned = re.sub(r"\$(?=\()", "", cleaned)
    m = _COMMIT_TYPE_RE.search(cleaned)
    if m:
        description = re.sub(
            r"^\$(?=(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)\b)\s*",
            "",
            m.group(3).strip(),
        )
        description = re.sub(
            r"^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)\s+",
            "",
            description,
        )
        return {
            "type": m.group(1),
            "scope": m.group(2) or "",
            "description": description,
        }
    lines = cleaned.split("\n")
    first_line = lines[0].strip() if lines else cleaned
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
    """Parse LLM response into {title, body}.

    The response is first cleaned of `` reasoning blocks,
    stray chat tokens, and conversational prefixes before parsing.
    """
    cleaned = clean_response(text)
    title = ""
    body = cleaned

    m_title = _PR_TITLE_RE.search(cleaned)
    if m_title:
        title = m_title.group(1).strip()

    m_body = _PR_BODY_RE.search(cleaned)
    if m_body:
        body = m_body.group(1).strip()

    if not title:
        lines = cleaned.split("\n")
        title = lines[0].strip() if lines else "Update"

    return {"title": title, "body": body}
