# ==========================================
# 1. IMPORTS
# ==========================================

# Módulos Locales
import Config
import Horarios
from modules.CurvaParcial import generar_curva_parcial, generar_curva_parcial_equipo
from modules.Agenda import generar_resumen_manana
from modules.AgendaHoy import agendahoy
from modules.AgendaPlAdmin import AgendaPlAdmin
from modules.AgendaSemProx import AgendaPlAdminSemanaSiguiente
from modules.RDs import RDs_comments
from modules.Burn import burndown, newday, listar_planes
from modules.SiemensCheck import parsear_oferta_robusto, exportar_excel, parsear_briket
from modules.mundopizza.menump import (
    mostrar_menu, setmp_start, elegir_item, elegir_precio, cancelar_setmp, 
    ELEGIR_ITEM, ELEGIR_PRECIO
)
from modules.sethorario import conv_sethorario, TAREAS_MAP
from modules.jobs import (
    job_dayin, job_rd, job_burn, job_agenda_preliminar, job_agenda_automatica,
    job_agenda_semana_prox, job_dayout, job_newday, job_food, job_pay
)

from modules.handlers import (
    conv_dayin, conv_dayout, conv_dayout_test,
    wrap_handler, confirmar_handler, generic_message, cancelar
)


# ==========================================
# 2. CONFIGURACIÓN Y CONSTANTES
# ==========================================

# Logging
Config.warnings.filterwarnings("ignore", message="If 'per_message=False'", category=UserWarning)
Config.warnings.filterwarnings("ignore", category=UserWarning, module="telegram")
Config.logging.basicConfig(level=Config.logging.INFO)
logger = Config.logging.getLogger(__name__)

# Timezone
TZ = Config.ZoneInfo("America/Argentina/Buenos_Aires")
ahora = Config.datetime.now(TZ)

# Global States
ELEGIR_ITEM, ELEGIR_PRECIO = range(2)
SET_TAREA, SET_HORA = range(2)
PENDIENTES = {}


# ==========================================
# 3. UTILIDADES DE SISTEMA Y TIEMPO
# ==========================================

def run_as_admin():
    try:
        if not Config.ctypes.windll.shell32.IsUserAnAdmin():
            Config.ctypes.windll.shell32.ShellExecuteW(None, "runas", Config.sys.executable, " ".join(Config.sys.argv), None, 1)
            Config.sys.exit()
    except Exception as e:
        print(f"⚠️ run_as_admin fallo: {e}")

def ensure_windows_time_service_running():
    try:
        result = Config.subprocess.run(["sc", "query", "w32time"], capture_output=True, text=True)
        if "RUNNING" not in result.stdout:
            print("🕒 Iniciando servicio 'w32time'...")
            Config.subprocess.run(["sc", "config", "w32time", "start=", "auto"], capture_output=True)
            Config.subprocess.run(["net", "start", "w32time"], capture_output=True)
    except Exception as e:
        print(f"⚠️ Error al verificar w32time: {e}")

def sync_system_time():
    try:
        Config.subprocess.run(['w32tm', '/resync'], check=True, capture_output=True, text=True)
        print("✅ Hora sincronizada via w32tm.")
    except Exception:
        try:
            client = Config.ntplib.NTPClient()
            resp = client.request("pool.ntp.org", timeout=5)
            ntp_time = Config.datetime.fromtimestamp(resp.tx_time, tz=Config.timezone.utc).astimezone(TZ)
            print(f"[DEBUG] NTP: {ntp_time}")
        except Exception as e2:
            print(f"❌ Fallback NTP failed: {e2}")

def tzutil_get_zone():
    try:
        result = Config.subprocess.run(['tzutil', '/g'], capture_output=True, text=True, check=True)
        windows_tz = result.stdout.strip()
        tz_map = {"Argentina Standard Time": "America/Argentina/Buenos_Aires",}
        return tz_map.get(windows_tz, windows_tz)
    except Config.subprocess.CalledProcessError:
        return "Unknown"

def set_system_timezone():
    """Set the system timezone to Argentina Standard Time."""
    desired_tz = "Argentina Standard Time"
    try:
        Config.subprocess.run(['tzutil', '/s', desired_tz], check=True)
        print(f"✅ System timezone set to {desired_tz}")
    except Config.subprocess.CalledProcessError as e:
        print(f"❌ Error setting system timezone: {e}")

def skip_if_feriado(job_func):
    @Config.wraps(job_func)
    async def wrapper(context):
        hoy = Config.datetime.now(Config.ARG_TZ).date()

        if hoy in Config.FERIADOS:
            print(f"⛔ {job_func.__name__} NO ejecutado ({hoy} feriado)")
            return

        await job_func(context)

    return wrapper

def ensure_windows_time_service_running():
    try:
        result = Config.subprocess.run(["sc", "query", "w32time"], capture_output=True, text=True)
        if "RUNNING" not in result.stdout:
            print("🕒 El servicio 'w32time' no está en ejecución. Intentando iniciarlo...")
            Config.subprocess.run(["sc", "config", "w32time", "start=", "auto"], capture_output=True)
            Config.subprocess.run(["net", "start", "w32time"], capture_output=True)
        else:
            print("🕒 El servicio 'w32time' ya está en ejecución.")
    except Exception as e:
        print(f"⚠️ Error al verificar/iniciar w32time: {e}")

    try:
        resync = Config.subprocess.run(["w32tm", "/resync"], capture_output=True, text=True)
        if resync.returncode == 0:
            print("✅ Hora sincronizada correctamente con w32tm.")
        else:
            print(f"⚠️ 'w32tm /resync' falló ({resync.returncode}): {resync.stderr.strip()}")
    except Exception as e:
        print(f"⚠️ No se pudo ejecutar w32tm /resync: {e}")

# Ejecución inmediata de permisos
run_as_admin()


# ==========================================
# 4. FUNCIONES AUXILIARES DE LÓGICA
# ==========================================

def normalizar_ausente(nombre: str) -> str:
    nombre = nombre.strip()
    if not nombre: return ""
    for alias in Config.ALIAS_PERSONAS.values():
        if nombre.upper() == alias.upper(): return alias.upper()
    for completo, alias in Config.ALIAS_PERSONAS.items():
        if nombre.lower() == completo.lower(): return alias.upper()
    return nombre.upper()

def convertir_elo_a_alias(elo_dict: dict) -> dict:
    return {Config.ALIAS_PERSONAS.get(j, j): r for j, r in elo_dict.items()}

def filtrar_disponibles(jugadores_elo: dict, ausentes: list) -> dict:
    ausentes_set = set(a.upper() for a in ausentes)
    return {j: e for j, e in jugadores_elo.items() if j.upper() not in ausentes_set}

async def maybe_await(job_func, context=None):
    sig = Config.inspect.signature(job_func)
    num_params = len(sig.parameters)
    
    def run_sync():
        if num_params == 0: return job_func()
        if num_params == 1: return job_func(context)
        return job_func(context, None)

    if Config.inspect.iscoroutinefunction(job_func):
        if num_params == 0: return await job_func()
        if num_params == 1: return await job_func(context)
        return await job_func(context, None)
    
    return await Config.asyncio.get_running_loop().run_in_executor(None, run_sync)


# ==========================================
# 5. HANDLERS DE MENSAJERÍA Y TELEGRAM
# ==========================================

async def safe_send_message(bot, chat_id, text, parse_mode=Config.ParseMode.HTML, **kwargs):
    MAX_LEN = 4000
    start = 0
    while start < len(text):
        end = start + MAX_LEN
        if end < len(text):
            newline_pos = text.rfind("\n", start, end)
            if newline_pos != -1: end = newline_pos + 1
        
        msg_chunk = text[start:end]
        while True:
            try:
                return await bot.send_message(chat_id, msg_chunk, parse_mode=parse_mode, **kwargs)
            except Config.RetryAfter as e:
                await Config.asyncio.sleep(e.retry_after)
        start = end

async def send_long_message(bot, chat_id, text, parse_mode="HTML", **kwargs):
    # Alias de compatibilidad
    await safe_send_message(bot, chat_id, text, parse_mode, **kwargs)

async def error_handler(update, context):
    err = context.error
    if isinstance(err, (Config.NetworkError, Config.TimedOut)):
        print("⚠️ Error de red con Telegram.")
        return
    print("❌ Error no controlado:", err)


# ==========================================
# 6. FUNCIONALIDADES DEL BOT (COMANDOS)
# ==========================================

async def manejar_pdf(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    pdf_path = "entrada.pdf"
    try:
        archivo = update.message.document
        if not archivo: return
        file = await archivo.get_file()
        await file.download_to_drive(pdf_path)

        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            texto = "\n".join([p.extract_text() or "" for p in pdf.pages])
        if "ARQ" in texto:
            items = parsear_oferta_robusto(pdf_path)
            nombre = Config.re.search(r"ARQ\d+", texto).group(0)
            excel_path = f"Oferta_Siemens_{nombre}.xlsx"
        elif "BRIKET S.A." in texto:
            items = parsear_briket(pdf_path)
            excel_path = f"OC_Briket_{Config.os.path.splitext(archivo.file_name)[0]}.xlsx"
        else:
            await update.message.reply_text("❌ No reconozco el tipo de PDF.")
            return
        exportar_excel(items, excel_path)
        with open(excel_path, "rb") as f:
            await update.message.reply_document(f)
    except Exception as e:
        logger.exception("Error en manejar_pdf")
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        if Config.os.path.exists(pdf_path): Config.os.remove(pdf_path)

async def curva_parcial(update, context):
    await update.message.reply_text("📈 Generando curvas...")
    buf = await generar_curva_parcial()
    await context.bot.send_photo(update.effective_chat.id, photo=Config.InputFile(buf, "curva.png"), caption="📊 Burndown actual")

async def burn(update, context):
    await update.message.reply_text("⚡ Ejecutando Burndown...")
    await burndown()
    await update.message.reply_text("✔️ Procesado.")

async def hoy(update, context):
    resultado = await agendahoy()
    if resultado: await safe_send_message(context.bot, update.effective_chat.id, resultado)
    else: await update.message.reply_text("⚠️ Nada hoy.")

# ==========================================
# 7. GESTIÓN DE JOBS Y HORARIOS
# ==========================================

def next_valid_run(job_time: Config.time, days=(0,1,2,3,4)):
    now = Config.datetime.now(TZ)
    job_dt = Config.datetime.combine(now.date(), job_time, TZ)
    if job_dt <= now: job_dt += Config.timedelta(days=1)
    while job_dt.weekday() not in days:
        job_dt += Config.timedelta(days=1)
    return job_dt

async def safe_job_runner(ctx, job_func, job_name, grace_period=300):
    start_ts = Config._time.time()
    task = None
    try:
        print(f"[JOB] ▶ Ejecutando '{job_name}'...")
        task = Config.asyncio.create_task(maybe_await(job_func, ctx))
        await Config.asyncio.wait_for(task, timeout=grace_period)
        print(f"[JOB] ✔ '{job_name}' finalizado ({Config._time.time() - start_ts:.1f}s)")
    except Config.asyncio.TimeoutError:
        print(f"[JOB] ⏱ Timeout en '{job_name}', cancelando tarea...")
        if task:
            task.cancel()
            try:
                await task
            except Config.asyncio.CancelledError:
                print(f"[JOB] 🗑 Tarea '{job_name}' cancelada correctamente.")
            except Exception as e:
                print(f"[JOB] ⚠️ Excepción al cancelar tarea '{job_name}': {e}")
    except Exception as e:
        tb = Config.traceback.format_exc()
        print(f"[JOB] ❌ Error en '{job_name}': {e}\n{tb}")
        if ctx and getattr(ctx, "bot", None):
            try:
                await ctx.bot.send_message(chat_id=Config.ADMIN_CHAT_ID, text=f"❌ Error en job '{job_name}': {e}")
            except Exception:
                pass
    finally:
        print(f"[JOB] ⏹ '{job_name}' terminado.\n", flush=True)

async def clear_jobs(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    job_queue = context.job_queue
    if job_queue is not None:
        jobs = job_queue.jobs()
        for job in jobs:
            job.schedule_removal()
            print(f"🗑️ Job '{job.name}' eliminado manualmente.\n")
        await update.message.reply_text("✅ JobQueue limpiado manualmente.", parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ JobQueue no inicializado.", parse_mode="HTML")

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

    if isinstance(job_time, Config.datetime):
        # ya es datetime con o sin tz
        if job_time.tzinfo is None:
            job_time = job_time.replace(tzinfo=Config.ARG_TZ)
        else:
            job_time = job_time.astimezone(Config.ARG_TZ)
    elif isinstance(job_time, Config.time):
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
        interval=Config.timedelta(days=1),
        first=next_run,
        name=job_name
    )

    print(f"📋 {next_run.strftime('%A %d/%m/%Y |%H:%M:%S|')} → {job_name}")

async def job_restart(context: Config.ContextTypes.DEFAULT_TYPE):
    print("♻️ Reiniciando bot automáticamente...")
    await Config.asyncio.sleep(2)
    Config.os.execv(Config.sys.executable, ['python'] + Config.sys.argv)


# ==========================================
# 8. CONVERSATION HANDLERS
# ==========================================

conv_setmp = Config.ConversationHandler(
    entry_points=[Config.CommandHandler("setmp", setmp_start)],
    states={
        ELEGIR_ITEM: [Config.CallbackQueryHandler(elegir_item)],
        ELEGIR_PRECIO: [Config.MessageHandler(Config.filters.TEXT & ~Config.filters.COMMAND, elegir_precio)],
    },
    fallbacks=[Config.CommandHandler("cancelar", cancelar_setmp)],
)


# ==========================================
# 9. COMANDOS
# ==========================================

# Estados para el Config.ConversationHandler
ELEGIR_ITEM, ELEGIR_PRECIO = range(2)
PENDIENTES = {}  # guarda acciones pendientes por usuario


async def curva_parcial_huemul(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(f"📈 Generando curva de burndown Huemul")

    buf = await generar_curva_parcial_equipo("Huemules")
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=Config.InputFile(buf, filename="curva_diferencia.png"),
        caption=f"📊 Burndown Huemul actual"
    )

async def curva_parcial_caiman(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(f"📈 Generando curva de burndown Caimán")

    buf = await generar_curva_parcial_equipo("Caimanes")
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=Config.InputFile(buf, filename="curva_diferencia.png"),
        caption=f"📊 Burndown Caimám actual"
    )

async def curva_parcial_zorro(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(f"📈 Generando curva de burndown Zorro")

    buf = await generar_curva_parcial_equipo("Zorros")
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=Config.InputFile(buf, filename="curva_diferencia.png"),
        caption=f"📊 Burndown Zorro actual"
    )

async def newburnreg(update: Config.pdate, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Newday manual")
    await update.message.reply_text("⚡ Ejecutando tarea...", parse_mode="HTML")
    await newday()
    await update.message.reply_text("✔️ Nuevos registros de Burndown creados en Notion", parse_mode=Config.ParseMode.HTML)

async def rd(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  RD manual")
    resultado = await RDs_comments(concatenado=True)
    await update.message.reply_text(resultado, parse_mode=Config.ParseMode.HTML)

async def rd2(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  RD manual")
    try:
        # Ejecutamos exactamente lo mismo que el Job programado
        await maybe_await(job_rd, context)

        await update.message.reply_text(
            "✅ Job RD ejecutado manualmente.",
            parse_mode=Config.ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Error al ejecutar job_rd manual: {e}",
            parse_mode=Config.ParseMode.HTML
        )

async def epicas(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Épicas")
    try:
        # Obtener el mensaje de listar_planes (ya devuelve HTML seguro)
        msg = await listar_planes()
        
        # No escapar todo el HTML, solo usarlo tal cual
        await safe_send_message(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            text=msg,
            parse_mode=Config.ParseMode.HTML
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
    return Config.ConversationHandler.END

async def agenda(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Agenda mañana")
    resultado = await generar_resumen_manana()
    if resultado and resultado.strip():
        await safe_send_message(context.bot, update.effective_chat.id, resultado, parse_mode=Config.ParseMode.HTML)
    else:
        await update.message.reply_text("⚠️ No se encontró información para mostrar.", parse_mode=Config.ParseMode.HTML)

async def agendaPlanAdmin(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Agenda PL ADmin")
    resultado = await AgendaPlAdmin()
    await safe_send_message(context.bot, update.effective_chat.id, resultado, parse_mode=Config.ParseMode.HTML)

async def agendaSemProxima(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  Agenda semana próxima")
    resultado = await AgendaPlAdminSemanaSiguiente()
    await safe_send_message(context.bot, update.effective_chat.id, resultado, parse_mode=Config.ParseMode.HTML)

async def debug_jobs(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(TZ).strftime('%d/%m/%y %H:%M')} - Mostrar Jobs programados ")
    jobs = context.job_queue.jobs()
    if not jobs:
        msg = "⛔ No hay jobs programados en el JobQueue."
    else:
        ahora = Config.datetime.now(TZ)
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
        await update.callback_query.edit_message_text(msg, parse_mode=Config.ParseMode.HTML)
    else:
        await update.message.reply_text(msg, parse_mode=Config.ParseMode.HTML)

async def debug_jobs2(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    jobs = context.job_queue.jobs()
    if not jobs:
        await update.message.reply_text("❌ No hay jobs activos.")
        return

    lines = ["🧾 *Jobs actualmente programados:*\n"]
    now = Config.datetime.now(TZ)

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

async def chatid(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
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

async def ping(update, context):
    await update.message.reply_text("🏓 pong")

# ==========================================
# MENÚ SET HORARIOS
# ==========================================

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
        minutos = hora_actual.hour * 60 + hora_actual.minute
        tareas.append((minutos, nombre, var_name, hora_actual))
    tareas.sort(key=lambda x: x[0])
    keyboard = [
        [Config.InlineKeyboardButton(f"{nombre} ({hora_actual.strftime('%H:%M')})", callback_data=var_name)]
        for _, nombre, var_name, hora_actual in tareas
    ]
    reply_markup = Config.InlineKeyboardMarkup(keyboard, row_width=1)
    texto = "🕑 Seleccioná la tarea que querés modificar:"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(texto, reply_markup=reply_markup)
    else:
        await update.message.reply_text(texto, reply_markup=reply_markup)
    return SET_TAREA

async def elegir_tarea(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tarea = query.data
    logger.info(f"Tarea seleccionada: {tarea}")
    if tarea not in TAREAS_MAP:
        logger.warning(f"Tarea inválida: {tarea}")
        await query.message.edit_text(
            "⚠️ Tarea inválida. Por favor, inicia de nuevo con /sethorario."
        )
        return Config.ConversationHandler.END
    context.user_data["tarea"] = tarea
    context.user_data["tarea_var"] = TAREAS_MAP[tarea]

    await query.message.edit_text(
        f"⏰ Elegiste <b>{tarea}</b>.\n\nIngresá la nueva hora en formato HH:MM (ej: 07:30)",
        parse_mode="HTML"
    )
    return SET_HORA

async def setear_hora(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    """Recibe la hora, actualiza Horarios.py y reprograma el job"""
    hora_str = update.message.text.strip()
    if not Config.re.match(r"^\d{2}:\d{2}$", hora_str):
        await update.message.reply_text("⚠️ Formato inválido. Usá HH:MM (ej: 08:45)")
        return SET_HORA

    hh, mm = map(int, hora_str.split(":"))
    nueva_hora = Config.time(hour=hh, minute=mm, tzinfo=Config.ARG_TZ)
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
        parse_mode=Config.ParseMode.HTML
    )
    return Config.ConversationHandler.END

async def cancelar_sethorario(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Configuración cancelada.")
    return Config.ConversationHandler.END


# ==========================================
# 10. INICIALIZACIÓN Y MAIN
# ==========================================

if __name__ == "__main__":
    print("🚀 Iniciando ZzRun247v5.2.py ...")

    ensure_windows_time_service_running()
    set_system_timezone()
    sync_system_time()

    app = Config.Application.builder().token(Config.TELEGRAM_TOKEN).build()
   
    # Configurar handlers
    app.add_handler(conv_dayin)
    app.add_handler(conv_dayout)
    app.add_handler(conv_dayout_test)
    app.add_handler(conv_sethorario)
    app.add_handler(conv_setmp)
    
    # Comandos con Wrap general "Ejecutando tarea"
    app.add_handler(Config.CommandHandler("debugjobs", wrap_handler(debug_jobs)))
    app.add_handler(Config.CommandHandler("next", wrap_handler(debug_jobs2)))
    app.add_handler(Config.CommandHandler("clearjobs", wrap_handler(clear_jobs)))
    app.add_handler(Config.CommandHandler("epic", wrap_handler(epicas)))
    app.add_handler(Config.CommandHandler("hoy", wrap_handler(hoy)))
    app.add_handler(Config.CommandHandler("agenda", wrap_handler(agenda)))
    app.add_handler(Config.CommandHandler("agendapladmin", wrap_handler(agendaPlanAdmin)))
    app.add_handler(Config.CommandHandler("agendasemprox", wrap_handler(agendaSemProxima)))
    app.add_handler(Config.CommandHandler("rd", wrap_handler(rd)))
    app.add_handler(Config.CommandHandler("rd2", wrap_handler(rd2)))
    
    # Comandos críticos, con pedido de confirmación 
    app.add_handler(confirmar_handler("burn", burn))
    app.add_handler(confirmar_handler("newday", newburnreg))
    
    # Comandos cortos, sin "Ejecutando tarea"
    app.add_handler(Config.CommandHandler("mp", mostrar_menu))
    app.add_handler(Config.CommandHandler("ChatID", chatid))
    app.add_handler(Config.CommandHandler("ping", ping))

    # Comandos cortos, con Wrap propio
    app.add_handler(Config.CommandHandler("curvas", curva_parcial))
    app.add_handler(Config.CommandHandler("curva_huemul", curva_parcial_huemul))
    app.add_handler(Config.CommandHandler("curva_caiman", curva_parcial_caiman))
    app.add_handler(Config.CommandHandler("curva_zorro", curva_parcial_zorro))
    
    app.add_handler(Config.MessageHandler(Config.filters.Document.PDF, manejar_pdf))

    #app.add_error_handler(error_handler)
    app.add_handler(Config.MessageHandler(Config.filters.TEXT & ~Config.filters.COMMAND, generic_message))

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
        Config.time(hour=3, minute=30, tzinfo=Config.ARG_TZ),
        name="Reinicio diario"
    )

    print(f"🤖 Bot corriendo... Hora actual: {Config.datetime.now(TZ).strftime('%H:%M:%S')} ({TZ})")
    app.run_polling(
        allowed_updates=Config.Update.ALL_TYPES,
        )

    print(f"🧾 Jobs en JobQueue al finalizar schedule: {len(jobs)}")
    for j in jobs:
        print(f" - job.name={j.name}, next_run={getattr(j, 'next_t', 'unknown')}")

