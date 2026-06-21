from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


DB_PATH = Path(__file__).resolve().parent / "career_command.db"


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with closing(connect()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL, company TEXT NOT NULL, location TEXT,
                source TEXT, url TEXT, description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Review', fit_score INTEGER,
                matched_skills TEXT, risks TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS interview_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, company TEXT,
                question TEXT NOT NULL, answer TEXT NOT NULL,
                overall_score INTEGER, clarity_score INTEGER,
                depth_score INTEGER, seniority_score INTEGER,
                evidence_score INTEGER, feedback TEXT, created_at TEXT NOT NULL
            );
            """
        )
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(jobs)")
        }
        migrations = {
            "external_id": "ALTER TABLE jobs ADD COLUMN external_id TEXT",
            "posted_date": "ALTER TABLE jobs ADD COLUMN posted_date TEXT",
            "fetched_at": "ALTER TABLE jobs ADD COLUMN fetched_at TEXT",
            "work_mode": "ALTER TABLE jobs ADD COLUMN work_mode TEXT",
            "experience_min": "ALTER TABLE jobs ADD COLUMN experience_min INTEGER",
            "experience_max": "ALTER TABLE jobs ADD COLUMN experience_max INTEGER",
            "skills": "ALTER TABLE jobs ADD COLUMN skills TEXT",
            "cloud_stack": "ALTER TABLE jobs ADD COLUMN cloud_stack TEXT",
            "data_stack": "ALTER TABLE jobs ADD COLUMN data_stack TEXT",
            "domain": "ALTER TABLE jobs ADD COLUMN domain TEXT",
            "salary": "ALTER TABLE jobs ADD COLUMN salary TEXT",
            "company_url": "ALTER TABLE jobs ADD COLUMN company_url TEXT",
            "credibility_score": "ALTER TABLE jobs ADD COLUMN credibility_score INTEGER",
            "credibility_flags": "ALTER TABLE jobs ADD COLUMN credibility_flags TEXT",
            "fit_reason": "ALTER TABLE jobs ADD COLUMN fit_reason TEXT",
            "suggested_action": "ALTER TABLE jobs ADD COLUMN suggested_action TEXT",
            "resume_keywords": "ALTER TABLE jobs ADD COLUMN resume_keywords TEXT",
            "raw_payload": "ALTER TABLE jobs ADD COLUMN raw_payload TEXT",
            "content_hash": "ALTER TABLE jobs ADD COLUMN content_hash TEXT",
            "occurrence_count": "ALTER TABLE jobs ADD COLUMN occurrence_count INTEGER DEFAULT 1",
            "first_seen": "ALTER TABLE jobs ADD COLUMN first_seen TEXT",
            "last_seen": "ALTER TABLE jobs ADD COLUMN last_seen TEXT",
        }
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(statement)
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url) WHERE url <> ''"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_identity "
            "ON jobs(company, title, location)"
        )
        connection.commit()


def add_job(record: dict, analysis: dict) -> bool:
    with closing(connect()) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO jobs (
                title, company, location, source, url, description, status,
                fit_score, matched_skills, risks, created_at, external_id,
                posted_date, fetched_at, work_mode, experience_min,
                experience_max, skills, cloud_stack, data_stack, domain,
                salary, company_url, credibility_score, credibility_flags,
                fit_reason, suggested_action, resume_keywords, raw_payload,
                content_hash, occurrence_count, first_seen, last_seen
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                record["title"], record["company"], record.get("location", ""),
                record.get("source", ""), record.get("url", ""),
                record["description"], record.get("status", "Review"),
                analysis["score"],
                json.dumps(analysis["matched_skills"]), json.dumps(analysis["risks"]),
                datetime.now(timezone.utc).isoformat(),
                record.get("external_id", ""), record.get("posted_date", ""),
                record.get("fetched_at", datetime.now(timezone.utc).isoformat()),
                record.get("work_mode", ""), record.get("experience_min"),
                record.get("experience_max"),
                json.dumps(record.get("skills", [])),
                json.dumps(record.get("cloud_stack", [])),
                json.dumps(record.get("data_stack", [])),
                record.get("domain", ""), record.get("salary", ""),
                record.get("company_url", ""),
                analysis.get("credibility_score", 0),
                json.dumps(analysis.get("credibility_flags", [])),
                analysis.get("reason", ""),
                analysis.get("suggested_action", "Review"),
                json.dumps(analysis.get("resume_keywords", [])),
                json.dumps(record.get("raw_payload", {}), default=str),
                record.get("content_hash", ""), record.get("occurrence_count", 1),
                record.get("first_seen", record.get("fetched_at", "")),
                record.get("last_seen", record.get("fetched_at", "")),
            ),
        )
        if cursor.rowcount == 0 and record.get("url"):
            connection.execute(
                """
                UPDATE jobs
                SET last_seen = ?, occurrence_count = COALESCE(occurrence_count, 1) + 1,
                    posted_date = COALESCE(NULLIF(?, ''), posted_date)
                WHERE url = ?
                """,
                (
                    record.get("last_seen", datetime.now(timezone.utc).isoformat()),
                    record.get("posted_date", ""),
                    record["url"],
                ),
            )
        connection.commit()
        return cursor.rowcount > 0


def get_jobs() -> pd.DataFrame:
    with closing(connect()) as connection:
        return pd.read_sql_query(
            "SELECT * FROM jobs ORDER BY fit_score DESC, created_at DESC", connection
        )


def update_job_status(job_id: int, status: str) -> None:
    with closing(connect()) as connection:
        connection.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
        connection.commit()


def delete_job(job_id: int) -> None:
    with closing(connect()) as connection:
        connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        connection.commit()


def find_description_reuse(content_hash: str, company: str) -> int:
    if not content_hash:
        return 0
    with closing(connect()) as connection:
        row = connection.execute(
            """
            SELECT COUNT(DISTINCT company) AS company_count
            FROM jobs WHERE content_hash = ? AND company <> ?
            """,
            (content_hash, company),
        ).fetchone()
        return int(row["company_count"] or 0)


def add_interview_result(
    role: str, company: str, question: str, answer: str, scores: dict, feedback: str
) -> None:
    with closing(connect()) as connection:
        connection.execute(
            """
            INSERT INTO interview_results (
                role, company, question, answer, overall_score, clarity_score,
                depth_score, seniority_score, evidence_score, feedback, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                role, company, question, answer, scores["overall"], scores["clarity"],
                scores["depth"], scores["seniority"], scores["evidence"], feedback,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()


def get_interview_results() -> pd.DataFrame:
    with closing(connect()) as connection:
        return pd.read_sql_query(
            """
            SELECT role, company, question, overall_score, clarity_score,
                   depth_score, seniority_score, evidence_score, feedback, created_at
            FROM interview_results ORDER BY created_at DESC
            """,
            connection,
        )
