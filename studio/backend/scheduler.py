import os
import json
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
try:
    from .database import get_db
except ImportError:
    from database import get_db

scheduler = BackgroundScheduler()

def check_scheduled_queue():
    """
    Periodic job that checks SQLite for posts due for publishing.
    """
    now_iso = datetime.utcnow().isoformat()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, content, media_urls, scheduled_for 
    FROM posts 
    WHERE status = 'scheduled' AND scheduled_for <= ?
    """, (now_iso,))
    
    due_posts = cursor.fetchall()
    for post in due_posts:
        post_id = post["id"]
        print(f"[SCHEDULER] Post due for publishing: {post_id}")
        
        # In local engine, mark published and log execution
        cursor.execute("""
        UPDATE posts 
        SET status = 'published', published_at = ? 
        WHERE id = ?
        """, (now_iso, post_id))
        conn.commit()
        print(f"[SCHEDULER] Post {post_id} marked as published at {now_iso}")

    conn.close()


def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(check_scheduled_queue, "interval", seconds=30, id="queue_checker", replace_existing=True)
        scheduler.start()
        print("[SCHEDULER] Local background scheduler started.")


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        print("[SCHEDULER] Local scheduler stopped.")
