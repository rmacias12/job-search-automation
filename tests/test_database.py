"""Tests for database persistence: dedup semantics, status-preserving
match upsert (regression for INSERT OR REPLACE data loss), and the
ensure_schema migration."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import database


def sample_job(job_id='adzuna_123', **overrides):
    job = {
        'job_id': job_id,
        'source': 'adzuna',
        'title': 'Senior Software Engineer',
        'company': 'Acme',
        'location': 'Remote',
        'description': 'Python, React, SQL.',
        'url': 'https://example.com/job/123',
        'salary_min': 170000,
        'salary_max': 210000,
        'salary_currency': 'USD',
        'salary_is_predicted': 1,
        'job_type': 'permanent',
        'remote_status': 'remote',
        'posted_date': '2026-10-14T06:56:35Z',
        'raw_data': {'id': '123'},
    }
    job.update(overrides)
    return job


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / 'test.db'
        self._orig = database.DATABASE_PATH
        database.DATABASE_PATH = self.db_path
        self.addCleanup(setattr, database, 'DATABASE_PATH', self._orig)
        database.ensure_schema()

    def test_ensure_schema_is_idempotent_and_migrates(self):
        # Run twice: must not raise
        database.ensure_schema()
        conn = database.get_connection()
        job_cols = {r[1] for r in conn.execute('PRAGMA table_info(jobs)')}
        match_cols = {r[1] for r in conn.execute('PRAGMA table_info(matches)')}
        conn.close()
        self.assertIn('salary_is_predicted', job_cols)
        self.assertIn('evidence', match_cols)

    def test_ensure_schema_migrates_legacy_database(self):
        # Simulate a legacy DB without the new columns
        legacy = Path(self.temp.name) / 'legacy.db'
        conn = sqlite3.connect(legacy)
        conn.execute("""CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL, source TEXT NOT NULL, title TEXT NOT NULL,
            company TEXT NOT NULL, location TEXT, description TEXT, url TEXT,
            salary_min INTEGER, salary_max INTEGER, salary_currency TEXT,
            job_type TEXT, remote_status TEXT, posted_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, raw_data TEXT)""")
        conn.execute("""CREATE TABLE matches (id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL, resume_id INTEGER NOT NULL, match_score REAL NOT NULL,
            skill_match_score REAL, title_match_score REAL, location_match_score REAL,
            salary_match_score REAL, status TEXT DEFAULT 'new', notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(job_id, resume_id))""")
        conn.commit()
        conn.close()
        database.DATABASE_PATH = legacy
        database.ensure_schema()
        conn = sqlite3.connect(legacy)
        job_cols = {r[1] for r in conn.execute('PRAGMA table_info(jobs)')}
        match_cols = {r[1] for r in conn.execute('PRAGMA table_info(matches)')}
        conn.close()
        self.assertIn('salary_is_predicted', job_cols)
        self.assertIn('evidence', match_cols)

    def test_insert_job_dedup_returns_zero_for_duplicate(self):
        first = database.insert_job(sample_job())
        assert first is not None
        self.assertGreater(first, 0)
        # Same provider id but different tracking URL => still a duplicate
        dup = database.insert_job(sample_job(url='https://example.com/job/123?utm_source=other'))
        self.assertEqual(dup, 0)
        conn = database.get_connection()
        count = conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_insert_job_stores_predicted_salary_and_date(self):
        database.insert_job(sample_job())
        conn = database.get_connection()
        row = conn.execute('SELECT salary_is_predicted, posted_date FROM jobs').fetchone()
        conn.close()
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], '2026-10-14T06:56:35Z')

    def test_blacklisted_job_not_inserted(self):
        database.blacklist_job('adzuna_999', title='Bad', company='Co')
        result = database.insert_job(sample_job(job_id='adzuna_999'))
        self.assertIsNone(result)

    def _insert_match(self, job_row_id, status='new', notes=None, score=70.0):
        return database.insert_match({
            'job_id': job_row_id, 'resume_id': 1, 'match_score': score,
            'skill_match_score': 60.0, 'title_match_score': 70.0,
            'location_match_score': 100.0, 'salary_match_score': 90.0,
            'status': status, 'notes': notes,
            'evidence': json.dumps({'found_skills': ['python']}),
        })

    def test_rematch_preserves_user_status_and_notes_and_row_id(self):
        """Regression: INSERT OR REPLACE used to delete the row, resetting
        status to 'new', dropping notes, and orphaning applications."""
        job_row_id = database.insert_job(sample_job())
        self._insert_match(job_row_id)
        # User progresses the match
        conn = database.get_connection()
        conn.execute("UPDATE matches SET status='applied', notes='Applied via LinkedIn' WHERE job_id=?",
                     (job_row_id,))
        conn.commit()
        match_id_before = conn.execute('SELECT id FROM matches WHERE job_id=?', (job_row_id,)).fetchone()[0]
        conn.close()
        # Re-match with new scores
        self._insert_match(job_row_id, status='new', notes=None, score=85.0)
        conn = database.get_connection()
        row = conn.execute('SELECT id, status, notes, match_score, evidence FROM matches WHERE job_id=?',
                           (job_row_id,)).fetchone()
        conn.close()
        self.assertEqual(row[0], match_id_before)   # same row id
        self.assertEqual(row[1], 'applied')          # user status preserved
        self.assertEqual(row[2], 'Applied via LinkedIn')  # notes preserved
        self.assertEqual(row[3], 85.0)               # score refreshed
        self.assertEqual(json.loads(row[4]), {'found_skills': ['python']})  # evidence refreshed

    def test_rematch_updates_machine_owned_status(self):
        job_row_id = database.insert_job(sample_job())
        self._insert_match(job_row_id, status='auto_rejected', notes='Salary below minimum requirement')
        # Job now passes gates on re-match
        self._insert_match(job_row_id, status='new', notes=None, score=80.0)
        conn = database.get_connection()
        row = conn.execute('SELECT status, notes FROM matches WHERE job_id=?', (job_row_id,)).fetchone()
        conn.close()
        self.assertEqual(row[0], 'new')
        self.assertIsNone(row[1])

    def test_user_rejected_status_preserved_on_rematch(self):
        # 'rejected' is user-owned (employer declined) — never recomputed
        job_row_id = database.insert_job(sample_job())
        self._insert_match(job_row_id)
        conn = database.get_connection()
        conn.execute("UPDATE matches SET status='rejected', notes='Employer declined' WHERE job_id=?",
                     (job_row_id,))
        conn.commit()
        conn.close()
        self._insert_match(job_row_id, status='new', notes=None, score=90.0)
        conn = database.get_connection()
        row = conn.execute('SELECT status, notes FROM matches WHERE job_id=?', (job_row_id,)).fetchone()
        conn.close()
        self.assertEqual(row[0], 'rejected')
        self.assertEqual(row[1], 'Employer declined')

    def test_not_interested_status_preserved_on_rematch(self):
        job_row_id = database.insert_job(sample_job())
        self._insert_match(job_row_id)
        conn = database.get_connection()
        conn.execute("UPDATE matches SET status='not_interested' WHERE job_id=?", (job_row_id,))
        conn.commit()
        conn.close()
        self._insert_match(job_row_id, status='new', score=95.0)
        conn = database.get_connection()
        status = conn.execute('SELECT status FROM matches WHERE job_id=?', (job_row_id,)).fetchone()[0]
        conn.close()
        self.assertEqual(status, 'not_interested')

    def test_blacklisted_status_never_recomputed(self):
        job_row_id = database.insert_job(sample_job())
        self._insert_match(job_row_id)
        conn = database.get_connection()
        conn.execute("UPDATE matches SET status='blacklisted' WHERE job_id=?", (job_row_id,))
        conn.commit()
        conn.close()
        self._insert_match(job_row_id, status='new', score=99.0)
        conn = database.get_connection()
        status = conn.execute('SELECT status FROM matches WHERE job_id=?', (job_row_id,)).fetchone()[0]
        conn.close()
        self.assertEqual(status, 'blacklisted')


if __name__ == '__main__':
    unittest.main()
