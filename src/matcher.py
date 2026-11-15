"""
Job-Resume Matching Engine
Combines keyword filtering (hard requirements) with scoring
Design ready for semantic (embedding) matching addition
"""

import re
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field


# Alternate spellings so truncated job descriptions still match resume skills.
SKILL_ALIASES = {
    'node.js': ['node.js', 'nodejs', 'node js', 'node'],
    'ci/cd': ['ci/cd', 'cicd', 'continuous integration', 'continuous delivery', 'continuous deployment'],
    'rest api': ['rest api', 'rest apis', 'restful api', 'restful apis', 'restful'],
    'machine learning': ['machine learning', 'ml'],
    'gcp': ['gcp', 'google cloud platform', 'google cloud'],
    'aws': ['aws', 'amazon web services'],
    'sql': ['sql', 'transact-sql', 't-sql', 'mysql', 'postgresql', 'ms sql', 'mssql'],
    'javascript': ['javascript', 'ecmascript'],
    'python': ['python', 'python3'],
    'azure': ['azure', 'microsoft azure'],
}

# Title tokens that signal a senior individual-contributor role.
SENIOR_TITLE_PATTERN = re.compile(r'\b(senior|staff|principal|lead|architect|sr\.?)\b')


@dataclass
class MatchResult:
    """Container for match scoring results."""
    job_id: int
    resume_id: int
    overall_score: float  # 0-100
    passed_gates: bool  # Did it pass all keyword requirements?
    
    # Component scores
    skill_match_score: float  # 0-100
    title_match_score: float  # 0-100
    location_match_score: float  # 0-100
    salary_match_score: float  # 0-100
    
    # Gate failure reasons (if any)
    gate_failures: List[str]
    
    # Structured, JSON-serializable evidence for why the job scored this way
    evidence: Dict = field(default_factory=dict)


class KeywordMatcher:
    """
    Keyword-based matching for filtering and scoring.
    Acts as the "gatekeeper" - rejects jobs that don't meet hard requirements.
    """
    
    def __init__(self, resume_data: Dict):
        """
        Initialize with parsed resume data.
        
        Args:
            resume_data: Dictionary with keys like:
                - skills: List[str]
                - primary_skills: List[str] (subset used for skill scoring; falls back to skills)
                - titles: List[str] (previous job titles)
                - preferred_titles: List[str] (titles being targeted; falls back to titles)
                - experience_years: int
                - preferred_locations: List[str]
                - preferred_job_types: List[str] (e.g., ['remote', 'hybrid'])
                - target_salary_min: int
                - target_salary_max: int
                - required_skills: List[str] (must-haves)
                - excluded_keywords: List[str] (deal-breakers, multi-word phrases supported)
        """
        self.resume = resume_data
        
        # Normalize for case-insensitive matching
        self.skills = set(s.lower() for s in resume_data.get('skills', []))
        self.titles = set(t.lower() for t in resume_data.get('titles', []))
        self.required_skills = set(s.lower() for s in resume_data.get('required_skills', []))
        self.excluded_keywords = set(k.lower() for k in resume_data.get('excluded_keywords', []))
        # Ordered lists used for scoring
        self.primary_skills = [s.lower() for s in resume_data.get('primary_skills', [])]
        self.preferred_titles = [t.lower() for t in resume_data.get('preferred_titles', [])]
    
    def match_job(self, job: Dict) -> MatchResult:
        """
        Match a single job against the resume.
        Returns MatchResult with scores and gate status.
        """
        # Normalize job data
        job_description = job.get('description', '') or ''
        job_desc = (job_description + ' ' + job.get('title', '')).lower()
        job_title = job.get('title', '') or ''
        job_location = job.get('location', '') or ''
        remote_status = (job.get('remote_status', '') or '').lower()
        
        # Run all gates
        gate_failures = []
        
        # Gate 1: Required skills must be present
        if self.required_skills:
            missing_required = [s for s in sorted(self.required_skills)
                                if not self._skill_present(s, job_desc)]
            if missing_required:
                gate_failures.append(f"Missing required skills: {', '.join(missing_required)}")
        
        # Gate 2: No excluded keywords (multi-word phrases supported)
        if self.excluded_keywords:
            found_excluded = [k for k in sorted(self.excluded_keywords)
                              if re.search(r'\b' + re.escape(k) + r'\b', job_desc)]
            if found_excluded:
                gate_failures.append(f"Found excluded keywords: {', '.join(found_excluded)}")
        
        # Gate 3: Location preference
        location_pass, location_score = self._score_location(
            job_location, remote_status, job_title, job_description
        )
        if not location_pass and self.resume.get('preferred_locations'):
            gate_failures.append(f"Location not acceptable: {job_location or 'Unknown'}")
        
        # Gate 4: Salary alignment
        salary_pass, salary_score = self._score_salary(
            job.get('salary_min'), job.get('salary_max')
        )
        if not salary_pass:
            gate_failures.append("Salary below minimum requirement")
        
        passed_gates = len(gate_failures) == 0
        
        # Calculate component scores
        skill_score, found_skills = self._score_skills(job_desc)
        title_score = self._score_title(job_title.lower())
        
        # Weighted overall score
        # Can tune these weights based on what matters most
        overall_score = (
            skill_score * 0.40 +
            title_score * 0.25 +
            location_score * 0.20 +
            salary_score * 0.15
        )
        
        evidence = {
            'found_skills': found_skills,
            'skills_basis': 'primary_skills' if self.primary_skills else 'skills',
            'remote': self._infer_remote(job_location, remote_status, job_title, job_description),
            'salary_unknown': job.get('salary_min') is None and job.get('salary_max') is None,
            'salary_predicted': bool(job.get('salary_is_predicted')),
            'gate_failures': list(gate_failures),
        }
        
        return MatchResult(
            job_id=job.get('id', 0),
            resume_id=0,  # Will be set by caller
            overall_score=round(overall_score, 2),
            passed_gates=passed_gates,
            skill_match_score=round(skill_score, 2),
            title_match_score=round(title_score, 2),
            location_match_score=round(location_score, 2),
            salary_match_score=round(salary_score, 2),
            gate_failures=gate_failures,
            evidence=evidence
        )
    
    def match_jobs(self, jobs: List[Dict], min_score: float = 0.0) -> List[MatchResult]:
        """
        Match multiple jobs and return sorted results.
        
        Args:
            jobs: List of job dictionaries
            min_score: Minimum overall score to include
        
        Returns:
            List of MatchResult objects, sorted by score descending
        """
        results = []
        for job in jobs:
            result = self.match_job(job)
            if result.passed_gates and result.overall_score >= min_score:
                results.append(result)
        
        # Sort by overall score descending
        results.sort(key=lambda x: x.overall_score, reverse=True)
        return results
    
    def _skill_present(self, skill: str, text: str) -> bool:
        """Check whether a skill (or a known alias of it) appears in text."""
        candidates = [skill] + SKILL_ALIASES.get(skill, [])
        return any(re.search(r'\b' + re.escape(c) + r'\b', text) for c in candidates)
    
    def _extract_skills(self, text: str) -> set:
        """Extract mentioned skills from job text."""
        return set(s for s in self.skills if self._skill_present(s, text))
    
    def _extract_words(self, text: str) -> set:
        """Extract all words from text for matching."""
        words = re.findall(r'\b[a-z]+\b', text)
        return set(words)
    
    def _score_skills(self, job_desc: str) -> Tuple[float, List[str]]:
        """
        Score skill match (0-100) against the primary_skills list when set,
        so a broad resume is not penalized for skills a short ad never
        mentions. Returns (score, found_skills).
        """
        basis = self.primary_skills if self.primary_skills else sorted(self.skills)
        if not basis:
            return 100.0, []  # Neutral if no skills specified
        
        found = [s for s in basis if self._skill_present(s, job_desc)]
        score = 100.0 * len(found) / len(basis)
        return score, found
    
    def _score_title(self, job_title: str) -> float:
        """
        Score title match (0-100) against preferred_titles (falling back to
        previous titles). Uses token coverage so partial matches still score,
        with a bonus for senior individual-contributor markers.
        """
        prefs = self.preferred_titles or sorted(self.titles)
        if not prefs:
            return 100.0  # Neutral if no titles specified
        
        best = 0.0
        for title in prefs:
            if not title:
                continue
            # Exact / substring match
            if title in job_title or (job_title and job_title in title):
                best = 100.0
                break
            # Token coverage and overlap
            title_words = set(re.findall(r'[a-z]+', title))
            job_words = set(re.findall(r'[a-z]+', job_title))
            if title_words and job_words:
                intersection = title_words & job_words
                coverage = len(intersection) / len(title_words)
                jaccard = len(intersection) / len(title_words | job_words)
                best = max(best, 100.0 * max(coverage, jaccard))
        
        # Senior IC bonus for titles that don't exactly match a preferred title
        if best < 100.0 and SENIOR_TITLE_PATTERN.search(job_title):
            best = min(100.0, best + 15.0)
        
        return best
    
    def _infer_remote(self, job_location: str, remote_status: str,
                      job_title: str = "", job_description: str = "") -> str:
        """Infer remote/hybrid from the status field or the ad text."""
        if remote_status in ('remote', 'hybrid'):
            return remote_status
        text = f"{job_title} {job_description} {job_location}".lower()
        if re.search(r'\bhybrid\b', text):
            return 'hybrid'
        if re.search(r'\bremote\b|\bremotely\b|work(?:s)? from home|\bwfh\b|home[- ]based', text):
            return 'remote'
        return 'unknown'
    
    def _score_location(self, job_location: str, remote_status: str,
                        job_title: str = "", job_description: str = "") -> Tuple[bool, float]:
        """
        Score location match.
        Returns (passes_gate, score_0_to_100).
        """
        preferred_locations = [str(l).lower().strip() for l in self.resume.get('preferred_locations', []) if str(l).strip()]
        preferred_types = [str(t).lower() for t in self.resume.get('preferred_job_types', [])]
        
        if not preferred_locations and not preferred_types:
            return True, 100.0  # Any location acceptable
        
        wants_remote = any('remote' in t for t in preferred_types) or 'remote' in preferred_locations
        cities = [loc for loc in preferred_locations if 'remote' not in loc]
        
        inferred = self._infer_remote(job_location, remote_status, job_title, job_description)
        loc = (job_location or '').lower()
        city_match = any(
            c in loc or any(word in loc for word in c.split())
            for c in cities
        )
        
        # Gate: must be remote-capable or in a preferred city
        if wants_remote and cities:
            passes = inferred in ('remote', 'hybrid') or city_match
        elif wants_remote:
            passes = inferred in ('remote', 'hybrid')
        elif cities:
            passes = city_match or inferred == 'remote'
        else:
            passes = True
        
        # Score
        if inferred == 'remote' or city_match:
            score = 100.0
        elif inferred == 'hybrid':
            score = 70.0
        else:
            score = 0.0
        
        return passes, score
    
    def _score_salary(self, job_min: Optional[int], job_max: Optional[int]) -> Tuple[bool, float]:
        """
        Score salary alignment.
        Returns (passes_gate, score_0_to_100).
        """
        target_min = self.resume.get('target_salary_min')
        target_max = self.resume.get('target_salary_max')
        
        if not target_min and not target_max:
            return True, 100.0  # No salary requirements
        
        if not job_min and not job_max:
            return True, 50.0  # Unknown salary - neutral, keep the opportunity
        
        # Use job max if min not specified, or vice versa
        effective_job_min = job_min or job_max
        effective_job_max = job_max or job_min
        
        # Gate: job's top of range must reach our minimum
        if target_min and effective_job_max < target_min:
            return False, 0.0  # Job max is below our minimum
        
        if target_min:
            if effective_job_min >= target_min:
                return True, 100.0  # Meets or exceeds target (even above target_max - good!)
            # Ranges overlap: job max reaches target min but starts below it
            ratio = effective_job_max / target_min  # >= 1.0 because the gate passed
            return True, min(90.0, 60.0 + 60.0 * (ratio - 1.0))
        
        # Only maximum specified (unusual but handle it)
        if target_max and effective_job_min is not None:
            if effective_job_min <= target_max:
                return True, 100.0
            return False, 0.0
        return True, 100.0


def create_test_resume() -> Dict:
    """Create a sample resume for testing."""
    return {
        'skills': [
            'python', 'javascript', 'react', 'aws', 'docker', 
            'kubernetes', 'sql', 'postgresql', 'git', 'ci/cd'
        ],
        'primary_skills': ['python', 'javascript', 'react', 'sql', 'git'],
        'required_skills': ['python'],  # Must have
        'titles': [
            'software engineer', 'backend developer', 'full stack developer'
        ],
        'preferred_titles': [
            'senior software engineer', 'staff engineer', 'software architect'
        ],
        'experience_years': 5,
        'preferred_locations': ['San Francisco', 'Remote', 'Austin'],
        'preferred_job_types': ['remote', 'hybrid'],
        'target_salary_min': 120000,
        'target_salary_max': 180000,
        'excluded_keywords': ['senior architect', 'junior', 'entry level']
    }


# Example usage
if __name__ == "__main__":
    # Test with sample data
    from job_searcher import MockJobSearcher
    
    print("Testing Keyword Matcher...")
    print("=" * 60)
    
    # Get test jobs
    searcher = MockJobSearcher()
    jobs = searcher.search_jobs("software engineer")
    
    # Create test resume
    resume = create_test_resume()
    
    # Create matcher and evaluate
    matcher = KeywordMatcher(resume)
    results = matcher.match_jobs(jobs, min_score=0)
    
    print(f"\nPrimary Skills: {', '.join(resume['primary_skills'])}")
    print(f"Required: {', '.join(resume['required_skills'])}")
    print(f"Target Salary: ${resume['target_salary_min']:,} - ${resume['target_salary_max']:,}")
    print(f"Preferred Locations: {', '.join(resume['preferred_locations'])}")
    print()
    print(f"Matched {len(results)} jobs:")
    print("-" * 60)
    
    print("\nAll jobs evaluation:")
    for job in jobs:
        result = matcher.match_job(job)
        status = "✅ PASS" if result.passed_gates else "❌ FAIL"
        print(f"\n{status} {job['title']} at {job['company']} - Score: {result.overall_score:.1f}%")
        if result.gate_failures:
            print(f"   Gate failures: {', '.join(result.gate_failures)}")
        print(f"   ├─ Skills: {result.skill_match_score:.1f}% (found: {', '.join(result.evidence['found_skills'])})")
        print(f"   ├─ Title: {result.title_match_score:.1f}%")
        print(f"   ├─ Location: {result.location_match_score:.1f}% ({result.evidence['remote']})")
        print(f"   └─ Salary: {result.salary_match_score:.1f}%")
    
    if not results:
        print("\nNo jobs passed all keyword gates!")
