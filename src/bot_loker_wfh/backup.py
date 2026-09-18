"""Local SQLite backup and restore helpers."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path


def backup_database(source_path: Path, backup_path: Path) -> Path:
    source_path = Path(source_path)
    backup_path = Path(backup_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Database not found: {source_path}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source_path)) as source, closing(
        sqlite3.connect(backup_path)
    ) as target:
        source.backup(target)
    return backup_path


def restore_database(backup_path: Path, target_path: Path) -> Path:
    backup_path = Path(backup_path)
    target_path = Path(target_path)
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(backup_path)) as source, closing(
        sqlite3.connect(target_path)
    ) as target:
        source.backup(target)
    return target_path
