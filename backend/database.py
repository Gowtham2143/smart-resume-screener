"""
Lightweight SQLite storage for jobs and scored candidates.
No ORM on purpose -- this is a small project and plain SQL is easier to audit.
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resume_screener.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id                  TEXT PRIMARY KEY,
            job_id              TEXT NOT NULL,
            filename            TEXT NOT NULL,
            stored_path         TEXT NOT NULL,
            candidate_name      TEXT,
            raw_text            TEXT,
            skills              TEXT,
            experience_summary  TEXT,
            education_summary   TEXT,
            match_score         INTEGER,
            justification       TEXT,
            created_at          TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs (id)
        )
    """)
    conn.commit()
    conn.close()


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------- jobs ------------------------------------

def create_job(title, description):
    job_id = uuid.uuid4().hex
    conn = _connect()
    conn.execute(
        "INSERT INTO jobs (id, title, description, created_at) VALUES (?, ?, ?, ?)",
        (job_id, title, description, _now()),
    )
    conn.commit()
    conn.close()
    return job_id


def get_job(job_id):
    conn = _connect()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_jobs():
    conn = _connect()
    rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_job(job_id):
    conn = _connect()
    conn.execute("DELETE FROM candidates WHERE job_id = ?", (job_id,))
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()


# ------------------------------- candidates ---------------------------------

def add_candidate(job_id, filename, stored_path, raw_text, evaluation):
    candidate_id = uuid.uuid4().hex
    conn = _connect()
    conn.execute(
        """INSERT INTO candidates
           (id, job_id, filename, stored_path, candidate_name, raw_text,
            skills, experience_summary, education_summary, match_score,
            justification, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            candidate_id,
            job_id,
            filename,
            stored_path,
            evaluation.get("candidate_name"),
            raw_text,
            json.dumps(evaluation.get("skills", [])),
            evaluation.get("experience_summary"),
            evaluation.get("education_summary"),
            evaluation.get("match_score"),
            evaluation.get("justification"),
            _now(),
        ),
    )
    conn.commit()
    conn.close()
    return candidate_id


def _row_to_candidate(row):
    d = dict(row)
    d["skills"] = json.loads(d["skills"]) if d.get("skills") else []
    d.pop("raw_text", None)  # don't ship the full resume text back on list views
    return d


def get_candidate(candidate_id):
    conn = _connect()
    row = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    conn.close()
    return _row_to_candidate(row) if row else None


def list_candidates(job_id):
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM candidates WHERE job_id = ? ORDER BY match_score DESC, created_at ASC",
        (job_id,),
    ).fetchall()
    conn.close()
    return [_row_to_candidate(r) for r in rows]


def delete_candidate(candidate_id):
    conn = _connect()
    conn.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
    conn.commit()
    conn.close()
