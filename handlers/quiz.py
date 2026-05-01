from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from services.pdf_service import extract_text_from_pdf
from services.quiz_service import get_exam_questions
import db

SUBJECT, PDF_WAIT, QUIZ_ING = range(3)

async def start_quiz_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك! أرسل اسم المادة أولاً (مثلاً: نظم معلومات):")
    return SUBJECT

async def handle_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['subject'] = update.message.text
    await update.message.reply_text(f"ممتاز! الآن ارفع ملف PDF يحتوي على 'الاختبارات السابقة' لمادة {update.message.text}:")
    return PDF_WAIT

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document or not update.message.document.file_name.endswith('.pdf'):
        await update.message.reply_text("عذراً، يرجى رفع ملف بصيغة PDF فقط.")
        return PDF_WAIT

    processing_msg = await update.message.reply_text("جاري قراءة الاختبار السابق واستخراج الأسئلة... ⏳")
    
    # تحميل الملف ومعالجته
    pdf_file = await update.message.document.get_file()
    pdf_bytes = await pdf_file.download_as_bytearray()
    
    text = extract_text_from_pdf(pdf_bytes)
    if not text:
        await processing_msg.edit_text("لم أتمكن من قراءة محتوى الملف، تأكد أنه ملف نصي وليس صوراً.")
        return ConversationHandler.END

    # استخراج الأسئلة عبر الخدمة
    questions = await get_exam_questions(text)
    
    if not questions:
        await processing_msg.edit_text("لم أجد أسئلة اختيار من متعدد واضحة في هذا الملف. حاول مع ملف آخر.")
        return ConversationHandler.END

    context.user_data['questions'] = questions
    context.user_data['current_idx'] = 0
    context.user_data['score'] = 0
    
    await processing_msg.delete()
    return await send_question(update, context)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data['current_idx']
    questions = context.user_data['questions']

    if idx >= len(questions):
        score = context.user_data['score']
        total = len(questions)
        subject = context.user_data['subject']
        db.save_result(update.effective_user.id, subject, score, total)
        
        msg = f"✅ اكتمل الاختبار!\nالمادة: {subject}\nنتيجتك: {score} من {total}"
        if update.callback_query:
            await update.callback_query.message.edit_text(msg)
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END

    q = questions[idx]
    # استخدام أزرار A, B, C, D لتجنب تشوه الواجهة إذا كانت الخيارات طويلة
    keyboard = []
    labels = ["A", "B", "C", "D"]
    for i, opt in enumerate(q['options']):
        btn_text = f"{labels[i]}: {opt[:50]}" # عرض أول 50 حرف من الخيار
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=opt)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"السؤال {idx+1}:\n\n{q['question']}"
    
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
    return QUIZ_ING

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    idx = context.user_data['current_idx']
    correct = context.user_data['questions'][idx]['answer']
    user_choice = query.data
    
    if user_choice == correct:
        context.user_data['score'] += 1
    
    context.user_data['current_idx'] += 1
    return await send_question(update, context)
