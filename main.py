import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from config import BOT_TOKEN
from db import init_db
from handlers.start import start
from handlers.reports import reports
from handlers.common import help_command, cancel_command
from handlers.quiz import (
    SUBJECT,
    PDF_WAIT,
    QUESTION_COUNT,
    QUIZ,
    new_quiz,
    receive_subject,
    receive_pdf,
    choose_question_count,
    handle_answer,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

def main():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN غير موجود في Environment Variables")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    quiz_conv = ConversationHandler(
        entry_points=[CommandHandler("newquiz", new_quiz)],
        states={
            SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_subject)],
            PDF_WAIT: [MessageHandler(filters.Document.ALL, receive_pdf)],
            QUESTION_COUNT: [CallbackQueryHandler(choose_question_count, pattern=r"^qcount\|")],
            QUIZ: [CallbackQueryHandler(handle_answer, pattern=r"^ans\|")],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reports", reports))
    app.add_handler(quiz_conv)
    app.add_handler(CommandHandler("cancel", cancel_command))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
