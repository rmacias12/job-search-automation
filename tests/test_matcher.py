"""Tests for the keyword matching engine (regression tests for the
tuple-unpacking score bug, phrase exclusions, remote/salary gates,
primary-skill scoring and title coverage scoring)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from matcher import KeywordMatcher, MatchResult


def base_resume(**overrides):
    resume = {
        'skills': ['python', 'javascript', 'react', 'sql', 'git', 'azure',
                   'node.js', 'ci/cd', 'rest api', 'machine learning', 'gcp'],
        'primary_skills': ['python', 'javascript', 'react', 'sql', 'git'],
        'titles': ['software engineer'],
        'preferred_titles': ['senior software engineer', 'software architect'],
        'preferred_locations': ['Remote', 'Columbus'],
        'preferred_job_types': [],
        'target_salary_min': 85000,
        'target_salary_max': 125000,
        'required_skills': [],
        'excluded_keywords': ['Entry level', 'Junior'],
    }
    resume.update(overrides)
    return resume


def job(**overrides):
    data = {
        'id': 1,
        'title': 'Senior Software Engineer',
        'company': 'Acme',
        'location': 'Remote, US',
        'description': 'Build Python services and React frontends with JavaScript. SQL and git required.',
        'salary_min': 95000,
        'salary_max': 115000,
        'remote_status': 'unknown',
    }
    data.update(overrides)
    return data


class ScoringRegressionTests(unittest.TestCase):
    def test_location_and_salary_contribute_real_points(self):
        """Regression: scores used to receive the (passes, score) tuple's
        boolean instead of the score, capping overall at ~65."""
        m = KeywordMatcher(base_resume())
        r = m.match_job(job())
        self.assertEqual(r.location_match_score, 100.0)
        self.assertEqual(r.salary_match_score, 100.0)
        # skills: python, javascript, react, sql, git all in description => 100
        self.assertEqual(r.skill_match_score, 100.0)
        # title: 'senior software engineer' substring match => 100
        self.assertEqual(r.title_match_score, 100.0)
        self.assertEqual(r.overall_score, 100.0)
        self.assertTrue(r.passed_gates)

    def test_overall_can_exceed_old_65_cap(self):
        m = KeywordMatcher(base_resume())
        r = m.match_job(job())
        self.assertGreater(r.overall_score, 65.0)


class GateTests(unittest.TestCase):
    def test_multiword_excluded_phrase_is_detected(self):
        """Regression: 'entry level' could never match single-token words."""
        m = KeywordMatcher(base_resume())
        r = m.match_job(job(description='Entry level developers welcome. Python, git, sql, react, javascript.'))
        self.assertFalse(r.passed_gates)
        self.assertTrue(any('entry level' in f.lower() for f in r.gate_failures))

    def test_single_word_exclusion_still_works(self):
        m = KeywordMatcher(base_resume())
        r = m.match_job(job(title='Junior Python Developer',
                            description='Python, git, sql, react, javascript.'))
        self.assertFalse(r.passed_gates)

    def test_salary_below_minimum_fails_gate(self):
        m = KeywordMatcher(base_resume())
        r = m.match_job(job(salary_min=55000, salary_max=75000))
        self.assertFalse(r.passed_gates)
        self.assertTrue(any('salary' in f.lower() for f in r.gate_failures))

    def test_overlapping_salary_range_passes_with_partial_score(self):
        m = KeywordMatcher(base_resume())
        r = m.match_job(job(salary_min=70000, salary_max=95000))
        self.assertTrue(r.passed_gates)
        self.assertGreaterEqual(r.salary_match_score, 60.0)
        self.assertLess(r.salary_match_score, 100.0)

    def test_unknown_salary_is_neutral_not_rejected(self):
        m = KeywordMatcher(base_resume())
        r = m.match_job(job(salary_min=None, salary_max=None))
        self.assertTrue(r.passed_gates)
        self.assertEqual(r.salary_match_score, 50.0)
        self.assertTrue(r.evidence['salary_unknown'])

    def test_onsite_other_city_fails_location_gate(self):
        m = KeywordMatcher(base_resume())
        r = m.match_job(job(location='Austin, TX', remote_status='onsite',
                            description='Onsite in Austin. Python, git, sql, react, javascript.'))
        self.assertFalse(r.passed_gates)
        self.assertTrue(any('location' in f.lower() for f in r.gate_failures))

    def test_remote_inferred_from_title_when_status_unknown(self):
        m = KeywordMatcher(base_resume())
        r = m.match_job(job(location='US', title='Senior Software Engineer - Remote',
                            remote_status='unknown'))
        self.assertEqual(r.evidence['remote'], 'remote')
        self.assertTrue(r.passed_gates)
        self.assertEqual(r.location_match_score, 100.0)

    def test_columbus_hybrid_passes_with_city_match(self):
        m = KeywordMatcher(base_resume())
        r = m.match_job(job(location='Columbus, Franklin County', remote_status='hybrid'))
        self.assertTrue(r.passed_gates)
        self.assertEqual(r.location_match_score, 100.0)

    def test_required_skill_gate_uses_aliases(self):
        m = KeywordMatcher(base_resume(required_skills=['node.js']))
        r = m.match_job(job(description='Strong Node experience required. Python, git, sql, react, javascript.'))
        self.assertTrue(r.passed_gates)


class SkillAndTitleScoringTests(unittest.TestCase):
    def test_primary_skills_basis_not_full_resume(self):
        m = KeywordMatcher(base_resume())
        r = m.match_job(job(description='Python and SQL only.'))
        # 2 of 5 primary skills found => 40, not 2/11 of all skills
        self.assertEqual(r.evidence['skills_basis'], 'primary_skills')
        self.assertEqual(r.skill_match_score, 40.0)
        self.assertEqual(sorted(r.evidence['found_skills']), ['python', 'sql'])

    def test_falls_back_to_all_skills_without_primary(self):
        resume = base_resume()
        del resume['primary_skills']
        m = KeywordMatcher(resume)
        r = m.match_job(job(description='Python and SQL only.'))
        self.assertEqual(r.evidence['skills_basis'], 'skills')
        self.assertAlmostEqual(r.skill_match_score, round(100.0 * 2 / 11, 2))

    def test_title_coverage_and_senior_bonus(self):
        m = KeywordMatcher(base_resume())
        r = m.match_job(job(title='GenAI Python Systems Engineer - Senior Manager'))
        # coverage of 'senior software engineer' tokens: {senior} / 3? 'engineer' too => 2/3
        self.assertGreaterEqual(r.title_match_score, 60.0)

    def test_non_senior_unrelated_title_scores_low(self):
        m = KeywordMatcher(base_resume())
        r = m.match_job(job(title='Dental Practice Coordinator'))
        self.assertLess(r.title_match_score, 30.0)

    def test_evidence_is_json_serializable(self):
        import json
        m = KeywordMatcher(base_resume())
        r = m.match_job(job())
        json.dumps(r.evidence)  # must not raise
        self.assertIn('found_skills', r.evidence)
        self.assertIn('remote', r.evidence)
        self.assertIn('salary_predicted', r.evidence)

    def test_predicted_salary_flag_recorded(self):
        m = KeywordMatcher(base_resume())
        r = m.match_job(job(salary_is_predicted=1))
        self.assertTrue(r.evidence['salary_predicted'])

    def test_truncated_description_still_scores(self):
        """Adzuna truncates descriptions to ~500 chars; scoring must not crash
        or zero out on short text."""
        m = KeywordMatcher(base_resume())
        r = m.match_job(job(description='Python. React.'))
        self.assertGreater(r.skill_match_score, 0.0)
        self.assertTrue(r.passed_gates)


if __name__ == '__main__':
    unittest.main()
