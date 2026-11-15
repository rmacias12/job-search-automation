"""
Job Searcher module for fetching jobs from various sources.
Primary source: Adzuna API (free tier available)
"""

import os
import re
from credentials import get_credential, has_credential
import requests
import hashlib
from typing import List, Dict, Optional
from urllib.parse import urlencode


class JobSearchError(RuntimeError):
    """A job search request failed. Messages never contain URLs or credentials."""


def infer_remote_status(title: str = "", description: str = "", location: str = "") -> str:
    """Best-effort remote/hybrid detection from ad text (Adzuna has no such field)."""
    text = f"{title} {description} {location}".lower()
    if re.search(r"\bhybrid\b", text):
        return "hybrid"
    if re.search(r"\bremote\b|\bremotely\b|work(?:s)? from home|\bwfh\b|home[- ]based", text):
        return "remote"
    return "unknown"


class AdzunaJobSearcher:
    """
    Search for jobs using Adzuna API.
    Free tier: 100 requests/day
    Sign up at: https://developer.adzuna.com/
    """
    
    BASE_URL = "https://api.adzuna.com/v1/api/jobs/us/search/1"
    
    def __init__(self, app_id: str = None, api_key: str = None):
        """
        Initialize with API credentials.
        Uses credentials.json references, then legacy environment variables.
        """
        self.app_id = get_credential("ADZUNA_APP_ID", app_id)
        self.api_key = get_credential("ADZUNA_API_KEY", api_key)
        
        if not self.app_id or not self.api_key:
            raise ValueError(
                "Adzuna API credentials required. "
                "Configure ADZUNA_APP_ID and ADZUNA_API_KEY in credentials.json "
                "or pass to constructor."
            )
    
    def search_jobs(
        self,
        query: str,
        location: str = None,
        salary_min: Optional[int] = None,
        salary_max: Optional[int] = None,
        job_type: str = None,
        max_results: int = 20,
        max_days_old: Optional[int] = None,
        sort_by: Optional[str] = None,
        page: int = 1
    ) -> List[Dict]:
        """
        Search for jobs using Adzuna API.
        
        Args:
            query: Job title or keywords (e.g., "software engineer")
            location: Location (e.g., "New York" or "Remote")
            salary_min: Minimum annual salary
            salary_max: Maximum annual salary
            job_type: 'fulltime', 'parttime', 'contract', or 'internship'
            max_results: Number of results to return (max 50)
            max_days_old: Only return ads posted within this many days
            sort_by: 'default', 'hybrid', 'date', 'salary', or 'relevance'
            page: Result page number (1-based) for deep sweeps
        
        Returns:
            List of standardized job dictionaries
        
        Raises:
            JobSearchError: On network/API failures (sanitized message).
        """
        
        params = {
            'app_id': self.app_id,
            'app_key': self.api_key,
            'results_per_page': min(max_results, 50),
            'what': query,
        }
        
        if location:
            params['where'] = location
        
        if salary_min:
            params['salary_min'] = salary_min
            
        if salary_max:
            params['salary_max'] = salary_max
            
        if job_type:
            type_map = {
                'fulltime': 'permanent',
                'parttime': 'part_time',
                'contract': 'contract',
                'internship': 'contract'
            }
            params['contract_type'] = type_map.get(job_type, 'permanent')
        
        if max_days_old:
            params['max_days_old'] = max_days_old
        
        if sort_by:
            if sort_by not in ('default', 'hybrid', 'date', 'salary', 'relevance'):
                raise ValueError(f"Invalid sort_by: {sort_by}")
            params['sort_by'] = sort_by
        
        url = self.BASE_URL.rsplit('/', 1)[0] + f'/{max(1, int(page))}'
        
        try:
            response = requests.get(url, params=params, timeout=30)
        except requests.exceptions.RequestException:
            # Never surface the exception text: request URLs embed credentials.
            raise JobSearchError("Adzuna network request failed (connection error or timeout)") from None
        
        if response.status_code != 200:
            raise JobSearchError(f"Adzuna API returned HTTP {response.status_code}")
        
        try:
            data = response.json()
        except ValueError:
            raise JobSearchError("Adzuna API returned a non-JSON response") from None
        
        jobs = [self._standardize_job(result) for result in data.get('results', [])]
        print(f"Found {len(jobs)} jobs from Adzuna")
        return jobs
    
    @staticmethod
    def _standardize_job(adzuna_job: dict) -> dict:
        """
        Convert Adzuna job format to our standard format.
        Uses Adzuna's stable provider id so the same ad dedupes across
        searches even when redirect URLs carry different tracking params.
        """
        url = adzuna_job.get('redirect_url', '')
        provider_id = str(adzuna_job.get('id') or '').strip()
        if provider_id:
            job_id = f"adzuna_{provider_id}"
        else:
            # Fallback for ads without an id: hash the URL
            job_id = f"adzuna_{hashlib.md5(url.encode()).hexdigest()[:12]}"
        
        title = adzuna_job.get('title', '').strip()
        description = adzuna_job.get('description', '')
        location = adzuna_job.get('location', {}).get('display_name', '')
        salary_min = adzuna_job.get('salary_min')
        salary_max = adzuna_job.get('salary_max')
        
        return {
            'job_id': job_id,
            'source': 'adzuna',
            'title': title,
            'company': adzuna_job.get('company', {}).get('display_name', 'Unknown'),
            'location': location,
            'description': description,
            'url': url,
            'salary_min': int(salary_min) if salary_min else None,
            'salary_max': int(salary_max) if salary_max else None,
            'salary_currency': adzuna_job.get('salary_currency', 'USD'),
            'salary_is_predicted': 1 if str(adzuna_job.get('salary_is_predicted', '0')) == '1' else 0,
            'job_type': adzuna_job.get('contract_type', 'unknown'),
            'remote_status': infer_remote_status(title, description, location),
            'posted_date': adzuna_job.get('created') or adzuna_job.get('created_at') or '',
            'raw_data': adzuna_job
        }


class MockJobSearcher:
    """
    Mock searcher for testing without API calls.
    Returns sample software engineering jobs.
    """
    
    def search_jobs(
        self,
        query: str = "software engineer",
        location: str = None,
        **kwargs
    ) -> List[Dict]:
        """Return mock job data for testing."""
        
        mock_jobs = [
            {
                'job_id': 'mock_001',
                'source': 'mock',
                'title': 'Senior Software Engineer',
                'company': 'TechCorp Inc',
                'location': location or 'San Francisco, CA',
                'description': 'Looking for a senior software engineer with Python, React, AWS, and Docker experience. 5+ years required. Remote-friendly. Experience with JavaScript, SQL, PostgreSQL, git, CI/CD pipelines required.',
                'url': 'https://example.com/job/001',
                'salary_min': 120000,
                'salary_max': 160000,
                'salary_currency': 'USD',
                'job_type': 'fulltime',
                'remote_status': 'hybrid',
                'posted_date': '2024-01-15'
            },
            {
                'job_id': 'mock_002',
                'source': 'mock',
                'title': 'Full Stack Developer',
                'company': 'StartupXYZ',
                'location': location or 'New York, NY',
                'description': 'Join our growing team! We need a Full Stack Developer with Python, JavaScript, React, AWS, Docker, and Kubernetes experience. Database experience with PostgreSQL required. Knowledge of git and CI/CD processes preferred.',
                'url': 'https://example.com/job/002',
                'salary_min': 90000,
                'salary_max': 130000,
                'salary_currency': 'USD',
                'job_type': 'fulltime',
                'remote_status': 'remote',
                'posted_date': '2024-01-14'
            },
            {
                'job_id': 'mock_003',
                'source': 'mock',
                'title': 'Backend Engineer',
                'company': 'DataSystems',
                'location': location or 'Austin, TX',
                'description': 'Python backend developer needed. Experience with Django, PostgreSQL, and Redis required.',
                'url': 'https://example.com/job/003',
                'salary_min': 110000,
                'salary_max': 150000,
                'salary_currency': 'USD',
                'job_type': 'fulltime',
                'remote_status': 'onsite',
                'posted_date': '2024-01-13'
            },
            {
                'job_id': 'mock_004',
                'source': 'mock',
                'title': 'Machine Learning Engineer',
                'company': 'AI Innovations',
                'location': location or 'Remote',
                'description': 'Build ML models using PyTorch and TensorFlow. Experience with NLP and computer vision preferred.',
                'url': 'https://example.com/job/004',
                'salary_min': 140000,
                'salary_max': 180000,
                'salary_currency': 'USD',
                'job_type': 'fulltime',
                'remote_status': 'remote',
                'posted_date': '2024-01-12'
            },
            {
                'job_id': 'mock_005',
                'source': 'mock',
                'title': 'DevOps Engineer',
                'company': 'CloudFirst',
                'location': location or 'Seattle, WA',
                'description': 'Manage Kubernetes clusters and CI/CD pipelines. Terraform and AWS experience required.',
                'url': 'https://example.com/job/005',
                'salary_min': 125000,
                'salary_max': 165000,
                'salary_currency': 'USD',
                'job_type': 'fulltime',
                'remote_status': 'hybrid',
                'posted_date': '2024-01-11'
            }
        ]
        
        print(f"Returning {len(mock_jobs)} mock jobs for testing")
        return mock_jobs


def get_job_searcher(use_mock: bool = False, **credentials) -> AdzunaJobSearcher:
    """
    Factory function to get a job searcher instance.
    
    Args:
        use_mock: If True, return mock searcher for testing
        **credentials: Optional credentials for Adzuna API
    """
    if use_mock:
        return MockJobSearcher()
    
    return AdzunaJobSearcher(**credentials)


# Example usage
if __name__ == "__main__":
    # Test with mock data first
    print("Testing with mock job searcher...")
    searcher = get_job_searcher(use_mock=True)
    jobs = searcher.search_jobs("software engineer", "Remote")
    
    for job in jobs:
        print(f"\n{job['title']} at {job['company']}")
        print(f"  Location: {job['location']}")
        print(f"  Salary: ${job['salary_min']:,} - ${job['salary_max']:,}")
        print(f"  URL: {job['url']}")