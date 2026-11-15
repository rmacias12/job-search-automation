#!/usr/bin/env python3
"""
Simple FastAPI server to serve job search data to the web UI.
Install dependencies: pip install fastapi uvicorn
"""

import sqlite3
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add src to path for database imports
sys.path.insert(0, str(Path(__file__).parent / "src"))
from database import blacklist_job, get_blacklisted_count
from tracking import ApplicationTracker

app = FastAPI(title="Job Search API")

# Enable CORS for the web UI
app.add_middleware(
    CORSMiddleware,
    # Any localhost port (tunnels/remote access); LAN origins stay blocked.
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = Path(__file__).parent / "data" / "job_search.db"


class Job(BaseModel):
    id: int
    match_id: int
    title: str
    company: str
    location: str
    url: str
    match_score: float
    status: str
    notes: Optional[str]
    salary_min: Optional[int]
    salary_max: Optional[int]
    updated_at: str
    posted_date: Optional[str] = None
    remote_status: Optional[str] = None
    salary_is_predicted: Optional[int] = None
    evidence: Optional[str] = None


class Stats(BaseModel):
    total_matches: int
    new: int
    interested: int
    applied: int
    phone_screen: int
    technical_interview: int
    final_interview: int
    offer: int
    rejected: int
    withdrawn: int
    not_interested: int = 0
    auto_rejected: int = 0
    blacklisted: int
    response_rate: float
    avg_match_score: float


class StatusUpdate(BaseModel):
    status: str


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/jobs", response_model=dict)
def get_jobs(status: Optional[str] = None, min_score: Optional[float] = None,
             max_score: Optional[float] = None, q: Optional[str] = None,
             sort: str = "score", limit: int = 60, offset: int = 0):
    """Paginated job list (server-side filter/search/sort).
    Excludes blacklisted and gate-rejected rows by default."""
    conn = get_db()
    cursor = conn.cursor()
    
    select = ("SELECT m.id as match_id, j.id as id, j.title, j.company, j.location, j.url, "
              "m.match_score, m.status, m.notes, m.updated_at, j.salary_min, j.salary_max, "
              "j.posted_date, j.remote_status, j.salary_is_predicted, m.evidence, "
             "j.created_at as pulled_at "
              "FROM matches m JOIN jobs j ON m.job_id = j.id")
    
    params = []
    conditions = []
    
    # status accepts a comma-separated list for multi-select filtering
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else []
    if statuses:
        valid = set(ApplicationTracker.VALID_STATUSES) | {"blacklisted"}
        statuses = [s for s in statuses if s in valid]
    
    # Hide blacklisted, machine gate-rejected, and triaged-out rows unless
    # explicitly requested. 'rejected' (employer declined the user) stays
    # visible by default: it is pipeline history.
    for hidden in ('blacklisted', 'auto_rejected', 'not_interested'):
        if hidden not in statuses:
            conditions.append(f"m.status != '{hidden}'")
    
    if statuses:
        conditions.append("m.status IN (" + ",".join("?" * len(statuses)) + ")")
        params.extend(statuses)
    
    if min_score is not None and min_score > 0:
        conditions.append("m.match_score >= ?")
        params.append(min_score)
    
    if max_score is not None and max_score < 100:
        conditions.append("m.match_score <= ?")
        params.append(max_score)
    
    if q:
        conditions.append("(j.title LIKE ? OR j.company LIKE ? OR j.location LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    
    cursor.execute("SELECT COUNT(*) FROM matches m JOIN jobs j ON m.job_id = j.id" + where, params)
    total = cursor.fetchone()[0]
    
    # sort accepts a comma-separated key list (primary, then tiebreaks),
    # e.g. sort=score,pulled. Unknown keys are dropped; m.id keeps pages stable.
    SORT_FIELDS = {"score": "m.match_score DESC",
                   "pulled": "j.created_at DESC",
                   "posted": "j.posted_date DESC",
                   "company": "j.company ASC",
                   "salary": "j.salary_min DESC",
                   "date": "m.updated_at DESC"}  # legacy alias
    keys = [k.strip() for k in sort.split(",") if k.strip() in SORT_FIELDS][:3]
    if not keys:
        keys = ["score"]
    order = ", ".join(SORT_FIELDS[k] for k in keys) + ", m.id DESC"
    
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    
    cursor.execute(select + where + f" ORDER BY {order} LIMIT ? OFFSET ?",
                   params + [limit, offset])
    rows = cursor.fetchall()
    conn.close()
    
    jobs = [dict(row) for row in rows]
    return {"jobs": jobs, "count": len(jobs), "total": total,
            "limit": limit, "offset": offset,
            "has_more": offset + len(jobs) < total}


@app.get("/api/stats", response_model=Stats)
def get_stats():
    """Get pipeline statistics."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM matches")
    total = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) as new_count,
            SUM(CASE WHEN status = 'interested' THEN 1 ELSE 0 END) as interested_count,
            SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) as applied_count,
            SUM(CASE WHEN status = 'phone_screen' THEN 1 ELSE 0 END) as phone_count,
            SUM(CASE WHEN status = 'technical_interview' THEN 1 ELSE 0 END) as tech_count,
            SUM(CASE WHEN status = 'final_interview' THEN 1 ELSE 0 END) as final_count,
            SUM(CASE WHEN status = 'offer' THEN 1 ELSE 0 END) as offer_count,
            SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected_count,
            SUM(CASE WHEN status = 'withdrawn' THEN 1 ELSE 0 END) as withdrawn_count,
            SUM(CASE WHEN status = 'not_interested' THEN 1 ELSE 0 END) as not_interested_count,
            SUM(CASE WHEN status = 'auto_rejected' THEN 1 ELSE 0 END) as auto_rejected_count,
            AVG(match_score) as avg_score
        FROM matches
    """)
    row = cursor.fetchone()
    conn.close()
    
    n = lambda key: row[key] or 0  # get_db() sets row_factory = sqlite3.Row
    
    # Calculate response rate: heard back / everything actually applied to.
    # 'applied' alone is NOT a response; machine auto-rejects and
    # not-interested triage are not part of the application pipeline.
    heard_back = (n('phone_count') + n('tech_count') + n('final_count')
                  + n('offer_count') + n('rejected_count') + n('withdrawn_count'))
    applied_total = n('applied_count') + heard_back
    response_rate = (heard_back / applied_total * 100) if applied_total > 0 else 0
    
    # Get blacklisted count
    blacklisted = get_blacklisted_count()
    
    return Stats(
        total_matches=total,
        new=n('new_count'),
        interested=n('interested_count'),
        applied=n('applied_count'),
        phone_screen=n('phone_count'),
        technical_interview=n('tech_count'),
        final_interview=n('final_count'),
        offer=n('offer_count'),
        rejected=n('rejected_count'),
        withdrawn=n('withdrawn_count'),
        not_interested=n('not_interested_count'),
        auto_rejected=n('auto_rejected_count'),
        blacklisted=blacklisted,
        response_rate=response_rate,
        avg_match_score=round(n('avg_score'), 1)
    )


@app.put("/api/jobs/{match_id}/status")
def update_status(match_id: int, update: StatusUpdate):
    """Update the status of a job."""
    allowed = set(ApplicationTracker.VALID_STATUSES) | {'blacklisted'}
    if update.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {', '.join(sorted(allowed))}")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify the match exists and grab the provider id for Notion mirroring
    cursor.execute(
        "SELECT m.id, j.job_id FROM matches m JOIN jobs j ON m.job_id = j.id WHERE m.id = ?",
        (match_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")
    adzuna_id = row["job_id"]
    
    # Update status
    cursor.execute(
        "UPDATE matches SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (update.status, match_id)
    )
    conn.commit()
    conn.close()
    
    # Mirror to the Notion page (best-effort) so a later --pull can't revert
    # UI triage back to the board's stale status.
    try:
        num = str(adzuna_id or "").split("_", 1)[-1]
        if num.isdigit():
            from notion_sync import NotionSync
            NotionSync().update_page_status(num, update.status)
    except Exception:
        pass
    
    return {"success": True, "match_id": match_id, "status": update.status}


@app.delete("/api/jobs/{match_id}")
def delete_job(match_id: int):
    """Blacklist a job by setting status to 'blacklisted' - keeps in DB for Notion sync."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get job info
    cursor.execute("""
        SELECT m.id, j.id as job_id, j.title, j.company, j.job_id as adzuna_id
        FROM matches m 
        JOIN jobs j ON m.job_id = j.id 
        WHERE m.id = ?
    """, (match_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_info = dict(row)
    adzuna_id = job_info.get('adzuna_id') or str(job_info.get('job_id'))
    
    # Add to blacklist (prevents re-adding on future searches)
    blacklist_job(
        adzuna_id=adzuna_id,
        title=job_info.get('title'),
        company=job_info.get('company'),
        reason="Deleted by user"
    )
    
    # CHANGE: Set status to 'blacklisted' instead of deleting
    # This keeps the job in SQLite for Notion sync purposes
    cursor.execute(
        "UPDATE matches SET status = 'blacklisted', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (match_id,)
    )
    
    conn.commit()
    conn.close()
    
    return {
        "success": True, 
        "match_id": match_id,
        "status": "blacklisted",
        "message": "Job blacklisted. Will be hidden from UI but still synced to Notion."
    }


@app.post("/api/export")
def export_to_json():
    """Export all jobs and stats to a JSON file for static hosting."""
    jobs_data = get_jobs()
    stats_data = get_stats()
    
    export_data = {
        "jobs": jobs_data["jobs"],
        "stats": stats_data.dict(),
        "exported_at": datetime.now().isoformat()
    }
    
    export_path = Path(__file__).parent / "web" / "public" / "jobs.json"
    with open(export_path, "w") as f:
        json.dump(export_data, f, indent=2)
    
    return {"success": True, "path": str(export_path)}


if __name__ == "__main__":
    import uvicorn
    # Bind to localhost by default; set JOB_API_HOST=0.0.0.0 to expose on the LAN.
    host = os.getenv("JOB_API_HOST", "127.0.0.1")
    print("Starting Job Search API server...")
    print(f"API will be available at: http://{host}:8000")
    print("\nEndpoints:")
    print("  GET  /api/jobs           - List all jobs")
    print("  GET  /api/jobs?status=X  - Filter by status")
    print("  GET  /api/stats          - Get statistics")
    print("  PUT  /api/jobs/{id}/status - Update job status")
    print("\nPress Ctrl+C to stop")
    uvicorn.run(app, host=host, port=8000)