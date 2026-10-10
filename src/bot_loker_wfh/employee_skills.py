"""Safe local markdown skills for real office employees."""

from __future__ import annotations

import re
from pathlib import Path
from threading import RLock

from .office_desk import ROLES

EMPLOYEE_IDS = frozenset(ROLES)
SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills" / "employees"
MAX_MARKDOWN_BYTES = 32 * 1024
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_CACHE: dict[str, tuple[int, int, str]] = {}
_CACHE_LOCK = RLock()


def _path(employee_id: str) -> Path:
    if not isinstance(employee_id, str) or employee_id not in EMPLOYEE_IDS or not _ID_RE.fullmatch(employee_id):
        raise KeyError(employee_id)
    candidate = (SKILLS_DIR / f"{employee_id}.md").resolve()
    root = SKILLS_DIR.resolve()
    if candidate.parent != root or candidate.suffix != ".md":
        raise ValueError("invalid employee skills path")
    return candidate


def load_employee_skills(employee_id: str) -> str:
    """Read one allowlisted employee file, caching unchanged files by mtime and size."""
    path = _path(employee_id)
    try:
        stat = path.stat()
    except (FileNotFoundError, OSError) as error:
        raise KeyError(employee_id) from error
    if not path.is_file() or stat.st_size > MAX_MARKDOWN_BYTES:
        raise ValueError("employee skills file is invalid")
    signature = (stat.st_mtime_ns, stat.st_size)
    with _CACHE_LOCK:
        cached = _CACHE.get(employee_id)
        if cached and cached[:2] == signature:
            return cached[2]
        content = path.read_text(encoding="utf-8")
        if len(content.encode("utf-8")) > MAX_MARKDOWN_BYTES:
            raise ValueError("employee skills file is invalid")
        _CACHE[employee_id] = (*signature, content)
        return content


def all_employee_skills() -> dict[str, str]:
    """Return available local skills for every allowlisted employee."""
    return {employee_id: load_employee_skills(employee_id) for employee_id in sorted(EMPLOYEE_IDS)}
