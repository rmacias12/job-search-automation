"""
Application Tracking Module
Manages job application status, notes, follow-ups, and pipeline views
"""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from database import get_connection


class ApplicationTracker:
    """Track job applications through the pipeline."""
    
    VALID_STATUSES = ['new', 'interested', 'applied', 'phone_screen', 
                      'technical_interview', 'final_interview', 'offer', 'rejected',
                      'withdrawn', 'not_interested']
    
    DISPLAY_STATUSES = {
        'new': '🆕 New',
        'interested': '⭐ Interested',
        'applied': '📤 Applied',
        'phone_screen': '📞 Phone Screen',
        'technical_interview': '💻 Technical',
        'final_interview': '🎯 Final Round',
        'offer': '🎉 Offer',
        'rejected': '❌ Rejected',
        'withdrawn': '🚫 Withdrawn',
        'not_interested': '👎 Not Interested',
        'auto_rejected': '⚙️ Auto-Rejected'
    }
    
    def __init__(self):
        self.conn = get_connection()
    
    def __del__(self):
        if hasattr(self, 'conn'):
            self.conn.close()
    
    def update_status(self, match_id: int, status: str, notes: str = None) -> bool:
        """
        Update the status of a job match.
        
        Args:
            match_id: The match ID from the database
            status: One of VALID_STATUSES
            notes: Optional notes about the status change
            
        Returns:
            True if successful, False otherwise
        """
        if status not in self.VALID_STATUSES:
            print(f"❌ Invalid status: {status}")
            print(f"   Valid options: {', '.join(self.VALID_STATUSES)}")
            return False
        
        cursor = self.conn.cursor()
        
        # Update match status
        if notes:
            cursor.execute("""
                UPDATE matches 
                SET status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, notes, match_id))
        else:
            cursor.execute("""
                UPDATE matches 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, match_id))
        
        # Also log to applications table if this is an application status
        if status in ['applied', 'phone_screen', 'technical_interview', 'final_interview', 'offer', 'rejected']:
            self._log_application_event(match_id, status, notes)
        
        self.conn.commit()
        
        if cursor.rowcount > 0:
            display_name = self.DISPLAY_STATUSES.get(status, status)
            print(f"✅ Updated match #{match_id} to {display_name}")
            return True
        else:
            print(f"❌ Match #{match_id} not found")
            return False
    
    def _log_application_event(self, match_id: int, status: str, notes: str = None):
        """Log application event to applications table."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO applications (match_id, response_status, notes)
            VALUES (?, ?, ?)
        """, (match_id, status, notes))
        
        self.conn.commit()
    
    def add_note(self, match_id: int, note: str) -> bool:
        """Add a note to an existing match."""
        cursor = self.conn.cursor()
        
        # Get existing notes
        cursor.execute("SELECT notes FROM matches WHERE id = ?", (match_id,))
        row = cursor.fetchone()
        
        if not row:
            print(f"❌ Match #{match_id} not found")
            return False
        
        existing_notes = row[0] or ""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_note = f"[{timestamp}] {note}"
        
        if existing_notes:
            updated_notes = f"{existing_notes}\n{new_note}"
        else:
            updated_notes = new_note
        
        cursor.execute("""
            UPDATE matches 
            SET notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (updated_notes, match_id))
        
        self.conn.commit()
        print(f"✅ Added note to match #{match_id}")
        return True
    
    def set_follow_up(self, match_id: int, follow_up_date: str) -> bool:
        """
        Set a follow-up reminder date.
        
        Args:
            match_id: The match ID
            follow_up_date: Date string in YYYY-MM-DD format
        """
        try:
            # Validate date format
            datetime.strptime(follow_up_date, "%Y-%m-%d")
        except ValueError:
            print(f"❌ Invalid date format. Use YYYY-MM-DD (e.g., 2026-04-15)")
            return False
        
        cursor = self.conn.cursor()
        
        # Check if application record exists, create if not
        cursor.execute("SELECT id FROM applications WHERE match_id = ?", (match_id,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO applications (match_id, response_status)
                VALUES (?, 'applied')
            """, (match_id,))
        
        # Update follow-up date
        cursor.execute("""
            UPDATE applications 
            SET follow_up_date = ?
            WHERE match_id = ?
        """, (follow_up_date, match_id))
        
        self.conn.commit()
        print(f"✅ Set follow-up for match #{match_id} on {follow_up_date}")
        return True
    
    def get_matches_by_status(self, status: str = None, limit: int = None) -> List[Dict]:
        """Get matches filtered by status.
        
        Args:
            status: Filter by status (None for all)
            limit: Maximum number of results (None for no limit)
        """
        cursor = self.conn.cursor()
        
        if status:
            if limit:
                cursor.execute("""
                    SELECT 
                        m.id as match_id,
                        j.title,
                        j.company,
                        j.location,
                        j.url,
                        m.match_score,
                        m.status,
                        m.notes,
                        m.updated_at,
                        j.salary_min,
                        j.salary_max
                    FROM matches m
                    JOIN jobs j ON m.job_id = j.id
                    WHERE m.status = ?
                    ORDER BY m.match_score DESC
                    LIMIT ?
                """, (status, limit))
            else:
                cursor.execute("""
                    SELECT 
                        m.id as match_id,
                        j.title,
                        j.company,
                        j.location,
                        j.url,
                        m.match_score,
                        m.status,
                        m.notes,
                        m.updated_at,
                        j.salary_min,
                        j.salary_max
                    FROM matches m
                    JOIN jobs j ON m.job_id = j.id
                    WHERE m.status = ?
                    ORDER BY m.match_score DESC
                """, (status,))
        else:
            if limit:
                cursor.execute("""
                    SELECT 
                        m.id as match_id,
                        j.title,
                        j.company,
                        j.location,
                        j.url,
                        m.match_score,
                        m.status,
                        m.notes,
                        m.updated_at,
                        j.salary_min,
                        j.salary_max
                    FROM matches m
                    JOIN jobs j ON m.job_id = j.id
                    ORDER BY m.updated_at DESC
                    LIMIT ?
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT 
                        m.id as match_id,
                        j.title,
                        j.company,
                        j.location,
                        j.url,
                        m.match_score,
                        m.status,
                        m.notes,
                        m.updated_at,
                        j.salary_min,
                        j.salary_max
                    FROM matches m
                    JOIN jobs j ON m.job_id = j.id
                    ORDER BY m.updated_at DESC
                """)
        
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_follow_ups_due(self, days: int = 7) -> List[Dict]:
        """Get applications needing follow-up within N days."""
        cursor = self.conn.cursor()
        
        future_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        
        cursor.execute("""
            SELECT 
                m.id as match_id,
                j.title,
                j.company,
                j.url,
                m.match_score,
                m.status,
                a.follow_up_date,
                m.notes
            FROM applications a
            JOIN matches m ON a.match_id = m.id
            JOIN jobs j ON m.job_id = j.id
            WHERE a.follow_up_date <= ? 
              AND a.follow_up_date >= ?
              AND m.status IN ('applied', 'phone_screen', 'technical_interview')
            ORDER BY a.follow_up_date ASC
        """, (future_date, today))
        
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_stats(self) -> Dict:
        """Get application pipeline statistics."""
        cursor = self.conn.cursor()
        
        stats = {
            'total_matches': 0,
            'new': 0,
            'interested': 0,
            'applied': 0,
            'phone_screen': 0,
            'technical_interview': 0,
            'final_interview': 0,
            'offer': 0,
            'rejected': 0,
            'withdrawn': 0,
            'not_interested': 0,
            'auto_rejected': 0,
            'response_rate': 0,
            'avg_match_score': 0,
            'follow_ups_due': 0
        }
        
        # Count by status
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM matches
            GROUP BY status
        """)
        for status, count in cursor.fetchall():
            if status in stats:
                stats[status] = count
            stats['total_matches'] += count
        
        # Average match score of applied jobs
        cursor.execute("""
            SELECT AVG(match_score) 
            FROM matches 
            WHERE status IN ('applied', 'phone_screen', 'technical_interview', 
                            'final_interview', 'offer', 'rejected')
        """)
        row = cursor.fetchone()
        stats['avg_match_score'] = round(row[0], 1) if row[0] else 0
        
        # Response rate (heard back / total applied)
        cursor.execute("""
            SELECT COUNT(*) FROM matches 
            WHERE status IN ('rejected', 'phone_screen', 'technical_interview', 
                            'final_interview', 'offer', 'withdrawn')
        """)
        heard_back = cursor.fetchone()[0]
        
        applied = stats['applied'] + stats['phone_screen'] + stats['technical_interview'] + \
                  stats['final_interview'] + stats['offer'] + stats['rejected'] + stats['withdrawn']
        
        if applied > 0:
            stats['response_rate'] = round((heard_back / applied) * 100, 1)
        
        # Follow-ups due
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("""
            SELECT COUNT(*) FROM applications 
            WHERE follow_up_date <= ? AND follow_up_date IS NOT NULL
        """, (today,))
        stats['follow_ups_due'] = cursor.fetchone()[0]
        
        return stats
    
    def get_pipeline_view(self) -> Dict[str, List[Dict]]:
        """Get jobs organized by pipeline stage for kanban view."""
        pipeline = {
            'new': [],
            'interested': [],
            'applied': [],
            'interviewing': [],
            'offer': [],
            'rejected': []
        }
        
        # New matches
        pipeline['new'] = self.get_matches_by_status('new', limit=20)
        
        # Interested
        pipeline['interested'] = self.get_matches_by_status('interested', limit=20)
        
        # Applied (waiting to hear back)
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                m.id as match_id,
                j.title,
                j.company,
                j.location,
                j.url,
                m.match_score,
                m.status,
                m.updated_at
            FROM matches m
            JOIN jobs j ON m.job_id = j.id
            WHERE m.status = 'applied'
            ORDER BY m.updated_at DESC
            LIMIT 20
        """)
        columns = [desc[0] for desc in cursor.description]
        pipeline['applied'] = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        # Interviewing (all interview stages)
        cursor.execute("""
            SELECT 
                m.id as match_id,
                j.title,
                j.company,
                j.location,
                j.url,
                m.match_score,
                m.status,
                m.updated_at
            FROM matches m
            JOIN jobs j ON m.job_id = j.id
            WHERE m.status IN ('phone_screen', 'technical_interview', 'final_interview')
            ORDER BY m.updated_at DESC
            LIMIT 20
        """)
        columns = [desc[0] for desc in cursor.description]
        pipeline['interviewing'] = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        # Offers
        pipeline['offer'] = self.get_matches_by_status('offer', limit=10)
        
        # Rejected
        pipeline['rejected'] = self.get_matches_by_status('rejected', limit=10)
        
        return pipeline
    
    def get_job_history(self, match_id: int) -> Optional[Dict]:
        """Get full timeline of a specific job application."""
        cursor = self.conn.cursor()
        
        # Get match and job details
        cursor.execute("""
            SELECT 
                m.id as match_id,
                j.title,
                j.company,
                j.location,
                j.url,
                j.description,
                m.match_score,
                m.status,
                m.notes,
                m.created_at,
                m.updated_at
            FROM matches m
            JOIN jobs j ON m.job_id = j.id
            WHERE m.id = ?
        """, (match_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        columns = [desc[0] for desc in cursor.description]
        history = dict(zip(columns, row))
        
        # Get application events
        cursor.execute("""
            SELECT 
                response_status,
                applied_date,
                follow_up_date,
                notes
            FROM applications
            WHERE match_id = ?
            ORDER BY applied_date ASC
        """, (match_id,))
        
        history['events'] = [
            {
                'status': row[0],
                'date': row[1],
                'follow_up': row[2],
                'notes': row[3]
            }
            for row in cursor.fetchall()
        ]
        
        return history


def format_salary(salary_min, salary_max, currency='USD'):
    """Format salary range for display."""
    if salary_min and salary_max:
        return f"${salary_min:,} - ${salary_max:,}"
    elif salary_min:
        return f"${salary_min:,}+"
    elif salary_max:
        return f"Up to ${salary_max:,}"
    return "Not specified"


# Example usage
if __name__ == "__main__":
    tracker = ApplicationTracker()
    
    print("Application Tracker Test")
    print("=" * 60)
    
    # Show stats
    stats = tracker.get_stats()
    print("\n📊 Pipeline Stats:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Show pipeline
    print("\n📋 Pipeline View:")
    pipeline = tracker.get_pipeline_view()
    for stage, jobs in pipeline.items():
        print(f"\n  {stage.upper()} ({len(jobs)} jobs):")
        for job in jobs[:3]:
            print(f"    - {job['title']} @ {job['company']}")
    
    # Show follow-ups
    follow_ups = tracker.get_follow_ups_due(days=7)
    if follow_ups:
        print(f"\n🔔 Follow-ups due: {len(follow_ups)}")
    else:
        print("\n✅ No follow-ups due")