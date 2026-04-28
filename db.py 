import json
import sqlite3
from datetime import datetime
from config import DB_PATH

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_user_id TEXT UNIQUE NOT NULL,
                username TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_user_id TEXT NOT NULL,
                subject TEXT NOT NULL,
                score INTEGER NOT NULL,
                total INTEGER NOT NULL,
                language TEXT NOT NULL,
                date TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS pdf_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT UNIQUE NOT NULL,
                file_name TEXT,
                language TEXT NOT NULL,
                extracted_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS pdf_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_hash TEXT UNIQUE NOT NULL,
                chunk_text TEXT NOT NULL,
                keywords_json TEXT NOT NULL,
                learning_points_json TEXT NOT NULL,
                used_count INTEGER DEFAULT 0,
                last_used_at TEXT,
                created_at TEXT NOT NULL
            )
        """)

        c.execute("CREATE INDEX IF NOT EXISTS idx_results_user_date ON results(tg_user_id, date DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pdf_chunks_file_hash ON pdf_chunks(file_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pdf_chunks_usage ON pdf_chunks(file_hash, used_count, last_used_at)")
        conn.commit()

def save_user(tg_user_id, username):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO users (tg_user_id, username) VALUES (?, ?)",
            (str(tg_user_id), username or "")
        )
        conn.commit()

def save_result(tg_user_id, subject, score, total, language):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO results (tg_user_id, subject, score, total, language, date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(tg_user_id), subject, score, total, language, now_str())
        )
        conn.commit()

def get_results(tg_user_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT subject, score, total, language, date
            FROM results
            WHERE tg_user_id = ?
            ORDER BY id DESC
            """,
            (str(tg_user_id),)
        )
        return [dict(row) for row in c.fetchall()]

def get_pdf_cache(file_hash):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT file_hash, file_name, language, extracted_text, created_at, updated_at
            FROM pdf_cache
            WHERE file_hash = ?
            """,
            (file_hash,)
        )
        row = c.fetchone()
        return dict(row) if row else None

def upsert_pdf_cache(file_hash, file_name, language, extracted_text):
    with get_conn() as conn:
        c = conn.cursor()
        ts = now_str()
        c.execute(
            """
            INSERT INTO pdf_cache (file_hash, file_name, language, extracted_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_hash) DO UPDATE SET
                file_name = excluded.file_name,
                language = excluded.language,
                extracted_text = excluded.extracted_text,
                updated_at = excluded.updated_at
            """,
            (file_hash, file_name, language, extracted_text, ts, ts)
        )
        conn.commit()

def get_chunk_count(file_hash):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) AS cnt FROM pdf_chunks WHERE file_hash = ?", (file_hash,))
        row = c.fetchone()
        return row["cnt"] if row else 0

def save_chunks(file_hash, chunks):
    with get_conn() as conn:
        c = conn.cursor()
        ts = now_str()
        rows = []
        for item in chunks:
            rows.append(
                (
                    file_hash,
                    item["chunk_index"],
                    item["chunk_hash"],
                    item["chunk_text"],
                    json.dumps(item["keywords"], ensure_ascii=False),
                    json.dumps(item["learning_points"], ensure_ascii=False),
                    ts,
                )
            )

        c.executemany(
            """
            INSERT OR IGNORE INTO pdf_chunks
            (file_hash, chunk_index, chunk_hash, chunk_text, keywords_json, learning_points_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows
        )
        conn.commit()

def sample_chunks(file_hash, limit=3):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, file_hash, chunk_index, chunk_hash, chunk_text, keywords_json,
                   learning_points_json, used_count, last_used_at
            FROM pdf_chunks
            WHERE file_hash = ?
            ORDER BY used_count ASC,
                     CASE WHEN last_used_at IS NULL THEN 0 ELSE 1 END ASC,
                     last_used_at ASC,
                     RANDOM()
            LIMIT ?
            """,
            (file_hash, limit)
        )
        rows = c.fetchall()

    result = []
    for row in rows:
        item = dict(row)
        item["keywords"] = json.loads(item["keywords_json"])
        item["learning_points"] = json.loads(item["learning_points_json"])
        result.append(item)
    return result

def mark_chunks_used(chunk_ids):
    if not chunk_ids:
        return

    with get_conn() as conn:
        c = conn.cursor()
        ts = now_str()
        c.executemany(
            """
            UPDATE pdf_chunks
            SET used_count = used_count + 1,
                last_used_at = ?
            WHERE id = ?
            """,
            [(ts, cid) for cid in chunk_ids]
        )
        conn.commit()
