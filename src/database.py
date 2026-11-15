"""
Database module for job search automation.
Handles SQLite initialization and CRUD operations.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

DATABASE_PATH = Path(__file__).parent.parent / "data" / "job_search.db"


def init_database():
    """Initialize SQLite database with required tables."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Jobs table - stores job postings from various sources
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT,
            description TEXT,
            url TEXT,
            salary_min INTEGER,
            salary_max INTEGER,
            salary_currency TEXT,
            job_type TEXT,
            remote_status TEXT,
            posted_date TEXT,
            salary_is_predicted INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            raw_data TEXT
        )
    """)
    
    # Resumes table - stores parsed resume data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resume_id TEXT UNIQUE NOT NULL,
            name TEXT,
            email TEXT,
            phone TEXT,
            skills TEXT,
            experience_years INTEGER,
            current_title TEXT,
            preferred_locations TEXT,
            preferred_job_types TEXT,
            target_salary_min INTEGER,
            target_salary_max INTEGER,
            raw_text TEXT,
            parsed_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Matches table - stores scoring between jobs and resumes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            resume_id INTEGER NOT NULL,
            match_score REAL NOT NULL,
            skill_match_score REAL,
            title_match_score REAL,
            location_match_score REAL,
            salary_match_score REAL,
            status TEXT DEFAULT 'new',
            notes TEXT,
            evidence TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id),
            FOREIGN KEY (resume_id) REFERENCES resumes(id),
            UNIQUE(job_id, resume_id)
        )
    """)
    
    # Applications table - tracks jobs you've applied to
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            applied_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            application_method TEXT,
            follow_up_date TIMESTAMP,
            response_status TEXT DEFAULT 'pending',
            notes TEXT,
            FOREIGN KEY (match_id) REFERENCES matches(id)
        )
    """)
    
    # Create indexes for faster queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company)")
    
    # Blacklist table - tracks permanently deleted jobs to prevent re-adding
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            adzuna_id TEXT UNIQUE NOT NULL,
            title TEXT,
            company TEXT,
            deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reason TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_title ON jobs(title)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_score ON matches(match_score)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status)")
    
    conn.commit()
    conn.close()
    print(f"Database initialized at: {DATABASE_PATH}")


def get_connection():
    """Get a database connection."""
    return sqlite3.connect(DATABASE_PATH)


def ensure_schema():
    """Create the database if needed and migrate missing columns in place."""
    if not DATABASE_PATH.exists():
        init_database()
    conn = get_connection()
    cursor = conn.cursor()
    job_cols = {row[1] for row in cursor.execute("PRAGMA table_info(jobs)")}
    if 'salary_is_predicted' not in job_cols:
        cursor.execute("ALTER TABLE jobs ADD COLUMN salary_is_predicted INTEGER DEFAULT 0")
    match_cols = {row[1] for row in cursor.execute("PRAGMA table_info(matches)")}
    if 'evidence' not in match_cols:
        cursor.execute("ALTER TABLE matches ADD COLUMN evidence TEXT")
    conn.commit()
    conn.close()


def is_blacklisted(adzuna_id: str) -> bool:
    """Check if a job is permanently blacklisted."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM blacklist WHERE adzuna_id = ?", (adzuna_id,))
        return cursor.fetchone() is not None
    finally:
        conn.close()


def blacklist_job(adzuna_id: str, title: str = None, company: str = None, reason: str = None) -> bool:
    """Permanently blacklist a job to prevent it from being re-added."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO blacklist (adzuna_id, title, company, reason)
            VALUES (?, ?, ?, ?)
        """, (adzuna_id, title, company, reason))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Error blacklisting job: {e}")
        return False
    finally:
        conn.close()


def get_blacklisted_count() -> int:
    """Get the number of blacklisted jobs."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM blacklist")
        result = cursor.fetchone()
        return result[0] if result else 0
    finally:
        conn.close()


def insert_job(job_data: dict) -> Optional[int]:
    """
    Insert a job into the database.
    Returns the new job's database ID, 0 if the job already existed
    (deduped), or None if blacklisted / on error.
    """
    job_id = job_data.get('job_id')
    
    # Check if job is blacklisted
    if job_id and is_blacklisted(job_id):
        return None
    
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO jobs (
                job_id, source, title, company, location, description,
                url, salary_min, salary_max, salary_currency, job_type,
                remote_status, posted_date, salary_is_predicted, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            job_data.get('source'),
            job_data.get('title'),
            job_data.get('company'),
            job_data.get('location'),
            job_data.get('description'),
            job_data.get('url'),
            job_data.get('salary_min'),
            job_data.get('salary_max'),
            job_data.get('salary_currency'),
            job_data.get('job_type'),
            job_data.get('remote_status'),
            job_data.get('posted_date'),
            int(job_data.get('salary_is_predicted') or 0),
            json.dumps(job_data.get('raw_data', {}))
        ))
        
        conn.commit()
        
        if cursor.rowcount == 0:
            # Already existed (UNIQUE job_id) — deduped, not new
            return 0
        
        return cursor.lastrowid
        
    except Exception as e:
        print(f"Error inserting job: {e}")
        return None
    finally:
        conn.close()


def insert_resume(resume_data: dict) -> int:
    """Insert a parsed resume into the database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO resumes (
                resume_id, name, email, phone, skills, experience_years,
                current_title, preferred_locations, preferred_job_types,
                target_salary_min, target_salary_max, raw_text, parsed_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            resume_data.get('resume_id'),
            resume_data.get('name'),
            resume_data.get('email'),
            resume_data.get('phone'),
            json.dumps(resume_data.get('skills', [])),
            resume_data.get('experience_years'),
            resume_data.get('current_title'),
            json.dumps(resume_data.get('preferred_locations', [])),
            json.dumps(resume_data.get('preferred_job_types', [])),
            resume_data.get('target_salary_min'),
            resume_data.get('target_salary_max'),
            resume_data.get('raw_text'),
            json.dumps(resume_data.get('parsed_data', {}))
        ))
        
        conn.commit()
        
        cursor.execute("SELECT id FROM resumes WHERE resume_id = ?", (resume_data.get('resume_id'),))
        result = cursor.fetchone()
        return result[0] if result else None
        
    except Exception as e:
        print(f"Error inserting resume: {e}")
        return None
    finally:
        conn.close()


def insert_match(match_data: dict) -> bool:
    """Insert or update a match score between a job and resume.
    
    On re-match, scores and evidence are refreshed but user-managed
    statuses (interested/applied/interview stages/offer/rejected/
    not_interested/blacklisted...) and their notes are PRESERVED. Only
    machine-owned statuses ('new'/'auto_rejected') are recomputed. The row
    keeps its id, so application records never dangle.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO matches (
                job_id, resume_id, match_score, skill_match_score,
                title_match_score, location_match_score, salary_match_score,
                status, notes, evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, resume_id) DO UPDATE SET
                match_score = excluded.match_score,
                skill_match_score = excluded.skill_match_score,
                title_match_score = excluded.title_match_score,
                location_match_score = excluded.location_match_score,
                salary_match_score = excluded.salary_match_score,
                evidence = excluded.evidence,
                status = CASE
                    WHEN matches.status IN ('new', 'auto_rejected') THEN excluded.status
                    ELSE matches.status
                END,
                notes = CASE
                    WHEN matches.status IN ('new', 'auto_rejected') THEN excluded.notes
                    ELSE matches.notes
                END,
                updated_at = CURRENT_TIMESTAMP
        """, (
            match_data.get('job_id'),
            match_data.get('resume_id'),
            match_data.get('match_score'),
            match_data.get('skill_match_score'),
            match_data.get('title_match_score'),
            match_data.get('location_match_score'),
            match_data.get('salary_match_score'),
            match_data.get('status', 'new'),
            match_data.get('notes'),
            match_data.get('evidence')
        ))
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"Error inserting match: {e}")
        return False
    finally:
        conn.close()


def get_top_matches(limit: int = 20, min_score: float = 0.0) -> list:
    """Get top-scoring job matches for review."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            j.title, j.company, j.location, j.url,
            m.match_score, m.status, m.notes, m.id as match_id
        FROM matches m
        JOIN jobs j ON m.job_id = j.id
        WHERE m.status = 'new' AND m.match_score >= ?
        ORDER BY m.match_score DESC
        LIMIT ?
    """, (min_score, limit))
    
    columns = [desc[0] for desc in cursor.description]
    results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    conn.close()
    return results


def update_match_status(match_id: int, status: str, notes: str = None) -> bool:
    """Update the status of a match (e.g., 'interested', 'rejected', 'applied')."""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        if notes:
            cursor.execute("""
                UPDATE matches 
                SET status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, notes, match_id))
        else:
            cursor.execute("""
                UPDATE matches 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, match_id))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating match: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    init_database()
    print("Database schema created successfully!")