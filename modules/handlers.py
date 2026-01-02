# ==========================================
# 1. IMPORTS
# ==========================================

# Módulos Locales
import Config
from modules.DayIN import DayIN, DayInEquipo
from modules.DayOUT import (
    DayOUT,
    DayOutTest,
    DayOutEquipo,
    DayOutProcesar,
)

# ==========================================
# CONSTANTES
# ==========================================

CONFIRMAR = 999

ESPERANDO_EQUIPO_DAYIN = 100
ESPERANDO_EQUIPO_DAYOUT = 200
ESPERANDO_EQUIPO_DAYOUT_TEST = 201

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

async def manejar_confirmacion(update: Config.Update, context: Config.CallbackContext):
    respuesta = update.message.text.strip().lower()

    if respuesta in ("sí", "si"):
        if "pendiente" in context.user_data:
            funcion_real = context.user_data.pop("pendiente")
            return await funcion_real(update, context)
        else:
            await update.message.reply_text("⚠️ No hay ninguna acción pendiente.")
    else:
        await update.message.reply_text("❌ Acción cancelada.")

    return Config.ConversationHandler.END


def confirmar_handler(comando: str, funcion_real):
    async def handler(update: Config.Update, context: Config.CallbackContext):
        context.user_data["pendiente"] = funcion_real
        await update.message.reply_text(
            f"⚠️ Vas a ejecutar <b>{comando}</b>.\n¿Confirmás? (sí/no)",
            parse_mode=Config.ParseMode.HTML,
        )
        return CONFIRMAR

    return Config.ConversationHandler(
        entry_points=[Config.CommandHandler(comando, handler)],
        states={
            CONFIRMAR: [
                Config.MessageHandler(
                    Config.filters.TEXT & ~Config.filters.COMMAND,
                    manejar_confirmacion,
                )
            ]
        },
        fallbacks=[Config.CommandHandler("cancelar", cancelar)],
    )


# ==========================================
# TECLADOS
# ==========================================

def create_team_keyboard(include_todos=False):
    keyboard = [
        [
            Config.InlineKeyboardButton("Caimanes", callback_data="team_Caimanes"),
            Config.InlineKeyboardButton("Zorros", callback_data="team_Zorros"),
            Config.InlineKeyboardButton("Huemules", callback_data="team_Huemules"),
        ]
    ]

    if include_todos:
        keyboard.append([
            Config.InlineKeyboardButton("Todos", callback_data="team_Todos"),
        ])

    keyboard.append([
        Config.InlineKeyboardButton("Cancelar", callback_data="team_Cancelar"),
    ])

    return Config.InlineKeyboardMarkup(keyboard)


# ==========================================
# CONVERSACIÓN /DAYOUT
# ==========================================

async def start_dayout(update: Config.Update, context: Config.CallbackContext):
    await update.message.reply_text(
        "📋 DayOUT:",
        reply_markup=create_team_keyboard(),
    )
    return ESPERANDO_EQUIPO_DAYOUT


async def recibir_equipo_dayout(update: Config.Update, context: Config.CallbackContext):
    query = update.callback_query
    await query.answer()

    equipo = query.data.replace("team_", "")

    if equipo == "Cancelar":
        await query.message.reply_text("❌ Operación cancelada.")
        return Config.ConversationHandler.END

    async with Config.aiohttp.ClientSession() as session:
        if equipo == "Todos":
            await query.message.reply_text("⚡ Ejecutando DayOUT de todos los equipos...")
            resultados = await DayOutProcesar(session, Config.EQUIPOS)
            await query.message.reply_text(
                "✔️ DayOUT de TODOS los equipos publicado en Notion\n\n"
                + "\n".join(resultados)
            )
        else:
            await query.message.reply_text(f"⚡ Ejecutando DayOUT de {equipo}...")
            resultados = await DayOutProcesar(session, [equipo])
            await query.message.reply_text(
                f"✔️ DayOUT de {equipo} publicado en Notion\n\n"
                + "\n".join(resultados)
            )

    return Config.ConversationHandler.END


conv_dayout = Config.ConversationHandler(
    entry_points=[Config.CommandHandler("dayout", start_dayout)],
    states={
        ESPERANDO_EQUIPO_DAYOUT: [
            Config.CallbackQueryHandler(recibir_equipo_dayout, pattern="^team_")
        ]
    },
    fallbacks=[Config.CommandHandler("cancelar", cancelar)],
)


# ==========================================
# CONVERSACIÓN /DAYOUTTEST
# ==========================================

async def start_dayout_test(update: Config.Update, context: Config.CallbackContext):
    await update.message.reply_text(
        "📋 DayOUT de prueba:",
        reply_markup=create_team_keyboard(),
    )
    return ESPERANDO_EQUIPO_DAYOUT_TEST


async def recibir_equipo_dayout_test(update: Config.Update, context: Config.CallbackContext):
    query = update.callback_query
    await query.answer()

    equipo = query.data.replace("team_", "")

    if equipo == "Cancelar":
        await query.message.reply_text("❌ Operación cancelada.")
        return Config.ConversationHandler.END

    async with Config.aiohttp.ClientSession() as session:
        if equipo == "Todos":
            await query.message.reply_text(
                "⚡ Ejecutando DayOUT de prueba de todos los equipos..."
            )
            for eq in Config.EQUIPOS:
                await DayOutTest(update, session, eq)
            await query.message.reply_text(
                "✔️ DayOUT de prueba de TODOS los equipos enviado"
            )
        else:
            await query.message.reply_text(
                f"⚡ Ejecutando DayOUT de prueba de {equipo}..."
            )
            await DayOutTest(update, session, equipo)
            await query.message.reply_text(
                f"✔️ DayOUT de prueba de {equipo} enviado"
            )

    return Config.ConversationHandler.END


conv_dayout_test = Config.ConversationHandler(
    entry_points=[Config.CommandHandler("dayouttest", start_dayout_test)],
    states={
        ESPERANDO_EQUIPO_DAYOUT_TEST: [
            Config.CallbackQueryHandler(
                recibir_equipo_dayout_test, pattern="^team_"
            )
        ]
    },
    fallbacks=[Config.CommandHandler("cancelar", cancelar)],
)


# ==========================================
# CONVERSACIÓN /DAYIN
# ==========================================

async def start_dayin(update: Config.Update, context: Config.CallbackContext):
    await update.message.reply_text(
        "📋 DayIN:",
        reply_markup=create_team_keyboard(include_todos=True),
    )
    return ESPERANDO_EQUIPO_DAYIN


async def recibir_equipo_dayin(update: Config.Update, context: Config.CallbackContext):
    query = update.callback_query
    await query.answer()

    equipo = query.data.replace("team_", "")

    if equipo == "Cancelar":
        await query.message.reply_text("❌ Operación cancelada.")
        return Config.ConversationHandler.END

    if equipo == "Todos":
        await query.message.reply_text("⚡ Ejecutando DayIN de todos los equipos...")
        for eq in Config.EQUIPOS:
            await DayInEquipo(eq)
        await query.message.reply_text(
            "✔️ DayIN de TODOS los equipos publicado en Notion"
        )
    else:
        await query.message.reply_text(f"⚡ Ejecutando DayIN de {equipo}...")
        await DayInEquipo(equipo)
        await query.message.reply_text(
            f"✔️ DayIN de {equipo} publicado en Notion"
        )

    return Config.ConversationHandler.END


conv_dayin = Config.ConversationHandler(
    entry_points=[Config.CommandHandler("dayin", start_dayin)],
    states={
        ESPERANDO_EQUIPO_DAYIN: [
            Config.CallbackQueryHandler(recibir_equipo_dayin, pattern="^team_")
        ]
    },
    fallbacks=[Config.CommandHandler("cancelar", cancelar)],
)


# ==========================================
# COMANDO SIMPLE /DAYIN (DIRECTO)
# ==========================================

@wrap_handler
async def dayin(update: Config.Update, context: Config.CallbackContext):
    resultado = await DayIN()
    await update.message.reply_text(
        resultado,
        parse_mode=Config.ParseMode.HTML,
    )
