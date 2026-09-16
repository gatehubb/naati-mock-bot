import os
import json
import random
import asyncio
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
from telegram.request import HTTPXRequest
import google.generativeai as genai

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
ADMIN_PASSWORD = "2377451"

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

DIALOGS_FILE = "dialogs.json"

AUTH_ADMIN, ADMIN_MENU, DIALOG_NAME, INTRO_VOICE, SEGMENT_VOICE, SEGMENT_TEXT, NEXT_ACTION = range(7)

def load_dialogs():
    if os.path.exists(DIALOGS_FILE):
        with open(DIALOGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_dialogs(data):
    with open(DIALOGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- Start & Main Menu ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 آزمون تعیین سطح (به زودی)", callback_data="disabled")],
        [InlineKeyboardButton("📖 توضیحات آزمون ناتی از ابتدا تا روز امتحان (به زودی)", callback_data="disabled")],
        [InlineKeyboardButton("📑 تحلیل کارنامه امتحانی (به زودی)", callback_data="disabled")],
        [InlineKeyboardButton("🎧 انجام آزمون ماک", callback_data="start_mock")]
    ]
    await update.message.reply_text(
        "سلام! به ربات آمادگی آزمون NAATI CCL خوش آمدید.\nلطفاً گزینه مورد نظر خود را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def main_menu_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "disabled":
        await query.message.reply_text("این بخش به زودی فعال خواهد شد.")
        return

    if query.data == "start_mock":
        dialogs = load_dialogs()
        if not dialogs:
            await query.message.reply_text("هیچ دیالوگی در سیستم ثبت نشده است. ابتدا از طریق پنل مدیریت دیالوگ اضافه کنید.")
            return

        selected_key = random.choice(list(dialogs.keys()))
        selected_dialog = dialogs[selected_key]
        context.user_data["active_mock"] = {
            "dialog": selected_dialog,
            "current_index": 0,
            "responses": []
        }

        keyboard = [
            [InlineKeyboardButton("✅ بله، آماده‌ام", callback_data="confirm_mock_yes")],
            [InlineKeyboardButton("❌ انصراف", callback_data="confirm_mock_no")]
        ]
        await query.message.reply_text(
            f"🎯 آزمون ماک آماده است.\nعنوان: **{selected_dialog['name']}**\n\nآیا برای شروع ماک آماده هستید؟",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

# --- Mock Test Flow ---
async def handle_mock_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_mock_no":
        await query.message.reply_text("آزمون ماک لغو شد.")
        return

    if query.data == "confirm_mock_yes":
        msg = await query.message.reply_text("⏱ آزمون در حال شروع است... 5")
        for i in range(4, 0, -1):
            await asyncio.sleep(1)
            await msg.edit_text(f"⏱ آزمون در حال شروع است... {i}")
        await asyncio.sleep(1)
        await msg.edit_text("🚀 آزمون شروع شد!")

        mock_data = context.user_data["active_mock"]
        intro_id = mock_data["dialog"]["intro_file_id"]
        await query.message.reply_voice(voice=intro_id, caption="🎙 فایل Introduction")

        await send_next_mock_segment(update, context)

async def send_next_mock_segment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    mock_data = context.user_data.get("active_mock")
    if not mock_data:
        return

    idx = mock_data["current_index"]
    segments = mock_data["dialog"]["segments"]

    if idx >= len(segments):
        await context.bot.send_message(
            chat_id=chat_id,
            text="🎉 آزمون ماک به پایان رسید. پاسخ‌های شما جهت ارزیابی پردازش خواهند شد."
        )
        context.user_data["in_mock"] = False
        return

    seg = segments[idx]
    await context.bot.send_voice(
        chat_id=chat_id,
        voice=seg["voice_id"],
        caption=f"🎧 سگمنت شماره {idx + 1}\n\n🎙 لطفاً پاسخ صوتی خود را ضبط و ارسال کنید..."
    )
    context.user_data["in_mock"] = True

async def handle_user_mock_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("in_mock"):
        await update.message.reply_text("برای شروع تمرین یا ماک، از منوی اصلی اقدام کنید.")
        return

    mock_data = context.user_data.get("active_mock")
    voice_file = update.message.voice
    
    mock_data["responses"].append({
        "segment_index": mock_data["current_index"],
        "voice_id": voice_file.file_id
    })

    await update.message.reply_text("✅ پاسخ صوتی شما دریافت شد.")
    mock_data["current_index"] += 1
    
    await send_next_mock_segment(update, context)

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
        await update.message.reply_text("❌ رمز عبور اشتباه است.")
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
            await query.message.reply_text(msg, parse_mode="Markdown")
        return ADMIN_MENU

async def get_dialog_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["new_dialog"]["name"] = name
    await update.message.reply_text(f"عنوان «{name}» ثبت شد.\n\n🎙 اکنون فایل صوتی **Introduction** را ارسال کنید:")
    return INTRO_VOICE

async def get_intro_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice_file = update.message.voice or update.message.audio
    if not voice_file:
        await update.message.reply_text("لطفاً یک فایل صوتی/وویس ارسال کنید.")
        return INTRO_VOICE
    context.user_data["new_dialog"]["intro_file_id"] = voice_file.file_id
    await update.message.reply_text("✅ فایل صوتی Introduction ثبت شد.\n\n🎙 اکنون فایل صوتی **سگمنت اول** را ارسال کنید:")
    return SEGMENT_VOICE

async def get_segment_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice_file = update.message.voice or update.message.audio
    if not voice_file:
        await update.message.reply_text("لطفاً فایل صوتی سگمنت را ارسال کنید.")
        return SEGMENT_VOICE
    seg_num = len(context.user_data["new_dialog"]["segments"]) + 1
    context.user_data["current_segment"] = {"voice_id": voice_file.file_id}
    await update.message.reply_text(f"✅ وویس سگمنت {seg_num} دریافت شد.\n\n✏️ اکنون **متن ترجمه مرجع** سگمنت {seg_num} را ارسال کنید:")
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
        f"✅ سگمنت {seg_count} ثبت شد.\nاقدام بعدی را انتخاب کنید:",
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
        await query.message.reply_text(f"🎉 دیالوگ «{context.user_data['new_dialog']['name']}» با موفقیت ذخیره شد.")
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عملیات لغو شد.")
    return ConversationHandler.END

def main():
    # افزایش تایم‌آوت و قابلیت تلاش مجدد برای جلوگیری از خطای شبکه Bad Gateway
    request = HTTPXRequest(connect_timeout=20, read_timeout=20)
    app = Application.builder().token(TELEGRAM_TOKEN).request(request).build()

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
    app.add_handler(CallbackQueryHandler(main_menu_callbacks, pattern="^(disabled|start_mock)$"))
    app.add_handler(CallbackQueryHandler(handle_mock_confirmation, pattern="^confirm_mock_"))
    app.add_handler(MessageHandler(filters.VOICE, handle_user_mock_voice))

    print("Bot started...")
    app.run_polling()

if __name__ == '__main__':
    main()
