# Job Search Automation - User Guide

**Created:** April 4, 2026  
**Location:** `~/job-search-automation/`  
**Skill:** `skill_view job-search-automation`

---

## What This Tool Does

Automatically searches for jobs, matches them against your resume/skills, and ranks them by relevance so you can focus on applying to the best opportunities.

**The Pipeline:**
```
PDF Resume → Parse Skills → Search Jobs → Match & Score → Review Top 20
                                                      ↓
                                               [Optional: Sync to Notion]
```

**Two Database Options:**
- **SQLite** (Default): Local database, CLI-based tracking, works offline
- **Notion** (Optional): Visual kanban board, cloud sync, mobile access  

*You can use both — SQLite for daily CLI workflow, Notion for visual organization.*

---

## Quick Start (5 Minutes)

### 1. Setup (One-Time)

```bash
cd ~/job-search-automation
source venv/bin/activate

# Initialize SQLite database (required - stores jobs locally)
python src/cli.py --init

# Parse your resume (or use sample)
python src/cli.py --parse-resume ~/Documents/my_resume.pdf

# Edit the generated config
nano resume_config.json  # or use VS Code
```

**Note:** The `--init` command creates a local SQLite database at `data/job_search.db`. This is required for the tool to work. The optional Notion integration (see below) is for visual sync only and doesn't replace SQLite.

**Required edits to `resume_config.json`:**
```json
{
  "required_skills": ["python", "aws"],
  "excluded_keywords": ["junior", "entry-level"],
  "target_salary_min": 120000,
  "target_salary_max": 180000,
  "preferred_locations": ["San Francisco", "Remote", "Austin"]
}
```

### 2. Run Your First Search

```bash
# Test with mock data (no API keys needed)
python src/cli.py --search "software engineer" \
                  --location "Remote" \
                  --mock --match --display

# This will:
# 1. Generate 5 test jobs
# 2. Match against your resume
# 3. Show top matches with scores
```

### 3. Get Real Jobs (Optional)

Sign up at https://developer.adzuna.com/ (free, 100 requests/day):

```bash
export ADZUNA_APP_ID="your_app_id"
export ADZUNA_API_KEY="your_api_key"

# Now search real jobs
python src/cli.py --search "data scientist" \
                  --location "New York" \
                  --match --display
```

### 4. Use the CLI (Recommended)

```bash
# Make sure you're in the project directory and venv is activated
cd ~/job-search-automation
source venv/bin/activate

# Use from project directory
python src/cli.py --display
python src/cli.py --search-profile hands_on --match --display
python src/cli.py --sync-notion
```

---

### Full Command Reference

```bash
python src/cli.py [OPTIONS]

Core Commands:
  --init                    Initialize database
  --parse-resume PATH       Parse PDF and create config
  --sample-resume           Create example config
  
Job Search:
  --search "query"          Search for jobs
  --location "City"         Filter by location
  --mock                    Use test data (no API needed)
  --max-results 50          Jobs to fetch (default: 20)
  --search-profile PROFILE  Multi-role search (leadership/technical/hands_on/consulting/all)
  
Matching:
  --match                   Score jobs against resume
  --semantic                Use AI semantic matching (needs OpenAI key)
  --min-score 50            Minimum score to include (0-100)
  
Output:
  --display                 Show all tracked jobs
  --display --limit N       Show with limit
  --display --status STATUS Filter by status
  --detailed                Show score breakdown per job
  
Export:
  --export-csv PATH         Export matches to CSV
  --export-json PATH        Export matches to JSON

Application Tracking:
  --display                 List all tracked applications
  --display --limit N       List with limit
  --display --status STATUS Filter by status
  --pipeline                Show kanban-style pipeline view
  --stats                   Show application statistics
  --update-status ID        Update status of match ID
  --to-status STATUS        New status (use with --update-status)
  --add-note ID             Add note to match ID (use --note "text")
  --follow-up ID            Set follow-up date (use --note "YYYY-MM-DD")
  --follow-ups-due          Show applications needing follow-up
  --show ID                 Show full history and notes for match ID

Notion Sync:
  --sync-notion             Sync matches to Notion
  --notion-status STATUS    Only sync specific status
  --pull                    Pull status from Notion
  --dry-run                 Preview changes without applying
```

### Example Workflows

**Daily Job Check:**
```bash
python src/cli.py --search "senior engineer" --location "Remote" --match --display
```

**Test Different Titles:**
```bash
python src/cli.py --search "full stack developer" --mock --match --display
python src/cli.py --search "backend engineer" --mock --match --display
```

**With Semantic Ranking:**
```bash
export OPENAI_API_KEY="***"
python src/cli.py --search "software engineer" --match --semantic --display
```

**View All Tracked Jobs:**
```bash
# List all jobs (no limit)
python src/cli.py --display

# List with limit
python src/cli.py --display --limit 50

# View all "applied" jobs
python src/cli.py --display --status applied

# View top 20 "new" jobs
python src/cli.py --display --status new --limit 20
```

**Update Job Status:**
```bash
# Mark job #5 as applied
python src/cli.py --update-status 5 --to-status applied --note "Applied via LinkedIn"

# Set follow-up reminder
python src/cli.py --follow-up 5 --note "2026-04-15"
```

---

## Understanding Match Scores

### Keyword Matching (Default)

**Score Components:**
- **40%** Skills match (Python, React, AWS, etc.)
- **25%** Title match (Software Engineer ≈ Full Stack Developer)
- **20%** Location (Remote preferred vs. onsite)
- **15%** Salary alignment

**Gates (Hard Filters):**
- Must have `required_skills`
- Must NOT have `excluded_keywords`
- Salary must be above `target_salary_min`
- Location must be in `preferred_locations`

### Semantic Matching (--semantic)

Uses AI embeddings to understand **meaning**, not just keywords.

**Example:**
```
Your resume: "Built ML pipelines in PyTorch"
Job posting: "Develop deep learning models"

Keyword match: 0% (no shared words)
Semantic match: 85% (AI understands relationship)
```

**When to use:**
- You want to catch jobs where you'd be a good fit even if wording differs
- You're willing to pay for OpenAI API calls (~$0.01 per search)
- You want the best possible ranking quality

### Hybrid Mode (Recommended)

1. **Keyword gates** filter out bad fits (no Python, salary too low)
2. **Semantic ranking** scores quality among passing jobs
3. **Combined score** = 60% keyword + 40% semantic

---

## Database Structure

Your data lives in `data/job_search.db`:

| Table | What's Stored |
|-------|---------------|
| `jobs` | All job postings from searches |
| `resumes` | Your parsed resume data |
| `matches` | Job-resume scores and status |
| `applications` | Jobs you've applied to |
| `blacklist` | Permanently excluded job IDs |

**Key Fields in `matches` table:**
- `match_score` - Overall relevance score (0-100)
- `skill_match_score` - Keyword match component
- `semantic_score` - AI semantic match (if used)
- `status` - Pipeline stage (new, interested, applied, etc.)
- `notes` - Your notes about the job

**View matches directly:**
```bash
sqlite3 data/job_search.db "SELECT title, company, match_score, status FROM jobs JOIN matches ON jobs.id = matches.job_id ORDER BY match_score DESC LIMIT 10;"
```

---

## Web UI (React Dashboard)

The system includes a modern React-based web interface for visual job management.

### Starting the Web UI

```bash
# Terminal 1: Start API server
source venv/bin/activate
python api_server.py

# Terminal 2: Start React dev server
cd web
npm install  # First time only
npm run dev
```

Open http://localhost:5173 in your browser.

### Web UI Features

| Feature | Description |
|---------|-------------|
| **Stats Panel** | Pipeline metrics at a glance |
| **Status Filter** | Filter jobs by pipeline stage |
| **Min Score Slider** | Show only high-match jobs |
| **Search** | Filter by title, company, location |
| **Sort** | Sort by score, date, or company |
| **Status Dropdown** | Update job status inline |
| **Bulk Select** | Select multiple jobs for batch actions |
| **Delete** | Move jobs to blacklist |
| **Dark Mode** | Toggle between light/dark themes |

### API Endpoints

The Web UI connects to the API server at `http://localhost:8000`:

- `GET /api/jobs` - List all jobs (supports `?status=` and `?min_score=`)
- `GET /api/stats` - Get pipeline statistics
- `PUT /api/jobs/{id}/status` - Update job status
- `DELETE /api/jobs/{id}` - Blacklist a job

---

## Telegram Integration (Future)

**Status:** Not yet implemented, but here's how it could work:

### Concept: Telegram Topics for Job Categories

Telegram Topics let you organize discussions within a channel:

```
📱 Your Job Search Channel
├── 💼 Software Engineering Jobs (matches 80%+)
├── 🎯 Data Science Jobs (matches 80%+)
├── 🔍 All New Matches (24hr digest)
├── ✅ Applied (jobs you applied to)
├── ⭐ Interested (save for later)
└── ❌ Rejected (not a fit)
```

### How It Would Work

**1. Daily Digest (8:00 AM)**
```
Hermes sends to "🔍 All New Matches" topic:

🌅 Daily Job Digest - April 5
Found 12 new jobs, 4 high-quality matches

Top Picks:
1. Senior Software Engineer @ Stripe (94%)
   💰 $180-220K | Remote | Python, AWS, React
   🔗 https://stripe.com/jobs/...

2. Staff Engineer @ Airbnb (89%)
   💰 $200-250K | Hybrid SF | System Design, Python
   🔗 https://airbnb.com/careers/...

[4 more...]

Reply to mark as interested or applied!
```

**2. Category-Specific Auto-Posting**
```
Hermes detects "Machine Learning" in job title → Posts to "🤖 ML Jobs" topic
Hermes detects "Frontend" in description → Posts to "🎨 Frontend Jobs" topic
```

**3. Interactive Commands**
```
You reply "interested" to a job post → Hermes moves it to "⭐ Interested" topic
You reply "applied" → Moved to "✅ Applied", sets follow-up reminder
You reply "reject" → Moved to "❌ Rejected", learns your preferences
```

**4. Slash Commands in Telegram**
```
/search software engineer remote
/status (shows pipeline stats)
/top (shows top 10 matches)
/remind me in 3 days about Stripe application
```

### Implementation Plan

**Phase 1: Basic Notifications**
- Run job search daily via cron
- Send top 5 matches to your Telegram channel

**Phase 2: Topics Organization**
- Create different topics for job types
- Auto-categorize based on keywords in title/description

**Phase 3: Interactive**
- Reply handling (interested/applied/reject)
- Status tracking
- Follow-up reminders

### Setup Required (When Built)

```bash
# Set your Telegram channel
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHANNEL_ID="..."

# Add to Hermes config
echo "telegram_channel: your_channel_id" >> ~/.hermes/config.yaml

# Schedule daily search
cronjob create --schedule "0 8 * * *" \
               --prompt "Run job search automation and send top matches to Telegram"
```

---

## Other Output Ideas

### Notion Database
```
Create Notion database with columns:
- Company | Role | Score | Status | URL | Notes

Hermes syncs matches every morning
You move cards: New → Applied → Interview → Offer
```

### Email Digest
```
Daily 8 AM email with:
- Subject: "12 New Jobs Found - 4 High Matches"
- Table: Company | Role | Score | Link
- One-click "Apply" buttons
```

### Airtable
```
Similar to Notion but better for:
- Application tracking
- Follow-up dates
- Contact management
```

### RSS Feed
```
Generate RSS feed of your top matches
Subscribe in Feedly/Raindrop for passive tracking
```

---

## Tips for Best Results

### 1. Rich Job Descriptions Matter

**Bad (low match %):**
```
"Looking for a developer. Must know programming."
```

**Good (high match %):**
```
"Senior Python developer with 5+ years experience in AWS, 
Docker, Kubernetes. React frontend experience preferred. 
PostgreSQL database expertise required."
```

Adzuna API usually has full descriptions. Mock data is simplified.

### 2. Tune Your Filters

Start broad, then narrow:

```json
// Week 1: Broad
"required_skills": [],
"min_score": 20

// Week 2: Focus
"required_skills": ["python", "senior"],
"min_score": 60

// Week 3: Specific
"required_skills": ["python", "aws", "senior"],
"excluded_keywords": ["junior", "contract"],
"min_score": 70
```

### 3. Use Semantic Matching Sparingly

- **Daily searches:** Use keyword only (faster, free)
- **Weekly deep dive:** Use semantic for top 50 keyword matches
- **Quality checks:** Use semantic when you're not finding good fits

### 4. Track Your Applications

```bash
# Mark a match as applied
sqlite3 data/job_search.db "UPDATE matches SET status='applied' WHERE id=5;"

# See all applied jobs
sqlite3 data/job_search.db "SELECT j.title, j.company FROM jobs j JOIN matches m ON j.id=m.job_id WHERE m.status='applied';"
```

---

## Troubleshooting

**"No jobs found"**
```bash
# Check API keys
echo $ADZUNA_APP_ID
echo $ADZUNA_API_KEY

# Use mock data instead
python src/cli.py --search "..." --mock
```

**"No matches passing"**
- Check `resume_config.json` syntax with: `python -m json.tool resume_config.json`
- Lower `--min-score` threshold
- Reduce `required_skills` list

**"Database is locked"**
- Stop any other processes using the database
- SQLite only allows one writer at a time

**"Import errors"**
```bash
cd ~/job-search-automation
source venv/bin/activate
pip install requests pdfplumber numpy
```

---

## Advanced: Customizing the Code

### Change Scoring Weights

Edit `src/matcher.py`, line ~45:
```python
# Current weights
overall_score = (
    skill_score * 0.40 +
    title_score * 0.25 +
    location_score * 0.20 +
    salary_score * 0.15
)

# Example: Prioritize salary
overall_score = (
    skill_score * 0.30 +
    title_score * 0.20 +
    location_score * 0.15 +
    salary_score * 0.35  # Now 35%!
)
```

### Add New Job Source

Edit `src/job_searcher.py` to add LinkedIn/Indeed scrapers using Apify.

### Change Output Format

Edit `src/cli.py` `display_matches()` function to export as CSV, Markdown, etc.

---

## Exporting Your Matches

### CSV Export

```bash
# Simple export (basic info)
python src/cli.py --display --export-csv ~/Desktop/jobs.csv

# Detailed export (with score breakdown)
python src/cli.py --display --detailed --export-csv ~/Desktop/jobs_detailed.csv
```

**CSV includes:**
- Rank, Title, Company, Location
- Match score (e.g., "84.5%")
- Individual scores: skills, title, location, salary
- Job URL
- Status (new/applied/rejected)
- Notes (gate failure reasons)
- Matched date

**Open in:** Excel, Google Sheets, Numbers, Airtable

### JSON Export

```bash
# Standard export
python src/cli.py --display --export-json ~/Desktop/jobs.json

# With detailed scores
python src/cli.py --display --detailed --export-json ~/Desktop/jobs_full.json
```

**JSON structure:**
```json
{
  "exported_at": "2026-04-05T16:32:14",
  "total_matches": 12,
  "matches": [
    {
      "rank": 1,
      "title": "Senior Software Engineer",
      "company": "Stripe",
      "location": "Remote",
      "match_score": 94.2,
      "url": "https://stripe.com/jobs/...",
      "status": "new",
      "detailed_scores": {
        "skill": 95.0,
        "title": 90.0,
        "location": 100.0,
        "salary": 92.0
      },
      "notes": null,
      "matched_date": "2026-04-05 08:15:00"
    }
  ]
}
```

**Use JSON for:**
- Importing to other tools
- Building custom dashboards
- Feeding to notification bots (Telegram, Slack)
- Archiving search results

### Example: Email Yourself Daily Matches

```bash
# Create a script
#!/bin/bash
cd ~/job-search-automation
source venv/bin/activate

# Run search and export
python src/cli.py --search "$SEARCH_QUERY" \
                  --location "Remote" \
                  --match \
                  --export-json /tmp/daily_jobs.json

# Email the JSON (requires mail setup)
mail -s "Daily Job Matches" your@email.com < /tmp/daily_jobs.json
```

### Example: Import to Notion

```python
# Use the JSON export with Notion API
import json
import requests

with open('jobs.json') as f:
    data = json.load(f)

for job in data['matches'][:5]:  # Top 5
    # Create Notion page
    requests.post(
        "https://api.notion.com/v1/pages",
        headers={"Authorization": f"Bearer {NOTION_TOKEN}"},
        json={
            "parent": {"database_id": "..."},
            "properties": {
                "Company": {"title": [{"text": {"content": job['company']}}]},
                "Role": {"rich_text": [{"text": {"content": job['title']}}]},
                "Score": {"number": job['match_score']},
                "URL": {"url": job['url']},
                "Status": {"select": {"name": "New"}}
            }
        }
    )
```

---

## Application Tracking

Once you've matched jobs, you'll want to track them through your application pipeline.

### View Your Pipeline

```bash
# See kanban-style view of all stages
python src/cli.py --pipeline
```

Output:
```
================================================================================
📋 APPLICATION PIPELINE
================================================================================

🆕 NEW (3 jobs)
----------------------------------------------------------------------
  [1] Senior Software Engineer @ TechCorp Inc | Score: 61.4%
  [2] Full Stack Developer @ StartupXYZ | Score: 61.4%
  ...

⭐ INTERESTED (1 job)
----------------------------------------------------------------------
  [3] ML Engineer @ OpenAI | Score: 89.2%

📤 APPLIED (2 jobs)
----------------------------------------------------------------------
  [4] Backend Dev @ Stripe | Score: 94.1% | $180K - $220K
  [5] Staff Engineer @ Airbnb | Score: 87.3% | $200K - $250K

💬 INTERVIEWING (1 job)
----------------------------------------------------------------------
  [6] Senior Dev @ Coinbase | Score: 82.5% | Status: phone_screen

🎉 OFFER (0 jobs)
----------------------------------------------------------------------
  (empty)

❌ REJECTED (1 job)
----------------------------------------------------------------------
  [7] DevOps @ CloudFirst | Score: 76.2%
```

### Update Job Status

```bash
# Mark as interested (save for later)
python src/cli.py --update-status 1 --to-status interested

# Mark as applied
python src/cli.py --update-status 1 --to-status applied \
                  --note "Applied via LinkedIn, waiting for response"

# Mark rejection
python src/cli.py --update-status 5 --to-status rejected

# Accept offer!
python src/cli.py --update-status 8 --to-status offer
```

**All status options:**
- `new` - Just matched, haven't reviewed
- `interested` - Saving for later
- `applied` - Application sent
- `phone_screen` - First interview scheduled
- `technical_interview` - Coding/systems round
- `final_interview` - Last round
- `offer` - 🎉 Got the offer!
- `rejected` - Company said no
- `withdrawn` - You pulled out

### Add Notes

```bash
# Add note to a job
python src/cli.py --add-note 5 --note "Recruiter mentioned they're Series C, 200 employees"

# View all notes and history
python src/cli.py --show 5
```

Output:
```
📄 JOB HISTORY: Senior Software Engineer @ Stripe

Company: Stripe
Location: Remote
Match Score: 94.2%
Current Status: 🎯 Final Round
URL: https://stripe.com/jobs/...

Timeline:
  2026-04-05 08:15 - 🆕 New
  2026-04-05 09:30 - ⭐ Interested
  2026-04-05 14:00 - 📤 Applied
             Note: Applied via referral from Sarah
  2026-04-07 10:00 - 📞 Phone Screen
  2026-04-10 11:00 - 💻 Technical
  2026-04-15 14:00 - 🎯 Final Round
             Follow-up: 2026-04-18

All Notes:
[2026-04-05 14:00] Applied via referral from Sarah
[2026-04-07 10:30] Recruiter mentioned they're looking for K8s experience
```

### Follow-up Reminders

```bash
# Set follow-up date
python src/cli.py --follow-up 5 --note "2026-04-18"

# See all follow-ups due
python src/cli.py --follow-ups-due
```

Output:
```
🔔 Follow-ups due in next 7 days (2 jobs):

[5] Senior Software Engineer @ Stripe
    Status: phone_screen | Follow-up by: 2026-04-15
    Notes: Check back if haven't heard

[8] Backend Dev @ Coinbase
    Status: applied | Follow-up by: 2026-04-12
```

### View Statistics

```bash
python src/cli.py --stats
```

Output:
```
📊 APPLICATION PIPELINE STATISTICS

Total Jobs Tracked: 28
Average Match Score (applied): 84.3%
Response Rate: 45.0%
⚠️  Follow-ups Due: 2

Pipeline Breakdown:
  🆕 New: 12
  ⭐ Interested: 3
  📤 Applied: 8
  📞 Phone Screen: 2
  💻 Technical: 1
  🎯 Final: 1
  🎉 Offer: 1
  ❌ Rejected: 2
```

### List Jobs by Status

```bash
# All jobs
python src/cli.py --list

# Only applied
python src/cli.py --list --status applied

# Everything in interview process
python src/cli.py --list --status phone_screen
python src/cli.py --list --status technical_interview
```

---

## Notion Integration (Optional)

Sync your job matches from SQLite to Notion for a visual kanban board and better organization.

**Why use both?**
- **SQLite**: Fast, works offline, CLI commands, primary data store
- **Notion**: Pretty UI, drag-and-drop kanban, mobile app, easy sharing

*Notion is a one-way sync from SQLite → Notion. Keep using the CLI for daily workflow, sync to Notion when you want a visual view.*

### Setup

1. **Create Notion Integration:**
   - Go to https://www.notion.so/my-integrations
   - Click "New integration"
   - Name: `Job Search Automation`
   - Copy the token (starts with `secret_`)

2. **Create Database:**
   - Create a new page called "Jobs"
   - Add an inline database called "Job Search"
   - Add these properties:
     - **Name** (Title)
     - **Company** (Text)
     - **Location** (Text)
     - **Salary** (Text)
     - **Status** (Select: New, Interested, Applied, Phone Screen, Interview, Offer, Rejected)
     - **Match Score** (Number)
     - **Applied Date** (Date)
     - **URL** (URL)
     - **Notes** (Text)

3. **Connect Integration:**
   - Click "..." on your database
   - "Add connections" → select "Job Search Automation"

4. **Get Database ID:**
   - Copy your database page URL
   - ID is the part after the last `/`: `https://www.notion.so/.../DATABASE_ID?...`

5. **Configure Environment:**
   ```bash
   export NOTION_TOKEN="secret...here"
   export NOTION_DATABASE_ID="your_database_id_here"
   ```
   
   *Add these to your `~/.bashrc` or `~/.zshrc` to make them permanent.*

### Usage

```bash
# Sync all matches to Notion (SQLite → Notion)
python src/cli.py --sync-notion

# Sync only "interested" jobs
python src/cli.py --sync-notion --notion-status interested

# Sync only "applied" jobs
python src/cli.py --sync-notion --notion-status applied

# Pull status changes from Notion (Notion → SQLite)
python src/cli.py --sync-notion --pull

# Preview pull without making changes
python src/cli.py --sync-notion --pull --dry-run

# Preview sync without making changes
python src/cli.py --sync-notion --dry-run
```

### Two-Way Sync Strategy

**SQLite is the source of truth** for job data and pipeline status. Use this workflow:

1. **Update status in CLI** (primary): `python src/cli.py --update-status 5 --to-status applied`
2. **Push to Notion** (visual view): `python src/cli.py --sync-notion`
3. **Optionally pull back** if you moved cards in Notion: `python src/cli.py --sync-notion --pull`

**Key principle:** CLI controls status, Notion provides visualization.

### What Gets Synced

- Job title, company, location
- Salary range (if available)
- Current status (maps to your Notion status options)
- Match score (0-100)
- Job URL (clickable in Notion)
- Application date (if set)
- Notes (truncated to 2000 chars)

### Benefits

- **Visual Kanban:** Drag jobs between stages
- **Calendar View:** See interview dates
- **Filters:** "Show me all remote jobs >$150K"
- **Mobile Access:** Check on your phone
- **Share:** Let career coaches view your progress

---

## Next Features to Build

**Priority 1 (Quick wins):** ✅ DONE
- ✅ CSV export of matches
- ✅ JSON export for other tools
- ✅ Application tracking in CLI
- ✅ Multi-profile job search

**Priority 2 (Medium effort):**
- ✅ Notion integration module
- [ ] Email digest sender
- [ ] Telegram bot notifications

**Priority 3 (Harder):**
- [ ] LinkedIn scraping via Apify
- [ ] Cover letter generator using AI
- [ ] Company research (Glassdoor ratings, funding, etc.)

---

## Search Profiles (Multi-Role Job Search)

Instead of searching one job title at a time, use **search profiles** to run multiple searches across different career tracks.

### Available Profiles

| Profile | Searches For | Best For |
|---------|-------------|----------|
| `leadership` | Engineering Manager, Director, VP Eng, CTO | Management track |
| `technical` | Principal Engineer, Staff Engineer, Architect | IC leadership track |
| `hands_on` | Senior Software Engineer, Python Developer | Individual contributor |
| `consulting` | Technology Consultant, Fractional CTO | Consulting/contracting |
| `ai` | AI Engineer, ML Engineer, GenAI, LLM, MLOps | AI/ML focused roles |
| `all` | Everything above combined | Comprehensive search |

### Usage

```bash
# Search all leadership roles
python src/cli.py --search-profile leadership --match --display

# Search technical architecture roles
python src/cli.py --search-profile technical --match --display

# Comprehensive search (all profiles)
python src/cli.py --search-profile all --max-results 10 --match --display

# Combine with location filter
python src/cli.py --search-profile leadership --location "Remote" --match --display
```

### Example: Daily Comprehensive Search

```bash
# Run 'all' profile to catch every relevant opportunity
python src/cli.py --search-profile all \
                  --max-results 10 \
                  --match \
                  --display
```

This runs 30+ searches across all role types, giving you maximum coverage in one command.

### What Gets Searched (Leadership Profile Example)

```
- engineering manager
- director of engineering  
- vp engineering
- head of engineering
- cto
- chief technology officer
- engineering director
```

Each search is independent - you'll get different jobs for "engineering manager" vs "director of engineering" even though they're similar roles.

---

## Summary

**You now have:**
- ✅ **SQLite database** (required) - Local storage for jobs, matches, applications
- ✅ **Notion sync** (optional) - Visual kanban board that mirrors your SQLite data
- ✅ Resume parser (PDF → structured data)
- ✅ Job searcher (Adzuna API + mock data)
- ✅ Keyword matching (hard requirements)
- ✅ Semantic matching (AI-powered ranking)
- ✅ CLI interface to run everything

**Recommended Workflow:**
```bash
# 1. Daily comprehensive search (saves to SQLite)
cd ~/job-search-automation
./jobsearch --search-profile all --max-results 10 --match --display

# 2. Update status as you apply
./jobsearch --update-status 5 --to-status applied --note "Applied via LinkedIn"

# 3. Sync to Notion for visual view (optional)
./jobsearch --sync-notion
```

**For help:**
```bash
python src/cli.py --help
skill_view job-search-automation
```

---

*Last updated: April 4, 2026*  
*Want updates or have questions? Check the Telegram integration section above for future notification options.*