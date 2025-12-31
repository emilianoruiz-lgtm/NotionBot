import ctypes
import sys
import asyncio
import logging
import warnings
import html
import subprocess
import inspect
import re
import os
import sys

import tzdata
import Config
import Horarios
import json

import ntplib
import win32api
import win32con

import re
from functools import wraps
import traceback
import time as _time
from modules.CurvaParcial import generar_curva_parcial, generar_curva_parcial_equipo
from datetime import datetime, timedelta, date



warnings.filterwarnings("ignore", message="If 'per_message=False'", category=UserWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="telegram")
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def run_as_admin():
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            # Opcional: relanzar de forma controlada si es estrictamente necesario
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            sys.exit()
    except Exception as e:
        print(f"⚠️ run_as_admin fallo: {e}")

run_as_admin()




from telegram import InlineKeyboardButton, InlineKeyboardMarkup,Update, InputFile
from telegram.constants import ParseMode
from telegram.error import RetryAfter,NetworkError, TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,  
    ConversationHandler,
    filters,
    ContextTypes,
    JobQueue
)


from datetime import datetime, time, timedelta, date, timezone
from zoneinfo import ZoneInfo
from math import ceil

from modules.Ranking import generar_equipos, generar_ranking_metegol, generar_mensaje_cambio_elo, generar_elo_metegol, RankingELO, generar_resumen_metegol
from modules.Agenda import generar_resumen_manana
from modules.AgendaHoy import agendahoy
from modules.AgendaPlAdmin import AgendaPlAdmin
from modules.AgendaSemProx import AgendaPlAdminSemanaSiguiente
from modules.RDs import RDs_comments
from modules.DayIN import DayIN, DayInEquipo
from modules.DayOUT import DayOUT,DayOutTest, DayOutEquipo
from modules.Burn import burndown, newday, listar_planes
from modules.SiemensCheck import parsear_oferta_robusto, exportar_excel,parsear_briket
from telegram.ext import CommandHandler, MessageHandler, filters, ConversationHandler
from modules.mundopizza.menump import mostrar_menu, setmp_start, elegir_item, elegir_precio, cancelar_setmp, ELEGIR_ITEM, ELEGIR_PRECIO


# Zona horaria Argentina
TZ = ZoneInfo("America/Argentina/Buenos_Aires")


from modules.jobs import (
    job_dayin,
    job_rd,
    job_burn,
    job_agenda_preliminar,
    job_agenda_automatica,
    job_agenda_semana_prox,
    job_dayout,
    job_newday,
    job_food,
    job_pay,
    job_rank
)
from modules.handlers import (
    conv_equipos,
    conv_torneo,
    conv_dayin,
    conv_dayout,
    conv_dayout_test,
    wrap_handler,
    confirmar_handler,
    generic_message,
    cancelar
)

from modules.sethorario import conv_sethorario, TAREAS_MAP

# Zona horaria Argentina
ahora = datetime.now(TZ)
#print(f"Día de la semana {ahora.weekday()}")  # 0=Lunes, 6=Domingo



async def error_handler(update, context):
    err = context.error

    if isinstance(err, (NetworkError, TimedOut)):
        # Error típico de Telegram / red
        print("⚠️ Error de red con Telegram. Reintentando...")
        return

    # Otros errores
    print("❌ Error no controlado:", err)



async def job_restart(context: ContextTypes.DEFAULT_TYPE):
    print("♻️ Reiniciando bot automáticamente...")
    # Espera un par de segundos para liberar recursos
    await asyncio.sleep(2)
    # Lanza un nuevo proceso del mismo script
    os.execv(sys.executable, ['python'] + sys.argv)

PENDIENTES = {}  # guarda acciones pendientes por usuario

async def manejar_pdf(update, context):
    """
    Maneja PDFs enviados al bot:
    - descarga a entrada.pdf
    - detecta tipo (Siemens vs Briket)
    - genera Excel
    - responde al usuario
    """
    pdf_path = "entrada.pdf"  

    try:
        archivo = update.message.document
        if not archivo:
            await update.message.reply_text("⚠️ No se recibió ningún documento PDF.")
            return

        # Descargar archivo
        file = await archivo.get_file()
        await file.download_to_drive(pdf_path)

        import pdfplumber

        # Abrir PDF correcto
        with pdfplumber.open(pdf_path) as pdf:
            texto = "\n".join([p.extract_text() or "" for p in pdf.pages])

        # --- DETECCIÓN DEL TIPO ---
        if "ARQ" in texto:
            print("Detectado: Oferta Siemens")
            items = parsear_oferta_robusto(pdf_path)
            nombre = re.search(r"ARQ\d+", texto).group(0)
            excel_path = f"Oferta_Siemens_{nombre}.xlsx"

        elif "BRIKET S.A." in texto:
            print("Detectado: OC Briket")
            items = parsear_briket(pdf_path)

            # Obtener nombre del PDF original
            pdf_name = archivo.file_name  # ej: "32781.pdf"
            pdf_stem = os.path.splitext(pdf_name)[0]  # ej: "32781"

            excel_path = f"OC_Briket_{pdf_stem}.xlsx"


        else:
            await update.message.reply_text("❌ No reconozco el tipo de PDF.")
            return

        # --- EXPORTAR EXCEL ---
        exportar_excel(items, excel_path)

        # --- ENVIAR EXCEL ---
        with open(excel_path, "rb") as f:
            await update.message.reply_document(f)

    except Exception as e:
        logger.exception("Excepción en manejar_pdf")
        await update.message.reply_text(f"❌ Error procesando PDF: {e}")

    finally:
        # limpiar archivo temporal
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except:
            pass




async def curva_parcial(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(f"📈 Generando curvas de burndown")

    buf = await generar_curva_parcial()
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=InputFile(buf, filename="curva_diferencia.png"),
        caption=f"📊 Burndown actual"
    )


async def curva_parcial_huemul(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(f"📈 Generando curva de burndown Huemul")

    buf = await generar_curva_parcial_equipo("Huemules")
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=InputFile(buf, filename="curva_diferencia.png"),
        caption=f"📊 Burndown Huemul actual"
    )
    

async def curva_parcial_caiman(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(f"📈 Generando curva de burndown Caimán")

    buf = await generar_curva_parcial_equipo("Caimanes")
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=InputFile(buf, filename="curva_diferencia.png"),
        caption=f"📊 Burndown Caimám actual"
    )
    

async def curva_parcial_zorro(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(f"📈 Generando curva de burndown Zorro")

    buf = await generar_curva_parcial_equipo("Zorros")
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=InputFile(buf, filename="curva_diferencia.png"),
        caption=f"📊 Burndown Zorro actual"
    )


async def safe_send_message(bot, chat_id, text, parse_mode=ParseMode.HTML, **kwargs):
    """
    Envía un mensaje asegurando que no se rompa por FloodControl.
    """
    MAX_LEN = 4000  # Telegram permite hasta ~4096 caracteres por mensaje
    start = 0

    while start < len(text):
        end = start + MAX_LEN
        # Cortar en salto de línea si es posible
        if end < len(text):
            newline_pos = text.rfind("\n", start, end)
            if newline_pos != -1:
                end = newline_pos + 1

        msg_chunk = text[start:end]

        while True:
            try:
                return await bot.send_message(chat_id, msg_chunk, parse_mode=parse_mode, **kwargs)
            except RetryAfter as e:
                print(f"⚠️ Flood control: esperando {e.retry_after} segundos antes de reenviar mensaje")
                await asyncio.sleep(e.retry_after)

        start = end

def tzutil_get_zone():
    try:
        result = subprocess.run(['tzutil', '/g'], capture_output=True, text=True, check=True)
        windows_tz = result.stdout.strip()
        # Map Windows timezone to IANA
        tz_map = {
            "Argentina Standard Time": "America/Argentina/Buenos_Aires",
            # Add other mappings if needed
        }
        return tz_map.get(windows_tz, windows_tz)
    except subprocess.CalledProcessError:
        return "Unknown"

def set_system_timezone():
    """Set the system timezone to Argentina Standard Time."""
    desired_tz = "Argentina Standard Time"
    try:
        subprocess.run(['tzutil', '/s', desired_tz], check=True)
        print(f"✅ System timezone set to {desired_tz}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error setting system timezone: {e}")

def sync_system_time():
    """Simpler sync: ask Windows to resync with its NTP servers via w32tm.
    If w32tm falla (permiso o error), hacemos un fetch NTP para diagnóstico.
    """
    try:
        # This is the simplest: ask Windows to resync (requires admin)
        subprocess.run(['w32tm', '/resync'], check=True, capture_output=True, text=True)
        print("✅ Requested system time resync via 'w32tm /resync'.")
        # Log detallado para depuración
        ahora = datetime.now(TZ)
        print(f"TZ_Time = {ahora}\nSysTime = {datetime.now(TZ)}\n")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ 'w32tm /resync' failed: {e}. Attempting to fetch NTP time for diagnostics...")
        try:
            client = ntplib.NTPClient()
            resp = client.request("pool.ntp.org", version=3, timeout=5)
            ntp_time = datetime.fromtimestamp(resp.tx_time, tz=timezone.utc).astimezone(TZ)
            print(f"[DEBUG] NTP time (no set): {ntp_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except Exception as e2:
            print(f"❌ Fallback NTP fetch failed: {e2}")

async def send_long_message(bot, chat_id, text, parse_mode="HTML", message_thread_id=None):
    MAX_LEN = 4000
    start = 0
    while start < len(text):
        end = start + MAX_LEN
        if end < len(text):
            newline_pos = text.rfind("\n", start, end)
            if newline_pos != -1:
                end = newline_pos + 1
        await bot.send_message(
            chat_id=chat_id,
            text=text[start:end],
            parse_mode=parse_mode,
            message_thread_id=message_thread_id
        )
        start = end

def normalizar_ausente(nombre: str) -> str:
    nombre = nombre.strip()
    if not nombre:
        return ""
    for alias in Config.ALIAS_PERSONAS.values():
        if nombre.upper() == alias.upper():
            return alias.upper()
    for completo, alias in Config.ALIAS_PERSONAS.items():
        if nombre.lower() == completo.lower():
            return alias.upper()
    return nombre.upper()

def convertir_elo_a_alias(elo_dict: dict) -> dict:
    elo_dict_alias = {}
    for jugador, rating in elo_dict.items():
        alias = Config.ALIAS_PERSONAS.get(jugador, jugador)
        elo_dict_alias[alias] = rating
    return elo_dict_alias

def filtrar_disponibles(jugadores_elo: dict, ausentes: list) -> dict:
    ausentes_set = set(a.upper() for a in ausentes)
    return {j: e for j, e in jugadores_elo.items() if j.upper() not in ausentes_set}

async def procesar_ausentes(update: Update, context: ContextTypes.DEFAULT_TYPE, tipo: str = "equipos"):
    texto = update.message.text
    ausentes = [normalizar_ausente(a) for a in texto.split(",") if a.strip()]
    jugadores_elo = context.user_data.get("elo", {}).copy()
    disponibles = filtrar_disponibles(jugadores_elo, ausentes)

    if tipo == "equipos":
        msg = await generar_equipos(disponibles, ausentes)
        titulo = "🏆 Mejores equipos posibles"
    elif tipo == "torneo":
        msg = await generar_equipos(disponibles, ausentes)
        titulo = "🏆 Torneo Metegol"
    else:
        msg = "⚠ Tipo desconocido"
        titulo = "Error"

    await update.message.reply_text(
        f"{titulo} excluyendo a {', '.join(ausentes)}:\n{msg}",
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END

async def burn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Burn manual")
    await update.message.reply_text("⚡ Ejecutando tarea...", parse_mode="HTML")
    await burndown()
    await update.message.reply_text("✔️ Puntajes de Burndown chequeados", parse_mode=ParseMode.HTML)

async def newburnreg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Newday manual")
    await update.message.reply_text("⚡ Ejecutando tarea...", parse_mode="HTML")
    await newday()
    await update.message.reply_text("✔️ Nuevos registros de Burndown creados en Notion", parse_mode=ParseMode.HTML)

async def rd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  RD manual")
    resultado = await RDs_comments(concatenado=True)
    await update.message.reply_text(resultado, parse_mode=ParseMode.HTML)

async def rd2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  RD manual")
    try:
        # Ejecutamos exactamente lo mismo que el Job programado
        await maybe_await(job_rd, context)

        await update.message.reply_text(
            "✅ Job RD ejecutado manualmente.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Error al ejecutar job_rd manual: {e}",
            parse_mode=ParseMode.HTML
        )

#------------------------- SET MENU PRECIOS ----------------------

# Estados para el ConversationHandler
ELEGIR_ITEM, ELEGIR_PRECIO = range(2)

# Definir el ConversationHandler para /setmp
conv_setmp = ConversationHandler(
    entry_points=[CommandHandler("setmp", setmp_start)],
    states={
        ELEGIR_ITEM: [CallbackQueryHandler(elegir_item)],  # Cambiar a CallbackQueryHandler
        ELEGIR_PRECIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, elegir_precio)],
    },
    fallbacks=[CommandHandler("cancelar", cancelar_setmp)],
)

#------------------------- FIN SET MENU PRECIOS ----------------------



async def medal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Medal")
    try:
        puntos_total, torneos_jugados, torneos_puntuados, logros, registros_por_fecha, elo_dict = await generar_elo_metegol()
        elo = convertir_elo_a_alias(elo_dict)
        ausentes_raw = context.args if context.args else []
        ausentes = [normalizar_ausente(a) for a in ausentes_raw]
        ranking_texto = generar_ranking_metegol(
            puntos_total, torneos_jugados, torneos_puntuados, logros, registros_por_fecha, elo, ausentes
        )
        await send_long_message(context.bot, update.effective_chat.id, ranking_texto)
    except Exception as e:
        await update.message.reply_text(f"⚠ Error en /medal: {e}")

async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Rank")
    msg = await RankingELO()
    await update.message.reply_text(f"{msg}", parse_mode=ParseMode.HTML)
    return ConversationHandler.END


async def epicas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Épicas")
    try:
        # Obtener el mensaje de listar_planes (ya devuelve HTML seguro)
        msg = await listar_planes()
        
        # No escapar todo el HTML, solo usarlo tal cual
        await safe_send_message(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            text=msg,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error en epicas: {e}\nMensaje original: {msg}")
        # Enviar mensaje sin formato en caso de error
        await safe_send_message(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            text=f"⚠️ Error al mostrar épicas: {str(e)}\nMensaje sin formato:\n{msg}",
            parse_mode=None
        )
    return ConversationHandler.END

#async def elo(update: Update, context: ContextTypes.DEFAULT_TYPE):
#    msg = await generar_mensaje_cambio_elo()
#    await update.message.reply_text(f"{msg}", parse_mode=ParseMode.HTML)
#    return ConversationHandler.END

async def hoy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Agenda hoy")
    resultado = await agendahoy()
    if resultado and resultado.strip():
        await safe_send_message(context.bot, update.effective_chat.id, resultado, parse_mode=ParseMode.HTML)


    else:
        await update.message.reply_text("⚠️ No se encontró información para mostrar.", parse_mode=ParseMode.HTML)

async def agenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Agenda mañana")
    resultado = await generar_resumen_manana()
    if resultado and resultado.strip():
        await safe_send_message(context.bot, update.effective_chat.id, resultado, parse_mode=ParseMode.HTML)


    else:
        await update.message.reply_text("⚠️ No se encontró información para mostrar.", parse_mode=ParseMode.HTML)

async def agendaPlanAdmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Agenda PL ADmin")
    resultado = await AgendaPlAdmin()
    await safe_send_message(context.bot, update.effective_chat.id, resultado, parse_mode=ParseMode.HTML)

async def agendaSemProxima(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Agenda semana próxima")
    resultado = await AgendaPlAdminSemanaSiguiente()
    await safe_send_message(context.bot, update.effective_chat.id, resultado, parse_mode=ParseMode.HTML)

async def maybe_await(job_func, context=None):
    """
    Garantiza un awaitable:
    - Si job_func es coroutinefunction, lo await directamente (con sus parámetros).
    - Si es sync, lo ejecuta en executor (para no bloquear event loop).
    """
    sig = inspect.signature(job_func)
    num_params = len(sig.parameters)

    # función auxiliar que ejecuta sync functions
    def run_sync():
        if num_params == 0:
            return job_func()
        elif num_params == 1:
            return job_func(context)
        else:
            return job_func(context, None)

    if inspect.iscoroutinefunction(job_func):
        if num_params == 0:
            return await job_func()
        elif num_params == 1:
            return await job_func(context)
        else:
            return await job_func(context, None)
    else:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, run_sync)


def default_job_logger(message: str):
    # pequeña util para timestamp en prints
    print(f"[JOB] {_time.strftime('%Y-%m-%d %H:%M:%S')} - {message}", flush=True)


#------------------------- SET HORARIOS ----------------------



SET_TAREA, SET_HORA = range(2)

# Mapeo alias -> variables
MAP_TAREAS = {
    "DayIN": "hora_dayin",
    "Comentarios RD": "hora_rd",
    "Burn1": "hora_burn1",
    "Burn2": "hora_burn2",
    "Burn3": "hora_burn3",
    "Burn4": "hora_burn4",
    "Agenda Pre": "hora_agenda_pre",
    "Agenda": "hora_agenda",
    "DayOUT": "hora_dayout",
    "NewDay": "hora_newday",
}

async def sethorario_start(update, context):
    tareas = []
    for nombre, var_name in MAP_TAREAS.items():
        hora_actual = getattr(Horarios, var_name)
        # Convertimos a minutos para poder ordenar
        minutos = hora_actual.hour * 60 + hora_actual.minute
        tareas.append((minutos, nombre, var_name, hora_actual))

    # Ordenamos por minutos
    tareas.sort(key=lambda x: x[0])

    # Creamos el teclado solo con la lista ordenada
    keyboard = [
        [InlineKeyboardButton(f"{nombre} ({hora_actual.strftime('%H:%M')})", callback_data=var_name)]
        for _, nombre, var_name, hora_actual in tareas
    ]

    reply_markup = InlineKeyboardMarkup(keyboard, row_width=1)
    texto = "🕑 Seleccioná la tarea que querés modificar:"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(texto, reply_markup=reply_markup)
    else:
        await update.message.reply_text(texto, reply_markup=reply_markup)

    return SET_TAREA





async def elegir_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tarea = query.data
    logger.info(f"Tarea seleccionada: {tarea}")
    if tarea not in TAREAS_MAP:
        logger.warning(f"Tarea inválida: {tarea}")
        await query.message.edit_text(
            "⚠️ Tarea inválida. Por favor, inicia de nuevo con /sethorario."
        )
        return ConversationHandler.END

    context.user_data["tarea"] = tarea
    context.user_data["tarea_var"] = TAREAS_MAP[tarea]

    await query.message.edit_text(
        f"⏰ Elegiste <b>{tarea}</b>.\n\nIngresá la nueva hora en formato HH:MM (ej: 07:30)",
        parse_mode="HTML"
    )
    return SET_HORA


async def setear_hora(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe la hora, actualiza Horarios.py y reprograma el job"""
    hora_str = update.message.text.strip()
    if not re.match(r"^\d{2}:\d{2}$", hora_str):
        await update.message.reply_text("⚠️ Formato inválido. Usá HH:MM (ej: 08:45)")
        return SET_HORA

    hh, mm = map(int, hora_str.split(":"))
    nueva_hora = time(hour=hh, minute=mm, tzinfo=Config.ARG_TZ)

    var_name = context.user_data["tarea_var"]

    # === Actualizar Horarios.py ===
    with open("Horarios.py", "r", encoding="utf-8") as f:
        lines = f.readlines()
    with open("Horarios.py", "w", encoding="utf-8") as f:
        for line in lines:
            if line.strip().startswith(f"{var_name} = time("):
                f.write(f"{var_name} = time(hour={hh}, minute={mm}, tzinfo=Config.ARG_TZ)\n")
            else:
                f.write(line)

    setattr(Horarios, var_name, nueva_hora)

    # Eliminar job viejo
    jobs = context.job_queue.get_jobs_by_name(var_name)
    for job in jobs:
        job.schedule_removal()

    # Reagendar job
    job_map = {
        "hora_dayin": job_dayin,
        "hora_rd": job_rd,
        "hora_burn1": job_burn,
        "hora_burn2": job_burn,
        "hora_burn3": job_burn,
        "hora_burn4": job_burn,
        "hora_agenda_pre": job_agenda_preliminar,
        "hora_agenda": job_agenda_automatica,
        "hora_dayout": job_dayout,
        "hora_newday": job_newday,
    }


    job_func = job_map[var_name]

    await update.message.reply_text(
        f"✅ Horario de <b>{var_name}</b> actualizado a {hora_str}",
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END


async def cancelar_sethorario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Configuración cancelada.")
    return ConversationHandler.END



#------------------------- FIN SET HORARIOS ----------------------

def next_valid_run(job_time: time, days=(0,1,2,3,4)):
    """Devuelve el próximo datetime válido para un job según horario y días hábiles."""
    now = datetime.now(TZ)
    job_dt = datetime.combine(now.date(), job_time, TZ)

    # Si la hora ya pasó, pasamos al día siguiente
    if job_dt <= now:
        job_dt += timedelta(days=1)

    # Avanzar hasta que caiga en un día válido
    while job_dt.weekday() not in days:
        job_dt += timedelta(days=1)

    return job_dt


def schedule_daily_job(app, job_func, job_time, days=(0, 1, 2, 3, 4), job_name="Job", grace_period=600):
    """Agrega un job diario robusto (solo lunes-viernes, respeta hora y TZ)."""
    if job_time.tzinfo is None:
        job_time = job_time.replace(tzinfo=TZ)
        print(f"⚠️ [DEBUG] job_time '{job_name}' no tenía tzinfo, se asignó {TZ}")

    async def job_wrapper(ctx):
        try:
            await safe_job_runner(ctx, job_func, job_name, grace_period)
        except Exception as e:
            print(f"❌ Excepción no capturada en job_wrapper '{job_name}': {e}")

    # Eliminar previos
    for j in app.job_queue.get_jobs_by_name(job_name):
        print(f"🧹 Eliminando job existente con nombre {job_name}")
        j.schedule_removal()

    if isinstance(job_time, datetime):
        # ya es datetime con o sin tz
        if job_time.tzinfo is None:
            job_time = job_time.replace(tzinfo=Config.ARG_TZ)
        else:
            job_time = job_time.astimezone(Config.ARG_TZ)
    elif isinstance(job_time, time):
        # es un time plano
        if job_time.tzinfo is None:
            job_time = job_time.replace(tzinfo=Config.ARG_TZ)
    else:
        raise TypeError(f"job_time debe ser datetime o time, no {type(job_time)}")



    # Calcular próximo run correcto
    next_run = next_valid_run(job_time, days)

    # Crear el job (run_daily usa hora, pero forzamos initial datetime)
    app.job_queue.run_repeating(
        job_wrapper,
        interval=timedelta(days=1),
        first=next_run,
        name=job_name
    )

    print(f"📋 {next_run.strftime('%A %d/%m/%Y |%H:%M:%S|')} → {job_name}")





async def debug_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {datetime.now(TZ).strftime('%d/%m/%y %H:%M')} - Mostrar Jobs programados ")
    jobs = context.job_queue.jobs()
    if not jobs:
        msg = "⛔ No hay jobs programados en el JobQueue."
    else:
        ahora = datetime.now(TZ)
        hora_map = {
            "DayIN automático": Horarios.hora_dayin,
            "Comentarios RD": Horarios.hora_rd,
            "Primer burn del día": Horarios.hora_burn1,
            "Segundo burn del día": Horarios.hora_burn2,
            "Tercer burn del día": Horarios.hora_burn3,
            "Prelim. agenda mañana": Horarios.hora_agenda_pre,
            "Agenda de mañana": Horarios.hora_agenda,
            "Último burn del día": Horarios.hora_burn4,
            "DayOut automático": Horarios.hora_dayout,
            "Nuevos registros": Horarios.hora_newday,
            "Food reminder": Horarios.hora_food,
            "Rank reminder": Horarios.hora_rank,
            "Pay reminder": Horarios.hora_pay,
        }

        msg = f"⏰ Jobs programados (hoy)\n\n📅 {ahora.strftime('%d/%m/%y')}\n"

        entries = []
        for job in jobs:
            job_time = hora_map.get(job.name)
            if not job_time:
                continue
            
            job_dt_today = ahora.replace(hour=job_time.hour, minute=job_time.minute, second=0, microsecond=0)
            vencido = job_dt_today <= ahora
            entries.append((job_dt_today, job.name, job_time.strftime("%H:%M"), vencido))

        for _, name, timestr, vencido in sorted(entries, key=lambda x: x[0]):
            icon = "❌" if vencido else "✅"
            nombre_corto = name.replace("automático", "auto").replace("Primer burn del día", "Burn1") \
                              .replace("Segundo burn del día", "Burn2").replace("Tercer burn del día", "Burn3") \
                              .replace("Último burn del día", "Burn4").replace("Prelim. agenda mañana", "Agenda pre") \
                              .replace("Agenda de mañana", "Agenda")
            msg += f"{icon} {timestr} {nombre_corto}\n" 
            
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


TZ = ZoneInfo("America/Argentina/Buenos_Aires")

async def debug_jobs2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = context.job_queue.jobs()
    if not jobs:
        await update.message.reply_text("❌ No hay jobs activos.")
        return

    lines = ["🧾 *Jobs actualmente programados:*\n"]
    now = datetime.now(TZ)

    for job in jobs:
        # Algunos jobs aún no tienen next_run_time hasta que corre el loop
        next_run = getattr(job, "next_run_time", None)

        if next_run is None:
            estado = "⚪ Esperando inicialización"
            hora = "—"
        else:
            diff = (next_run - now).total_seconds()
            if diff < 0:
                estado = "🕓 Ya pasó hoy"
            elif diff < 3600:
                estado = "⏰ Próximo dentro de 1h"
            elif diff < 24 * 3600:
                estado = "🟢 Activo hoy"
            else:
                estado = "🟡 Próximo día"
            hora = next_run.strftime("%Y-%m-%d %H:%M:%S")

        lines.append(f"• *{job.name}* → `{hora}`  ({estado})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")



async def clear_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_queue = context.job_queue
    if job_queue is not None:
        jobs = job_queue.jobs()
        for job in jobs:
            job.schedule_removal()
            print(f"🗑️ Job '{job.name}' eliminado manualmente.\n")
        await update.message.reply_text("✅ JobQueue limpiado manualmente.", parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ JobQueue no inicializado.", parse_mode="HTML")





async def job_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    now = datetime.now().strftime("%H:%M:%S")
    await context.bot.send_message(job.chat_id, text=f"⏰ Job ejecutado a las {now}")

def ensure_windows_time_service_running():
    try:
        # Verificar estado del servicio
        result = subprocess.run(["sc", "query", "w32time"], capture_output=True, text=True)
        if "RUNNING" not in result.stdout:
            print("🕒 El servicio 'w32time' no está en ejecución. Intentando iniciarlo...")
            subprocess.run(["sc", "config", "w32time", "start=", "auto"], capture_output=True)
            subprocess.run(["net", "start", "w32time"], capture_output=True)
        else:
            print("🕒 El servicio 'w32time' ya está en ejecución.")
    except Exception as e:
        print(f"⚠️ Error al verificar/iniciar w32time: {e}")

    try:
        # Intentar sincronizar
        resync = subprocess.run(["w32tm", "/resync"], capture_output=True, text=True)
        if resync.returncode == 0:
            print("✅ Hora sincronizada correctamente con w32tm.")
        else:
            print(f"⚠️ 'w32tm /resync' falló ({resync.returncode}): {resync.stderr.strip()}")
    except Exception as e:
        print(f"⚠️ No se pudo ejecutar w32tm /resync: {e}")


async def safe_job_runner(ctx, job_func, job_name, grace_period=300):
    start_ts = _time.time()
    task = None
    try:
        print(f"[JOB] ▶ Ejecutando '{job_name}'...")
        task = asyncio.create_task(maybe_await(job_func, ctx))
        await asyncio.wait_for(task, timeout=grace_period)
        print(f"[JOB] ✔ '{job_name}' finalizado ({_time.time() - start_ts:.1f}s)")
    except asyncio.TimeoutError:
        print(f"[JOB] ⏱ Timeout en '{job_name}', cancelando tarea...")
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                print(f"[JOB] 🗑 Tarea '{job_name}' cancelada correctamente.")
            except Exception as e:
                print(f"[JOB] ⚠️ Excepción al cancelar tarea '{job_name}': {e}")
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[JOB] ❌ Error en '{job_name}': {e}\n{tb}")
        if ctx and getattr(ctx, "bot", None):
            try:
                await ctx.bot.send_message(chat_id=Config.ADMIN_CHAT_ID, text=f"❌ Error en job '{job_name}': {e}")
            except Exception:
                pass
    finally:
        print(f"[JOB] ⏹ '{job_name}' terminado.\n", flush=True)


async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    thread_id = update.message.message_thread_id  # Puede ser None si no estás en un topic

    if thread_id is not None:
        await update.message.reply_text(
            f"📌 El ID de este chat es: {chat_id}\n"
            f"🧵 El THREAD_ID es: {thread_id}"
        )
    else:
        await update.message.reply_text(
            f"📌 El ID de este chat es: {chat_id}\n"
            f"🧵 Este mensaje no está dentro de un thread."
        )

def skip_if_feriado(job_func):
    @wraps(job_func)
    async def wrapper(context):
        hoy = datetime.now(Config.ARG_TZ).date()

        if hoy in Config.FERIADOS:
            print(f"⛔ {job_func.__name__} NO ejecutado ({hoy} feriado)")
            return

        await job_func(context)

    return wrapper

async def ping(update, context):
    await update.message.reply_text("🏓 pong")

if __name__ == "__main__":
    print("🚀 Iniciando ZzRun247v5.2.py ...")

    ensure_windows_time_service_running()
    set_system_timezone()
    sync_system_time()

    app = Application.builder().token(Config.TELEGRAM_TOKEN).build()
    app.add_error_handler(error_handler)

    # Configurar handlers
    app.add_handler(conv_equipos)
    app.add_handler(conv_torneo)
    app.add_handler(conv_dayin)
    app.add_handler(conv_dayout)
    app.add_handler(conv_dayout_test)
    app.add_handler(conv_sethorario)
    app.add_handler(conv_setmp)
    app.add_handler(CommandHandler("debugjobs", wrap_handler(debug_jobs)))
    app.add_handler(CommandHandler("next", wrap_handler(debug_jobs2)))
    app.add_handler(CommandHandler("clearjobs", wrap_handler(clear_jobs)))
    app.add_handler(CommandHandler("medal", wrap_handler(medal)))
    app.add_handler(CommandHandler("rank", wrap_handler(rank)))
    app.add_handler(CommandHandler("epic", wrap_handler(epicas)))
    # app.add_handler(CommandHandler("elo", wrap_handler(elo)))
    app.add_handler(CommandHandler("hoy", wrap_handler(hoy)))
    app.add_handler(CommandHandler("agenda", wrap_handler(agenda)))
    app.add_handler(CommandHandler("agendapladmin", wrap_handler(agendaPlanAdmin)))
    app.add_handler(CommandHandler("agendasemprox", wrap_handler(agendaSemProxima)))
    app.add_handler(CommandHandler("rd", wrap_handler(rd)))
    app.add_handler(CommandHandler("rd2", wrap_handler(rd2)))
    app.add_handler(confirmar_handler("burn", burn))
    app.add_handler(confirmar_handler("newday", newburnreg))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generic_message))

    app.add_handler(CommandHandler("mp", mostrar_menu))
    app.add_handler(CommandHandler("curvas", wrap_handler(curva_parcial)))
    app.add_handler(CommandHandler("curva_huemul", wrap_handler(curva_parcial_huemul)))
    app.add_handler(CommandHandler("curva_caiman", wrap_handler(curva_parcial_caiman)))
    app.add_handler(CommandHandler("curva_zorro", wrap_handler(curva_parcial_zorro)))
    app.add_handler(MessageHandler(filters.Document.PDF, manejar_pdf))

    app.add_handler(CommandHandler("ChatID", chatid))

    app.add_handler(CommandHandler("ping", ping))

    # Programar todos los jobs
    jobs_to_schedule = [
        (skip_if_feriado(job_dayin), Horarios.hora_dayin, "DayIN automático"),
        (skip_if_feriado(job_rd), Horarios.hora_rd, "Comentarios RD"),
        (skip_if_feriado(job_burn), Horarios.hora_burn1, "Primer burn del día"),
        (skip_if_feriado(job_burn), Horarios.hora_burn2, "Segundo burn del día"),
        (skip_if_feriado(job_burn), Horarios.hora_burn3, "Tercer burn del día"),
        (skip_if_feriado(job_agenda_preliminar), Horarios.hora_agenda_pre, "Prelim. agenda mañana"),
        (skip_if_feriado(job_agenda_automatica), Horarios.hora_agenda, "Agenda de mañana"),
        (skip_if_feriado(job_agenda_semana_prox), Horarios.hora_agenda_sem, "Agenda semana prox"),     
        (skip_if_feriado(job_burn), Horarios.hora_burn4, "Último burn del día"),
        (skip_if_feriado(job_dayout), Horarios.hora_dayout, "DayOut automático"),
        (skip_if_feriado(job_newday), Horarios.hora_newday, "Nuevos registros"),
        (skip_if_feriado(job_food), Horarios.hora_food, "Food reminder"),
        # (job_rank, Horarios.hora_rank, "Rank reminder"),
        (skip_if_feriado(job_pay), Horarios.hora_pay, "Pay reminder"),
    ]

    app.job_queue.set_application(app)  

    for job_func, job_time, job_name in jobs_to_schedule:

        # Caso: NO correr estos los viernes
        if job_func in (job_agenda_preliminar, job_agenda_automatica):
            schedule_daily_job(app, job_func, job_time, days=(0, 1, 2, 3), job_name=job_name)
            continue

        # Caso general: todos los jobs que sí deben correr de lunes a viernes
        schedule_daily_job(app, job_func, job_time, days=(0, 1, 2, 3, 4), job_name=job_name)

    # Nuevo job especial para viernes
    schedule_daily_job(
        app,
        job_agenda_semana_prox,
        Horarios.hora_agenda,  # o la hora que quieras
        days=(4,),             # Solo viernes
        job_name="Agenda semana próxima"
    )


    jobs = app.job_queue.jobs

    app.job_queue.run_daily(
        job_restart,
        time(hour=3, minute=30, tzinfo=Config.ARG_TZ),
        name="Reinicio diario"
    )

    print(f"🤖 Bot corriendo... Hora actual: {datetime.now(TZ).strftime('%H:%M:%S')} ({TZ})")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        )

    print(f"🧾 Jobs en JobQueue al finalizar schedule: {len(jobs)}")
    for j in jobs:
        print(f" - job.name={j.name}, next_run={getattr(j, 'next_t', 'unknown')}")

