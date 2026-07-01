"""Test setup for the cbmem package.

Adds ``docker/codebase-memory/src`` to ``sys.path`` so the
``codebase_memory`` package can be imported directly by tests. In
production the same path is added by the shim at
``src/codefreedom/tools/codebase_memory.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CBMEM_SRC = _REPO_ROOT / "docker" / "codebase-memory" / "src"
if str(_CBMEM_SRC) not in sys.path:
    sys.path.insert(0, str(_CBMEM_SRC))
