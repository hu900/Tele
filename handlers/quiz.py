import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from config import MAX_PDF_SIZE_MB
from db import (
    get_pdf_cache,
    upsert_pdf_cache,
    get_chunk_count,
    save_chunks,
    sample_chunks,
    mark_chunks_used,
    save_result,
)
from services.pdf_service import is_valid_pdf_bytes, extract_text_from_pdf_bytes, sha256_bytes
from services.language_service import detect_text_language, get_language_label
from services.chunk_service import prepare_chunks
from services.quiz_service import generate_quiz_from_chunks

SUBJECT, PDF_WAIT, QUESTION_COUNT, QUIZ = range(4)
OPTION_LABELS = ["A", "B", "C", "D"]

PDF_PROCESS_TIMEOUT = 60   # ثانية لمعالجة PDF
QUIZ_GEN_TIMEOUT   = 120  # ثانية لتوليد الأسئلة


# ─────────────────────────────────────────────
# Keyboards
# ─────────────────────────────────────────────

def count_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("3",  callback_data="qcount|3"),
            InlineKeyboardButton("5",  callback_data="qcount|5"),
            InlineKeyboardButton("7",  callback_data="qcount|7"),
            InlineKeyboardButton("10", callback_data="qcount|10"),
        ]
    ])


def answer_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("A", callback_data="ans|0"),
            InlineKeyboardButton("B", callback_data="ans|1"),
        ],
        [
            InlineKeyboardButton("C", callback_data="ans|2"),
            InlineKeyboardButton("D", callback_data="ans|3"),
        ],
    ])


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def option_label(index: int) -> str:
    if 0 <= index < len(OPTION_LABELS):
        return OPTION_LABELS[index]
    return str(index + 1)


def format_options_text(options):
    return "\n".join(
        f"{option_label(i)}) {opt}"
        for i, opt in enumerate(options[:4])
    )


def chunk_limit_for_questions(num_q: int) -> int:
    if num_q <= 3:  return 2
    if num_q <= 5:  return 3
    if num_q <= 7:  return 4
    return 6


async def _run_in_executor(func, *args):
    """تشغيل دالة blocking في thread منفصل حتى لا يتجمد البوت"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


# ─────────────────────────────────────────────
# Handlers
# ─────────────────────────────────────────────

async def new_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("أرسل اسم المادة لبدء اختبار جديد.")
    return SUBJECT


async def receive_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = update.message.text.strip()
    if len(subject) < 2:
        await update.message.reply_text("اكتب اسم مادة صالح.")
        return SUBJECT
    context.user_data["subject"] = subject
    await update.message.reply_text("الآن أرسل ملف PDF.")
    return PDF_WAIT


async def receive_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        await update.message.reply_text("أرسل ملف PDF فقط.")
        return PDF_WAIT

    if not doc.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("الملف ليس PDF.")
        return PDF_WAIT

    if doc.file_size > MAX_PDF_SIZE_MB * 1024 * 1024:
        await update.message.reply_text(
            f"حجم الملف كبير جدًا. الحد الأقصى {MAX_PDF_SIZE_MB}MB."
        )
        return PDF_WAIT

    status_msg = await update.message.reply_text("⏳ جاري تحميل الملف...")

    # ── تحميل الملف ──
    try:
        file = await asyncio.wait_for(
            doc.get_file(),
            timeout=30
        )
        file_bytes = bytes(await asyncio.wait_for(
            file.download_as_bytearray(),
            timeout=30
        ))
    except asyncio.TimeoutError:
        await status_msg.edit_text("❌ انتهت مهلة تحميل الملف. حاول مرة أخرى.")
        return PDF_WAIT
    except Exception as e:
        await status_msg.edit_text(f"❌ فشل تحميل الملف: {type(e).__name__}")
        return PDF_WAIT

    if not is_valid_pdf_bytes(file_bytes):
        await status_msg.edit_text("❌ الملف لا يبدو PDF صالحًا.")
        return PDF_WAIT

    await status_msg.edit_text("⏳ جاري قراءة وفهرسة الملف...")

    file_hash = sha256_bytes(file_bytes)
    cached = get_pdf_cache(file_hash)

    if cached:
        extracted_text = cached["extracted_text"]
        language       = cached["language"]
        from_cache     = True
    else:
        # ── استخراج النص بـ timeout ──
        try:
            extracted_text = await asyncio.wait_for(
                _run_in_executor(extract_text_from_pdf_bytes, file_bytes),
                timeout=PDF_PROCESS_TIMEOUT
            )
        except asyncio.TimeoutError:
            await status_msg.edit_text(
                "❌ استغرق استخراج النص وقتًا طويلًا جدًا.\n"
                "جرّب ملفًا أصغر أو بعدد صفحات أقل."
            )
            return PDF_WAIT
        except Exception as e:
            await status_msg.edit_text(f"❌ خطأ أثناء قراءة الملف: {type(e).__name__}")
            return PDF_WAIT

        if not extracted_text or len(extracted_text.strip()) < 20:
            await status_msg.edit_text(
                "❌ لم أستطع استخراج نص كافٍ من الملف.\n"
                "تأكد أن الملف يحتوي نصًا وليس صورًا فقط."
            )
            return PDF_WAIT

        language = detect_text_language(extracted_text)
        upsert_pdf_cache(file_hash, doc.file_name, language, extracted_text)
        from_cache = False

    # ── تجهيز الـ chunks ──
    current_chunk_count = get_chunk_count(file_hash)
    if current_chunk_count == 0:
        try:
            chunks = await asyncio.wait_for(
                _run_in_executor(prepare_chunks, file_hash, extracted_text, language),
                timeout=PDF_PROCESS_TIMEOUT
            )
        except asyncio.TimeoutError:
            await status_msg.edit_text(
                "❌ استغرق تحليل الملف وقتًا طويلًا جدًا. حاول مرة أخرى."
            )
            return PDF_WAIT
        except Exception as e:
            await status_msg.edit_text(f"❌ خطأ أثناء تحليل الملف: {type(e).__name__}")
            return PDF_WAIT

        if not chunks:
            await status_msg.edit_text("❌ تعذر تقسيم الملف إلى مقاطع صالحة.")
            return PDF_WAIT

        save_chunks(file_hash, chunks)
        current_chunk_count = len(chunks)

    context.user_data["file_hash"] = file_hash
    context.user_data["language"]  = language

    lang_label = get_language_label(language)
    cache_msg  = "✅ تم العثور على نسخة مخزنة" if from_cache else "✅ تم فهرسة الملف"

    await status_msg.edit_text(
        f"{cache_msg}\n"
        f"📄 اللغة: {lang_label}\n"
        f"📦 عدد المقاطع: {current_chunk_count}\n\n"
        f"اختر عدد الأسئلة:",
        reply_markup=count_keyboard()
    )
    return QUESTION_COUNT


async def choose_question_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    _, num_q    = q.data.split("|")
    num_q       = int(num_q)
    file_hash   = context.user_data.get("file_hash")
    language    = context.user_data.get("language", "arabic")
    chunk_limit = chunk_limit_for_questions(num_q)

    await q.edit_message_text("⏳ جاري استخراج الأسئلة من الملف...")

    questions      = []
    selected_chunks = []

    for extra in [chunk_limit, chunk_limit + 2, chunk_limit + 4]:
        selected_chunks = sample_chunks(file_hash, extra)
        if not selected_chunks:
            break

        try:
            questions = await asyncio.wait_for(
                _run_in_executor(
                    generate_quiz_from_chunks,
                    selected_chunks, num_q, language
                ),
                timeout=QUIZ_GEN_TIMEOUT
            )
        except asyncio.TimeoutError:
            await q.message.reply_text(
                "❌ انتهت مهلة توليد الأسئلة.\n"
                "حاول مرة أخرى أو اختر عدد أسئلة أقل."
            )
            context.user_data.clear()
            return ConversationHandler.END
        except Exception as e:
            await q.message.reply_text(f"❌ خطأ أثناء استخراج الأسئلة: {type(e).__name__}")
            context.user_data.clear()
            return ConversationHandler.END

        if questions and len(questions) >= max(2, min(num_q, 3)):
            break

    if not questions:
        await q.message.reply_text(
            "❌ لم أتمكن من استخراج أسئلة من هذا الملف.\n"
            "تأكد أن الملف يحتوي أسئلة اختبار واضحة."
        )
        context.user_data.clear()
        return ConversationHandler.END

    chunk_ids = [item["id"] for item in selected_chunks if "id" in item]
    if chunk_ids:
        mark_chunks_used(chunk_ids)

    context.user_data["quiz"]        = questions
    context.user_data["qi"]          = 0
    context.user_data["score"]       = 0
    context.user_data["answers_log"] = []

    await q.message.reply_text(
        f"✅ تم استخراج {len(questions)} سؤال. البداية الآن!"
    )
    await send_question(q.message.chat_id, context)
    return QUIZ


async def send_question(chat_id, context: ContextTypes.DEFAULT_TYPE):
    quiz  = context.user_data["quiz"]
    qi    = context.user_data["qi"]
    item  = quiz[qi]
    total = len(quiz)
    language = context.user_data.get("language", "arabic")

    header = (
        f"📘 السؤال {qi + 1} من {total}"
        if language == "arabic"
        else f"📘 Question {qi + 1} of {total}"
    )
    options_text = format_options_text(item["options"])

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"{header}\n\n{item['question']}\n\n{options_text}",
        reply_markup=answer_keyboard()
    )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if not q.data.startswith("ans|"):
        return QUIZ

    selected_idx = int(q.data.split("|")[1])
    quiz = context.user_data["quiz"]
    qi   = context.user_data["qi"]
    item = quiz[qi]

    if selected_idx < 0 or selected_idx >= len(item["options"]):
        await q.message.reply_text("خيار غير صالح.")
        return QUIZ

    selected     = item["options"][selected_idx]
    correct      = item["answer"]
    correct_idx  = item["options"].index(correct) if correct in item["options"] else -1
    ok           = selected == correct
    language     = context.user_data.get("language", "arabic")

    if ok:
        context.user_data["score"] += 1

    context.user_data["answers_log"].append({
        "your_answer":    selected,
        "correct_answer": correct,
        "result":         "✅" if ok else "❌"
    })

    await q.edit_message_reply_markup(reply_markup=None)

    selected_label = option_label(selected_idx)
    correct_label  = option_label(correct_idx) if correct_idx >= 0 else "?"

    if language == "arabic":
        feedback = (
            f"✅ إجابة صحيحة\nاخترت: {selected_label}) {selected}"
            if ok else
            f"❌ إجابة خاطئة\nاخترت: {selected_label}) {selected}\nالصحيحة: {correct_label}) {correct}"
        )
    else:
        feedback = (
            f"✅ Correct!\nYou chose: {selected_label}) {selected}"
            if ok else
            f"❌ Wrong!\nYou chose: {selected_label}) {selected}\nCorrect: {correct_label}) {correct}"
        )

    await q.message.reply_text(feedback)

    context.user_data["qi"] += 1
    if context.user_data["qi"] >= len(quiz):
        return await finish_quiz(update, context)

    await send_question(q.message.chat_id, context)
    return QUIZ


async def finish_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    score    = context.user_data["score"]
    total    = len(context.user_data["quiz"])
    subject  = context.user_data.get("subject", "بدون مادة")
    language = context.user_data.get("language", "arabic")
    pct      = int(score / total * 100) if total else 0

    save_result(update.effective_user.id, subject, score, total, language)

    emoji = "🏆" if pct >= 80 else "📊"

    if language == "arabic":
        result_text = (
            f"{emoji} النتيجة النهائية\n\n"
            f"المادة: {subject}\n"
            f"النتيجة: {score}/{total}\n"
            f"النسبة: {pct}%"
        )
    else:
        result_text = (
            f"{emoji} Final Result\n\n"
            f"Subject: {subject}\n"
            f"Score: {score}/{total}\n"
            f"Percentage: {pct}%"
        )

    await update.effective_chat.send_message(result_text)
    context.user_data.clear()
    return ConversationHandler.END
