"""MySQL Database layer and automatic migration from legacy SQLite for loker-house."""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Sequence

import pymysql
import pymysql.cursors

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "loker-house")

SQLITE_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "app.db"

MYSQL_INIT_SCHEMAS = [
    """CREATE TABLE IF NOT EXISTS jobs (
        id VARCHAR(191) PRIMARY KEY,
        source VARCHAR(191) NOT NULL,
        external_id VARCHAR(191) NOT NULL,
        source_external_key VARCHAR(191) NOT NULL,
        canonical_fingerprint VARCHAR(191) NOT NULL,
        title VARCHAR(255) NOT NULL,
        company VARCHAR(255) NOT NULL,
        description LONGTEXT NOT NULL,
        location VARCHAR(255),
        salary_min INT,
        salary_max INT,
        currency VARCHAR(50),
        apply_url TEXT NOT NULL,
        posted_at VARCHAR(191),
        fetched_at VARCHAR(191) NOT NULL,
        relevance_score DOUBLE,
        embedding_model VARCHAR(191),
        embedding_version VARCHAR(191),
        status VARCHAR(191) NOT NULL DEFAULT 'DISCOVERED',
        filtered_reason TEXT,
        UNIQUE KEY idx_source_ext (source, external_id),
        UNIQUE KEY idx_source_key (source_external_key),
        UNIQUE KEY idx_fp (canonical_fingerprint)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS applications (
        id VARCHAR(191) PRIMARY KEY,
        job_id VARCHAR(191) NOT NULL,
        idempotency_key VARCHAR(191) NOT NULL,
        status VARCHAR(191) NOT NULL DEFAULT 'DRAFT_READY',
        cover_letter LONGTEXT NOT NULL,
        cv_summary LONGTEXT NOT NULL,
        method VARCHAR(191),
        retry_count INT NOT NULL DEFAULT 0,
        created_at VARCHAR(191) NOT NULL,
        approved_at VARCHAR(191),
        submitted_at VARCHAR(191),
        last_status_check_at VARCHAR(191),
        notes TEXT,
        llm_provider VARCHAR(191),
        llm_model VARCHAR(191),
        UNIQUE KEY idx_job (job_id),
        UNIQUE KEY idx_idem (idempotency_key)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS submission_attempts (
        id VARCHAR(191) PRIMARY KEY,
        application_id VARCHAR(191) NOT NULL,
        attempt_number INT NOT NULL,
        result VARCHAR(191) NOT NULL,
        error_message TEXT,
        confirmation_url TEXT,
        confirmation_reference VARCHAR(191),
        attempted_at VARCHAR(191) NOT NULL,
        UNIQUE KEY idx_app_attempt (application_id, attempt_number)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS application_status_history (
        id VARCHAR(191) PRIMARY KEY,
        application_id VARCHAR(191) NOT NULL,
        from_status VARCHAR(191),
        to_status VARCHAR(191) NOT NULL,
        changed_by VARCHAR(191) NOT NULL,
        changed_at VARCHAR(191) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS filters (
        id VARCHAR(191) PRIMARY KEY,
        role_keywords TEXT NOT NULL,
        exclusion_keywords TEXT NOT NULL,
        min_relevance_score DOUBLE NOT NULL DEFAULT 0.65,
        max_posting_age_days INT NOT NULL DEFAULT 14,
        no_response_after_days INT NOT NULL DEFAULT 21,
        max_bids INT DEFAULT NULL,
        updated_at VARCHAR(191) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS companies_ats (
        id VARCHAR(191) PRIMARY KEY,
        company_name VARCHAR(191) NOT NULL,
        ats_type VARCHAR(191) NOT NULL,
        ats_slug VARCHAR(191) NOT NULL,
        active INT NOT NULL DEFAULT 1,
        UNIQUE KEY idx_ats_type_slug (ats_type, ats_slug)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS company_blocklist (
        id VARCHAR(191) PRIMARY KEY,
        company_name VARCHAR(191) NOT NULL UNIQUE,
        reason TEXT,
        added_at VARCHAR(191) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS leads (
        id VARCHAR(191) PRIMARY KEY,
        source VARCHAR(191) NOT NULL,
        external_id VARCHAR(191) NOT NULL,
        kind VARCHAR(191) NOT NULL,
        title VARCHAR(255) NOT NULL,
        client_name VARCHAR(255),
        budget_text VARCHAR(191),
        budget_min INT,
        budget_max INT,
        currency VARCHAR(50),
        url TEXT NOT NULL,
        skills_text TEXT,
        description LONGTEXT NOT NULL,
        posted_at VARCHAR(191),
        fetched_at VARCHAR(191) NOT NULL,
        status VARCHAR(191) NOT NULL DEFAULT 'NEW',
        proposal LONGTEXT,
        comment TEXT,
        UNIQUE KEY idx_lead_source_ext (source, external_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS llm_calls (
        id VARCHAR(191) PRIMARY KEY,
        run_id VARCHAR(191),
        task VARCHAR(191) NOT NULL,
        provider VARCHAR(191) NOT NULL,
        model VARCHAR(191) NOT NULL,
        attempt INT NOT NULL DEFAULT 1,
        status VARCHAR(191) NOT NULL,
        error_code VARCHAR(191),
        latency_ms INT,
        prompt_tokens INT,
        completion_tokens INT,
        application_id VARCHAR(191),
        created_at VARCHAR(191) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS ats_registry (
        id VARCHAR(191) PRIMARY KEY,
        ats_name VARCHAR(191) NOT NULL,
        host VARCHAR(191) NOT NULL UNIQUE,
        mode VARCHAR(191) NOT NULL,
        open_button_label VARCHAR(191),
        verified_at VARCHAR(191),
        active INT NOT NULL DEFAULT 1
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS form_sessions (
        id VARCHAR(191) PRIMARY KEY,
        application_id VARCHAR(191) NOT NULL,
        engine VARCHAR(191) NOT NULL,
        host VARCHAR(191) NOT NULL,
        mode VARCHAR(191) NOT NULL,
        page_number INT NOT NULL DEFAULT 1,
        status VARCHAR(191) NOT NULL,
        filled_count INT NOT NULL DEFAULT 0,
        ai_answer_count INT NOT NULL DEFAULT 0,
        manual_count INT NOT NULL DEFAULT 0,
        skipped_protected_count INT NOT NULL DEFAULT 0,
        captcha INT NOT NULL DEFAULT 0,
        tool_calls INT NOT NULL DEFAULT 0,
        error_code VARCHAR(191),
        user_feedback TEXT,
        started_at VARCHAR(191) NOT NULL,
        finished_at VARCHAR(191)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS form_field_events (
        id VARCHAR(191) PRIMARY KEY,
        session_id VARCHAR(191) NOT NULL,
        label VARCHAR(255) NOT NULL,
        role VARCHAR(191) NOT NULL,
        field_class VARCHAR(191) NOT NULL,
        action VARCHAR(191) NOT NULL,
        source VARCHAR(191),
        reason TEXT,
        confidence DOUBLE,
        value_preview TEXT,
        created_at VARCHAR(191) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS app_settings (
        setting_key VARCHAR(191) PRIMARY KEY,
        setting_value TEXT NOT NULL,
        updated_at VARCHAR(191) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS office_reports (
        id VARCHAR(191) PRIMARY KEY,
        employee VARCHAR(191) NOT NULL,
        period_start VARCHAR(191) NOT NULL,
        period_end VARCHAR(191) NOT NULL,
        created_at VARCHAR(191) NOT NULL,
        summary LONGTEXT NOT NULL,
        delivered INT NOT NULL DEFAULT 0,
        rating INT DEFAULT NULL,
        rating_note TEXT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS office_instructions (
        employee VARCHAR(191) PRIMARY KEY,
        instruction TEXT NOT NULL,
        updated_at VARCHAR(191) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS office_character_state (
        character_id VARCHAR(191) PRIMARY KEY,
        role VARCHAR(50) NOT NULL DEFAULT 'staff',
        x DOUBLE NOT NULL DEFAULT 0,
        y DOUBLE NOT NULL DEFAULT 0,
        z DOUBLE NOT NULL DEFAULT 0,
        yaw DOUBLE NOT NULL DEFAULT 0,
        updated_at VARCHAR(191) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS employee_memories (
        id VARCHAR(191) PRIMARY KEY,
        employee_id VARCHAR(191) NOT NULL,
        kind VARCHAR(50) NOT NULL,
        content TEXT NOT NULL,
        importance DOUBLE NOT NULL DEFAULT 1.0,
        created_at VARCHAR(191) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS office_meetings (
        id VARCHAR(191) PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'scheduled',
        starts_at VARCHAR(191) NOT NULL,
        ended_at VARCHAR(191)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""",

    """CREATE TABLE IF NOT EXISTS office_meeting_events (
        id VARCHAR(191) PRIMARY KEY,
        meeting_id VARCHAR(191) NOT NULL,
        employee_id VARCHAR(191) NOT NULL,
        event_type VARCHAR(50) NOT NULL,
        content TEXT NOT NULL,
        created_at VARCHAR(191) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"""
]

DEFAULT_FILTER_INSERT = """
INSERT IGNORE INTO filters (
  id, role_keywords, exclusion_keywords, min_relevance_score, max_posting_age_days, no_response_after_days, updated_at
) VALUES (
  'default',
  '["laravel", "flutter", "nestjs", "react", "python", "backend", "full stack", "fullstack", "mobile developer", "software engineer", "software developer", "web developer", "programmer"]',
  '["unpaid", "commission only", "equity only", "must relocate"]',
  0.65, 14, 21, NOW()
);
"""

DEFAULT_ATS_INSERT = """
INSERT IGNORE INTO ats_registry (id, ats_name, host, mode, open_button_label) VALUES
  ('gh-1', 'Greenhouse', 'job-boards.greenhouse.io', 'auto_fill', NULL),
  ('gh-2', 'Greenhouse', 'boards.greenhouse.io', 'auto_fill', NULL),
  ('lv-1', 'Lever', 'jobs.lever.co', 'auto_fill', 'Apply for this job'),
  ('lv-2', 'Lever', 'jobs.eu.lever.co', 'auto_fill', 'Apply for this job'),
  ('ab-1', 'Ashby', 'jobs.ashbyhq.com', 'assist', 'Apply'),
  ('wk-1', 'Workable', 'apply.workable.com', 'assist', 'Apply for this job'),
  ('sr-1', 'SmartRecruiters', 'jobs.smartrecruiters.com', 'assist', 'I''m interested'),
  ('kb-1', 'Kalibrr', 'www.kalibrr.com', 'assist', 'Apply');
"""


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class MySQLCursorWrapper:
    def __init__(self, cursor: pymysql.cursors.Cursor):
        self._cur = cursor

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    @property
    def lastrowid(self) -> Any:
        return self._cur.lastrowid

    def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] | None = None) -> MySQLCursorWrapper:
        translated_sql = sql
        # SQLite -> MySQL syntax transformations
        translated_sql = re.sub(r"INSERT\s+OR\s+IGNORE", "INSERT IGNORE", translated_sql, flags=re.IGNORECASE)
        translated_sql = re.sub(r"INSERT\s+OR\s+REPLACE", "REPLACE", translated_sql, flags=re.IGNORECASE)
        translated_sql = re.sub(r"strftime\('%Y-%m-%dT%H:%M:%fZ',\s*'now'\)", "NOW()", translated_sql, flags=re.IGNORECASE)
        translated_sql = re.sub(r"DATETIME\('now'\)", "NOW()", translated_sql, flags=re.IGNORECASE)
        
        # Handle PRAGMA table_info(tbl) -> SHOW COLUMNS FROM tbl
        pragma_match = re.search(r"PRAGMA\s+table_info\(([^)]+)\)", translated_sql, flags=re.IGNORECASE)
        if pragma_match:
            tbl_name = pragma_match.group(1).strip(" `'\"")
            translated_sql = f"SHOW COLUMNS FROM `{tbl_name}`"

        # Convert SQLite `?` placeholders to MySQL `%s`
        if "?" in translated_sql:
            translated_sql = translated_sql.replace("?", "%s")

        if params is None:
            self._cur.execute(translated_sql)
        else:
            self._cur.execute(translated_sql, params)
        return self

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> MySQLCursorWrapper:
        translated_sql = sql.replace("?", "%s")
        translated_sql = re.sub(r"INSERT\s+OR\s+IGNORE", "INSERT IGNORE", translated_sql, flags=re.IGNORECASE)
        self._cur.executemany(translated_sql, seq_of_params)
        return self

    def fetchone(self) -> tuple | dict | None:
        return self._cur.fetchone()

    def fetchall(self) -> list:
        res = self._cur.fetchall()
        # Handle PRAGMA response emulation (cid, name, type, notnull, dflt_value, pk)
        if hasattr(self._cur, "description") and self._cur.description:
            col_names = [col[0] for col in self._cur.description]
            if "Field" in col_names and "Type" in col_names:
                # Converter for table_info queries
                emulated = []
                for idx, row in enumerate(res):
                    if isinstance(row, dict):
                        emulated.append((idx, row["Field"], row["Type"], 0, None, 1 if row["Key"] == "PRI" else 0))
                    else:
                        emulated.append((idx, row[0], row[1], 0, None, 1 if row[3] == "PRI" else 0))
                return emulated
        return list(res)

    def close(self) -> None:
        self._cur.close()


class MySQLConnectionWrapper:
    def __init__(self, raw_conn: pymysql.Connection):
        self._conn = raw_conn

    def cursor(self) -> MySQLCursorWrapper:
        return MySQLCursorWrapper(self._conn.cursor())

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> MySQLCursorWrapper:
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> MySQLCursorWrapper:
        cur = self.cursor()
        cur.executemany(sql, seq_of_params)
        return cur

    def executescript(self, script: str) -> None:
        statements = [s.strip() for s in script.split(";") if s.strip()]
        cur = self.cursor()
        for statement in statements:
            cur.execute(statement)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> MySQLConnectionWrapper:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


def ensure_mysql_db() -> None:
    """Ensure database `loker-house` and all tables exist in MySQL."""
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD)
    with conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    conn.commit()
    conn.close()

    raw_conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DB, autocommit=False)
    conn_wrap = MySQLConnectionWrapper(raw_conn)
    for sql in MYSQL_INIT_SCHEMAS:
        conn_wrap.execute(sql)
    conn_wrap.execute(DEFAULT_FILTER_INSERT)
    conn_wrap.execute(DEFAULT_ATS_INSERT)
    conn_wrap.commit()
    conn_wrap.close()


def migrate_sqlite_to_mysql() -> None:
    """Migrate rows from legacy SQLite data/app.db to MySQL `loker-house` if sqlite database exists."""
    if not SQLITE_DB_PATH.exists():
        return

    try:
        sq_conn = sqlite3.connect(SQLITE_DB_PATH)
        sq_cur = sq_conn.cursor()
        sq_tables = [r[0] for r in sq_cur.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
        
        if not sq_tables:
            sq_conn.close()
            return

        raw_my = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DB, autocommit=False)
        my_conn = MySQLConnectionWrapper(raw_my)

        for table in sq_tables:
            if table.startswith("sqlite_"):
                continue
            sq_cur.execute(f"SELECT * FROM `{table}`")
            rows = sq_cur.fetchall()
            if not rows:
                continue
            cols = [d[0] for d in sq_cur.description]
            placeholders = ", ".join(["%s"] * len(cols))
            cols_str = ", ".join([f"`{c}`" for c in cols])
            insert_sql = f"INSERT IGNORE INTO `{table}` ({cols_str}) VALUES ({placeholders})"
            my_conn.executemany(insert_sql, rows)

        my_conn.commit()
        my_conn.close()
        sq_conn.close()

        # Archive SQLite file to .bak once migrated
        bak_path = SQLITE_DB_PATH.with_suffix(".db.bak")
        if not bak_path.exists():
            SQLITE_DB_PATH.rename(bak_path)
    except Exception as err:
        print(f"[MySQL Migration Warning] Migration from SQLite skipped: {err}")


def open_db(database_path: str | Path | None = None) -> MySQLConnectionWrapper:
    """Return an active connection to MySQL `loker-house`."""
    ensure_mysql_db()
    migrate_sqlite_to_mysql()
    raw_conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        autocommit=False,
        cursorclass=pymysql.cursors.Cursor
    )
    return MySQLConnectionWrapper(raw_conn)


def apply_schema(connection: Any) -> None:
    """Ensure database schema is up to date."""
    ensure_mysql_db()
