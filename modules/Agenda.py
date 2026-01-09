# ==========================================
# IMPORTS
# ==========================================

# Módulos Locales
import Config


# ==========================================
# CONFIGURACIÓN Y CONSTANTES
# ==========================================

ESPERANDO_FECHA_AGENDA = 300
ACCION_LABELS = {
    "ok": "Confirmado",
    "error": "Con errores",
    "auto": "Auto-confirmado",
}
ICONOS_ACCION = {
    "ok": "✅",
    "error": "❌",
    "auto": "🤖",
    "cancel": "🚫",
}

NOTION_CORRECCION_URL = (
    "https://www.notion.so/eproc/"
    "7eb7b4c654f14203ac8dcd7d864dc722"
    "?v=284152ff88c5807ab848000c530e12a3"
)

ACCION_FEEDBACK = {
    "ok": lambda u: f"✅ Agenda confirmada por {u}",
    "error": lambda u: (
        f"❌ Errores reportados por {u}\n\n"
        f"✏️ Corregir en Notion:\n"
        f"{NOTION_CORRECCION_URL}"
    ),
}

ACCION_TEXTO_LOG = {
    "ok": "Agenda confirmada por",
    "error": "Errores reportados por",
    "auto": "Agenda auto-confirmada por",
}

PREGUNTAS_EXTRA_POR_EQUIPO = {
    "Admin": [
        "¿Hay <b>vacaciones</b>, <b>días de licencia</b> o <b>eventos logísticos</b> asociados a {responsables} previstos para mañana que no estén registrados?",
    ],
    "DEFAULT": [
        "¿Hay <b>visitas a planta</b>, <b>inducciones</b>, <b>estudios médicos</b>, <b>vacaciones</b> o <b>días de licencia</b> asociados a {responsables} previstos para mañana que no estén registrados?",
    ],
}


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
# HELPERS
# ==========================================
def get_menciones_equipo(equipo):
    cfg = Config.EQUIPOS_CONFIG.get(equipo, {})
    integrantes = cfg.get("integrantes", [])

    menciones = []
    for nombre in integrantes:
        alias = Config.ALIAS_PERSONAS.get(nombre)
        if alias and alias.startswith("@"):
            menciones.append(alias)
        else:
            # fallback seguro
            menciones.append(f"@{nombre.split()[0]}")

    return menciones


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

def get_titulo_registro(props):
    title_prop = props.get("Name", {}).get("title", [])
    if title_prop:
        return "".join(t.get("plain_text", "") for t in title_prop)
    return "Sin título"

def get_cliente(props):
    cliente_prop = props.get("Cliente")
    if not cliente_prop:
        return None

    roll = cliente_prop.get("rollup")
    if not roll:
        return None

    if roll.get("type") != "array":
        return None

    textos = []

    for el in roll.get("array", []):
        t = el.get("type")

        if t == "title":
            textos.append("".join(x["plain_text"] for x in el.get("title", [])))

        elif t == "rich_text":
            textos.append("".join(x["plain_text"] for x in el.get("rich_text", [])))    


        elif t == "select":
            if el.get("select"):
                textos.append(el["select"].get("name"))

        elif t == "multi_select":
            textos.extend(ms["name"] for ms in el.get("multi_select", []))

        elif t == "formula":
            f = el.get("formula", {})
            textos.append(
                f.get("string")
                or str(f.get("number"))
                or str(f.get("boolean"))
            )

    textos = [t for t in textos if t]
    return ", ".join(textos) if textos else None

def filtrar_registros_por_equipo(registros, equipo):
    if equipo == "General":
        return registros

    filtrados = []

    for r in registros:
        equipos = r["properties"].get("Equipo", {}).get("multi_select", [])
        nombres = [e["name"] for e in equipos]

        if equipo in nombres:
            filtrados.append(r)

    return filtrados

def generar_agenda_por_fecha_y_equipo(fecha, equipo):
    registros = get_registros_calendar_por_fecha(fecha)
    registros_equipo = filtrar_registros_por_equipo(registros, equipo)
    return resumen_calendar(registros_equipo, fecha), registros_equipo

def armar_mensaje_confirmacion(equipo, fecha, texto_agenda, hay_registros):
    _, nombre_mostrar = get_team_config(equipo)
    f"Equipo: <b>{nombre_mostrar}</b>\n\n"
    # 🔹 Buscar pregunta extra por equipo (si existe)

    preguntas = (
        PREGUNTAS_EXTRA_POR_EQUIPO.get(equipo)
        or PREGUNTAS_EXTRA_POR_EQUIPO.get("DEFAULT", [])
    )

    bloque_preguntas = ""

    if equipo != "General" and preguntas:
        menciones = get_menciones_equipo(equipo)
        menciones_txt = " ".join(menciones)

        preguntas_formateadas = [
            p.format(responsables=menciones_txt) for p in preguntas
        ]

        bloque_preguntas = (
            "\n\n"
            + "\n".join(f" {p}" for p in preguntas_formateadas)
        )
    else:
        bloque_preguntas = ""



    if hay_registros:
        return (
            f"<b>REVISIÓN DE AGENDA</b>\n"
            f"Equipo: <b>{equipo}</b>\n\n"
            f"{texto_agenda}\n\n"
            "¿Los registros previstos son correctos?"
            f"{bloque_preguntas}"
        )
    else:
        return (
            f"<b>REVISIÓN DE AGENDA</b>\n"
            f"Equipo: <b>{equipo}</b>\n\n"
            "⚠️ No hay registros cargados para mañana.\n"
            "¿Esto es correcto?"
            f"{bloque_preguntas}"
        )



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

def keyboard_confirmacion_agenda(equipo, fecha):
    fecha_str = fecha.strftime("%Y-%m-%d")

    return Config.InlineKeyboardMarkup([
        [
            Config.InlineKeyboardButton(
                "✅ Correcto",
                callback_data=f"agenda_ok:{equipo}:{fecha_str}"
            ),
            Config.InlineKeyboardButton(
                "❌ Hay errores",
                callback_data=f"agenda_error:{equipo}:{fecha_str}"
            )
        ]
    ])


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

    await query.message.edit_text("🕐 Revisando calendario...")

    resultado = await Config.asyncio.to_thread(generar_agenda_por_fecha, fecha)
    await query.message.edit_text(
        resultado,
        parse_mode=Config.ParseMode.HTML
    )

    return Config.ConversationHandler.END

conv_agenda = Config.ConversationHandler(
    entry_points=[Config.CommandHandler("agenda", start_agenda)],
    states={
        ESPERANDO_FECHA_AGENDA: [
            Config.CallbackQueryHandler(
                recibir_fecha_agenda, pattern="^agenda_(antesayer|ayer|hoy|manana|pasadomanana|cancelar)$"

            )
        ]
    },
    fallbacks=[Config.CommandHandler("cancelar", Config.cancelar)],
)

async def agenda_confirmacion_handler(update: Config.Update, context: Config.CallbackContext):
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user
    print("📥 CALLBACK:", data)
    try:
        prefix, rest = data.split("_", 1)
        accion, equipo, fecha = rest.split(":")                 
    except ValueError as e:
        print("❌ ERROR parseando callback:", data, e)
        return

    username = (
        f"@{user.username}"
        if user.username
        else f"{user.first_name} {user.last_name or ''}".strip()
    )

    # 🧾 Registro interno (memoria en runtime)
    key = f"{equipo}:{fecha}"
    context.application.bot_data.setdefault("agenda_confirmaciones", {})
    context.application.bot_data["agenda_confirmaciones"][key] = {
        "accion": accion,
        "usuario": username,
        "timestamp": Config.datetime.now(Config.ARG_TZ)
    }

    accion, equipo, fecha = data.replace("agenda_", "").split(":")

    usuario = query.from_user.full_name
    icono = ICONOS_ACCION.get(accion, "ℹ️")
    label = ACCION_LABELS.get(accion, accion.upper())

    # 🔔 Aviso al chat central
    texto_log = ACCION_TEXTO_LOG.get(accion, "Acción registrada por")

    mensaje_log = (
        f"📅 <b>Agenda {fecha}</b>\n"
        f"Equipo <b>{equipo}</b>\n"
        f"{texto_log} <b>{usuario}</b>\n"
        f"{icono} <b>{label}</b>"
    )


    try:
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_DEBUG,
            text=mensaje_log,
            parse_mode=Config.ParseMode.HTML
        )
    except Config.BadRequest as e:
        print(f"⚠️ No se pudo enviar log a CHAT_ID_DEBUG ({Config.CHAT_ID_DEBUG}): {e}")

    # 🧼 Feedback en el chat del equipo
    await query.edit_message_reply_markup(None)

    if accion == "ok":
        mensaje_equipo = f"✅ Agenda confirmada por {username}"

    elif accion == "error":
        mensaje_equipo = ACCION_FEEDBACK.get(
            accion,
            lambda u: f"ℹ️ Acción registrada por {u}"
        )(username)

    else:
        mensaje_equipo = f"ℹ️ Acción registrada por {username}: {accion}"

    await query.message.reply_text(mensaje_equipo)              

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
                titulo_registro = get_titulo_registro(props).strip().lower().capitalize()
                cliente = get_cliente(props)

                for p in personas or ["Sin persona"]:
                    if tipo.lower() == "visita a planta" and cliente:
                        if hora:
                            resumen_lines.append(f"      {p} | Visita {cliente} {hora}")
                        else:
                            resumen_lines.append(f"      {p} | Visita {cliente} ")

                    elif tipo.lower() in ["evento personal", "evento eproc"]:
                        if hora:
                            resumen_lines.append(f"      {p} | {titulo_registro} {hora}")
                        else:
                            resumen_lines.append(f"      {p} | {titulo_registro}")
                    else:
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
# JOB AGENDA PRELIMINAR POR EQUIPO
# ============================

async def job_agenda_preliminar_por_equipo(context: Config.CallbackContext):
    ahora = Config.datetime.now(Config.ARG_TZ)

    if not is_weekday(ahora) or ahora.date() in Config.FERIADOS:
        print("⚠️ Job agenda preliminar por equipo no ejecutado (no hábil / feriado)")
        return

    fecha = ahora.date() + Config.timedelta(days=1)

    print(f"📤 Agenda preliminar por equipo ({fecha})")

    for equipo, cfg in Config.EQUIPOS_CONFIG.items():
        chat_id = cfg.get("chat_id")
        if equipo == "General":
            continue  # ⛔ NO se evalúa, NO se procesa, NO existe acá

        if not chat_id:
            continue  # equipo sin chat asignado

        try:
            texto, regs = await Config.asyncio.to_thread(
                generar_agenda_por_fecha_y_equipo,
                fecha,
                equipo
            )

            mensaje = armar_mensaje_confirmacion(
                equipo=equipo,  # 👈 CLAVE
                fecha=fecha,
                texto_agenda=texto,
                hay_registros=bool(regs)
            )

            await context.bot.send_message(
                chat_id=chat_id,
                text=mensaje,
                parse_mode="HTML",
                reply_markup=keyboard_confirmacion_agenda(equipo, fecha)
            )

            print(f"✅ Enviado a {equipo}")

        except Exception as e:
            print(f"❌ Error enviando agenda a {equipo}: {e}")


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
