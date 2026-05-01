"""
handlers/quiz.py — معالج الاختبار الكامل

إصلاحات وتحسينات:
  - مطابقة أسماء States والدوال مع main.py (كانت مختلفة تماماً)
  - callback_data يستخدم index بدلاً من النص (الحد 64 بايت في Telegram)
  - استخدام PDF caching من db.py
  - استخدام chunk_service لتقطيع النص
  - حفظ النتيجة في db بعد انتهاء الاختبار
  - التحقق من حجم الملف ونوعه
  - معالجة أخطاء شاملة
  - عرض ملخص الأخطاء في النهاية
"""
import hashlib
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

import db
from config import MAX_PDF_SIZE_MB
from services.chunk_service import prepare_chunks
from services.language_service import detect_text_language, get_language_label
from services.pdf_service import extract_text_from_pdf
from services.quiz_service import generate_questions

logger = logging.getLogger(__name__)

# ─── States (يجب أن تتطابق مع main.py) ───────────────────────────────────────
SUBJECT, PDF_WAIT, QUESTION_COUNT, QUIZ = range(4)

# ─── /newquiz ─────────────────────────────────────────────────────────────────

async def new_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نقطة دخول الاختبار."""
    user = update.effective_user
    db.save_user(user.id, user.username)
    context.user_data.clear()

    await update.message.reply_text(
        "📚 *اختبار جديد*\n\n"
        "أرسل اسم المادة أو الموضوع الذي تريد الاختبار فيه:",
        parse_mode="Markdown",
    )
    return SUBJECT


# ─── استقبال اسم المادة ───────────────────────────────────────────────────────

async def receive_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال اسم المادة والانتقال لطلب الـ PDF."""
    subject = update.message.text.strip()
    if not subject:
        await update.message.reply_text("⚠️ الاسم لا يمكن أن يكون فارغاً. أرسل اسم المادة:")
        return SUBJECT

    context.user_data["subject"] = subject

    await update.message.reply_text(
        f"✅ المادة: *{subject}*\n\n"
        f"الآن أرسل ملف PDF للاختبار السابق\n"
        f"_(الحد الأقصى: {MAX_PDF_SIZE_MB} ميجابايت)_",
        parse_mode="Markdown",
    )
    return PDF_WAIT


# ─── استقبال ملف PDF ──────────────────────────────────────────────────────────

async def receive_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    استقبال PDF، استخراج النص، كاشيع، تقطيع، ثم عرض اختيار عدد الأسئلة.
    """
    doc = update.message.document

    # التحقق من نوع الملف
    if not (doc.mime_type == "application/pdf" or
            (doc.file_name or "").lower().endswith(".pdf")):
        await update.message.reply_text("⚠️ يرجى إرسال ملف PDF فقط.")
        return PDF_WAIT

    # التحقق من الحجم
    max_bytes = MAX_PDF_SIZE_MB * 1024 * 1024
    if doc.file_size and doc.file_size > max_bytes:
        await update.message.reply_text(
            f"⚠️ الملف كبير جداً ({doc.file_size // (1024*1024)} ميجابايت).\n"
            f"الحد الأقصى المسموح: {MAX_PDF_SIZE_MB} ميجابايت."
        )
        return PDF_WAIT

    msg = await update.message.reply_text("⏳ جاري تحميل الملف...")

    try:
        # تحميل الملف
        tg_file = await doc.get_file()
        file_bytes = bytes(await tg_file.download_as_bytearray())
        file_hash = hashlib.md5(file_bytes).hexdigest()

        # ─── التحقق من الكاش ──────────────────────────────────────────────
        cached = db.get_pdf_cache(file_hash)
        if cached:
            text     = cached["extracted_text"]
            language = cached["language"]
            lang_label = get_language_label(language)
            await msg.edit_text(f"✅ تم التعرف على الملف من الكاش!\n🌐 اللغة: {lang_label}")
        else:
            await msg.edit_text("⏳ جاري استخراج النص من PDF...")
            text = extract_text_from_pdf(file_bytes)

            if not text or len(text.strip()) < 80:
                await msg.edit_text(
                    "❌ لم يتمكن من استخراج نص من الملف.\n"
                    "تأكد أن الـ PDF يحتوي على نص قابل للنسخ (وليس صور مسحوحة ضوئياً)."
                )
                return PDF_WAIT

            language   = detect_text_language(text)
            lang_label = get_language_label(language)

            # حفظ في الكاش
            db.upsert_pdf_cache(file_hash, doc.file_name, language, text)

            # إنشاء chunks إذا لم تكن موجودة
            if db.get_chunk_count(file_hash) == 0:
                await msg.edit_text("⏳ جاري تحليل المحتوى وتقطيعه...")
                chunks = prepare_chunks(file_hash, text, language)
                if chunks:
                    db.save_chunks(file_hash, chunks)
                    logger.info("✅ تم إنشاء %d chunk للملف %s", len(chunks), file_hash[:8])

            await msg.edit_text(f"✅ تم تحليل الملف!\n🌐 اللغة: {lang_label}")

        # حفظ بيانات الجلسة
        context.user_data["file_hash"] = file_hash
        context.user_data["language"]  = language
        context.user_data["file_name"] = doc.file_name or "ملف"

        # ─── اختيار عدد الأسئلة ──────────────────────────────────────────
        keyboard = [
            [
                InlineKeyboardButton("5️⃣  أسئلة",   callback_data="qcount|5"),
                InlineKeyboardButton("🔟 أسئلة",    callback_data="qcount|10"),
            ],
            [
                InlineKeyboardButton("1️⃣5️⃣ سؤالاً", callback_data="qcount|15"),
                InlineKeyboardButton("2️⃣0️⃣ سؤالاً", callback_data="qcount|20"),
            ],
        ]
        lang_label = get_language_label(language)
        await msg.edit_text(
            f"✅ *تم تحليل الملف بنجاح!*\n\n"
            f"📄 {doc.file_name or 'الملف'}\n"
            f"🌐 اللغة المكتشفة: {lang_label}\n\n"
            f"كم سؤالاً تريد في الاختبار؟",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return QUESTION_COUNT

    except Exception as e:
        logger.error("خطأ في معالجة PDF: %s", e, exc_info=True)
        await msg.edit_text(
            "❌ حدث خطأ أثناء معالجة الملف.\n"
            "حاول مرة أخرى أو أرسل ملفاً مختلفاً."
        )
        return PDF_WAIT


# ─── اختيار عدد الأسئلة ──────────────────────────────────────────────────────

async def choose_question_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال العدد المختار وتوليد الأسئلة."""
    query = update.callback_query
    await query.answer()

    count     = int(query.data.split("|")[1])
    file_hash = context.user_data["file_hash"]
    language  = context.user_data["language"]

    await query.edit_message_text(f"⏳ جاري توليد {count} سؤالاً من الاختبار السابق...")

    try:
        # جلب chunks ذكي من DB (الأقل استخداماً أولاً)
        chunks_limit = max(2, count // 4 + 2)
        chunks = db.sample_chunks(file_hash, limit=chunks_limit)

        if chunks:
            text_content = "\n\n---\n\n".join(c["chunk_text"] for c in chunks)
            db.mark_chunks_used([c["id"] for c in chunks])
        else:
            # fallback: استخدم النص الكامل
            cached = db.get_pdf_cache(file_hash)
            text_content = cached["extracted_text"] if cached else ""

        if not text_content:
            await query.edit_message_text("❌ لم يتم العثور على محتوى. حاول رفع الملف مجدداً.")
            return ConversationHandler.END

        questions = await generate_questions(text_content, count=count, language=language)

        if not questions:
            await query.edit_message_text(
                "❌ لم يتم العثور على أسئلة اختيار من متعدد في النص.\n"
                "تأكد أن الملف يحتوي على أسئلة واضحة."
            )
            return ConversationHandler.END

        # تهيئة بيانات الاختبار
        context.user_data["questions"]   = questions
        context.user_data["current_idx"] = 0
        context.user_data["score"]       = 0
        context.user_data["wrong"]       = []

        await query.edit_message_text(
            f"✅ تم توليد *{len(questions)}* سؤالاً!\n\n"
            f"يبدأ الاختبار الآن... حظاً موفقاً! 🎯",
            parse_mode="Markdown",
        )
        return await _send_question(query.message.chat_id, context)

    except Exception as e:
        logger.error("خطأ في توليد الأسئلة: %s", e, exc_info=True)
        await query.edit_message_text("❌ حدث خطأ أثناء توليد الأسئلة. حاول مرة أخرى.")
        return ConversationHandler.END


# ─── معالجة الإجابة ───────────────────────────────────────────────────────────

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    استقبال الإجابة، عرض النتيجة، والانتقال للسؤال التالي.
    callback_data: ans|{choice_idx}
    """
    query = update.callback_query
    await query.answer()

    choice_idx = int(query.data.split("|")[1])
    idx        = context.user_data["current_idx"]
    questions  = context.user_data["questions"]
    q          = questions[idx]
    options    = q.get("options", [])

    correct_idx = q.get("correct_index", 0)
    is_correct  = (choice_idx == correct_idx)

    # بناء نص الإجابة
    if is_correct:
        context.user_data["score"] += 1
        result_emoji = "✅"
        result_text  = f"{result_emoji} *إجابة صحيحة!*"
    else:
        correct_text = options[correct_idx] if correct_idx < len(options) else "—"
        result_emoji = "❌"
        result_text  = (
            f"{result_emoji} *إجابة خاطئة!*\n"
            f"الإجابة الصحيحة: _{correct_text}_"
        )
        context.user_data["wrong"].append({
            "question":    q["question"],
            "your_answer": options[choice_idx] if choice_idx < len(options) else "—",
            "correct":     correct_text,
        })

    # تعديل رسالة السؤال لإظهار النتيجة
    score = context.user_data["score"]
    done  = idx + 1
    total = len(questions)
    await query.edit_message_text(
        f"{result_text}\n\n"
        f"_النتيجة حتى الآن: {score}/{done}_",
        parse_mode="Markdown",
    )

    context.user_data["current_idx"] += 1

    if context.user_data["current_idx"] >= total:
        return await _finish_quiz(query.message.chat_id, context)

    return await _send_question(query.message.chat_id, context)


# ─── دوال مساعدة ──────────────────────────────────────────────────────────────

async def _send_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إرسال السؤال الحالي مع أزرار الإجابة."""
    idx       = context.user_data["current_idx"]
    questions = context.user_data["questions"]
    total     = len(questions)
    q         = questions[idx]
    options   = q.get("options", [])

    # تخطي الأسئلة بدون خيارات
    if not options:
        logger.warning("تخطي سؤال بدون خيارات — index %d", idx)
        context.user_data["current_idx"] += 1
        if context.user_data["current_idx"] >= total:
            return await _finish_quiz(chat_id, context)
        return await _send_question(chat_id, context)

    # الأحرف العربية للخيارات (أ ب ج د هـ)
    ar_labels = ["أ", "ب", "ج", "د", "هـ"]
    keyboard  = []
    for i, opt in enumerate(options[:5]):
        label = ar_labels[i] if i < len(ar_labels) else str(i + 1)
        # اقتطاع الخيار إذا كان طويلاً (Telegram limit 64 bytes للـ callback_data)
        btn_text = f"{label}) {opt[:55]}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"ans|{i}")])

    progress_bar = "▓" * idx + "░" * (total - idx - 1)
    text = (
        f"📝 *سؤال {idx + 1} من {total}*\n"
        f"`{progress_bar}`\n\n"
        f"{q['question']}"
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return QUIZ


async def _finish_quiz(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض النتيجة النهائية وحفظها في قاعدة البيانات."""
    score    = context.user_data["score"]
    questions = context.user_data["questions"]
    total    = len(questions)
    subject  = context.user_data.get("subject", "غير محدد")
    language = context.user_data.get("language", "arabic")
    wrong    = context.user_data.get("wrong", [])
    pct      = round(score / total * 100) if total > 0 else 0

    # تقييم الدرجة
    if pct >= 90:
        grade = "🏆 ممتاز"
    elif pct >= 75:
        grade = "🥈 جيد جداً"
    elif pct >= 60:
        grade = "🥉 جيد"
    elif pct >= 50:
        grade = "⚠️ مقبول"
    else:
        grade = "❌ يحتاج مراجعة"

    # نص النتيجة
    text = (
        f"🎯 *انتهى الاختبار!*\n\n"
        f"📚 المادة: {subject}\n"
        f"✅ الصحيح: *{score}* / {total}\n"
        f"📊 النسبة: *{pct}%*\n"
        f"التقييم: {grade}\n"
    )

    # ملخص الأخطاء (أول 5 فقط لتجنب رسالة طويلة)
    if wrong:
        text += f"\n\n❌ *الأخطاء ({len(wrong)} سؤال):*\n"
        for i, w in enumerate(wrong[:5], 1):
            q_short = w["question"][:80] + ("…" if len(w["question"]) > 80 else "")
            text += f"\n*{i}.* {q_short}\n   ✅ _{w['correct']}_\n"
        if len(wrong) > 5:
            text += f"\n_...و {len(wrong) - 5} أخطاء أخرى_"

    text += "\n\n💡 اكتب /newquiz لبدء اختبار جديد"

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
    )

    # حفظ النتيجة في DB
    db.save_result(chat_id, subject, score, total, language)
    logger.info("✅ نتيجة محفوظة: user=%s subject=%s score=%d/%d", chat_id, subject, score, total)

    context.user_data.clear()
    return ConversationHandler.END
