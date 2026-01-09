# ==========================================
# 1. IMPORTS
# ==========================================

# Módulos Locales
import Config
import Horarios
from modules.CurvaParcial import generar_curva_parcial, generar_curva_parcial_equipo
from modules.Agenda import conv_agenda, job_agenda_preliminar, job_agenda_automatica, job_agenda_preliminar_por_equipo, agenda_confirmacion_handler
from modules.DayOUT import conv_dayout, job_dayout
from modules.DayIN import conv_dayin, job_dayin
from modules.NewDay import newburnreg, job_newday
from modules.Resumen import resumen
from modules.RDs import RDs_comments
from modules.Burn import burn, job_burn
from modules.SiemensCheck import parsear_oferta_robusto, exportar_excel, parsear_briket
from modules.mundopizza.menump import conv_setmp, mostrar_menu, job_food, job_pay
from modules.sethorario import conv_sethorario
from modules.jobs import job_dayin
from modules.RDs import job_rd
from modules.Deploy import job_deploy, deploy_handler
from modules.Launch import launch_equipo, elegir_equipo
from modules.jobs import schedule_daily_job, debug_jobs, clear_jobs, job_restart
from modules.Utilities import conv_notion_id, conv_props, notion_users_start, message_teams
from modules.handlers import (wrap_handler, confirmar_handler, generic_message)
from modules.Calendar import deploy_calendar_handler

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


# ==========================================
# 4. HELPERS
# ==========================================




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
    try:
        buf = await generar_curva_parcial()
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return
    except Exception as e:
        await update.message.reply_text("❌ Error inesperado generando curva")
        raise
    await context.bot.send_photo(update.effective_chat.id, photo=Config.InputFile(buf, "curva.png"), caption="📊 Burndown actual")

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
    
async def rd(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  RD manual")
    resultado = await RDs_comments(concatenado=True)
    await update.message.reply_text(resultado, parse_mode=Config.ParseMode.HTML)

async def rd2(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(TZ).strftime('%d/%m/%y %H:%M')} -  RD manual")
    try:
        # Ejecutamos exactamente lo mismo que el Job programado
        await Config.maybe_await(job_rd, context)

        await update.message.reply_text(
            "✅ Job RD ejecutado manualmente.",
            parse_mode=Config.ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Error al ejecutar job_rd manual: {e}",
            parse_mode=Config.ParseMode.HTML
        )

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
# INICIALIZACIÓN Y MAIN
# ==========================================
run_as_admin()

if __name__ == "__main__":
    print("🚀 Iniciando NotionBot...")

    ensure_windows_time_service_running()
    set_system_timezone()
    sync_system_time()

    app = Config.Application.builder().token(Config.TELEGRAM_TOKEN).build()
   
    # Configurar handlers
    app.add_handler(conv_dayin)
    app.add_handler(conv_dayout)
    app.add_handler(conv_sethorario)
    app.add_handler(conv_setmp)
    app.add_handler(conv_agenda)
    app.add_handler(conv_notion_id)
    app.add_handler(conv_props)

    
    # Comandos con Wrap general "Ejecutando tarea"
    app.add_handler(Config.CommandHandler("debugjobs", wrap_handler(debug_jobs)))
    app.add_handler(Config.CommandHandler("clearjobs", wrap_handler(clear_jobs)))
    app.add_handler(Config.CommandHandler("rd", wrap_handler(rd)))
    app.add_handler(Config.CommandHandler("rd2", wrap_handler(rd2)))
    
    # Comandos críticos, con pedido de confirmación 
    app.add_handler(confirmar_handler("burn", burn))
    app.add_handler(confirmar_handler("deploy", deploy_handler))
    app.add_handler(confirmar_handler("newday", newburnreg))
    
    # Comandos cortos, sin "Ejecutando tarea"
    app.add_handler(Config.CommandHandler("mp", mostrar_menu))
    app.add_handler(Config.CommandHandler("ChatID", chatid))
    app.add_handler(Config.CommandHandler("ping", ping))
    app.add_handler(Config.CommandHandler("epic", resumen))
    app.add_handler(Config.CommandHandler("notion_users", notion_users_start))
    app.add_handler(    Config.CommandHandler("launch_equipo", elegir_equipo))
    app.add_handler(Config.CommandHandler("notificar_eq", message_teams))
    app.add_handler(Config.CallbackQueryHandler(launch_equipo,pattern=r"^launch_equipo:"))
    app.add_handler(Config.CommandHandler("calendar", deploy_calendar_handler))

    # Comandos cortos, con Wrap propio
    app.add_handler(Config.CommandHandler("curvas", curva_parcial))
    app.add_handler(Config.CommandHandler("curva_huemul", curva_parcial_huemul))
    app.add_handler(Config.CommandHandler("curva_caiman", curva_parcial_caiman))
    app.add_handler(Config.CommandHandler("curva_zorro", curva_parcial_zorro))
    
    app.add_handler(Config.MessageHandler(Config.filters.Document.PDF, manejar_pdf))

    #app.add_error_handler(error_handler)
    app.add_handler(Config.MessageHandler(Config.filters.TEXT & ~Config.filters.COMMAND, generic_message))
    app.add_handler(Config.CallbackQueryHandler(agenda_confirmacion_handler, pattern="^agenda_(ok|error):",block=False))

    # Programar todos los jobs
    jobs_to_schedule = [
        (skip_if_feriado(job_dayin), Horarios.hora_dayin, "DayIN automático"),
        (skip_if_feriado(job_rd), Horarios.hora_rd, "Comentarios RD"),
        (skip_if_feriado(job_burn), Horarios.hora_burn1, "Primer burn del día"),
        (skip_if_feriado(job_burn), Horarios.hora_burn2, "Segundo burn del día"),
        (skip_if_feriado(job_burn), Horarios.hora_burn3, "Tercer burn del día"),
        (skip_if_feriado(job_agenda_preliminar), Horarios.hora_agenda_pre, "Prelim. agenda mañana"),
        #(skip_if_feriado(job_agenda_preliminar_por_equipo), Horarios.hora_agenda_pre_eq, "Prelim. agenda equipo"),
        (skip_if_feriado(job_agenda_automatica), Horarios.hora_agenda, "Agenda de mañana"),
        (skip_if_feriado(job_burn), Horarios.hora_burn4, "Último burn del día"),
        (skip_if_feriado(job_dayout), Horarios.hora_dayout, "DayOut automático"),
        (skip_if_feriado(job_newday), Horarios.hora_newday, "Nuevos registros"),
        (skip_if_feriado(job_food), Horarios.hora_food, "Food reminder"),
        (skip_if_feriado(job_pay), Horarios.hora_pay, "Pay reminder"),
        (skip_if_feriado(job_deploy), Horarios.hora_deploy, "Deploy"),
    ]

    app.job_queue.set_application(app)  

    for job_func, job_time, job_name in jobs_to_schedule:

        # Caso: NO correr estos los viernes
        if job_func in (job_agenda_preliminar, job_agenda_automatica):
            schedule_daily_job(app, job_func, job_time, days=(0, 1, 2, 3), job_name=job_name)
            continue

        # Caso general: todos los jobs que sí deben correr de lunes a viernes
        schedule_daily_job(app, job_func, job_time, days=(0, 1, 2, 3, 4), job_name=job_name)


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

