# ==========================================
# 1. IMPORTS
# ==========================================

# Módulos Locales
import Config
from modules.DayIN import DayIN, DayInEquipo
from modules.DayOUT import DayOUT,DayOutTest, DayOutEquipo, DayOutProcesar


# ============================
# Wrap global cancelar
# ============================
async def cancelar(update: Config.Update, context: Config.CallbackContext):
    await Config.update.message.reply_text("❌ Conversación cancelada.")
    return Config.ConversationHandler.END

# ============================
# Wrap global cualquier cosa
# ============================
async def generic_message(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    await Config.update.message.reply_text("⚡ Comando no reconocido. Usa /help")

# ============================
# Wrap global ejecutando tarea
# ============================
def wrap_handler(func):
    async def wrapper(update: Config.Update, context: Config.CallbackContext):
        await Config.update.message.reply_text("⚡ Ejecutando tarea...", parse_mode="HTML")
        return await func(update, context)
    return wrapper

# ============================
# Wrap global confirmar
# ============================
CONFIRMAR = 999
async def manejar_confirmacion(update: Config.Update, context: Config.CallbackContext):
    user_id = Config.update.effective_user.id
    respuesta = Config.update.message.text.strip().lower()

    if respuesta in ["sí", "si"]:
        if "pendiente" in context.user_data:
            funcion_real = context.user_data.pop("pendiente")
            return await funcion_real(update, context)
        else:
            await Config.update.message.reply_text("⚠️ No hay ninguna acción pendiente.")
    else:
        await Config.update.message.reply_text("❌ Acción cancelada.")
    return Config.ConversationHandler.END

# Wrap para pedir confirmación
def confirmar_handler(comando, funcion_real):
    async def handler(update: Config.Update, context: Config.CallbackContext):
        user_id = Config.update.effective_user.id
        context.user_data["pendiente"] = funcion_real
        await Config.update.message.reply_text(
            f"⚠️ Vas a ejecutar <b>{comando}</b>.\n¿Confirmás? (sí/no)",
            parse_mode="HTML"
        )
        return CONFIRMAR

    return Config.ConversationHandler(
        entry_points=[Config.CommandHandler(comando, handler)],
        states={
            CONFIRMAR: [Config.MessageHandler(Config.filters.TEXT & ~Config.filters.COMMAND, manejar_confirmacion)]
        },
        fallbacks=[Config.CommandHandler("cancelar", cancelar)]
    )

# ============================
# CONVERSACIÓN /DAYOUT
# ============================
ESPERANDO_EQUIPO_DAYOUT = 200
ESPERANDO_EQUIPO_DAYOUT_TEST = 201
# --- Wrap PARA CREAR TECLADO DE EQUIPOS ---
def create_team_keyboard():
    keyboard = [
        [
            Config.InlineKeyboardButton("Caimanes", callback_data="team_Caimanes"),
            Config.InlineKeyboardButton("Zorros", callback_data="team_Zorros"),
            Config.InlineKeyboardButton("Huemules", callback_data="team_Huemules"),
        ],
        [
            Config.InlineKeyboardButton("Cancelar", callback_data="team_Cancelar"),
        ],
    ]
    return Config.InlineKeyboardMarkup(keyboard)

# --- CONVERSACIÓN /DAYOUT ---
async def start_dayout(update: Config.Update, context: Config.CallbackContext):
    await Config.update.message.reply_text(
        "📋 DayOUT:",
        reply_markup=create_team_keyboard(),
    )
    return ESPERANDO_EQUIPO_DAYOUT

async def recibir_equipo_dayout(update: Config.Update, context: Config.CallbackContext):
    query = Config.update.callback_query
    await query.answer()
    equipo_input = query.data.replace("team_", "")

    if equipo_input == "Cancelar":
        await query.message.reply_text("❌ Operación cancelada.")
        return Config.ConversationHandler.END

    async with Config.aiohttp.ClientSession() as session:
        if equipo_input == "Todos":
            await query.message.reply_text("⚡ Ejecutando DayOUT de todos los equipos...")
            resultados = await DayOutProcesar(session, Config.EQUIPOS)
            await query.message.reply_text(
                "✔️ DayOUT de TODOS los equipos publicado en Notion\n\n" +
                "\n".join(resultados)
            )
        else:
            await query.message.reply_text(f"⚡ Ejecutando DayOUT de {equipo_input}...")
            resultados = await DayOutProcesar(session, [equipo_input])
            await query.message.reply_text(
                f"✔️ DayOUT de {equipo_input} publicado en Notion\n\n" +
                "\n".join(resultados)
            )
    return Config.ConversationHandler.END

conv_dayout = Config.ConversationHandler(
    entry_points=[Config.CommandHandler("dayout", start_dayout)],
    states={
        ESPERANDO_EQUIPO_DAYOUT: [
            Config.CallbackQueryHandler(recibir_equipo_dayout, pattern="^team_")
        ]
    },
    fallbacks=[Config.CommandHandler("cancelar", cancelar)]
)

# --- CONVERSACIÓN /DAYOUTTEST ---
async def start_dayout_test(update: Config.Update, context: Config.CallbackContext):
    await Config.update.message.reply_text(
        "📋 DayOUT de prueba:",
        reply_markup=create_team_keyboard(),
    )
    return ESPERANDO_EQUIPO_DAYOUT_TEST

async def recibir_equipo_dayout_test(update: Config.Update, context: Config.CallbackContext):
    query = Config.update.callback_query
    await query.answer()

    equipo_input = query.data.replace("team_", "")

    if equipo_input == "Cancelar":
        await query.message.reply_text("❌ Operación cancelada.")
        return Config.ConversationHandler.END

    async with Config.aiohttp.ClientSession() as session:
        if equipo_input == "Todos":
            await query.message.reply_text("⚡ Ejecutando DayOUT de prueba de todos los equipos...")
            for eq in Config.EQUIPOS:
                await DayOutTest(update, session, eq)
            await query.message.reply_text("✔️ DayOUT de prueba de TODOS los equipos enviado al usuario")
        else:
            equipo_normalizado = equipo_input
            await query.message.reply_text(f"⚡ Ejecutando DayOUT de prueba de {equipo_normalizado}...")
            await DayOutTest(update, session, equipo_normalizado)
            await query.message.reply_text(f"✔️ DayOUT de prueba de {equipo_normalizado} enviado al usuario")
    return Config.ConversationHandler.END

conv_dayout_test = Config.ConversationHandler(
    entry_points=[Config.CommandHandler("dayouttest", start_dayout_test)],
    states={
        ESPERANDO_EQUIPO_DAYOUT_TEST: [
            Config.CallbackQueryHandler(recibir_equipo_dayout_test, pattern="^team_")
        ]
    },
    fallbacks=[Config.CommandHandler("cancelar", cancelar)]
)


# ============================
# CONVERSACIÓN /DAYIN 
# ============================
ESPERANDO_EQUIPO_DAYIN = 100
def create_team_keyboard_dayIn():
    keyboard = [
        [
            Config.InlineKeyboardButton("Caimanes", callback_data="team_Caimanes"),
            Config.InlineKeyboardButton("Zorros", callback_data="team_Zorros"),
            Config.InlineKeyboardButton("Huemules", callback_data="team_Huemules"),
        ],
        [
            Config.InlineKeyboardButton("Todos", callback_data="team_Todos"),
            Config.InlineKeyboardButton("Cancelar", callback_data="team_Cancelar"),
        ],
    ]
    return Config.InlineKeyboardMarkup(keyboard)

async def start_dayin(update: Config.Update, context: Config.CallbackContext):
    await Config.update.message.reply_text(
        "📋 DayIN:",
        reply_markup=create_team_keyboard_dayIn(),
    )
    return ESPERANDO_EQUIPO_DAYIN

async def recibir_equipo_dayin(update: Config.Update, context: Config.CallbackContext):
    query = Config.update.callback_query
    await query.answer()  
    equipo_input = query.data.replace("team_", "")

    if equipo_input == "Cancelar":
        await query.message.reply_text("❌ Operación cancelada.")
        return Config.ConversationHandler.END

    if equipo_input == "Todos":
        await query.message.reply_text("⚡ Ejecutando DayIN de todos los equipos...")
        for eq in Config.EQUIPOS:
            await DayInEquipo(eq)
        await query.message.reply_text("✔️ DayIN de TODOS los equipos publicado en Notion")
    else:
        equipo_normalizado = equipo_input
        await query.message.reply_text(f"⚡ Ejecutando DayIN de {equipo_normalizado}...")
        await DayInEquipo(equipo_normalizado)
        await query.message.reply_text(f"✔️ DayIN de {equipo_normalizado} publicado en Notion")
    return Config.ConversationHandler.END

conv_dayin = Config.ConversationHandler(
    entry_points=[Config.CommandHandler("dayin", start_dayin)],
    states={
        ESPERANDO_EQUIPO_DAYIN: [
            Config.CallbackQueryHandler(recibir_equipo_dayin, pattern="^team_")
        ]
    },
    fallbacks=[Config.CommandHandler("cancelar", cancelar)]
)


#---????????????

async def dayin(update: Config.Update, context: Config.CallbackContext):
    resultado = await DayIN()
    await Config.update.message.reply_text(resultado, parse_mode=Config.ParseMode.HTML)

async def cancelar(update: Config.Update, context: Config.CallbackContext):
    await Config.update.message.reply_text("❌ Conversación cancelada.")
    return Config.ConversationHandler.END