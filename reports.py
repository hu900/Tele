from telegram import Update
from telegram.ext import ContextTypes
from db import get_results

async def reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_results(update.effective_user.id)
    if not rows:
        await update.message.reply_text("📭 لا توجد نتائج بعد.")
        return

    lines = ["📊 آخر نتائجك:\n"]
    for row in rows[:10]:
        subject = row["subject"]
        score = row["score"]
        total = row["total"]
        language = row["language"]
        date = row["date"]
        pct = round(score / total * 100, 1) if total else 0
        lang_label = "العربية" if language == "arabic" else "English"
        lines.append(f"- {subject}: {score}/{total} ({pct}%) | {lang_label} | {date}")

    await update.message.reply_text("\n".join(lines))
