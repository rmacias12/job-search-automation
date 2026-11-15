# Job Search Automation - Quick Reference

## Setup

```bash
cd ~/job-search-automation
source venv/bin/activate

# Initialize SQLite database (required)
python src/cli.py --init

# Create resume config
python src/cli.py --sample-resume  # or --parse-resume your.pdf
```

**Note:** `--init` creates the SQLite database (required). Notion integration is optional (see below).

## Daily Workflow

```bash
cd ~/job-search-automation
source venv/bin/activate

# 1. Run comprehensive multi-profile search (saves to SQLite)
#    Searches: leadership + technical + hands_on + consulting roles
python src/cli.py --search-profile all --max-results 10 --match --display

# 2. Update status of interesting jobs
python src/cli.py --update-status 1 --to-status interested
python src/cli.py --update-status 2 --to-status applied --note "Applied via LinkedIn"

# 3. Check your pipeline
python src/cli.py --pipeline

# 4. Sync to Notion for visual kanban view (optional)
python src/cli.py --sync-notion

# 5. Export for records
python src/cli.py --display --export-csv ~/Desktop/jobs.csv
```

## All Commands

### Search & Match
| Command | Description |
|---------|-------------|
| `--search "query"` | Search for single job title |
| `--search-profile PROFILE` | Multi-role search (leadership/technical/hands_on/consulting/all) |
| `--location "City"` | Filter by location |
| `--mock` | Use test data |
| `--match` | Score against resume |
| `--semantic` | Use AI matching |
| `--display` | Show results |
| `--export-csv path` | Export to CSV |
| `--export-json path` | Export to JSON |

### Application Tracking
| Command | Description |
|---------|-------------|
| `--pipeline` | Kanban view of all stages |
| `--stats` | Pipeline statistics |
| `--display` | List all tracked jobs (no limit) |
| `--display --limit N` | List with limit (e.g., --limit 100) |
| `--display --status STATUS` | Filter by status (shows all) |
| `--display --status STATUS --limit N` | Filter with limit |
| `--update-status ID --to-status STATUS` | Update job status |
| `--add-note ID --note "text"` | Add note to job |
| `--follow-up ID --note "YYYY-MM-DD"` | Set reminder |
| `--follow-ups-due` | Show due follow-ups |
| `--show ID` | Full job history |

### Notion Sync
| Command | Description |
|---------|-------------|
| `--sync-notion` | Sync matches to Notion (SQLite → Notion) |
| `--notion-status STATUS` | Only sync specific status |
| `--pull` | Pull status from Notion (Notion → SQLite) |
| `--dry-run` | Preview changes without applying |
| `--sync-notion --notion-status interested` | Sync only interested jobs |

### Status Values
- `new` - Just matched
- `interested` - Save for later
- `applied` - Application sent
- `phone_screen` - First interview
- `technical_interview` - Coding round
- `final_interview` - Last round
- `offer` - Got offer!
- `rejected` - Company said no
- `withdrawn` - You withdrew

## Examples

```bash
# Update job #5 to applied with note
python src/cli.py --update-status 5 --to-status applied --note "Applied via referral"

# Set follow-up for job #5
python src/cli.py --follow-up 5 --note "2026-04-15"

# See all applied jobs
python src/cli.py --display --status applied

# See stats
python src/cli.py --stats

# View full history of job #5
python src/cli.py --show 5
```

## Files & Data Storage
| Location | Purpose |
|----------|---------|
| `~/job-search-automation/` | Project root |
| `~/job-search-automation/resume_config.json` | Your skills & preferences |
| `~/job-search-automation/data/job_search.db` | **SQLite database** (required) - stores all job data |
| Notion (optional) | Visual kanban board - synced from SQLite |
| `~/job-search-automation/JOB_SEARCH_AUTOMATION_GUIDE.md` | Full documentation |

## Environment Variables

**Required for basic use:**
```bash
# None - SQLite works out of the box!
```

**Optional - For real job data:**
```bash
export ADZUNA_APP_ID="..."
export ADZUNA_API_KEY="***"
```

**Optional - For AI features:**
```bash
export OPENAI_API_KEY="***"     # Semantic matching & PDF parsing
```

**Optional - For Notion sync:**
```bash
export NOTION_TOKEN="***"
export NOTION_DATABASE_ID="your-db-id"
```

## Tips & Troubleshooting

**Notion sync creates duplicates?**
- The sync now automatically updates existing entries instead of creating duplicates
- Same (title, company) jobs are deduplicated (different locations collapsed to one entry)
- "Applied" jobs are prioritized in sync regardless of match score

**Seeing 0 passed filters?**
- For senior/leadership roles, try empty `required_skills: []` in resume_config.json
- Check `preferred_locations` - leadership roles often require relocation
- Use `--min-score 0` to see all jobs: `./jobsearch --display --min-score 0`

**Want all locations shown separately?**
- CLI `--list` shows all location variations
- Notion sync collapses same (title, company) to one entry for cleaner view