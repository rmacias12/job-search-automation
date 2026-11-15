"""Tests for CLI search behavior: no silent mock fallback, salary/recency
filters passed through, sanitized failure output."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import cli
from job_searcher import JobSearchError


class SearchAndSaveTests(unittest.TestCase):
    def test_no_silent_mock_fallback_on_missing_credentials(self):
        """Regression: missing credentials used to quietly insert mock jobs
        into the production database."""
        buf = io.StringIO()
        with patch.object(cli, 'get_job_searcher', side_effect=ValueError('Adzuna API credentials required.')), \
             patch('database.insert_job') as insert_mock, \
             redirect_stdout(buf):
            saved = cli.search_and_save_jobs('python engineer')
        self.assertEqual(saved, 0)
        insert_mock.assert_not_called()
        out = buf.getvalue()
        self.assertIn('--mock', out)  # tells the user how to opt into test data

    def test_search_error_is_sanitized(self):
        buf = io.StringIO()
        fake = MagicMock()
        fake.search_jobs.side_effect = JobSearchError('Adzuna API returned HTTP 401')
        with patch.object(cli, 'get_job_searcher', return_value=fake), \
             patch.object(cli, '_load_resume_config', return_value={'target_salary_min': 85000}), \
             redirect_stdout(buf):
            saved = cli.search_and_save_jobs('python engineer')
        self.assertEqual(saved, 0)
        self.assertIn('401', buf.getvalue())

    def test_unexpected_exception_prints_type_only(self):
        buf = io.StringIO()
        fake = MagicMock()
        fake.search_jobs.side_effect = RuntimeError('url=https://api.adzuna.com?app_key=SECRET')
        with patch.object(cli, 'get_job_searcher', return_value=fake), \
             patch.object(cli, '_load_resume_config', return_value={}), \
             redirect_stdout(buf):
            saved = cli.search_and_save_jobs('python engineer')
        self.assertEqual(saved, 0)
        out = buf.getvalue()
        self.assertIn('RuntimeError', out)
        self.assertNotIn('SECRET', out)

    def test_real_search_passes_salary_and_recency_filters(self):
        fake = MagicMock()
        fake.search_jobs.return_value = []
        with patch.object(cli, 'get_job_searcher', return_value=fake), \
             patch.object(cli, '_load_resume_config', return_value={'target_salary_min': 85000}), \
             redirect_stdout(io.StringIO()):
            cli.search_and_save_jobs('python engineer', max_days_old=30, sort_by='date')
        kwargs = fake.search_jobs.call_args.kwargs
        self.assertEqual(kwargs['salary_min'], 85000)
        self.assertIsNone(kwargs.get('salary_max'))  # never hide above-target payers
        self.assertEqual(kwargs['max_days_old'], 30)
        self.assertEqual(kwargs['sort_by'], 'date')

    def test_mock_search_sends_no_api_filters(self):
        fake = MagicMock()
        fake.search_jobs.return_value = []
        with patch.object(cli, 'get_job_searcher', return_value=fake), \
             redirect_stdout(io.StringIO()):
            cli.search_and_save_jobs('python engineer', use_mock=True)
        kwargs = fake.search_jobs.call_args.kwargs
        self.assertIsNone(kwargs['salary_min'])
        self.assertIsNone(kwargs['max_days_old'])
        self.assertIsNone(kwargs['sort_by'])

    def test_duplicate_accounting(self):
        fake = MagicMock()
        fake.search_jobs.return_value = [{'job_id': 'a'}, {'job_id': 'b'}, {'job_id': 'a'}]
        buf = io.StringIO()
        with patch.object(cli, 'get_job_searcher', return_value=fake), \
             patch.object(cli, '_load_resume_config', return_value={}), \
             patch('database.insert_job', side_effect=[1, 2, 0]), \
             redirect_stdout(buf):
            saved = cli.search_and_save_jobs('python engineer')
        self.assertEqual(saved, 2)
        self.assertIn('1 duplicates skipped', buf.getvalue())


if __name__ == '__main__':
    unittest.main()
