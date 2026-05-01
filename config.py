import os

# ─── Telegram ────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ─── OpenAI ──────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# الموديل الافتراضي - تم تصحيح الاسم من gpt-5.4-mini إلى gpt-4o-mini
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# موديل احتياطي أرخص (اختياري)
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "")

# ─── Database ────────────────────────────────────────────────────────────────
# على Railway: استخدم مسار /data/quiz_bot.db مع Railway Volume
# أو اضبط DB_PATH في Environment Variables
DB_PATH = os.getenv("DB_PATH", "/data/quiz_bot.db")

# ─── PDF Settings ────────────────────────────────────────────────────────────
MAX_PDF_SIZE_MB      = int(os.getenv("MAX_PDF_SIZE_MB", "10"))
MAX_CHUNK_TEXT_CHARS = int(os.getenv("MAX_CHUNK_TEXT_CHARS", "1400"))
CHUNK_TARGET_CHARS   = int(os.getenv("CHUNK_TARGET_CHARS", "1200"))
CHUNK_MIN_CHARS      = int(os.getenv("CHUNK_MIN_CHARS", "500"))
CHUNK_MAX_CHARS      = int(os.getenv("CHUNK_MAX_CHARS", "1600"))

# ─── Quiz Settings ───────────────────────────────────────────────────────────
# الحد الأقصى لعدد النتائج المعروضة في /reports
MAX_RESULTS_DISPLAY = int(os.getenv("MAX_RESULTS_DISPLAY", "20"))

# مهلة الرد على السؤال بالثواني (0 = بلا مهلة)
ANSWER_TIMEOUT_SECONDS = int(os.getenv("ANSWER_TIMEOUT_SECONDS", "0"))
