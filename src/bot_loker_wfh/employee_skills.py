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


def _employee_sources(employee_id: str) -> list[Path]:
    if not isinstance(employee_id, str) or employee_id not in EMPLOYEE_IDS or not _ID_RE.fullmatch(employee_id):
        raise KeyError(employee_id)
    emp_dir = (SKILLS_DIR / employee_id).resolve()
    single_file = (SKILLS_DIR / f"{employee_id}.md").resolve()
    
    if emp_dir.is_dir():
        files = sorted(emp_dir.glob("*.md"))
        if files:
            return files
    if single_file.is_file():
        return [single_file]
    raise KeyError(employee_id)


def load_employee_skills(employee_id: str) -> str:
    """Read allowlisted employee skills, scanning employee folder or single file."""
    sources = _employee_sources(employee_id)
    combined_sig = tuple((p.stat().st_mtime_ns, p.stat().st_size) for p in sources)
    
    with _CACHE_LOCK:
        cached = _CACHE.get(employee_id)
        if cached and cached[: len(combined_sig)] == combined_sig:
            return cached[-1]
        
        parts = []
        for p in sources:
            content = p.read_text(encoding="utf-8-sig").strip()
            if content:
                parts.append(f"### Skill Source: {p.stem}\n{content}")
        
        full_content = "\n\n---\n\n".join(parts)
        if len(full_content.encode("utf-8")) > MAX_MARKDOWN_BYTES:
            full_content = full_content[:MAX_MARKDOWN_BYTES]
        _CACHE[employee_id] = (*combined_sig, full_content)
        return full_content


def all_employee_skills() -> dict[str, str]:
    """Return available local skills for every allowlisted employee."""
    return {employee_id: load_employee_skills(employee_id) for employee_id in sorted(EMPLOYEE_IDS)}
