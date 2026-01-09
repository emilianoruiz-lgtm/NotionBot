# ==========================================
# 1. IMPORTS
# ==========================================

# Módulos Locales
import Config
from modules.DayIN import DayIN, DayInEquipo


# ==========================================
# CONSTANTES
# ==========================================

CONFIRMAR = 999
CONFIRM_OK = "confirm_ok"
CONFIRM_CANCEL = "confirm_cancel"

# ==========================================
# HELPERS GENERALES
# ==========================================

def wrap_handler(func):
    """Wrapper para mostrar mensaje de ejecución"""
    async def wrapper(update: Config.Update, context: Config.CallbackContext):
        if update.message:
            await update.message.reply_text(
                "⚡ Ejecutando tarea...",
                parse_mode=Config.ParseMode.HTML,
            )
        return await func(update, context)
    return wrapper


# ==========================================
# CANCELAR / GENERIC
# ==========================================
async def cancelar(update: Config.Update, context: Config.CallbackContext):
    if update.message:
        await update.message.reply_text("❌ Conversación cancelada.")
    elif update.callback_query:
        await update.callback_query.message.reply_text("❌ Conversación cancelada.")
    return Config.ConversationHandler.END




async def generic_message(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("⚡ Comando no reconocido. Usa /help")


# ==========================================
# CONFIRMACIÓN GLOBAL
# ==========================================

async def confirmar_inline(update: Config.Update, context: Config.CallbackContext):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == CONFIRM_OK:
        if "pendiente" in context.user_data:
            funcion_real = context.user_data.pop("pendiente")

            await query.edit_message_text("⏳ Ejecutando acción...")
            await funcion_real(update, context)
        else:
            await query.edit_message_text("⚠️ No hay ninguna acción pendiente.")
    else:
        await query.edit_message_text("❌ Acción cancelada.")

    return Config.ConversationHandler.END



def confirmar_handler(comando: str, funcion_real):

    async def handler(update: Config.Update, context: Config.CallbackContext):
        context.user_data["pendiente"] = funcion_real

        keyboard = Config.InlineKeyboardMarkup([
            [
                Config.InlineKeyboardButton("✅ Confirmar", callback_data=CONFIRM_OK),
                Config.InlineKeyboardButton("❌ Cancelar", callback_data=CONFIRM_CANCEL),
            ]
        ])

        await update.message.reply_text(
            f"⚠️ Vas a ejecutar <b>{comando}</b>.\n¿Confirmás?",
            reply_markup=keyboard,
            parse_mode=Config.ParseMode.HTML,
        )

        return CONFIRMAR

    return Config.ConversationHandler(
        entry_points=[Config.CommandHandler(comando, handler)],
        states={
            CONFIRMAR: [
                Config.CallbackQueryHandler(
                    confirmar_inline,
                    pattern=f"^({CONFIRM_OK}|{CONFIRM_CANCEL})$"
                )
            ]
        },
        fallbacks=[Config.CommandHandler("cancelar", cancelar)],
    )




