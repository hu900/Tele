from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

HELP_TEXT = (
    "📘 أوامر البوت:\n\n"
    "/start - الصفحة الرئيسية\n"
    "/help - عرض المساعدة\n"
    "/newquiz - بدء اختبار جديد\n"
    "/reports - عرض النتائج السابقة\n"
    "/cancel - إلغاء العملية الحالية\n\n"
    "طريقة الاستخدام:\n"
    "1) أرسل /newquiz\n"
    "2) اكتب اسم المادة\n"
    "3) ارفع ملف PDF\n"
    "4) اختر عدد الأسئلة\n"
    "5) ابدأ الاختبار\n\n"
    "ملاحظة: إذا كان الملف موجودًا سابقًا، سيعيد البوت استخدام النص والمقاطع المخزنة "
    "ثم يختار chunks مختلفة ليولد أسئلة جديدة."
)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("تم إلغاء العملية الحالية ✅")
    return ConversationHandler.END
