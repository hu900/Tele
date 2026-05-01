from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from services.pdf_service import extract_text_from_pdf
from services.quiz_service import generate_questions

# حالات المحادثة
SUBJECT, PDF_UPLOAD, PLAYING = range(3)

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("مرحباً! أرسل اسم المادة التي ترفع اختباراتها السابقة:")
    return SUBJECT

async def handle_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['subject'] = update.message.text
    await update.message.reply_text(f"أرسل الآن ملف PDF الخاص بـ {update.message.text}:")
    return PDF_UPLOAD

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("جاري قراءة الاختبار... يرجى الانتظار ⏳")
    
    file = await update.message.document.get_file()
    file_bytes = await file.download_as_bytearray()
    
    # استخراج النص
    text = extract_text_from_pdf(file_bytes)
    
    # استخراج الأسئلة
    questions = await generate_questions(text)
    
    if not questions:
        await msg.edit_text("لم أتمكن من استخراج أسئلة واضحة. تأكد أن الملف يحتوي على أسئلة نصية.")
        return ConversationHandler.END
        
    context.user_data['questions'] = questions
    context.user_data['current_idx'] = 0
    context.user_data['score'] = 0
    
    await msg.delete()
    return await ask_question(update, context)

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data['current_idx']
    qs = context.user_data['questions']
    
    if idx >= len(qs):
        await (update.callback_query.message if update.callback_query else update.message).reply_text(
            f"انتهى الاختبار! نتيجتك: {context.user_data['score']} من {len(qs)}"
        )
        return ConversationHandler.END

    q = qs[idx]
    # أزرار (A, B, C, D) لتجنب أخطاء الطول في تيليجرام
    keyboard = []
    labels = ["A", "B", "C", "D"]
    for i, opt in enumerate(q['options']):
        keyboard.append([InlineKeyboardButton(f"{labels[i]}: {opt}", callback_data=opt)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"سؤال {idx+1}:\n{q['question']}"
    
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
    return PLAYING

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    idx = context.user_data['current_idx']
    correct = context.user_data['questions'][idx]['answer']
    
    if query.data == correct:
        context.user_data['score'] += 1
        
    context.user_data['current_idx'] += 1
    return await ask_question(update, context)
