# ==========================================
# 1. IMPORTS
# ==========================================

# Módulos Locales
import Config
from modules.DayIN import DayIN
from modules.DayOUT import DayOUT, DayOutEquipo
from modules.Burn import burndown, newday
from modules.RDs import RDs_comments
from modules.Agenda import generar_resumen_manana
from modules.mundopizza.menump import get_menu_text
from modules.AgendaSemProx import AgendaPlAdminSemanaSiguiente


ahora = Config.atetime.now(Config.ARG_TZ)


def is_weekday(date_to_check: Config.datetime) -> bool:
    return date_to_check.weekday() in (0, 1, 2, 3, 4)

def is_friday(date_to_check: Config.atetime) -> bool:
    return date_to_check.weekday() == 4

# ============================
# JOB DAYIN
# ============================
async def job_dayin(context: Config.CallbackContext):
    print("📤 job_dayin disparado a las", Config.datetime.now(Config.ARG_TZ))
    try:
        resultado = await DayIN()
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_DEBUG,
            text=f"[DayIN automático realizado]\n{resultado}",
            parse_mode="HTML"
        )
        print("📤 DayIN automático enviado")
    except Exception as e:
        print(f"❌ Error en job_dayin: {e}")


# ============================
# JOB DAYOUT
# ============================
async def job_dayout(context: Config.CallbackContext):
    print("📤 job_dayout disparado a las", Config.datetime.now(Config.ARG_TZ))
    try:
        resultado = await DayOUT()
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_LOG,
            text=f"[DayOUT automático]\n{resultado}",
            parse_mode="HTML"
        )
        print("📤 DayOUT automático enviado")
    except Exception as e:
        print(f"❌ Error en job_dayout: {e}")

# ============================
# JOB BURN
# ============================
async def job_burn(context: Config.CallbackContext):
    print("🔥 Ejecutando job_burn", Config.datetime.now(Config.ARG_TZ))
    resultado = await burndown()
    if resultado:
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_DEBUG,
            text=str(resultado),
            parse_mode="HTML"
        )

# ============================
# JOB NEWDAY
# ============================
async def job_newday(context: Config.CallbackContext):
    print("📤 job_newday disparado a las", Config.datetime.now(Config.ARG_TZ))
    resultado = await newday()
    if resultado:
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_DEBUG,
            text=str(resultado),
            parse_mode="HTML"
        )

# ============================
# JOB RD
# ============================

async def job_rd(context: Config.CallbackContext):
    print("📤 job_rd disparado a las", Config.datetime.now(Config.ARG_TZ))
    resultado = await RDs_comments(concatenado=False)
    if resultado:
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_LOG,
            text=str(resultado),
            parse_mode="HTML"
        )

# ============================
# JOB AGENDA PRELIMINAR
# ============================
async def job_agenda_preliminar(context: Config.CallbackContext):
    if not is_weekday(ahora) or ahora.date() in Config.FERIADOS:
        print(f"⚠ Prelim. agenda mañana no ejecutada: hoy ({ahora.strftime('%Y-%m-%d')}) no es un día hábil o es feriado.")
        return

    try:
        print(f"📤 job_agenda_preliminar disparado a las {ahora.strftime('%Y-%m-%d %H:%M:%S')}")
        resultado = await generar_resumen_manana()
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_LOG,
            text=f"[Agenda Preliminar]\n{resultado}",
            parse_mode="HTML"
        )
        print("📤 Mensaje de Agenda Preliminar enviado")
    except Exception as e:
        print(f"❌ Error en job_agenda_preliminar: {e}")

# ============================
# JOB AGENDA AUTOMÁTICA
# ============================
async def job_agenda_automatica(context: Config.CallbackContext):
    if not is_weekday(ahora) or ahora.date() in Config.FERIADOS:
        print(f"⚠️[DEBUG] Agenda automática no ejecutada: hoy ({ahora.strftime('%Y-%m-%d')}) no es un día hábil o es feriado.")
        return

    try:
        print(f"📤 job_agenda_automatica disparado a las {ahora.strftime('%Y-%m-%d %H:%M:%S')}")
        resultado = await generar_resumen_manana()
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_EPROC,
            text=f"{resultado}",
            parse_mode="HTML"
        )
        print("📤 Mensaje de Agenda automática enviado")
    except Exception as e:
        print(f"❌ Error en job_agenda_automatica: {e}")

# ============================
# JOB AGENDA SEM PROX
# ============================
async def job_agenda_semana_prox(context:Config. CallbackContext):
    if not is_friday(ahora) or ahora.date() in Config.FERIADOS:
        print(
            f"⚠️[DEBUG] Agenda semana prox no ejecutada: "
            f"hoy ({ahora.strftime('%Y-%m-%d')}) no es viernes o es feriado."
        )
        return

    try:
        print(f"📤 job_agenda_semana_prox disparado a las {ahora.strftime('%Y-%m-%d %H:%M:%S')}")
        resultado = await AgendaPlAdminSemanaSiguiente()
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_EPROC,
            text=f"{resultado}",
            parse_mode="HTML"
        )
        print("📤 Mensaje de Agenda automática enviado")
    except Exception as e:
        print(f"❌ Error en job_agenda_semana_prox: {e}")


# ============================
# JOB FOOD REMINDER
# ============================
async def job_food(context: Config.CallbackContext):
    if not is_weekday(ahora) or ahora.date() in Config.FERIADOS:
        print(f"⚠️[DEBUG] food no ejecutada: hoy ({ahora.strftime('%Y-%m-%d')}) no es un día hábil o es feriado.")
        return

    try:
        print(f"📤 job_food disparado a las {ahora.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Primer mensaje: recordatorio
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_TEAM,
            text="¡Acuérdense de pedir comida!!",
            parse_mode="HTML"
        )
        print("📤 Mensaje de food reminder enviado")

        # Segundo mensaje: menú
        menu_text = get_menu_text()
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_TEAM,
            text=menu_text,
            parse_mode="HTML"
        )
        print("📤 Menú enviado")
        
    except Exception as e:
        print(f"❌ Error en job_food: {e}")

# ============================
# JOB PAY REMINDER
# ============================
async def job_pay(context: Config.CallbackContext):
    if not is_weekday(ahora) or ahora.date() in Config.FERIADOS:
        print(f"⚠️[DEBUG] pay no ejecutada: hoy ({ahora.strftime('%Y-%m-%d')}) no es un día hábil o es feriado.")
        return

    try:
        print(f"📤 job_pay disparado a las {ahora.strftime('%Y-%m-%d %H:%M:%S')}")
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_TEAM,
            text=f"Acuerdensé de pagar la comida 💵!",
            parse_mode="HTML"
        )
        print("📤 Mensaje de pay reminder enviado")
    except Exception as e:
        print(f"❌ Error en job_pay: {e}")





