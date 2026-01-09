# ==========================================
# IMPORTS
# ==========================================

# Módulos Locales
import Config
import Horarios
from modules.Agenda import job_agenda_preliminar, job_agenda_automatica
from modules.DayOUT import job_dayout
from modules.DayIN import job_dayin
from modules.NewDay import job_newday
from modules.Burn import job_burn
from modules.mundopizza.menump import job_food, job_pay
from modules.jobs import job_dayin
from modules.RDs import job_rd


# ==========================================
# HELPERS DEL DOMINIO
# ==========================================
def next_valid_run(job_time: Config.time, days=(0,1,2,3,4)):
    now = Config.datetime.now(Config.ARG_TZ)
    job_dt = Config.datetime.combine(now.date(), job_time, Config.ARG_TZ)
    if job_dt <= now: job_dt += Config.timedelta(days=1)
    while job_dt.weekday() not in days:
        job_dt += Config.timedelta(days=1)
    return job_dt

async def safe_job_runner(ctx, job_func, job_name, grace_period=300):
    start_ts = Config._time.time()
    task = None
    try:
        print(f"[JOB] ▶ Ejecutando '{job_name}'...")
        task = Config.asyncio.create_task(Config.maybe_await(job_func, ctx))
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
        job_time = job_time.replace(tzinfo=Config.ARG_TZ)
        print(f"⚠️ [DEBUG] job_time '{job_name}' no tenía tzinfo, se asignó {Config.ARG_TZ}")

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
# LÓGICA DEBUG JOBS
# ==========================================
async def debug_jobs(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(Config.ARG_TZ).strftime('%d/%m/%y %H:%M')} - Mostrar Jobs programados ")
    jobs = context.job_queue.jobs()
    if not jobs:
        msg = "⛔ No hay jobs programados en el JobQueue."
    else:
        ahora = Config.datetime.now(Config.ARG_TZ)
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



