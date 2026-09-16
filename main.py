import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# کلیدها از تنظیمات Render خوانده می‌شوند
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

PROMPT_NAATI = """
تو یک ممتحن ارشد آزمون NAATI CCL در زبان‌های فارسی و انگلیسی هستی.
کاربر یک فایل صوتی برای تو ارسال می‌کند.
1. ابتدا صدای ارسالی را به دقت بشنو و متن آن را پیاده‌سازی (Transcript) کن.
2. آن را با معیارها و کدهای خطای رسمی NAATI سنجش کن:
   - Accuracy (A: Omissions, B: Distortions, C: Insertions)
   - Quality of Language (E-H for English, J-M for LOTE)
   - Delivery (O-Q: Pauses, Hesitations, Self-corrections)
3. تحلیلی دقیق، لحنی محترمانه و نمره‌دهی استانداردی ارائه بده و خطاهای موجود را دقیقا مشخص کن و راهکار اصلاحی بده.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! من ربات ارزیابی وویس NAATI هستم. وویس خودت رو بفرست تا تحلیلم رو بهت بدم.")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("در حال گوش دادن به وویس و تحلیل طبق استانداردهای NAATI...")
    
    file = await context.bot.get_file(update.message.voice.file_id)
    file_path = "voice.ogg"
    await file.download_to_drive(file_path)

    try:
        audio_file = genai.upload_file(path=file_path)
        response = model.generate_content([PROMPT_NAATI, audio_file])
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"خطایی رخ داد: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Bot started...")
    app.run_polling()

if __name__ == '__main__':
    main()
