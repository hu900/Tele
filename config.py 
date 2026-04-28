import os

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DB_PATH = os.getenv("DB_PATH", "quiz_bot.db")

# Default economic model for good quality/cost balance
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
# Optional cheaper fallback if you want maximum savings
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "")

MAX_PDF_SIZE_MB = int(os.getenv("MAX_PDF_SIZE_MB", "10"))

MAX_CHUNK_TEXT_CHARS = int(os.getenv("MAX_CHUNK_TEXT_CHARS", "1400"))
CHUNK_TARGET_CHARS = int(os.getenv("CHUNK_TARGET_CHARS", "1200"))
CHUNK_MIN_CHARS = int(os.getenv("CHUNK_MIN_CHARS", "500"))
CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "1600"))
