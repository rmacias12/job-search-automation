"""
Notion Integration Module
Syncs job matches to Notion database for visual tracking
"""

import os
from credentials import get_credential, has_credential
import json
import re
import time
from typing import List, Dict, Optional
from datetime import datetime
from database import get_connection


class NotionSync:
    """Sync job data to Notion database."""
    
    def __init__(self, token: str = None, database_id: str = None):
        self.token = get_credential("NOTION_TOKEN", token)
        self.database_id = get_credential("NOTION_DATABASE_ID", database_id)
        
        if not self.token:
            raise ValueError("Notion token required. Configure NOTION_TOKEN in credentials.json or pass to constructor.")
        if not self.database_id:
            raise ValueError("Database ID required. Configure NOTION_DATABASE_ID in credentials.json or pass to constructor.")
    
    def _make_request(self, endpoint: str, method: str = "GET", data: dict = None) -> dict:
        """Make HTTP request to Notion API."""
        import urllib.request
        import urllib.error
        
        url = f"https://api.notion.com/v1{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode() if data else None,
            headers=headers,
            method=method
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            print(f"❌ Notion API Error: {e.code}")
            print(f"   Response: {error_body}")
            raise
    
    def test_connection(self) -> bool:
        """Test if Notion API connection works."""
        try:
            result = self._make_request("/users/me")
            print(f"✅ Connected to Notion as: {result.get('name', 'Unknown')}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to Notion: {e}")
            return False
    
    def get_database_schema(self) -> dict:
        """Get the database schema to verify properties."""
        return self._make_request(f"/databases/{self.database_id}")
    
    def _find_existing_page(self, job_id: str) -> Optional[str]:
        """
        Check if a job already exists in Notion by job_id.
        Returns the Notion page ID if found, None otherwise.
        """
        import re
        try:
            # Query ALL pages with pagination
            all_results = []
            next_cursor = None
            
            while True:
                url = f"/databases/{self.database_id}/query"
                data = {"page_size": 100}
                if next_cursor:
                    data["start_cursor"] = next_cursor
                
                result = self._make_request(url, method="POST", data=data)
                all_results.extend(result.get("results", []))
                
                next_cursor = result.get("next_cursor")
                if not next_cursor:
                    break
            
            for page in all_results:
                page_url = page.get("properties", {}).get("URL", {}).get("url", "")
                # Check if URL contains the job ID (handles both /details/ID and /land/ad/ID)
                if job_id in page_url:
                    return page.get("id")
                # Also extract and compare ID from the URL
                match = re.search(r'/(?:details|land/ad)/(\d+)', page_url)
                if match and match.group(1) == job_id:
                    return page.get("id")
        except Exception as e:
            # If query fails, assume no duplicate (safer to create than miss)
            pass
        return None
    
    def _build_page_index(self) -> Dict[str, str]:
        """Query all database pages once and map Adzuna numeric ids to Notion
        page ids. Avoids a full-database scan per job during bulk syncs."""
        index: Dict[str, str] = {}
        next_cursor = None
        while True:
            data = {"page_size": 100}
            if next_cursor:
                data["start_cursor"] = next_cursor
            result = self._make_request(f"/databases/{self.database_id}/query",
                                        method="POST", data=data)
            for page in result.get("results", []):
                page_url = page.get("properties", {}).get("URL", {}).get("url", "") or ""
                match = re.search(r'/(?:details|land/ad)/(\d+)', page_url)
                if match:
                    index[match.group(1)] = page.get("id")
            next_cursor = result.get("next_cursor")
            if not next_cursor:
                break
        return index

    def ensure_schema_properties(self) -> bool:
        """Idempotently ensure the Notion database has the 'Date Pulled' /
        'Date Posted' date properties and a 'Not Interested' Status select
        option. Returns False when the schema could not be read/updated, so
        sync can proceed without them."""
        try:
            db = self._make_request(f"/databases/{self.database_id}")
            existing = (db or {}).get("properties", {})
            patch_props = {name: {"date": {}} for name in ("Date Pulled", "Date Posted")
                           if name not in existing}
            status_prop = existing.get("Status") or {}
            if status_prop.get("type") == "select":
                options = (status_prop.get("select") or {}).get("options") or []
                if not any(o.get("name") == "Not Interested" for o in options):
                    # Keep existing options by id so they are not deleted/recreated
                    kept = [{"id": o["id"], "name": o["name"], "color": o.get("color")}
                            for o in options if o.get("id")]
                    kept.append({"name": "Not Interested", "color": "gray"})
                    patch_props["Status"] = {"select": {"options": kept}}
            if patch_props:
                self._make_request(f"/databases/{self.database_id}", method="PATCH",
                                   data={"properties": patch_props})
            return True
        except Exception:
            return False

    def update_page_status(self, adzuna_num: str, status: str) -> bool:
        """Best-effort: set the Status select on the job's Notion page (if it
        has one) so web-UI triage is not reverted by the next pull.
        Returns False when the job has no page or Notion is unreachable."""
        try:
            page_id = self._build_page_index().get(str(adzuna_num))
            if not page_id:
                return False
            self._make_request(f"/pages/{page_id}", method="PATCH",
                               data={"archived": False,
                                     "properties": {
                                         "Status": {"select": {"name": self._map_status(status)}}}})
            return True
        except Exception:
            return False

    def sync_job(self, job: Dict, page_index: Optional[Dict[str, str]] = None,
                 include_dates: bool = True) -> str:
        """
        Sync a single job to Notion.
        Updates existing entry if found, creates new one otherwise.
        When page_index is provided (bulk syncs), it is consulted instead of
        re-querying the whole database for every job.
        Returns the Notion page ID.
        """
        # Check for existing entry
        existing_page_id = None
        job_url = job.get("url", "")
        if job_url:
            # Extract job_id from URL for matching
            # Handles both /details/ID and /land/ad/ID formats
            job_id_match = re.search(r'/(?:details|land/ad)/(\d+)', job_url)
            if job_id_match:
                if page_index is not None:
                    existing_page_id = page_index.get(job_id_match.group(1))
                else:
                    existing_page_id = self._find_existing_page(job_id_match.group(1))
        
        # Build properties for Notion
        properties = {
            "Name": {
                "title": [{"text": {"content": job.get("title", "Unknown Job")}}]
            },
            "Company": {
                "rich_text": [{"text": {"content": job.get("company", "Unknown")}}]
            },
            "Location": {
                "rich_text": [{"text": {"content": job.get("location", "Not specified")}}]
            },
            "Salary": {
                "rich_text": [{"text": {"content": self._format_salary(job)}}]
            },
            "Status": {
                "select": {"name": self._map_status(job.get("status", "new"))}
            },
            "Match Score": {
                "number": job.get("match_score", 0)
            },
            "URL": {
                "url": job_url
            }
        }
        
        # Add applied date if available
        if job.get("applied_date"):
            properties["Applied Date"] = {
                "date": {"start": job["applied_date"]}
            }
        
        # Date Pulled = when the job entered SQLite; Date Posted = the ad's own date
        if include_dates:
            pulled = str(job.get("pulled_at") or "")[:10]
            if pulled:
                properties["Date Pulled"] = {"date": {"start": pulled}}
            posted = str(job.get("posted_date") or "")[:10]
            if posted:
                properties["Date Posted"] = {"date": {"start": posted}}
        
        # Add notes if available
        if job.get("notes"):
            properties["Notes"] = {
                "rich_text": [{"text": {"content": job["notes"][:2000]}}]  # Notion limit
            }
        
        if existing_page_id:
            # Update existing entry
            data = {"properties": properties}
            self._make_request(f"/pages/{existing_page_id}", method="PATCH", data=data)
            return existing_page_id
        else:
            # Create new entry
            data = {
                "parent": {"database_id": self.database_id},
                "properties": properties
            }
            result = self._make_request("/pages", method="POST", data=data)
            return result.get("id")
    
    def sync_matches(self, status: str = None, limit: int = 200) -> int:
        """
        Sync job matches from SQLite to Notion.
        Prioritizes: 1) Applied jobs, 2) Interested jobs, 3) New jobs by score
        Returns number of jobs synced.
        Increased default limit to capture more unique jobs after deduplication.
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                m.id as match_id,
                j.title,
                j.company,
                j.location,
                j.url,
                j.salary_min,
                j.salary_max,
                m.match_score,
                m.status,
                m.notes,
                a.applied_date,
                j.posted_date,
                j.created_at as pulled_at
            FROM matches m
            JOIN jobs j ON m.job_id = j.id
            LEFT JOIN applications a ON a.match_id = m.id
            WHERE m.status NOT IN ('blacklisted', 'auto_rejected', 'not_interested')
        """
        
        if status:
            query += " AND m.status = ?"
            cursor.execute(query + " ORDER BY m.match_score DESC LIMIT ?", (status, limit))
        else:
            # Prioritize by status: applied first, then interested, then others by score
            # This ensures applied jobs always sync even with low match scores
            # Note: blacklisted jobs are already excluded in the base query
            full_query = query + """ 
                ORDER BY 
                    CASE m.status 
                        WHEN 'applied' THEN 1 
                        WHEN 'interested' THEN 2 
                        WHEN 'new' THEN 3 
                        ELSE 4 
                    END,
                    m.match_score DESC
                LIMIT ?
            """
            cursor.execute(full_query, (limit,))
        
        columns = [desc[0] for desc in cursor.description]
        matches = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()
        
        if not matches:
            print("No matches found to sync.")
            return 0
        
        # Deduplicate by (title, company) - same job posted in multiple locations
        seen_jobs = set()
        unique_matches = []
        for job in matches:
            key = (job.get('title', ''), job.get('company', ''))
            if key not in seen_jobs:
                seen_jobs.add(key)
                unique_matches.append(job)
        
        print(f"Found {len(matches)} matches, {len(unique_matches)} unique jobs to sync...")
        
        # Build the page index once so bulk syncs don't re-scan Notion per job
        try:
            page_index = self._build_page_index()
            print(f"Indexed {len(page_index)} existing Notion pages")
        except Exception:
            page_index = None
        
        dates_ok = self.ensure_schema_properties()
        if not dates_ok:
            print("⚠️  Date properties unavailable; syncing without Date Pulled/Date Posted")
        
        synced = 0
        for job in unique_matches:
            try:
                page_id = self.sync_job(job, page_index=page_index, include_dates=dates_ok)
                print(f"  ✅ {job['title']} @ {job['company']}")
                synced += 1
            except Exception as e:
                # Sanitized: HTTP error details were already printed by _make_request
                print(f"  ❌ Failed: {job['title']} - {type(e).__name__}")
            time.sleep(0.34)  # stay under Notion's ~3 requests/second limit
        
        print(f"\n✅ Synced {synced}/{len(matches)} jobs to Notion")
        return synced
    
    def pull_from_notion(self, dry_run: bool = False) -> dict:
        """
        Pull status changes from Notion back to SQLite.
        
        Args:
            dry_run: If True, preview changes without applying them
            
        Returns:
            Dict with counts: {'updated': int, 'unchanged': int, 'errors': int}
        """
        from database import update_match_status
        
        print("\n🔄 Pulling status from Notion...")
        if dry_run:
            print("   (DRY RUN - no changes will be made)")
        
        # Query all pages from Notion
        all_pages = []
        next_cursor = None
        
        while True:
            url = f"/databases/{self.database_id}/query"
            data = {"page_size": 100}
            if next_cursor:
                data["start_cursor"] = next_cursor
            
            try:
                result = self._make_request(url, method="POST", data=data)
                all_pages.extend(result.get("results", []))
                next_cursor = result.get("next_cursor")
                if not next_cursor:
                    break
            except Exception as e:
                print(f"❌ Failed to query Notion: {e}")
                return {'updated': 0, 'unchanged': 0, 'errors': 1}
        
        print(f"   Found {len(all_pages)} jobs in Notion")
        
        # Track results
        updated = 0
        unchanged = 0
        errors = 0
        
        # Reverse map Notion status to SQLite status
        reverse_status_map = {
            "New": "new",
            "Interested": "interested",
            "Applied": "applied",
            "Phone Screen": "phone_screen",
            "Interview": "technical_interview",
            "Offer": "offer",
            "Rejected": "rejected",
            "Not Interested": "not_interested"
        }
        
        for page in all_pages:
            try:
                props = page.get("properties", {})
                
                # Get job URL to identify it
                job_url = props.get("URL", {}).get("url", "")
                if not job_url:
                    continue
                
                # Get current status from Notion
                notion_status_obj = props.get("Status", {}).get("select", {})
                notion_status = notion_status_obj.get("name", "New") if notion_status_obj else "New"
                sqlite_status = reverse_status_map.get(notion_status, "new")
                
                # Find matching job in SQLite by URL
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT m.id, m.status FROM matches m JOIN jobs j ON m.job_id = j.id WHERE j.url = ?",
                    (job_url,)
                )
                result = cursor.fetchone()
                conn.close()
                
                if not result:
                    continue  # Job not found in SQLite
                
                match_id, current_status = result
                
                # Compare status
                if current_status != sqlite_status:
                    print(f"  {'Would update' if dry_run else 'Updating'}: {props.get('Name', {}).get('title', [{}])[0].get('text', {}).get('content', 'Unknown')}")
                    print(f"    Status: {current_status} → {sqlite_status}")
                    
                    if not dry_run:
                        if update_match_status(match_id, sqlite_status):
                            updated += 1
                        else:
                            errors += 1
                    else:
                        updated += 1  # Count as would-be updated
                else:
                    unchanged += 1
                    
            except Exception as e:
                print(f"  ❌ Error processing page: {e}")
                errors += 1
        
        print(f"\n{'Would update' if dry_run else 'Updated'}: {updated}")
        print(f"Unchanged: {unchanged}")
        if errors:
            print(f"Errors: {errors}")
        
        return {'updated': updated, 'unchanged': unchanged, 'errors': errors}
    
    def _format_salary(self, job: Dict) -> str:
        """Format salary for display."""
        min_sal = job.get("salary_min")
        max_sal = job.get("salary_max")
        
        if min_sal and max_sal:
            return f"${min_sal:,} - ${max_sal:,}"
        elif min_sal:
            return f"${min_sal:,}+"
        elif max_sal:
            return f"Up to ${max_sal:,}"
        return "Not specified"
    
    def _map_status(self, status: str) -> str:
        """Map internal status to Notion status options."""
        status_map = {
            "new": "New",
            "interested": "Interested",
            "applied": "Applied",
            "phone_screen": "Phone Screen",
            "technical_interview": "Interview",
            "final_interview": "Interview",
            "offer": "Offer",
            "rejected": "Rejected",
            "withdrawn": "Rejected",
            "not_interested": "Not Interested",
            "auto_rejected": "Auto-Rejected",
            "blacklisted": "Blacklisted"
        }
        return status_map.get(status, "New")


# CLI integration
def main():
    """CLI entry point for Notion sync."""
    import sys
    
    token = get_credential("NOTION_TOKEN")
    db_id = get_credential("NOTION_DATABASE_ID")
    
    if not token or not db_id:
        print("❌ Configure NOTION_TOKEN and NOTION_DATABASE_ID in credentials.json")
        print("   Use op://vault/item/field references for secrets.")
        print("   NOTION_DATABASE_ID may also be a plain database ID.")
        sys.exit(1)
    
    sync = NotionSync(token, db_id)
    
    # Test connection first
    if not sync.test_connection():
        sys.exit(1)
    
    # Sync matches
    status_filter = sys.argv[1] if len(sys.argv) > 1 else None
    sync.sync_matches(status=status_filter)


if __name__ == "__main__":
    main()