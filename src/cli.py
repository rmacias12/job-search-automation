"""
CLI Interface for Job Search Automation
Orchestrates: Job Search → Database Storage → Matching → Review Output
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Optional

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_database, ensure_schema, get_connection, get_top_matches, update_match_status, insert_resume, insert_match
from job_searcher import get_job_searcher, AdzunaJobSearcher, JobSearchError
from credentials import CredentialError
from matcher import KeywordMatcher
from resume_parser import ResumeParser, create_resume_config_from_pdf
from embedding_matcher import HybridMatcher
from tracking import ApplicationTracker, format_salary
from notion_sync import NotionSync


def _load_resume_config() -> dict:
    """Load resume_config.json if present; empty dict otherwise."""
    config_path = os.path.expanduser("~/job-search-automation/resume_config.json")
    try:
        with open(config_path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def search_and_save_jobs(
    query: str,
    location: str = None,
    use_mock: bool = False,
    max_results: int = 20,
    max_days_old: int = 30,
    sort_by: str = 'date'
) -> int:
    """
    Search for jobs and save to database.
    Real searches are filtered by the configured target salary minimum,
    limited to recent postings (max_days_old) and sorted newest first.
    salary_max is intentionally NOT sent to the API: jobs paying above the
    target ceiling are opportunities, not exclusions.
    Returns number of NEW jobs saved.
    """
    print(f"\n🔍 Searching for '{query}' jobs...")
    if location:
        print(f"   Location: {location}")
    
    # Get job searcher — real searches NEVER silently fall back to mock data
    if use_mock:
        searcher = get_job_searcher(use_mock=True)
        salary_min = None
    else:
        try:
            searcher = get_job_searcher(use_mock=False)
        except (ValueError, CredentialError) as e:
            print(f"❌ {e}")
            print("   Configure Adzuna credentials (see credentials.json),")
            print("   or pass --mock explicitly to use test data.")
            return 0
        salary_min = _load_resume_config().get('target_salary_min')
        if salary_min:
            print(f"   Filters: salary >= ${salary_min:,} | last {max_days_old} days | sorted by {sort_by}")
    
    # Search
    try:
        jobs = searcher.search_jobs(
            query=query,
            location=location,
            salary_min=salary_min,
            max_results=max_results,
            max_days_old=None if use_mock else max_days_old,
            sort_by=None if use_mock else sort_by
        )
    except JobSearchError as e:
        print(f"❌ Search failed: {e}")
        return 0
    except Exception as e:
        # Sanitized: never print exception text that may embed request URLs.
        print(f"❌ Search failed: {type(e).__name__}")
        return 0
    
    # Save to database
    if not jobs:
        print("No jobs found.")
        return 0
    
    from database import insert_job
    
    saved_count = 0
    dup_count = 0
    for job in jobs:
        result = insert_job(job)
        if result:
            saved_count += 1
        elif result == 0:
            dup_count += 1
    
    print(f"✅ Saved {saved_count} new jobs to database ({dup_count} duplicates skipped)")
    return saved_count


def match_jobs_against_resume(
    resume_data: dict,
    min_score: float = 0.0,
    use_semantic: bool = False,
    dry_run: bool = False
) -> list:
    """
    Match all unprocessed jobs against resume and save scores.
    Re-matching refreshes scores/evidence but preserves user-managed
    statuses and notes (see database.insert_match).
    Returns list of top matches.
    """
    print(f"\n🎯 Matching jobs against resume...")
    print(f"   Required skills: {', '.join(resume_data.get('required_skills', [])) or '(none)'}")
    print(f"   Target salary: ${resume_data.get('target_salary_min', 0):,} - ${resume_data.get('target_salary_max', 0):,}")
    if dry_run:
        print("   📋 DRY RUN — scores will be computed but NOT written")
    
    # Get unprocessed jobs from database
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get jobs that haven't been matched yet
    cursor.execute("""
        SELECT id, job_id, title, company, location, description, 
               salary_min, salary_max, job_type, remote_status
        FROM jobs
        WHERE id NOT IN (SELECT job_id FROM matches WHERE job_id IS NOT NULL)
    """)
    
    columns = [desc[0] for desc in cursor.description]
    jobs = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    
    if not jobs:
        print("No new jobs to match.")
        return []
    
    print(f"   Processing {len(jobs)} jobs...")
    
    # Get minimum score thresholds from config
    min_match_score = resume_data.get('min_match_score', 0)  # Keyword score threshold
    min_semantic_score = resume_data.get('min_semantic_score', 0)  # Semantic score threshold
    
    # Use hybrid matcher if semantic is enabled
    if use_semantic:
        print("   Using hybrid (keyword + semantic) matching...")
        if min_semantic_score > 0:
            print(f"   Minimum semantic score: {min_semantic_score}%")
        matcher = HybridMatcher(resume_data, use_local=False)
        # Apply the keyword threshold up front so embedding API calls are
        # only spent on jobs that could actually be saved.
        enriched_jobs = matcher.match_jobs(
            jobs, min_keyword_score=max(min_score, min_match_score)
        )
        keyword_matcher = KeywordMatcher(resume_data)
        
        # Filter and save matches to database
        saved_count = 0
        skipped_count = 0
        for job in enriched_jobs:
            semantic_score = job.get('semantic_score', 0)
            
            # Check minimum thresholds
            if min_semantic_score > 0 and semantic_score < min_semantic_score:
                skipped_count += 1
                continue
            
            # Re-run the keyword matcher for component scores and evidence
            kw_result = keyword_matcher.match_job(job)
            
            if not dry_run:
                insert_match({
                    'job_id': job['id'],
                    'resume_id': resume_data.get('id', 1),
                    'match_score': job['combined_score'],
                    'skill_match_score': kw_result.skill_match_score,
                    'title_match_score': kw_result.title_match_score,
                    'location_match_score': kw_result.location_match_score,
                    'salary_match_score': kw_result.salary_match_score,
                    'status': 'new',
                    'notes': f"Semantic: {job.get('semantic_score', 'N/A')}%",
                    'evidence': json.dumps(kw_result.evidence)
                })
            saved_count += 1
        
        if skipped_count > 0:
            print(f"   Skipped {skipped_count} jobs below minimum score thresholds")
        verb = "Would save" if dry_run else "Matched and saved"
        print(f"✅ {verb} {saved_count} jobs with hybrid scoring")
        
        # Convert to match format for display
        matches = []
        for job in enriched_jobs[:20]:
            matches.append({
                'title': job.get('title', 'Unknown'),
                'company': job.get('company', 'Unknown'),
                'location': job.get('location', 'Unknown'),
                'url': job.get('url', job.get('redirect_url', '')),
                'match_score': job.get('combined_score', job.get('keyword_score', 0)),
                'match_id': 0,
                'status': 'new'
            })
        return matches
    else:
        # Use keyword-only matcher
        matcher = KeywordMatcher(resume_data)
        
        if min_match_score > 0:
            print(f"   Minimum match score: {min_match_score}%")
        
        matched_count = 0
        eligible_count = 0
        rejected_count = 0
        skipped_count = 0
        
        for job in jobs:
            result = matcher.match_job(job)
            
            # Check minimum score threshold before saving
            if min_match_score > 0 and result.overall_score < min_match_score:
                skipped_count += 1
                continue
            
            # Save match (rejected = failed a hard gate, kept for transparency)
            if not dry_run:
                insert_match({
                    'job_id': job['id'],
                    'resume_id': resume_data.get('id', 1),
                    'match_score': result.overall_score,
                    'skill_match_score': result.skill_match_score,
                    'title_match_score': result.title_match_score,
                    'location_match_score': result.location_match_score,
                    'salary_match_score': result.salary_match_score,
                    'status': 'new' if result.passed_gates else 'auto_rejected',
                    'notes': ', '.join(result.gate_failures) if result.gate_failures else None,
                    'evidence': json.dumps(result.evidence)
                })
            
            if result.passed_gates:
                eligible_count += 1
            else:
                rejected_count += 1
            matched_count += 1
        
        if skipped_count > 0:
            print(f"   Skipped {skipped_count} jobs below {min_match_score}% match score")
        verb = "Would match" if dry_run else "Matched"
        suffix = " — nothing written (dry run)" if dry_run else ""
        print(f"✅ {verb} {matched_count} jobs ({eligible_count} eligible, {rejected_count} gate-rejected){suffix}")
        
        # Get top matches
        top_matches = get_top_matches(limit=20, min_score=min_score)
        return top_matches


def display_matches(matches: list, detailed: bool = False):
    """Display job matches in a formatted way."""
    if not matches:
        print("\nNo matching jobs found.")
        return
    
    print(f"\n{'='*80}")
    print(f"TOP {len(matches)} JOB MATCHES")
    print(f"{'='*80}\n")
    
    for i, match in enumerate(matches, 1):
        print(f"[{i}] {match['title']}")
        print(f"    🏢 {match['company']}")
        print(f"    📍 {match['location']}")
        print(f"    🔗 {match['url']}")
        print(f"    📊 Match Score: {match['match_score']:.1f}%")
        
        if detailed:
            # Get more details from database
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT skill_match_score, title_match_score, 
                       location_match_score, salary_match_score, notes
                FROM matches WHERE id = ?
            """, (match['match_id'],))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                print(f"       ├─ Skills: {row[0]:.1f}%")
                print(f"       ├─ Title: {row[1]:.1f}%")
                print(f"       ├─ Location: {row[2]:.1f}%")
                print(f"       └─ Salary: {row[3]:.1f}%")
                if row[4]:
                    print(f"       ⚠️  {row[4]}")
        
        print()


def export_matches_to_csv(matches: list, output_path: str, detailed: bool = False):
    """Export matches to CSV file."""
    import csv
    from datetime import datetime
    
    if not matches:
        print("No matches to export.")
        return
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or '.', exist_ok=True)
    
    # Define columns
    columns = ['rank', 'title', 'company', 'location', 'match_score', 'url', 'status']
    
    if detailed:
        # Get detailed scores from database
        conn = get_connection()
        cursor = conn.cursor()
        
        detailed_data = []
        for i, match in enumerate(matches, 1):
            cursor.execute("""
                SELECT skill_match_score, title_match_score, 
                       location_match_score, salary_match_score, notes, created_at
                FROM matches WHERE id = ?
            """, (match['match_id'],))
            row = cursor.fetchone()
            
            data = {
                'rank': i,
                'title': match['title'],
                'company': match['company'],
                'location': match['location'],
                'match_score': f"{match['match_score']:.1f}%",
                'skill_score': f"{row[0]:.1f}%" if row and row[0] else "N/A",
                'title_score': f"{row[1]:.1f}%" if row and row[1] else "N/A",
                'location_score': f"{row[2]:.1f}%" if row and row[2] else "N/A",
                'salary_score': f"{row[3]:.1f}%" if row and row[3] else "N/A",
                'url': match['url'],
                'status': match.get('status', 'new'),
                'notes': row[4] if row and row[4] else '',
                'matched_date': row[5] if row and row[5] else ''
            }
            detailed_data.append(data)
        
        conn.close()
        
        # Write detailed CSV
        fieldnames = ['rank', 'title', 'company', 'location', 'match_score', 
                      'skill_score', 'title_score', 'location_score', 'salary_score',
                      'url', 'status', 'notes', 'matched_date']
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(detailed_data)
    else:
        # Write simple CSV
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for i, match in enumerate(matches, 1):
                writer.writerow({
                    'rank': i,
                    'title': match['title'],
                    'company': match['company'],
                    'location': match['location'],
                    'match_score': f"{match['match_score']:.1f}%",
                    'url': match['url'],
                    'status': match.get('status', 'new')
                })
    
    print(f"✅ Exported {len(matches)} matches to: {output_path}")


def export_matches_to_json(matches: list, output_path: str, detailed: bool = False):
    """Export matches to JSON file."""
    import json
    from datetime import datetime
    
    if not matches:
        print("No matches to export.")
        return
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or '.', exist_ok=True)
    
    # Build export data
    export_data = {
        'exported_at': datetime.now().isoformat(),
        'total_matches': len(matches),
        'matches': []
    }
    
    conn = get_connection()
    cursor = conn.cursor()
    
    for i, match in enumerate(matches, 1):
        match_data = {
            'rank': i,
            'title': match['title'],
            'company': match['company'],
            'location': match['location'],
            'match_score': match['match_score'],
            'url': match['url'],
            'status': match.get('status', 'new')
        }
        
        if detailed:
            cursor.execute("""
                SELECT skill_match_score, title_match_score, 
                       location_match_score, salary_match_score, notes, created_at
                FROM matches WHERE id = ?
            """, (match['match_id'],))
            row = cursor.fetchone()
            
            if row:
                match_data['detailed_scores'] = {
                    'skill': row[0],
                    'title': row[1],
                    'location': row[2],
                    'salary': row[3]
                }
                match_data['notes'] = row[4]
                match_data['matched_date'] = row[5]
        
        export_data['matches'].append(match_data)
    
    conn.close()
    
    # Write JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Exported {len(matches)} matches to: {output_path}")


def create_sample_resume():
    """Create a sample resume configuration file."""
    import json
    
    sample = {
        "resume_id": "my_resume_001",
        "name": "Your Name",
        "email": "your.email@example.com",
        "skills": [
            "python", "javascript", "react", "aws", "docker",
            "kubernetes", "sql", "postgresql", "git", "ci/cd"
        ],
        "required_skills": ["python"],
        "titles": [
            "software engineer", "backend developer", "full stack developer"
        ],
        "experience_years": 5,
        "preferred_locations": ["San Francisco", "Remote", "Austin"],
        "preferred_job_types": ["remote", "hybrid"],
        "target_salary_min": 120000,
        "target_salary_max": 180000,
        "excluded_keywords": ["senior architect", "junior", "entry level"]
    }
    
    config_path = os.path.expanduser("~/job-search-automation/resume_config.json")
    with open(config_path, 'w') as f:
        json.dump(sample, f, indent=2)
    
    print(f"\n✅ Created sample resume config: {config_path}")
    print("   Edit this file with your real information!")
    return config_path


def main():
    parser = argparse.ArgumentParser(
        description='Job Search Automation CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize database
  python cli.py --init
  
  # Parse PDF resume
  python cli.py --parse-resume ~/Documents/my_resume.pdf
  
  # Search for jobs (mock data)
  python cli.py --search "software engineer" --mock
  
  # Full workflow with semantic matching
  python cli.py --search "data scientist" --location "Remote" --match --semantic --display
  
  # Just match existing jobs against resume
  python cli.py --match --display
  
  # Export matches to CSV
  python cli.py --display --export-csv ~/Desktop/job_matches.csv
  
  # Export matches to JSON with detailed scores
  python cli.py --display --detailed --export-json ~/Desktop/job_matches.json
  
  # Application tracking:
  # List all tracked applications (no limit - shows all)
  python src/cli.py --list
  
  # List with limit
  python src/cli.py --list --limit 50
  
  # List only "applied" jobs (no limit - shows all)
  python src/cli.py --list --status applied
  
  # List only "applied" jobs with limit
  python src/cli.py --list --status applied --limit 20
  
  # Update status
  python src/cli.py --update-status 5 --to-status applied --note "Applied via LinkedIn"
  
  # Add note to a job
  python cli.py --add-note 5 --note "Recruiter mentioned 2-week timeline"
  
  # Set follow-up reminder
  python cli.py --follow-up 5 --note "2026-04-15"
  
  # View follow-ups due
  python cli.py --follow-ups-due
  
  # List all applied jobs
  python cli.py --list --status applied
  
  # View full history of job #5
  python src/cli.py --show 5
  
  # Search Profiles (Multi-Role Search):
  # Search all leadership roles (manager, director, vp, cto)
  python src/cli.py --search-profile leadership --match --display
  
  # Search technical leadership roles (principal, staff, architect)
  python src/cli.py --search-profile technical --match --display
  
  # Search hands-on senior roles (senior engineer, python dev)
  python src/cli.py --search-profile hands_on --match --display
  
  # Search everything at once (all profiles combined)
  python src/cli.py --search-profile all --max-results 10 --match --display
  
  # Notion Integration:
  # Sync all matches to Notion (SQLite → Notion)
  python src/cli.py --sync-notion
  
  # Sync only "interested" jobs
  python src/cli.py --sync-notion --notion-status interested
  
  # Pull status changes from Notion (Notion → SQLite)
  python src/cli.py --sync-notion --pull
  
  # Preview pull without making changes
  python src/cli.py --sync-notion --pull --dry-run
  
  # Preview sync without making changes
  python src/cli.py --sync-notion --dry-run
  
  # Generate sample resume config
  python src/cli.py --sample-resume
        """
    )
    
    parser.add_argument('--init', action='store_true',
                        help='Initialize SQLite database')
    parser.add_argument('--search', type=str, metavar='QUERY',
                        help='Search query for jobs')
    parser.add_argument('--location', type=str,
                        help='Job location (e.g., "New York", "Remote")')
    parser.add_argument('--mock', action='store_true',
                        help='Use mock job data for testing')
    parser.add_argument('--max-results', type=int, default=20,
                        help='Maximum jobs to fetch (default: 20)')
    parser.add_argument('--match', action='store_true',
                        help='Match jobs against resume and score')
    parser.add_argument('--semantic', action='store_true',
                        help='Use semantic (embedding) matching (requires OpenAI key)')
    parser.add_argument('--display', action='store_true',
                        help='Display top matching jobs')
    parser.add_argument('--detailed', action='store_true',
                        help='Show detailed match breakdown')
    parser.add_argument('--min-score', type=float, default=0.0,
                        help='Minimum match score to include (0-100, default 0)')
    parser.add_argument('--max-days-old', type=int, default=30,
                        help='Only fetch jobs posted within N days (default 30)')
    parser.add_argument('--sort-by', type=str, default='date',
                        choices=['default', 'hybrid', 'date', 'salary', 'relevance'],
                        help='Adzuna result ordering (default: date, newest first)')
    parser.add_argument('--sample-resume', action='store_true',
                        help='Create example resume config file')
    parser.add_argument('--parse-resume', type=str, metavar='PDF_PATH',
                        help='Parse PDF resume and create config')
    
    # Export options
    parser.add_argument('--export-csv', type=str, metavar='PATH',
                        help='Export matches to CSV file (e.g., jobs.csv)')
    parser.add_argument('--export-json', type=str, metavar='PATH',
                        help='Export matches to JSON file (e.g., jobs.json)')
    
    # Application tracking
    parser.add_argument('--list', action='store_true',
                        help='List all tracked applications')
    parser.add_argument('--limit', type=int, metavar='N',
                        help='Limit number of results (use with --list or --display)')
    parser.add_argument('--status', type=str,
                        help='Filter by status (new/interested/applied/phone_screen/technical_interview/final_interview/offer/rejected/withdrawn/not_interested/auto_rejected)')
    parser.add_argument('--update-status', type=int, metavar='MATCH_ID',
                        help='Update status of a match')
    parser.add_argument('--to-status', type=str,
                        help='New status (use with --update-status)')
    parser.add_argument('--note', type=str,
                        help='Add note (use with --update-status)')
    parser.add_argument('--add-note', type=int, metavar='MATCH_ID',
                        help='Add note to a match')
    parser.add_argument('--follow-up', type=int, metavar='MATCH_ID',
                        help='Set follow-up reminder date (YYYY-MM-DD)')
    parser.add_argument('--follow-ups-due', action='store_true',
                        help='Show applications needing follow-up')
    parser.add_argument('--stats', action='store_true',
                        help='Show application pipeline statistics')
    parser.add_argument('--pipeline', action='store_true',
                        help='Show kanban-style pipeline view')
    parser.add_argument('--show', type=int, metavar='MATCH_ID',
                        help='Show full history of a specific job')
    
    # Search profiles
    parser.add_argument('--search-profile', type=str, metavar='PROFILE',
                        help='Multi-search profile: leadership, technical, hands_on, all')
    
    # Notion integration
    parser.add_argument('--sync-notion', action='store_true',
                        help='Sync matches to Notion database')
    parser.add_argument('--notion-status', type=str,
                        help='Only sync matches with this status (use with --sync-notion)')
    parser.add_argument('--pull', action='store_true',
                        help='Pull status changes from Notion back to SQLite (use with --sync-notion)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without applying them (use with --sync-notion or --pull)')
    
    args = parser.parse_args()
    
    # Handle --init
    if args.init:
        print("🗄️  Initializing database...")
        init_database()
        return
    
    # Handle --sample-resume
    if args.sample_resume:
        create_sample_resume()
        return
    
    # Handle --parse-resume
    if args.parse_resume:
        pdf_path = os.path.expanduser(args.parse_resume)
        if not os.path.exists(pdf_path):
            print(f"❌ File not found: {pdf_path}")
            return
        
        output_path = os.path.expanduser("~/job-search-automation/resume_config.json")
        create_resume_config_from_pdf(pdf_path, output_path)
        print(f"\n⚠️  Please edit {output_path} to add:")
        print("   - required_skills (your must-haves)")
        print("   - excluded_keywords (deal-breakers)")
        print("   - target_salary_min/max")
        print("   - preferred_locations")
        return
    
    # Ensure database exists and schema is migrated
    ensure_schema()
    
    # Handle --search
    if args.search:
        search_and_save_jobs(
            query=args.search,
            location=args.location,
            use_mock=args.mock,
            max_results=args.max_results,
            max_days_old=args.max_days_old,
            sort_by=args.sort_by
        )
    
    # Handle --search-profile
    if args.search_profile:
        # Define search profiles
        SEARCH_PROFILES = {
            "leadership": [
                "engineering manager",
                "director of engineering",
                "director engineering",
                "vp engineering",
                "vice president engineering",
                "head of engineering",
                "cto",
                "chief technology officer",
                "engineering director"
            ],
            "technical": [
                "principal engineer",
                "staff engineer",
                "senior architect",
                "solutions architect",
                "enterprise architect",
                "lead architect"
            ],
            "hands_on": [
                "senior software engineer",
                "senior developer",
                "python developer",
                "python engineer",
                "full stack engineer",
                "software architect"
            ],
            "consulting": [
                "technology consultant",
                "engineering consultant",
                "fractional cto",
                "technical consultant"
            ],
            "ai": [
                "ai engineer",
                "machine learning engineer",
                "ai architect",
                "mlops engineer",
                "ai product manager",
                "ai team lead",
                "generative ai engineer",
                "ai automation engineer",
                "llm engineer",
                "ai engineering manager",
                "prompt engineer",
                "ai solutions architect",
                "applied ai engineer"
            ],
            "all": []  # Will be populated from all above
        }
        # Build 'all' profile
        SEARCH_PROFILES["all"] = (
            SEARCH_PROFILES["leadership"] +
            SEARCH_PROFILES["technical"] +
            SEARCH_PROFILES["hands_on"] +
            SEARCH_PROFILES["consulting"] +
            SEARCH_PROFILES["ai"]
        )
        
        profile = args.search_profile.lower()
        if profile not in SEARCH_PROFILES:
            print(f"❌ Unknown search profile: {profile}")
            print(f"   Available profiles: {', '.join(SEARCH_PROFILES.keys())}")
            return
        
        search_terms = SEARCH_PROFILES[profile]
        print(f"\n{'='*70}")
        print(f"📋 SEARCH PROFILE: {profile.upper()} ({len(search_terms)} searches)")
        print(f"{'='*70}\n")
        
        total_jobs = 0
        for term in search_terms:
            jobs_saved = search_and_save_jobs(
                query=term,
                location=args.location,
                use_mock=args.mock,
                max_results=args.max_results,
                max_days_old=args.max_days_old,
                sort_by=args.sort_by
            )
            total_jobs += jobs_saved
            print()  # Blank line between searches
        
        print(f"{'='*70}")
        print(f"✅ Profile '{profile}' complete: {total_jobs} total jobs saved")
        print(f"{'='*70}")
    
    # Handle --match
    if args.match or args.display:
        # Load resume config
        config_path = os.path.expanduser("~/job-search-automation/resume_config.json")
        
        if not os.path.exists(config_path):
            print(f"\n⚠️  Resume config not found: {config_path}")
            print("   Run with --sample-resume to create one")
            return
        
        import json
        with open(config_path) as f:
            resume_data = json.load(f)
        
        # Match jobs
        matches = []
        if args.match:
            matches = match_jobs_against_resume(
                resume_data=resume_data,
                min_score=args.min_score,
                use_semantic=args.semantic
            )
        
        if args.display:
            # Refresh from database
            # Use --limit if provided, otherwise default to 20
            display_limit = args.limit if args.limit else 20
            matches = get_top_matches(limit=display_limit, min_score=args.min_score)
            display_matches(matches, detailed=args.detailed)
        
        # Handle exports if requested
        if args.export_csv:
            # Get matches if not already loaded
            if not matches:
                matches = get_top_matches(limit=20, min_score=args.min_score)
            export_matches_to_csv(
                matches, 
                args.export_csv, 
                detailed=args.detailed
            )
        
        if args.export_json:
            # Get matches if not already loaded
            if not matches:
                matches = get_top_matches(limit=20, min_score=args.min_score)
            export_matches_to_json(
                matches,
                args.export_json,
                detailed=args.detailed
            )
    
    # Handle application tracking commands
    tracker = ApplicationTracker()
    
    if args.update_status and args.to_status:
        tracker.update_status(args.update_status, args.to_status, args.note)
    
    if args.add_note:
        if args.note:
            tracker.add_note(args.add_note, args.note)
        else:
            print("❌ Use --note 'your note' with --add-note")
    
    if args.follow_up:
        if args.note:  # Reusing --note for date
            tracker.set_follow_up(args.follow_up, args.note)
        else:
            print("❌ Use --note 'YYYY-MM-DD' with --follow-up")
    
    if args.follow_ups_due:
        follow_ups = tracker.get_follow_ups_due(days=7)
        if follow_ups:
            print(f"\n🔔 Follow-ups due in next 7 days ({len(follow_ups)} jobs):")
            print("-" * 70)
            for job in follow_ups:
                print(f"[{job['match_id']}] {job['title']} @ {job['company']}")
                print(f"    Status: {job['status']} | Follow-up by: {job['follow_up_date']}")
                if job['notes']:
                    print(f"    Notes: {job['notes']}")
                print()
        else:
            print("\n✅ No follow-ups due in next 7 days")
    
    if args.stats:
        stats = tracker.get_stats()
        print(f"\n{'='*70}")
        print("📊 APPLICATION PIPELINE STATISTICS")
        print(f"{'='*70}\n")
        
        print(f"Total Jobs Tracked: {stats['total_matches']}")
        print(f"Average Match Score (applied): {stats['avg_match_score']:.1f}%")
        print(f"Response Rate: {stats['response_rate']:.1f}%")
        if stats['follow_ups_due'] > 0:
            print(f"⚠️  Follow-ups Due: {stats['follow_ups_due']}")
        print()
        
        print("Pipeline Breakdown:")
        status_order = ['new', 'interested', 'applied', 'phone_screen', 
                       'technical_interview', 'final_interview', 'offer', 
                       'rejected', 'withdrawn']
        for status in status_order:
            count = stats.get(status, 0)
            if count > 0:
                emoji = tracker.DISPLAY_STATUSES.get(status, status).split()[0]
                label = tracker.DISPLAY_STATUSES.get(status, status).split(maxsplit=1)[1]
                print(f"  {emoji} {label}: {count}")
    
    if args.pipeline:
        pipeline = tracker.get_pipeline_view()
        print(f"\n{'='*80}")
        print("📋 APPLICATION PIPELINE")
        print(f"{'='*80}\n")
        
        stages = [
            ('new', '🆕 NEW'),
            ('interested', '⭐ INTERESTED'),
            ('applied', '📤 APPLIED'),
            ('interviewing', '💬 INTERVIEWING'),
            ('offer', '🎉 OFFER'),
            ('rejected', '❌ REJECTED')
        ]
        
        for stage_key, stage_name in stages:
            jobs = pipeline.get(stage_key, [])
            print(f"\n{stage_name} ({len(jobs)} jobs)")
            print("-" * 70)
            if jobs:
                for job in jobs[:5]:
                    salary = format_salary(job.get('salary_min'), job.get('salary_max'))
                    print(f"  [{job['match_id']}] {job['title']}")
                    print(f"      @ {job['company']} | Score: {job['match_score']:.1f}% | {salary}")
                if len(jobs) > 5:
                    print(f"  ... and {len(jobs) - 5} more")
            else:
                print("  (empty)")
    
    if args.list or args.status:
        status_filter = args.status
        # Use --limit if provided, otherwise show all (no limit)
        limit = args.limit if args.limit else None
        jobs = tracker.get_matches_by_status(status_filter, limit=limit)
        
        if status_filter:
            display_name = tracker.DISPLAY_STATUSES.get(status_filter, status_filter)
            print(f"\n{display_name} ({len(jobs)} jobs)")
        else:
            total_count = tracker.get_stats()['total_matches']
            if limit:
                print(f"\nAll Tracked Jobs (showing {len(jobs)} of {total_count})")
            else:
                print(f"\nAll Tracked Jobs ({len(jobs)} jobs)")
        
        print("-" * 70)
        
        if jobs:
            for job in jobs:
                display_status = tracker.DISPLAY_STATUSES.get(job['status'], job['status'])
                print(f"\n[{job['match_id']}] {job['title']}")
                print(f"    @ {job['company']} | {job['location']}")
                print(f"    Score: {job['match_score']:.1f}% | Status: {display_status}")
                print(f"    URL: {job['url']}")
                if job['notes']:
                    # Show first line of notes only
                    note_preview = job['notes'].split('\n')[0][:80]
                    print(f"    📝 {note_preview}...")
        else:
            print("No jobs found.")
    
    if args.show:
        history = tracker.get_job_history(args.show)
        if history:
            print(f"\n{'='*70}")
            print(f"📄 JOB HISTORY: {history['title']}")
            print(f"{'='*70}\n")
            
            print(f"Company: {history['company']}")
            print(f"Location: {history['location']}")
            print(f"Match Score: {history['match_score']:.1f}%")
            print(f"Current Status: {tracker.DISPLAY_STATUSES.get(history['status'], history['status'])}")
            print(f"URL: {history['url']}")
            print()
            
            if history['events']:
                print("Timeline:")
                for event in history['events']:
                    display_status = tracker.DISPLAY_STATUSES.get(event['status'], event['status'])
                    print(f"  {event['date']} - {display_status}")
                    if event['notes']:
                        print(f"             Note: {event['notes']}")
                    if event['follow_up']:
                        print(f"             Follow-up: {event['follow_up']}")
            
            if history['notes']:
                print(f"\nAll Notes:")
                print(history['notes'])
        else:
            print(f"❌ Match #{args.show} not found")
    
    # Handle Notion sync
    if args.sync_notion:
        try:
            notion = NotionSync()
            if notion.test_connection():
                if args.pull:
                    # Pull from Notion to SQLite
                    result = notion.pull_from_notion(dry_run=args.dry_run)
                    if args.dry_run:
                        print(f"\n📋 Dry run complete - {result['updated']} jobs would be updated")
                    else:
                        print(f"\n✅ Pulled {result['updated']} updates from Notion")
                else:
                    # Default: Push from SQLite to Notion
                    if args.dry_run:
                        print("\n📋 Dry run: Would sync top 50 matches to Notion")
                        print("   Run without --dry-run to actually sync")
                    else:
                        synced = notion.sync_matches(status=args.notion_status, limit=50)
                        print(f"\n✅ Synced {synced} jobs to Notion")
        except Exception as e:
            print(f"❌ Notion sync failed: {e}")
            print("\nMake sure you've set:")
            print("  credentials.json: NOTION_TOKEN = op://vault/item/field")
            print("  credentials.json: NOTION_DATABASE_ID = your-database-id")


if __name__ == "__main__":
    main()