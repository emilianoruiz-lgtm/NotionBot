from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

#TELEGRAM_TOKEN = '1844138684:AAExApDRm2UkC1bD5lTRGhgH5fl6rKJWw7E' #Bot Zz
TELEGRAM_TOKEN = '8366578234:AAH3uUYpndGXlhslfSQdl6Brid_GEkAPTjA' #Bot DMP

async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"El ID de este chat es: {chat_id}")

app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("ChatID", chatid))

app.run_polling()