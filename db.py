"""
db.py — طبقة قاعدة البيانات (SQLite)
إصلاحات:
  - check_same_thread=False لدعم asyncio
  - WAL mode لأداء أفضل مع القراءة المتزامنة
  - LIMIT في get_results لتجنب استرجاع آلاف الصفوف
  - إغلاق آمن للاتصالات عبر context manager
  - إنشاء مجلد DB تلقائياً إذا لم يكن موجوداً
"""
import json
import logging
import os
import sqlite3
from datetime import datetime

from config import DB_PATH, MAX_RESULTS_DISPLAY

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_conn() -> sqlite3.Connection:
    """فتح اتصال SQLite مع إعدادات الأداء والأمان."""
    # إنشاء المجلد تلقائياً (مهم عند استخدام Railway Volume)
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False,   # ضروري مع asyncio
        timeout=10,                 # انتظر 10 ثوان قبل رفع OperationalError
    )
    conn.row_factory = sqlite3.Row

    # WAL mode: أسرع للكتابة المتزامنة مع القراءة
    conn.execute("PRAGMA journal_mode=WAL")
    # حماية البيانات عند الانهيار المفاجئ
    conn.execute("PRAGMA synchronous=NORMAL")

    return conn


# ─── Init ─────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """إنشاء الجداول والـ Indexes إذا لم تكن موجودة."""
    with get_conn() as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_user_id  TEXT UNIQUE NOT NULL,
                username    TEXT,
                created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now'))
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_user_id  TEXT NOT NULL,
                subject     TEXT NOT NULL,
                score       INTEGER NOT NULL,
                total       INTEGER NOT NULL,
                language    TEXT NOT NULL,
                date        TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS pdf_cache (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash      TEXT UNIQUE NOT NULL,
                file_name      TEXT,
                language       TEXT NOT NULL,
                extracted_text TEXT NOT NULL,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS pdf_chunks (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash            TEXT NOT NULL,
                chunk_index          INTEGER NOT NULL,
                chunk_hash           TEXT UNIQUE NOT NULL,
                chunk_text           TEXT NOT NULL,
                keywords_json        TEXT NOT NULL,
                learning_points_json TEXT NOT NULL,
                used_count           INTEGER DEFAULT 0,
                last_used_at         TEXT,
                created_at           TEXT NOT NULL
            )
        """)

        # Indexes
        c.execute("CREATE INDEX IF NOT EXISTS idx_results_user_date   ON results(tg_user_id, date DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pdf_chunks_file_hash ON pdf_chunks(file_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pdf_chunks_usage     ON pdf_chunks(file_hash, used_count, last_used_at)")

        conn.commit()
    logger.info("✅ قاعدة البيانات جاهزة: %s", DB_PATH)


# ─── Users ────────────────────────────────────────────────────────────────────

def save_user(tg_user_id: int | str, username: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (tg_user_id, username) VALUES (?, ?)",
            (str(tg_user_id), username or ""),
        )
        conn.commit()


# ─── Results ──────────────────────────────────────────────────────────────────

def save_result(
    tg_user_id: int | str,
    subject: str,
    score: int,
    total: int,
    language: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO results (tg_user_id, subject, score, total, language, date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(tg_user_id), subject, score, total, language, now_str()),
        )
        conn.commit()


def get_results(tg_user_id: int | str, limit: int | None = None) -> list[dict]:
    """
    جلب آخر نتائج المستخدم.
    limit: عدد النتائج (افتراضي: MAX_RESULTS_DISPLAY من config)
    """
    effective_limit = limit if limit is not None else MAX_RESULTS_DISPLAY
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT subject, score, total, language, date
            FROM results
            WHERE tg_user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (str(tg_user_id), effective_limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats(tg_user_id: int | str) -> dict:
    """إحصائيات إجمالية للمستخدم (مجموع الاختبارات، متوسط الدرجة)."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*)                          AS total_quizzes,
                COALESCE(SUM(score), 0)           AS total_correct,
                COALESCE(SUM(total), 0)           AS total_questions,
                ROUND(AVG(CAST(score AS REAL) / NULLIF(total,0) * 100), 1) AS avg_pct
            FROM results
            WHERE tg_user_id = ?
            """,
            (str(tg_user_id),),
        ).fetchone()
    return dict(row) if row else {}


# ─── PDF Cache ────────────────────────────────────────────────────────────────

def get_pdf_cache(file_hash: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT file_hash, file_name, language, extracted_text, created_at, updated_at
            FROM pdf_cache
            WHERE file_hash = ?
            """,
            (file_hash,),
        ).fetchone()
    return dict(row) if row else None


def upsert_pdf_cache(
    file_hash: str,
    file_name: str | None,
    language: str,
    extracted_text: str,
) -> None:
    ts = now_str()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO pdf_cache (file_hash, file_name, language, extracted_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_hash) DO UPDATE SET
                file_name      = excluded.file_name,
                language       = excluded.language,
                extracted_text = excluded.extracted_text,
                updated_at     = excluded.updated_at
            """,
            (file_hash, file_name, language, extracted_text, ts, ts),
        )
        conn.commit()


# ─── PDF Chunks ───────────────────────────────────────────────────────────────

def get_chunk_count(file_hash: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM pdf_chunks WHERE file_hash = ?",
            (file_hash,),
        ).fetchone()
    return row["cnt"] if row else 0


def save_chunks(file_hash: str, chunks: list[dict]) -> None:
    """حفظ chunks مع تجاهل المكررة (INSERT OR IGNORE)."""
    if not chunks:
        return
    ts = now_str()
    rows = [
        (
            file_hash,
            item["chunk_index"],
            item["chunk_hash"],
            item["chunk_text"],
            json.dumps(item["keywords"], ensure_ascii=False),
            json.dumps(item["learning_points"], ensure_ascii=False),
            ts,
        )
        for item in chunks
    ]
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO pdf_chunks
                (file_hash, chunk_index, chunk_hash, chunk_text,
                 keywords_json, learning_points_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def sample_chunks(file_hash: str, limit: int = 3) -> list[dict]:
    """
    اختيار chunks بذكاء:
      - الأقل استخداماً أولاً
      - ثم الأقدم في الاستخدام
      - ثم عشوائياً للتنويع
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, file_hash, chunk_index, chunk_hash, chunk_text,
                   keywords_json, learning_points_json, used_count, last_used_at
            FROM pdf_chunks
            WHERE file_hash = ?
            ORDER BY
                used_count ASC,
                CASE WHEN last_used_at IS NULL THEN 0 ELSE 1 END ASC,
                last_used_at ASC,
                RANDOM()
            LIMIT ?
            """,
            (file_hash, limit),
        ).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        item["keywords"]        = json.loads(item["keywords_json"])
        item["learning_points"] = json.loads(item["learning_points_json"])
        result.append(item)
    return result


def mark_chunks_used(chunk_ids: list[int]) -> None:
    """تحديث عداد الاستخدام للـ chunks المُستخدمة."""
    if not chunk_ids:
        return
    ts = now_str()
    with get_conn() as conn:
        conn.executemany(
            """
            UPDATE pdf_chunks
            SET used_count   = used_count + 1,
                last_used_at = ?
            WHERE id = ?
            """,
            [(ts, cid) for cid in chunk_ids],
        )
        conn.commit()


def delete_pdf_data(file_hash: str) -> None:
    """حذف PDF وكل chunks مرتبطة به (مفيد للتنظيف اليدوي)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM pdf_chunks WHERE file_hash = ?", (file_hash,))
        conn.execute("DELETE FROM pdf_cache  WHERE file_hash = ?", (file_hash,))
        conn.commit()
    logger.info("🗑️ تم حذف بيانات PDF: %s", file_hash)
