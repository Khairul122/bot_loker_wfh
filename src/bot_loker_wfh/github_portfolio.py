"""Public GitHub repositories as proof-of-work for freelance proposals.

Only public data from the official REST API is read (no token needed) and kept in
a local JSON file, so drafting a proposal never depends on the network.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

PORTFOLIO_PATH = Path("data/github_portfolio.json")
USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
MAX_PAGES = 5  # 500 repos

# What a repo's language says about the work behind it.
LANGUAGE_TERMS = {
    "php": "php laravel web backend api",
    "blade": "laravel php web",
    "dart": "flutter mobile android ios app",
    "typescript": "typescript javascript react nestjs node web frontend backend api",
    "javascript": "javascript react node web frontend",
    "python": "python data machine learning ai automation bot",
    "html": "web website frontend landing",
    "css": "web website frontend ui",
    "vue": "vue javascript web frontend",
    "kotlin": "kotlin android mobile",
    "java": "java android backend",
}
# Indonesian / abbreviated repo-name words mapped to what clients search for.
NAME_TERMS = {
    "ecommerce": "ecommerce shop store marketplace payment",
    "commerce": "ecommerce shop store",
    "marketplace": "marketplace ecommerce",
    "toko": "ecommerce shop store",
    "lms": "lms elearning education course",
    "edu": "education elearning school",
    "education": "education elearning school",
    "siakad": "school academic student management",
    "akademik": "school academic student",
    "keuangan": "finance accounting payment",
    "koperasi": "finance cooperative accounting",
    "iot": "iot arduino esp32 sensor hardware",
    "dashboard": "dashboard admin panel analytics",
    "admin": "admin dashboard panel",
    "backend": "backend api server",
    "api": "api backend",
    "spk": "decision support system",
    "topsis": "decision support algorithm",
    "knn": "machine learning classification",
    "naive": "machine learning classification",
    "bayes": "machine learning classification",
    "lstm": "machine learning ai prediction",
    "cnn": "machine learning ai image",
    "yolo": "ai computer vision object detection",
    "bot": "bot automation telegram",
    "desa": "government village website",
    "portofolio": "portfolio website",
    "portfolio": "portfolio website",
    "game": "game",
    "chat": "chat realtime",
    "maps": "maps location gis",
    "penjualan": "sales pos ecommerce",
    "sales": "sales pos",
    "stok": "inventory stock warehouse",
    "stock": "inventory stock",
    "inventory": "inventory stock warehouse",
    "gudang": "inventory warehouse",
    "inventori": "inventory stock warehouse",
    "persediaan": "inventory stock",
    "barang": "inventory product",
    "kasir": "pos cashier sales",
    "pos": "pos cashier sales",
    "umkm": "small business sales",
    "sekolah": "school education",
    "absensi": "attendance hr",
    "karyawan": "employee hr",
    "rental": "booking rental",
    "booking": "booking reservation",
    "reservasi": "booking reservation",
    "klinik": "clinic health",
    "rs": "hospital health",
    "apotek": "pharmacy health",
    "pembayaran": "payment",
    "payment": "payment",
    "mobile": "mobile app",
    "android": "android mobile app",
    "flutter": "flutter mobile",
    "laravel": "laravel php",
    "react": "react javascript",
    "website": "web website",
}
STOPWORDS = frozenset("a an and the for with to of in on is are be we you i need looking app web".split())


def _get_json(url: str) -> Any:
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "bot-loker-wfh"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_repos(username: str, *, get_json: Callable[[str], Any] = _get_json) -> list[dict]:
    if not USERNAME_RE.match(username or ""):
        raise ValueError("invalid GitHub username")
    repos: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        batch = get_json(
            f"https://api.github.com/users/{username}/repos?per_page=100&sort=updated&page={page}"
        )
        if not isinstance(batch, list) or not batch:
            break
        repos += [
            {
                "name": r.get("name") or "",
                "url": r.get("html_url") or "",
                "language": r.get("language") or "",
                "description": r.get("description") or "",
                "topics": list(r.get("topics") or []),
                "stars": int(r.get("stargazers_count") or 0),
                "updated_at": r.get("pushed_at") or r.get("updated_at") or "",
            }
            for r in batch
            if not r.get("fork") and not r.get("archived")
        ]
        if len(batch) < 100:
            break
    return repos


def sync_portfolio(username: str, path: Path = PORTFOLIO_PATH, **kwargs: Any) -> dict:
    data = {
        "username": username,
        "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repos": fetch_repos(username, **kwargs),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def load_portfolio(path: Path = PORTFOLIO_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"username": "", "synced_at": None, "repos": []}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOPWORDS and len(w) > 1}


def _expand(words: set[str]) -> set[str]:
    out = set(words)
    for word in words:
        out |= _words(NAME_TERMS.get(word, ""))
    return out


def repo_terms(repo: dict) -> tuple[set[str], set[str]]:
    """(what the repo is about, what its language implies): the first counts more."""
    # "JK-WebInventori2-ED" -> "JK Web Inventori 2 ED"
    about = _words(re.sub(r"([a-z])([A-Z0-9])", r"\1 \2", repo["name"]).replace("_", " ").replace("-", " "))
    about |= _words(repo.get("description", "")) | _words(" ".join(repo.get("topics", [])))
    return _expand(about), _words(LANGUAGE_TERMS.get(repo.get("language", "").lower(), ""))


def relevant_repos(portfolio: dict, project_text: str, limit: int = 3) -> list[dict]:
    """Repos whose name/topics (and, less, language) overlap the project most; ties: most recent."""
    wanted = _expand(_words(project_text))
    scored = []
    for repo in portfolio.get("repos", []):
        about, language = repo_terms(repo)
        score = 2 * len(about & wanted) + 0.5 * len(language & wanted) + min(repo.get("stars", 0), 5) * 0.1
        if score >= 2:  # at least one real topic match, not just a shared language
            scored.append((score, repo.get("updated_at", ""), repo))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [repo for _, _, repo in scored[:limit]]
