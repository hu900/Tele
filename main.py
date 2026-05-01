"""
main.py — نقطة الدخول الرئيسية للبوت
إصلاحات:
  - إضافة error_handler عام لالتقاط كل الأخطاء وتسجيلها
  - graceful shutdown عند SIGINT/SIGTERM
  - logging أوضح مع مستوى قابل للضبط عبر ENV
"""
import logging
import os
import traceback

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN
from db import init_db
from handlers.common import cancel_command, help_command
from handlers.quiz import (
    PDF_WAIT,
    QUESTION_COUNT,
    QUIZ,
    SUBJECT,
    choose_question_count,
    handle_answer,
    new_quiz,
    receive_pdf,
    receive_subject,
)
from handlers.reports import reports
from handlers.start import start

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
)
# تقليل ضوضاء httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ─── Error Handler ────────────────────────────────────────────────────────────

async def error_handler(update: object, context) -> None:
    """التقاط وتسجيل جميع الأخطاء غير المعالجة."""
    logger.error(
        "❌ خطأ غير متوقع:\n%s",
        "".join(traceback.format_exception(type(context.error), context.error, context.error.__traceback__)),
    )
    # إبلاغ المستخدم برسالة مناسبة إذا كان الخطأ مرتبطاً بـ update
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ حدث خطأ غير متوقع. يرجى المحاولة مجدداً أو كتابة /cancel للبدء من جديد."
            )
        except Exception:
            pass


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("❌ TELEGRAM_BOT_TOKEN غير موجود في Environment Variables")

    # تهيئة قاعدة البيانات
    init_db()

    # بناء التطبيق
    app = Application.builder().token(BOT_TOKEN).build()

    # ─── Conversation: Quiz ───────────────────────────────────────────────────
    quiz_conv = ConversationHandler(
        entry_points=[CommandHandler("newquiz", new_quiz)],
        states={
            SUBJECT:        [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_subject)],
            PDF_WAIT:       [MessageHandler(filters.Document.ALL, receive_pdf)],
            QUESTION_COUNT: [CallbackQueryHandler(choose_question_count, pattern=r"^qcount\|")],
            QUIZ:           [CallbackQueryHandler(handle_answer, pattern=r"^ans\|")],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        per_user=True,
        per_chat=True,
        allow_reentry=True,
        # رسالة عند انتهاء المحادثة بشكل غير متوقع
        conversation_timeout=None,
    )

    # ─── Handlers ─────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("help",    help_command))
    app.add_handler(CommandHandler("reports", reports))
    app.add_handler(quiz_conv)
    app.add_handler(CommandHandler("cancel",  cancel_command))

    # ─── Error Handler ────────────────────────────────────────────────────────
    app.add_error_handler(error_handler)

    # ─── Run ──────────────────────────────────────────────────────────────────
    logger.info("🚀 البوت يعمل الآن...")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
