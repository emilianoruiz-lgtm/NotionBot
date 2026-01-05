# ==========================================
# IMPORTS
# ==========================================

# Módulos Locales
import Config


# ==========================================
# CONFIGURACIÓN Y CONSTANTES
# ==========================================

ESPERANDO_FECHA_AGENDA = 300


# ==========================================
# UTILIDADES DE SISTEMA Y TIEMPO
# ==========================================

def is_weekday(dt):
    return dt.weekday() < 5  # lunes=0 ... viernes=4


def fecha_inicio(registro):
        date_prop = registro['properties'].get('Date', {}).get('date', {})
        if date_prop and date_prop.get('start'):
            try:
                return Config.dateutil.parser.isoparse(date_prop['start']).replace(tzinfo=None)
            except:
                return Config.datetime.max
        return Config.datetime.max


# ==========================================
# FUNCIONES DE DOMINIO (AGENDA)
# ==========================================

def get_team_config(equipo):
    cfg = Config.EQUIPOS_CONFIG.get(equipo, {})
    return (
        cfg.get("emoji", Config.DEFAULT_TEAM_EMOJI),
        cfg.get("display_name", equipo),
    )

def get_alias(nombre):
    return Config.ALIAS_PERSONAS.get(nombre, nombre)

def get_personas(props):
    personas = props.get('Person', {}).get('people', [])
    nombres = [p.get('name', '') for p in personas if p.get('name')]
    return [get_alias(n) for n in nombres]

def get_tipo(props):
    tipo = "Sin tipo"
    tipo_prop = props.get('Tipo')
    if tipo_prop:
        if tipo_prop.get('select'):
            tipo = tipo_prop['select'].get('name', 'Sin tipo')
        elif tipo_prop.get('multi_select'):
            if tipo_prop['multi_select']:
                tipo = tipo_prop['multi_select'][0].get('name', 'Sin tipo')
        elif tipo_prop.get('rollup'):
            arr = tipo_prop['rollup'].get('array', [])
            if arr:
                tipo = arr[0].get('name', 'Sin tipo')
    return tipo

def titulo_con_guiones(nombre, total=30):
    base = f"{nombre} "
    return base + "-" * max(0, total - len(base))


def get_hora(props):
    date_prop = props.get('Date', {}).get('date', {})
    if not date_prop or not date_prop.get('start'):
        return None

    try:
        dt = Config.dateutil.parser.isoparse(date_prop['start'])

        # Normalizar TZ
        if dt.tzinfo is None:
            dt = Config.ARG_TZ.localize(dt)
        else:
            dt = dt.astimezone(Config.ARG_TZ)

        # Si es medianoche exacta, asumimos "sin horario"
        if dt.hour == 0 and dt.minute == 0:
            return None

        return dt.strftime("%H:%M")
    except:
        return None


# ==========================================
# FETCH NOTION
# ==========================================

def get_registros_calendar_por_fecha(fecha_dt):
    registros = []
    has_more = True
    next_cursor = None

    while has_more:
        query = {"page_size": 100}
        if next_cursor:
            query["start_cursor"] = next_cursor

        response = Config.requests.post(
            f"https://api.notion.com/v1/databases/{Config.DATABASE_ID_CALENDAR}/query",
            headers=Config.HEADERS,
            json=query
        )
        data = response.json()
        registros.extend(data.get('results', []))
        has_more = data.get('has_more', False)
        next_cursor = data.get('next_cursor')

    registros_filtrados = []
    for r in registros:
        date_prop = r['properties'].get('Date', {}).get('date')
        if not date_prop or not date_prop.get('start'):
            continue

        start_dt = Config.dateutil.parser.isoparse(date_prop['start']).date()
        end_dt = (
            Config.dateutil.parser.isoparse(date_prop['end']).date()
            if date_prop.get('end')
            else start_dt
        )

        if start_dt <= fecha_dt <= end_dt:
            registros_filtrados.append(r)

    return registros_filtrados


# ==========================================
# SERVICIO DE DOMINIO
# ==========================================

def generar_agenda_por_fecha(fecha):
    registros = get_registros_calendar_por_fecha(fecha)
    return resumen_calendar(registros, fecha)


# ==========================================
# MENÚES TELEGRAM
# ==========================================

def create_agenda_keyboard():
    keyboard = [
        [
            Config.InlineKeyboardButton("📅 -2 días", callback_data="agenda_antesayer"),
        ],
        [
            Config.InlineKeyboardButton("📅 -1 día", callback_data="agenda_ayer"),
        ],
        [
            Config.InlineKeyboardButton("📅 <Hoy>", callback_data="agenda_hoy"),
        ],
        [
            Config.InlineKeyboardButton("📅 +1 día", callback_data="agenda_manana"),
        ],
        [
            Config.InlineKeyboardButton("📅 +2 días", callback_data="agenda_pasadomanana"),
        ],
        [
            Config.InlineKeyboardButton("Cancelar", callback_data="agenda_cancelar"),
        ],
    ]
    return Config.InlineKeyboardMarkup(keyboard)

async def start_agenda(update: Config.Update, context: Config.CallbackContext):
    await update.message.reply_text(
        "📋 ¿Qué agenda querés consultar?",
        reply_markup=create_agenda_keyboard(),
    )
    return ESPERANDO_FECHA_AGENDA


# ==========================================
# CONVERSATION HANDLERS
# ==========================================

# CONVERSACIÓN SELECCIÓN DE AGENDA
async def recibir_fecha_agenda(update: Config.Update, context: Config.CallbackContext):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "agenda_cancelar":
        await query.message.reply_text("❌ Operación cancelada.")
        return Config.ConversationHandler.END

    hoy = Config.date.today()

    if data == "agenda_antesayer":
        fecha = hoy - Config.timedelta(days=2)
    elif data == "agenda_ayer":
        fecha = hoy - Config.timedelta(days=1)
    elif data == "agenda_hoy":
        fecha = hoy
    elif data == "agenda_manana":
        fecha = hoy + Config.timedelta(days=1)
    elif data == "agenda_pasadomanana":
        fecha = hoy + Config.timedelta(days=2)
        titulo = "PASADO MAÑANA"
    else:
        await query.message.reply_text("⚠️ Opción inválida.")
        return Config.ConversationHandler.END

    await query.message.reply_text("🕐 Revisando calendario...")
    resultado = await Config.asyncio.to_thread(generar_agenda_por_fecha, fecha)
    await query.message.reply_text(
        resultado,
        parse_mode=Config.ParseMode.HTML,
    )

    return Config.ConversationHandler.END

conv_agenda = Config.ConversationHandler(
    entry_points=[Config.CommandHandler("agenda", start_agenda)],
    states={
        ESPERANDO_FECHA_AGENDA: [
            Config.CallbackQueryHandler(
                recibir_fecha_agenda, pattern="^agenda_"
            )
        ]
    },
    fallbacks=[Config.CommandHandler("cancelar", Config.cancelar)],
)


# ==========================================
# LÓGICA DE ARMADO DE AGENDA
# ==========================================

def resumen_calendar(registros, fecha):
    fecha_str = fecha.strftime("%d-%m-%Y")
    resumen_lines = [f"📅 <b>AGENDA {fecha_str}</b>"]
    registros.sort(key=fecha_inicio)
    equipos_dict = {}

    for r in registros:
        props = r['properties']
        tipo = get_tipo(props)
        tipo_lower = tipo.lower()

        if tipo in Config.TIPOS_SIN_ARRANQUE_NORMAL:
            equipos_dict.setdefault("Ausente", []).append(r)
            continue

        if tipo in Config.TIPOS_ARRANQUE_REMOTO:
            equipos_dict.setdefault("Inicio remoto", []).append(r)
            continue

        if tipo in Config.TIPOS_GUARDIA:
                equipos_dict.setdefault("Guardia", []).append(r)
                continue

        if tipo_lower in [t.lower() for t in ["Evento Personal", "Evento EPROC"]]:
            date_prop = props.get('Date', {}).get('date', {})
            hora_ok = None
            if date_prop and date_prop.get('start'):
                try:
                    dt_start = Config.dateutil.parser.isoparse(date_prop['start'])
                    if dt_start.tzinfo is None:
                        dt_start = Config.ARG_TZ.localize(dt_start)
                    else:
                        dt_start = dt_start.astimezone(Config.ARG_TZ)
                    hora_ok = dt_start.hour * 60 + dt_start.minute
                except:
                    hora_ok = None
            if hora_ok is None or hora_ok <= (8 * 60 + Config.MARGEN_MINUTOS):
                equipos_dict.setdefault("Ausente", []).append(r)
                continue

        # --- 3️⃣ En cualquier otro caso, agrupar por equipo o General ---
        equipos = props.get('Equipo', {}).get('multi_select', [])
        equipos_nombres = [e['name'] for e in equipos] or ["General"]
        for eq in equipos_nombres:
            equipos_dict.setdefault(eq, []).append(r)

    # --- Asegurar categorías base ---
    equipos_dict.setdefault("Ausente", [])
    equipos_dict.setdefault("Inicio remoto", [])
    equipos_dict.setdefault("General", [])
    equipos_dict.setdefault("Guardia", [])

    # --- Orden de apartados ---
    apartados_orden = ["Ausente"] + ["Inicio remoto"] + \
                      [e for e in equipos_dict if e not in ["Ausente", "Inicio remoto", "General", "Guardia"]] + \
                      ["General"] + ["Guardia"]

    #  --- Construcción del resumen ---
    for equipo in apartados_orden:
        regs = equipos_dict.get(equipo, [])

        if equipo == "General" and not regs:
            continue

        emojiteam, nombre_mostrar = get_team_config(equipo)
        titulo = titulo_con_guiones(nombre_mostrar)

        resumen_lines.append(f"\n<b>{emojiteam} {titulo}</b>")

        if regs:
            regs.sort(key=fecha_inicio)

            for r in regs:
                props = r['properties']
                tipo = get_tipo(props)
                personas = get_personas(props)
                hora = get_hora(props)

                for p in personas or ["Sin persona"]:
                    if hora:
                        resumen_lines.append(f"      {p} | {tipo} {hora}")
                    else:
                        resumen_lines.append(f"      {p} | {tipo}")
        else:
            resumen_lines.append(Config.NO_REGISTROS_TEXT)

    return "\n".join(resumen_lines)


# ============================
# JOB AGENDA PRELIMINAR
# ============================
async def job_agenda_preliminar(context: Config.CallbackContext):
    ahora = Config.datetime.now(Config.ARG_TZ)
    if not is_weekday(ahora) or ahora.date() in Config.FERIADOS:
        print(f"⚠ Prelim. agenda mañana no ejecutada: hoy ({ahora.strftime('%Y-%m-%d')}) no es un día hábil o es feriado.")
        return

    try:
        print(f"📤 job_agenda_preliminar disparado a las {ahora.strftime('%Y-%m-%d %H:%M:%S')}")
        fecha = ahora.date() + Config.timedelta(days=1)
        resultado = await Config.asyncio.to_thread(generar_agenda_por_fecha, fecha)
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
    ahora = Config.datetime.now(Config.ARG_TZ)
    if not is_weekday(ahora) or ahora.date() in Config.FERIADOS:
        print(f"⚠️[DEBUG] Agenda automática no ejecutada: hoy ({ahora.strftime('%Y-%m-%d')}) no es un día hábil o es feriado.")
        return

    try:
        print(f"📤 job_agenda_automatica disparado a las {ahora.strftime('%Y-%m-%d %H:%M:%S')}")
        fecha = ahora.date() + Config.timedelta(days=1)
        resultado = await Config.asyncio.to_thread(generar_agenda_por_fecha, fecha)
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_EPROC,
            text=f"{resultado}",
            parse_mode="HTML"
        )
        print("📤 Mensaje de Agenda automática enviado")
    except Exception as e:
        print(f"❌ Error en job_agenda_automatica: {e}")