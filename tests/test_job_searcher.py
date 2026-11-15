"""Tests for the Adzuna job searcher: standardization (provider id, posted
date, remote inference, predicted salary) and sanitized error handling."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import job_searcher
from job_searcher import AdzunaJobSearcher, JobSearchError, infer_remote_status


def adzuna_ad(**overrides):
    ad = {
        'id': '5927305087',
        'title': 'Data Engineer (Python) - Remote USA',
        'description': 'Fully remote role building Python pipelines.',
        'created': '2026-10-14T06:56:35Z',
        'redirect_url': 'https://www.adzuna.com/details/5927305087?utm_medium=api&utm_source=abc',
        'salary_min': 149532,
        'salary_max': 167644,
        'salary_currency': 'USD',
        'salary_is_predicted': '0',
        'contract_type': 'permanent',
        'company': {'display_name': 'ICF'},
        'location': {'display_name': 'Reston, Fairfax County'},
    }
    ad.update(overrides)
    return ad


class StandardizeTests(unittest.TestCase):
    def test_uses_stable_provider_id_not_url_hash(self):
        a = AdzunaJobSearcher._standardize_job(adzuna_ad())
        b = AdzunaJobSearcher._standardize_job(adzuna_ad(
            redirect_url='https://www.adzuna.com/details/5927305087?utm_medium=api&utm_source=DIFFERENT&v=XYZ'))
        self.assertEqual(a['job_id'], 'adzuna_5927305087')
        self.assertEqual(a['job_id'], b['job_id'])  # same ad, different tracking params

    def test_falls_back_to_url_hash_without_provider_id(self):
        j = AdzunaJobSearcher._standardize_job(adzuna_ad(id=None))
        self.assertTrue(j['job_id'].startswith('adzuna_'))
        self.assertEqual(len(j['job_id']), len('adzuna_') + 12)

    def test_posted_date_uses_created_field(self):
        """Regression: code read 'created_at' but the API returns 'created'."""
        j = AdzunaJobSearcher._standardize_job(adzuna_ad())
        self.assertEqual(j['posted_date'], '2026-10-14T06:56:35Z')

    def test_predicted_salary_flag_preserved(self):
        j = AdzunaJobSearcher._standardize_job(adzuna_ad(salary_is_predicted='1'))
        self.assertEqual(j['salary_is_predicted'], 1)
        j0 = AdzunaJobSearcher._standardize_job(adzuna_ad())
        self.assertEqual(j0['salary_is_predicted'], 0)

    def test_remote_inference(self):
        self.assertEqual(infer_remote_status('Senior Dev - Remote', '', ''), 'remote')
        self.assertEqual(infer_remote_status('Senior Dev', 'Hybrid schedule', ''), 'hybrid')
        self.assertEqual(infer_remote_status('Senior Dev', 'Work from home allowed', ''), 'remote')
        self.assertEqual(infer_remote_status('Senior Dev', 'Onsite daily', 'Austin, TX'), 'unknown')
        # hybrid wins when both appear
        self.assertEqual(infer_remote_status('Remote-friendly', 'hybrid schedule', ''), 'hybrid')

    def test_standardize_infers_remote_status(self):
        j = AdzunaJobSearcher._standardize_job(adzuna_ad())
        self.assertEqual(j['remote_status'], 'remote')


class SearchErrorTests(unittest.TestCase):
    def _searcher(self):
        return AdzunaJobSearcher(app_id='id12345', api_key='secret-key-value')

    def test_http_error_raises_sanitized(self):
        resp = MagicMock(status_code=401)
        with patch.object(job_searcher.requests, 'get', return_value=resp):
            with self.assertRaises(JobSearchError) as ctx:
                self._searcher().search_jobs('python')
        msg = str(ctx.exception)
        self.assertIn('401', msg)
        self.assertNotIn('secret-key-value', msg)
        self.assertNotIn('://', msg)
        self.assertNotIn('app_key', msg)

    def test_network_error_raises_sanitized(self):
        import requests as real_requests
        boom = real_requests.exceptions.ConnectionError(
            'HTTPSConnectionPool: Max retries exceeded with url: /v1/api?app_id=id12345&app_key=secret-key-value')
        with patch.object(job_searcher.requests, 'get', side_effect=boom):
            with self.assertRaises(JobSearchError) as ctx:
                self._searcher().search_jobs('python')
        self.assertNotIn('secret-key-value', str(ctx.exception))

    def test_non_json_response_raises_sanitized(self):
        resp = MagicMock(status_code=200)
        resp.json.side_effect = ValueError('not json')
        with patch.object(job_searcher.requests, 'get', return_value=resp):
            with self.assertRaises(JobSearchError):
                self._searcher().search_jobs('python')

    def test_params_include_recency_and_sort(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {'results': []}
        with patch.object(job_searcher.requests, 'get', return_value=resp) as get:
            self._searcher().search_jobs('python', salary_min=85000,
                                         max_days_old=30, sort_by='date')
        params = get.call_args.kwargs['params']
        self.assertEqual(params['salary_min'], 85000)
        self.assertEqual(params['max_days_old'], 30)
        self.assertEqual(params['sort_by'], 'date')

    def test_invalid_sort_by_rejected(self):
        with self.assertRaises(ValueError):
            self._searcher().search_jobs('python', sort_by='bogus')

    def test_page_param_builds_url(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {'results': []}
        with patch.object(job_searcher.requests, 'get', return_value=resp) as get:
            self._searcher().search_jobs('python', page=2)
        self.assertTrue(get.call_args.args[0].endswith('/search/2'))
        with patch.object(job_searcher.requests, 'get', return_value=resp) as get:
            self._searcher().search_jobs('python')
        self.assertTrue(get.call_args.args[0].endswith('/search/1'))
        with patch.object(job_searcher.requests, 'get', return_value=resp) as get:
            self._searcher().search_jobs('python', page=0)
        self.assertTrue(get.call_args.args[0].endswith('/search/1'))


if __name__ == '__main__':
    unittest.main()
