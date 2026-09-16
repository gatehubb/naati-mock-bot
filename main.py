import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
import google.generativeai as genai

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Environment variables
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
ADMIN_PASSWORD = "2377451"

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Conversation states for Admin Dialog Creation
AUTH_ADMIN, ADMIN_MENU, DIALOG_NAME, INTRO_VOICE, SEGMENT_VOICE, SEGMENT_TEXT, NEXT_ACTION = range(7)

# Data file path
DIALOGS_FILE = "dialogs.json"

def load_dialogs():
    if os.path.exists(DIALOGS_FILE):
        with open(DIALOGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_dialogs(data):
    with open(DIALOGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

PROMPT_NAATI = """
تو یک ممتحن ارشد آزمون NAATI CCL در زبان‌های فارسی و انگلیسی هستی.
کاربر یک فایل صوتی پاسخ به همراه متن ترجمه مرجع سگمنت را دارد.
1. ابتدا صدای ارسالی را پیاده‌سازی (Transcript) کن.
2. آن را با متن ترجمه مرجع مقایسه کن و بر اساس کدهای رسمی NAATI تحلیل کن:
   - Accuracy (Omissions, Distortions, Insertions)
   - Quality of Language
   - Delivery (Pauses, Hesitations)
3. نمره کسر شده، نمره نهایی سگمنت و نکات اصلاحی را دقیق ذکر کن.
"""

# --- Public Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! به ربات تمرین و ماک آزمون NAATI CCL خوش آمدید.\n"
        "جهت ورود به پنل مدیریت دستور /admin را ارسال کنید."
    )

# --- Admin Flow ---
async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔑 لطفا رمز عبور مدیریت را وارد کنید:")
    return AUTH_ADMIN

async def auth_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == ADMIN_PASSWORD:
        keyboard = [
            [InlineKeyboardButton("➕ افزودن دیالوگ جدید", callback_data="add_dialog")],
            [InlineKeyboardButton("📋 لیست دیالوگ‌ها", callback_data="list_dialogs")]
        ]
        await update.message.reply_text("✅ ورود موفقیت‌آمیز بود. گزینه مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ADMIN_MENU
    else:
        await update.message.reply_text("❌ رمز عبور اشتباه است. دسترسی رد شد.")
        return ConversationHandler.END

async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_dialog":
        context.user_data["new_dialog"] = {"segments": []}
        await query.message.reply_text("📝 لطفاً نام/عنوان دیالوگ را وارد کنید:")
        return DIALOG_NAME
    elif query.data == "list_dialogs":
        dialogs = load_dialogs()
        if not dialogs:
            await query.message.reply_text("هیچ دیالوگی ثبت نشده است.")
        else:
            msg = "📋 **لیست دیالوگ‌های ثبت‌شده:**\n\n"
            for d_id, d_info in dialogs.items():
                msg += f"🔹 {d_info['name']} ({len(d_info['segments'])} سگمنت)\n"
            await query.message.reply_text(msg)
        return ADMIN_MENU

async def get_dialog_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["new_dialog"]["name"] = name
    await update.message.reply_text(f"عنوان «{name}» ثبت شد.\n\n🎙 اکنون فایل صوتی **Introduction** (مقدمه دیالوگ) را ارسال کنید:")
    return INTRO_VOICE

async def get_intro_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice_file = update.message.voice or update.message.audio
    if not voice_file:
        await update.message.reply_text("لطفاً یک فایل صوتی/وویس ارسال کنید.")
        return INTRO_VOICE

    file_id = voice_file.file_id
    context.user_data["new_dialog"]["intro_file_id"] = file_id
    
    await update.message.reply_text("✅ فایل صوتی Introduction ثبت شد.\n\n🎙 اکنون فایل صوتی **سگمنت اول** را ارسال کنید:")
    return SEGMENT_VOICE

async def get_segment_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice_file = update.message.voice or update.message.audio
    if not voice_file:
        await update.message.reply_text("لطفاً یک فایل صوتی/وویس برای این سگمنت ارسال کنید.")
        return SEGMENT_VOICE

    seg_num = len(context.user_data["new_dialog"]["segments"]) + 1
    context.user_data["current_segment"] = {"voice_id": voice_file.file_id}
    
    await update.message.reply_text(f"✅ وویس سگمنت {seg_num} دریافت شد.\n\n✏️ اکنون **متن ترجمه مرجع** برای سگمنت {seg_num} را ارسال کنید:")
    return SEGMENT_TEXT

async def get_segment_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    current_seg = context.user_data["current_segment"]
    current_seg["translation_text"] = text
    
    context.user_data["new_dialog"]["segments"].append(current_seg)
    seg_count = len(context.user_data["new_dialog"]["segments"])

    keyboard = [
        [InlineKeyboardButton("➕ ارسال سگمنت بعدی", callback_data="next_segment")],
        [InlineKeyboardButton("🏁 اتمام دیالوگ", callback_data="finish_dialog")]
    ]
    await update.message.reply_text(
        f"✅ سگمنت شماره {seg_count} با موفقیت ثبت شد.\nاقدام بعدی را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return NEXT_ACTION

async def handle_next_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "next_segment":
        next_num = len(context.user_data["new_dialog"]["segments"]) + 1
        await query.message.reply_text(f"🎙 لطفاً فایل صوتی **سگمنت {next_num}** را ارسال کنید:")
        return SEGMENT_VOICE
    elif query.data == "finish_dialog":
        dialogs = load_dialogs()
        dialog_id = f"dialog_{len(dialogs) + 1}"
        dialogs[dialog_id] = context.user_data["new_dialog"]
        save_dialogs(dialogs)
        
        await query.message.reply_text(f"🎉 دیالوگ «{context.user_data['new_dialog']['name']}» با {len(context.user_data['new_dialog']['segments'])} سگمنت ذخیره شد.")
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.")
    return ConversationHandler.END

# --- Main App ---
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            AUTH_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, auth_check)],
            ADMIN_MENU: [CallbackQueryHandler(admin_menu_callback)],
            DIALOG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_dialog_name)],
            INTRO_VOICE: [MessageHandler(filters.VOICE | filters.AUDIO, get_intro_voice)],
            SEGMENT_VOICE: [MessageHandler(filters.VOICE | filters.AUDIO, get_segment_voice)],
            SEGMENT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_segment_text)],
            NEXT_ACTION: [CallbackQueryHandler(handle_next_action)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(admin_conv)

    print("Bot started...")
    app.run_polling()

if __name__ == '__main__':
    main()
