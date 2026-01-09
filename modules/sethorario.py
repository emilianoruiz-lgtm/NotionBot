# ==========================================
# IMPORTS
# ==========================================

# Módulos Locales
import Config
import Horarios
from modules.Agenda import job_agenda_preliminar, job_agenda_automatica, job_agenda_preliminar_por_equipo
from modules.DayOUT import job_dayout
from modules.DayIN import job_dayin
from modules.NewDay import job_newday
from modules.Burn import job_burn
from modules.mundopizza.menump import job_food, job_pay
from modules.jobs import job_dayin
from modules.RDs import job_rd
from modules.Deploy import job_deploy

# ==========================================
# CONFIGURACIÓN Y CONSTANTES
# ==========================================

SET_TAREA, SET_HORA = range(2)

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


# ==========================================
# FETCH TXT
# ==========================================




# ==========================================
# WRITE TXT
# ==========================================

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

# ==========================================
# SERVICIO DE DOMINIO
# ==========================================




# ==========================================
# MENÚES TELEGRAM
# ==========================================



# ==========================================
# CONVERSATION HANDLERS
# ==========================================
async def elegir_tarea(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tarea = query.data
    Config.logger.info(f"Tarea seleccionada: {tarea}")
    if tarea not in TAREAS_MAP:
        Config.logger.warning(f"Tarea inválida: {tarea}")
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

# ==========================================
# MENÚ SET HORARIOS
# ==========================================

async def cancelar_sethorario(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Configuración cancelada.")
    return Config.ConversationHandler.END





# Configura Config.logging
Config.logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=Config.logging.INFO
)
logger = Config.logging.getLogger(__name__)

# Silenciar logs de httpx y apscheduler
Config.logging.getLogger('httpx').setLevel(Config.logging.WARNING)
Config.logging.getLogger('apscheduler.scheduler').setLevel(Config.logging.WARNING)
Config.logging.getLogger('apscheduler').setLevel(Config.logging.WARNING)
Config.logging.getLogger('telegram.ext').setLevel(Config.logging.WARNING)

# Estados del ConversationHandler
SET_TAREA, SET_HORA = range(2)

# Diccionario de mapeo de nombres de tarea a variable de Horarios
TAREAS_MAP = {
    "DayIN": "hora_dayin",
    "RD": "hora_rd",
    "Burn1": "hora_burn1",
    "Burn2": "hora_burn2",
    "Burn3": "hora_burn3",
    "Agenda Pre": "hora_agenda_pre",
    "Agenda Pre EQ": "hora_agenda_pre_eq",
    "Agenda": "hora_agenda",
    "Agenda Semanal": "hora_agenda_sem",
    "Burn4": "hora_burn4",
    "DayOUT": "hora_dayout",
    "NewDay": "hora_newday",
    "food": "hora_food",
    "pay": "hora_pay",
    "deploy": "hora_deploy",
}

# Mapeo de variables a funciones de job
JOB_MAP = {
    "hora_dayin": job_dayin,
    "hora_rd": job_rd,
    "hora_burn1": job_burn,
    "hora_burn2": job_burn,
    "hora_burn3": job_burn,
    "hora_burn4": job_burn,
    "hora_agenda_pre": job_agenda_preliminar,
    "hora_agenda_pre_eq": job_agenda_preliminar_por_equipo,
    "hora_agenda": job_agenda_automatica,
    "hora_dayout": job_dayout,
    "hora_newday": job_newday,
    "hora_food": job_food,
    "hora_pay": job_pay,
    "hora_deploy": job_deploy,
}

async def debug_callback(update: Config.Update, context: Config.CallbackContext):
    """Handler genérico para capturar todos los callbacks."""
    logger.info(f"Callback recibido: data='{update.callback_query.data}' de user_id={update.effective_user.id}")
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(f"Callback recibido: {update.callback_query.data}. Procesando...")

async def cancelar_sethorario(update: Config.Update, context: Config.CallbackContext):
    logger.info("Conversación cancelada por usuario")
    await update.message.reply_text("❌ Conversación cancelada.")
    return Config.ConversationHandler.END

async def sethorario_start(update: Config.Update, context: Config.CallbackContext):
    logger.info(f"Iniciando /sethorario para user_id: {update.effective_user.id}")

    # Construyo lista con (hora, nombre, var_name)
    tareas_con_hora = []
    for nombre, var_name in TAREAS_MAP.items():
        try:
            hora_actual = getattr(Horarios, var_name)
            tareas_con_hora.append((hora_actual, nombre, var_name))
        except AttributeError as e:
            logger.error(f"Error al acceder a {var_name} en Horarios: {e}")
            continue

    # Ordenar por hora
    tareas_con_hora.sort(key=lambda x: x[0])

    # Construir teclado
    keyboard = []
    for hora, nombre, var_name in tareas_con_hora:
        label = f"{nombre} ({hora.strftime('%H:%M')})"
        keyboard.append([Config.InlineKeyboardButton(label, callback_data=nombre)])

    reply_markup = Config.InlineKeyboardMarkup(keyboard)
    texto = "⚙️ Seleccioná la tarea que querés modificar:"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(texto, reply_markup=reply_markup)
    else:
        await update.message.reply_text(texto, reply_markup=reply_markup)

    return SET_TAREA


async def elegir_tarea(update: Config.Update, context: Config.CallbackContext):
    try:
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

    except Exception as e:
        logger.error(f"Error en elegir_tarea: {e}", exc_info=True)
        await query.answer()
        await query.message.edit_text("⚠️ Error interno al procesar la selección. Intenta de nuevo.")
        return Config.ConversationHandler.END

def persistir_horas():
    """Reescribe Horarios.py con los valores actuales."""
    import inspect

    horarios_path = inspect.getfile(Horarios)  # ruta real del módulo Horarios
    lines = ["from datetime import time\nimport Config\n\n"]
    for _, var_name in TAREAS_MAP.items():
        try:
            t = getattr(Horarios, var_name)
            if not isinstance(t, Config.time):
                logger.error(f"Valor inválido para {var_name}: {t}")
                continue
            lines.append(f"{var_name} = time(hour={t.hour}, minute={t.minute}, tzinfo={Config.ARG_TZ})\n")
        except AttributeError as e:
            logger.error(f"Error al acceder a {var_name} en Horarios: {e}")
            continue

    try:
        with open(horarios_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        logger.info(f"Horarios.py actualizado exitosamente en {horarios_path}")

        # Recargar módulo
        import importlib
        importlib.reload(Horarios)
    except Exception as e:
        logger.error(f"Error al escribir Horarios.py: {e}", exc_info=True)
        raise

async def setear_hora(update: Config.Update, context: Config.CallbackContext):
    """Recibe la hora, valida formato, actualiza Horarios.py y reprograma el job."""
    texto = update.message.text.strip()
    hora_match = Config.re.match(r'^(\d{1,2}):(\d{2})$', texto)
    if not hora_match:
        logger.warning("Formato de hora inválido")
        await update.message.reply_text(
            "⚠️ Formato inválido. Debe ser HH:MM (ej: 07:30). Intentalo de nuevo."
        )
        return SET_HORA

    h, m = map(int, hora_match.groups())
    if not (0 <= h <= 23 and 0 <= m <= 59):
        logger.warning("Hora fuera de rango")
        await update.message.reply_text(
            "⚠️ Hora o minutos fuera de rango. Intenta nuevamente."
        )
        return SET_HORA

    try:
        nueva_hora = Config.time(hour=h, minute=m, tzinfo=Config.ARG_TZ)
        tarea = context.user_data.get("tarea")
        var_name = context.user_data.get("tarea_var")

        if not tarea or not var_name:
            logger.error("Error: tarea o var_name no encontrados en user_data")
            await update.message.reply_text(
                "⚠️ Error interno: no se encontró la tarea seleccionada. Inicia de nuevo."
            )
            return Config.ConversationHandler.END

        # Actualizar en memoria
        setattr(Horarios, var_name, nueva_hora)

        # Persistir en Horarios.py
        persistir_horas()

        # Reprogramar el job
        jobs = context.job_queue.get_jobs_by_name(var_name)
        for job in jobs:
            job.schedule_removal()
            logger.info(f"Job '{var_name}' eliminado para reprogramación")

        job_func = JOB_MAP.get(var_name)
        if job_func:
            await schedule_daily_job(
                context.application, job_func, nueva_hora,
                days=(0, 1, 2, 3, 4), job_name=var_name
            )
        else:
            logger.warning(f"No se encontró job_func para {var_name}")

        await update.message.reply_text(
            f"✅ Hora de <b>{tarea}</b> actualizada a {nueva_hora.strftime('%H:%M')} y guardada. Job reprogramado.",
            parse_mode="HTML"
        )
        logger.info("Actualización completada")
        return Config.ConversationHandler.END
    except Exception as e:
        logger.error(f"Error en setear_hora: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Error interno al guardar la hora. Intenta de nuevo.")
        return Config.ConversationHandler.END

async def schedule_daily_job(
    app, job_func, job_time: Config.time, days=(0, 1, 2, 3, 4), job_name="Job"
):
    """Programa un job diario en el JobQueue."""
    if getattr(job_time, "tzinfo", None) is None:
        job_time = job_time.replace(tzinfo=Config.ARG_TZ)

    async def job_wrapper(ctx):
        try:
            await job_func(ctx)
        except Exception as e:
            logger.error(f"Excepción en job '{job_name}': {e}")

    try:
        app.job_queue.run_daily(
            job_wrapper,
            time=job_time,
            days=days,
            name=job_name
        )
        logger.info(f"Job '{job_name}' programado exitosamente a {job_time.strftime('%H:%M %Z')}")
    except Exception as e:
        logger.error(f"Error al programar job '{job_name}': {e}")

conv_sethorario = Config.ConversationHandler(
    entry_points=[Config.CommandHandler("sethorario", sethorario_start)],
    states={
        SET_TAREA: [Config.CallbackQueryHandler(elegir_tarea, pattern=f"^({'|'.join(TAREAS_MAP.keys())})$")],
        SET_HORA: [Config.MessageHandler(Config.filters.TEXT & ~Config.filters.COMMAND, setear_hora)],
    },
    fallbacks=[Config.CommandHandler("cancelar", cancelar_sethorario)],
    map_to_parent={}
)