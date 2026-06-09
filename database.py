import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

@contextmanager
def get_db():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS repos (
                    id SERIAL PRIMARY KEY,
                    repo_name TEXT UNIQUE NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_review TEXT NOT NULL,
                    total_reviews INTEGER DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id SERIAL PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    pr_number INTEGER NOT NULL,
                    pr_title TEXT NOT NULL,
                    files_reviewed INTEGER DEFAULT 0,
                    issues_found INTEGER DEFAULT 0,
                    reviewed_at TEXT NOT NULL
                )
            """)

def log_review(repo_name, pr_number, pr_title, files_reviewed, issues_found):
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO repos (repo_name, first_seen, last_review, total_reviews)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (repo_name) DO UPDATE SET
                    last_review = EXCLUDED.last_review,
                    total_reviews = repos.total_reviews + 1
            """, (repo_name, now, now))
            cur.execute("""
                INSERT INTO reviews (repo_name, pr_number, pr_title, files_reviewed, issues_found, reviewed_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (repo_name, pr_number, pr_title, files_reviewed, issues_found, now))

def get_stats():
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT repo_name, first_seen, last_review, total_reviews
                FROM repos
                ORDER BY last_review DESC
            """)
            repos = cur.fetchall()

            cur.execute("SELECT COALESCE(SUM(total_reviews), 0) as total FROM repos")
            total_reviews = cur.fetchone()["total"]

            cur.execute("SELECT COALESCE(SUM(issues_found), 0) as total FROM reviews")
            total_issues = cur.fetchone()["total"]

            cur.execute("""
                SELECT repo_name, pr_number, pr_title, files_reviewed, issues_found, reviewed_at
                FROM reviews
                ORDER BY reviewed_at DESC
                LIMIT 10
            """)
            recent_reviews = cur.fetchall()

            return {
                "total_repos": len(repos),
                "total_reviews": int(total_reviews),
                "total_issues_found": int(total_issues),
                "repos": [dict(r) for r in repos],
                "recent_reviews": [dict(r) for r in recent_reviews]
            }

def log_repo_connected(repo_name: str):
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO repos (repo_name, first_seen, last_review, total_reviews)
                VALUES (%s, %s, %s, 0)
                ON CONFLICT (repo_name) DO NOTHING
            """, (repo_name, now, now))