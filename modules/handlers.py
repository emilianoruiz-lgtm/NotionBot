from telegram.ext import (
    Application, CommandHandler, CallbackContext, ConversationHandler, MessageHandler, filters
)
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, filters
from telegram import Update
from telegram.constants import ParseMode
from datetime import time
from telegram.ext import MessageHandler, filters
from telegram.ext import ContextTypes

from modules.Ranking import generar_equipos, generar_elo_metegol, RankingELO, generar_resumen_metegol

from modules.DayIN import DayIN, DayInEquipo
from modules.DayOUT import DayOUT,DayOutTest, DayOutEquipo, DayOutProcesar


import aiohttp


from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo  # Python 3.9+

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
ahora = datetime.now(TZ)
print(f"Día de la semana {ahora.weekday()}")  # 0=Lunes, 6=Domingo

# --- CONFIGURACIÓN ---
import Config



# ============================
# Función global cancelar
# ============================
async def cancelar(update: Update, context: CallbackContext):
    await update.message.reply_text("❌ Conversación cancelada.")
    return ConversationHandler.END

# ============================
# Función global cualquier cosa
# ============================
async def generic_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚡ Comando no reconocido. Usa /help")

# ============================
# Función global ejecutando tarea
# ============================

def wrap_handler(func):
    """
    Envuelve un handler normal para que antes muestre "Ejecutando tarea..."
    """
    async def wrapper(update: Update, context: CallbackContext):
        await update.message.reply_text("⚡ Ejecutando tarea...", parse_mode="HTML")
        return await func(update, context)
    return wrapper

# ============================
# Función global confirmar
# ============================
# Estado de confirmación
CONFIRMAR = 999

# Función para manejar la confirmación
async def manejar_confirmacion(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    respuesta = update.message.text.strip().lower()

    if respuesta in ["sí", "si"]:
        if "pendiente" in context.user_data:
            funcion_real = context.user_data.pop("pendiente")
            return await funcion_real(update, context)
        else:
            await update.message.reply_text("⚠️ No hay ninguna acción pendiente.")
    else:
        await update.message.reply_text("❌ Acción cancelada.")
    return ConversationHandler.END

# Función para pedir confirmación
def confirmar_handler(comando, funcion_real):
    async def handler(update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        context.user_data["pendiente"] = funcion_real
        await update.message.reply_text(
            f"⚠️ Vas a ejecutar <b>{comando}</b>.\n¿Confirmás? (sí/no)",
            parse_mode="HTML"
        )
        return CONFIRMAR

    return ConversationHandler(
        entry_points=[CommandHandler(comando, handler)],
        states={
            CONFIRMAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_confirmacion)]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )





# ============================
# CONVERSACIÓN /DAYOUT
# ============================
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

# --- ESTADOS DE CONVERSACIÓN ---
ESPERANDO_EQUIPO_DAYOUT = 200
ESPERANDO_EQUIPO_DAYOUT_TEST = 201

# --- FUNCIÓN PARA CREAR TECLADO DE EQUIPOS ---
def create_team_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("Caimanes", callback_data="team_Caimanes"),
            InlineKeyboardButton("Zorros", callback_data="team_Zorros"),
            InlineKeyboardButton("Huemules", callback_data="team_Huemules"),
        ],
        [
#            InlineKeyboardButton("Todos", callback_data="team_Todos"),
            InlineKeyboardButton("Cancelar", callback_data="team_Cancelar"),
        ],

    ]
    return InlineKeyboardMarkup(keyboard)

# --- CONVERSACIÓN /DAYOUT ---
async def start_dayout(update: Update, context: CallbackContext):
    """Inicia la conversación de /dayout mostrando botones de equipo."""
    await update.message.reply_text(
        "📋 Selecciona un equipo para el DayOUT:",
        reply_markup=create_team_keyboard(),
    )
    return ESPERANDO_EQUIPO_DAYOUT

async def recibir_equipo_dayout(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    equipo_input = query.data.replace("team_", "")

    if equipo_input == "Cancelar":
        await query.message.reply_text("❌ Operación cancelada.")
        return ConversationHandler.END

    async with aiohttp.ClientSession() as session:
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

    return ConversationHandler.END

conv_dayout = ConversationHandler(
    entry_points=[CommandHandler("dayout", start_dayout)],
    states={
        ESPERANDO_EQUIPO_DAYOUT: [
            CallbackQueryHandler(recibir_equipo_dayout, pattern="^team_")
        ]
    },
    fallbacks=[CommandHandler("cancelar", cancelar)]
)

# --- CONVERSACIÓN /DAYOUTTEST ---
async def start_dayout_test(update: Update, context: CallbackContext):
    """Inicia la conversación de /dayouttest mostrando botones de equipo."""
    await update.message.reply_text(
        "📋 Selecciona un equipo para el DayOUT de prueba:",
        reply_markup=create_team_keyboard(),
    )
    return ESPERANDO_EQUIPO_DAYOUT_TEST

async def recibir_equipo_dayout_test(update: Update, context: CallbackContext):
    """Procesa la selección de equipo vía botones para /dayouttest."""
    query = update.callback_query
    await query.answer()

    equipo_input = query.data.replace("team_", "")

    if equipo_input == "Cancelar":
        await query.message.reply_text("❌ Operación cancelada.")
        return ConversationHandler.END

    async with aiohttp.ClientSession() as session:
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

    return ConversationHandler.END

conv_dayout_test = ConversationHandler(
    entry_points=[CommandHandler("dayouttest", start_dayout_test)],
    states={
        ESPERANDO_EQUIPO_DAYOUT_TEST: [
            CallbackQueryHandler(recibir_equipo_dayout_test, pattern="^team_")
        ]
    },
    fallbacks=[CommandHandler("cancelar", cancelar)]
)



# ============================
# CONVERSACIÓN /DAYIN 
# ============================

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

# --- ESTADOS DE CONVERSACIÓN ---
ESPERANDO_EQUIPO_DAYIN = 100

def create_team_keyboard_dayIn():
    keyboard = [
        [
            InlineKeyboardButton("Caimanes", callback_data="team_Caimanes"),
            InlineKeyboardButton("Zorros", callback_data="team_Zorros"),
            InlineKeyboardButton("Huemules", callback_data="team_Huemules"),
        ],
        [
            InlineKeyboardButton("Todos", callback_data="team_Todos"),
            InlineKeyboardButton("Cancelar", callback_data="team_Cancelar"),
        ],

    ]
    return InlineKeyboardMarkup(keyboard)

# --- CONVERSACIÓN /DAYIN ---
async def start_dayin(update: Update, context: CallbackContext):
    """Inicia la conversación de /dayin mostrando botones de equipo."""
    await update.message.reply_text(
        "📋 Selecciona un equipo para el DayIN:",
        reply_markup=create_team_keyboard_dayIn(),
    )
    return ESPERANDO_EQUIPO_DAYIN

async def recibir_equipo_dayin(update: Update, context: CallbackContext):
    """Procesa la selección de equipo vía botones para /dayin."""
    query = update.callback_query
    await query.answer()  # Acknowledge the callback

    equipo_input = query.data.replace("team_", "")

    if equipo_input == "Cancelar":
        await query.message.reply_text("❌ Operación cancelada.")
        return ConversationHandler.END

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

    return ConversationHandler.END

conv_dayin = ConversationHandler(
    entry_points=[CommandHandler("dayin", start_dayin)],
    states={
        ESPERANDO_EQUIPO_DAYIN: [
            CallbackQueryHandler(recibir_equipo_dayin, pattern="^team_")
        ]
    },
    fallbacks=[CommandHandler("cancelar", cancelar)]
)

async def dayin(update: Update, context: CallbackContext):
    resultado = await DayIN()
    await update.message.reply_text(resultado, parse_mode=ParseMode.HTML)



# ============================
# CONVERSACIÓN /EQUIPOS
# ============================

# --- ESTADOS DE CONVERSACIÓN ---
ESPERANDO_AUSENTES_EQUIPOS = 1
ESPERANDO_AUSENTES_TORNEO = 2

async def start_equipos(update: Update, context: CallbackContext):
    try:
        resumen = await generar_resumen_metegol()
        puntos_total, torneos_jugados, torneos_puntuados, logros, registros_por_fecha, elo_dict = await generar_elo_metegol()
        context.user_data["resumen"] = resumen
        context.user_data["elo"] = convertir_elo_a_alias(elo_dict)
    except Exception as e:
        await update.message.reply_text(f"⚠ Error al generar resumen: {e}")
        return ConversationHandler.END

    await update.message.reply_text(
        "⚽ Equipos Metegol:\nPor favor, escribí los nombres de los jugadores que NO van a jugar hoy, separados por comas."
    )
    return ESPERANDO_AUSENTES_EQUIPOS

async def recibir_ausentes(update: Update, context: CallbackContext):
    texto = update.message.text
    ausentes = [normalizar_ausente(a) for a in texto.split(",") if a.strip()]
    jugadores_elo = context.user_data.get("elo", {}).copy()
    equipos_msg = await generar_equipos(jugadores_elo, ausentes)
    await update.message.reply_text(
        f"🏆 Mejores equipos posibles excluyendo a {', '.join(ausentes)}:\n{equipos_msg}",
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END


conv_equipos = ConversationHandler(
    entry_points=[CommandHandler("equipos", start_equipos)],
    states={
        ESPERANDO_AUSENTES_EQUIPOS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: procesar_ausentes(u, c, tipo="equipos"))
        ]
    },
    fallbacks=[CommandHandler("cancelar", cancelar)]
)

# ============================
# CONVERSACIÓN /TORNEO
# ============================
ESPERANDO_AUSENTES_TORNEO = 2

async def cancelar_torneo(update: Update, context: CallbackContext):
    await update.message.reply_text("❌ Conversación cancelada.")
    return ConversationHandler.END

async def start_torneo(update: Update, context: CallbackContext):
    # Solo preguntar quién no juega, sin consultar Notion todavía
    await update.message.reply_text(
        f"Pasame los nombres de los jugadores que NO van a jugar hoy, separados por comas.\n"
        f"Si todos juegan, respondé 'ninguno'."
    )
    return ESPERANDO_AUSENTES_TORNEO

async def recibir_ausentes_torneo(update: Update, context: CallbackContext):
    texto = update.message.text.strip()
    
    # Procesamos ausentes
    if texto.lower() in ["ninguno", "ningun", "ninguna", "ningun@, nadie"]:
        ausentes = []
    else:
        ausentes = [normalizar_ausente(a) for a in texto.split(",") if a.strip()]

    # Ahora sí consultamos Notion / ELO
    try:
        await update.message.reply_text("🪄 Calculando equipos...")
        resumen = await generar_resumen_metegol()
        puntos_total, torneos_jugados, torneos_puntuados, logros, registros_por_fecha, elo_dict = await generar_elo_metegol()
        context.user_data["resumen"] = resumen
        context.user_data["elo"] = convertir_elo_a_alias(elo_dict)
    except Exception as e:
        await update.message.reply_text(f"⚠ Error al generar resumen: {e}")
        return ConversationHandler.END

    jugadores_elo = context.user_data.get("elo", {}).copy()
    disponibles = filtrar_disponibles(jugadores_elo, ausentes)

    if not disponibles:
        await update.message.reply_text("⚠️ Todos los jugadores están ausentes o no se reconocieron los nombres.")
        return ConversationHandler.END

    # Generamos torneo / equipos
    msg = await generar_equipos(disponibles, ausentes)

    await update.message.reply_text(
        f"🏆 Torneo Metegol excluyendo a {', '.join(ausentes) if ausentes else 'nadie'}:\n{msg}",
        parse_mode=ParseMode.HTML
    )

    return ConversationHandler.END

conv_torneo = ConversationHandler(
    entry_points=[CommandHandler("torneo", start_torneo)],
    states={
        ESPERANDO_AUSENTES_TORNEO: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_ausentes_torneo)
        ]
    },
    fallbacks=[CommandHandler("cancelar", cancelar_torneo)]
)


async def cancelar(update: Update, context: CallbackContext):
    await update.message.reply_text("❌ Conversación cancelada.")
    return ConversationHandler.END


