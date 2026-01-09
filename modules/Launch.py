# ==========================================
# launch.PY
# Crea un registro por equipo y lo asocia al próximo sprint
# ==========================================

# ==========================================
# IMPORTS
# ==========================================
import Config




# ==========================================
# CONFIGURACIÓN Y CONSTANTES
# ==========================================
EQUIPOS_OMITIDOS = {
    "Caimanes",
    "Huemules",
    "Zorros",
    "General",
    "Admin"
}

DATABASE_ID_PLANNING = Config.DATABASE_ID_PLAN
DATABASE_ID_MEETINGS = Config.DATABASE_ID_MEETINGS

PLANNING_TEAM_PROP = "Equipo"
MEETING_TEAM_PROP = "Equipo"

PLANNING_MEETING_REL_PROP = "TEAM MEETING NOTES"
SPRINT_PROP = "SPRINTS"

# ==========================================
# HELPERS
# ==========================================

def get_plannings_equipo_sprint(equipo, sprint_id):
    payload = {
        "filter": {
            "and": [
                {
                    "property": PLANNING_TEAM_PROP,
                    "multi_select": {"contains": equipo}
                },
                {
                    "property": SPRINT_PROP,
                    "relation": {"contains": sprint_id}
                }
            ]
        }
    }

    r = Config.requests.post(
        f"https://api.notion.com/v1/databases/{DATABASE_ID_PLANNING}/query",
        headers=Config.HEADERS,
        json=payload
    )

    results = r.json().get("results", [])
    print(f"🔍 Buscando plannings | Equipo={equipo} | Sprint={sprint_id}")
    print(f"➡️ Resultados: {len(results)}")

    return results




# ==========================================
# FETCH NOTION
# ==========================================

def get_team_meeting(equipo, sprint_id):
    print("🔎 DEBUG TEAM MEETING")
    print("Equipo buscado:", equipo)
    print("Sprint ID:", sprint_id)
    print("DB MEETINGS:", Config.DATABASE_ID_MEETINGS)
    
    payload = {
        "filter": {
            "and": [
                {
                    "property": MEETING_TEAM_PROP,
                    "select": {"equals": equipo}
                },
                {
                    "property": SPRINT_PROP,
                    "relation": {"contains": sprint_id}
                }
            ]
        },
        "page_size": 1
    }

    r = Config.requests.post(
        f"https://api.notion.com/v1/databases/{DATABASE_ID_MEETINGS}/query",
        headers=Config.HEADERS,
        json=payload
    )

    results = r.json().get("results", [])

    data = r.json()
    print("Resultados encontrados:", len(data.get("results", [])))


    return results[0] if results else None

def get_sprint_activo():
    hoy = Config.datetime.now(Config.ARG_TZ).date()

    r = Config.requests.post(
        f"https://api.notion.com/v1/databases/{Config.DATABASE_ID_SPRINTS}/query",
        headers=Config.HEADERS,
        json={}
    )

    for sprint in r.json().get("results", []):
        date = sprint["properties"]["Date"]["date"]
        if not date:
            continue

        start = Config.datetime.fromisoformat(date["start"]).date()
        end = Config.datetime.fromisoformat(date["end"]).date()

        if start <= hoy <= end:
            return sprint

    return None




# ==========================================
# WRITE NOTION
# ==========================================

def vincular_planning_a_meeting(planning_id, meeting_id):
    payload = {
        "properties": {
            PLANNING_MEETING_REL_PROP: {
                "relation": [{"id": meeting_id}]
            }
        }
    }

    r = Config.requests.patch(
        f"https://api.notion.com/v1/pages/{planning_id}",
        headers=Config.HEADERS,
        json=payload
    )

    if r.status_code != 200:
        print("❌ Error vinculando planning a meeting:", r.text)



# ==========================================
# CONVERSATION HANDLERS
# ==========================================
def build_equipos_keyboard(omitidos=None):
    if omitidos is None:
        omitidos = set()

    buttons = []

    for equipo, cfg in Config.EQUIPOS_CONFIG.items():
        if equipo in omitidos:
            continue

        label = f"{cfg.get('emoji', '')} {cfg.get('display_name', equipo)}".strip()

        buttons.append([
            Config.InlineKeyboardButton(
                text=label,
                callback_data=f"launch_equipo:{equipo}"
            )
        ])

    return Config.InlineKeyboardMarkup(buttons)

async def elegir_equipo(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    keyboard = build_equipos_keyboard(
        omitidos= EQUIPOS_OMITIDOS  # o EQUIPOS_OMITIDOS si querés
    )

    await update.message.reply_text(
        "🧭 <b>Seleccioná equipo para el launch</b>",
        reply_markup=keyboard,
        parse_mode=Config.ParseMode.HTML
    )


async def launch_equipo(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data  # ej: "launch_equipo:Huemules"
    _, equipo = data.split(":", 1)

    sprint = get_sprint_activo()

    if not sprint:
        await query.edit_message_text("❌ No hay sprint activo")
        return

    # 👉 acá llamás TU lógica real
    await launch_para_equipo(sprint, equipo)

    await query.edit_message_text(
        f"🚀 <b>Launch ejecutado para {equipo}</b>",
        parse_mode=Config.ParseMode.HTML
    )

async def launch_para_equipo(sprint, equipo):
    sprint_id = sprint["id"]
    procesar_equipo_en_sprint(equipo, sprint_id)



async def launch_handler(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    """Handler Telegram para ejecutar launch con confirmación"""
    print(f"[CMD] {Config.datetime.now(Config.ARG_TZ).strftime('%d/%m/%y %H:%M')} - launch manual")
    
    if update.message:
        reply = update.message.reply_text
    else:
        reply = update.callback_query.message.reply_text

    await launch()
    

    await reply(
        "🚀 <b>launch ejecutado</b>\n"
        "Se crearon registros por equipo para el sprint correspondiente.",
        parse_mode=Config.ParseMode.HTML
    )

    return Config.ConversationHandler.END


# ==========================================
# SERVICIO DE DOMINIO
# ==========================================

def procesar_equipo_en_sprint(equipo, sprint_id):
    meeting = get_team_meeting(equipo, sprint_id)
    if not meeting:
        print(f"⚠️ No hay TEAM MEETING para {equipo}")
        return False

    plannings = get_plannings_equipo_sprint(equipo, sprint_id)

    if not plannings:
        print(f"ℹ️ No hay plannings para {equipo}")
        return True

    for planning in plannings:
        vincular_planning_a_meeting(planning["id"], meeting["id"])
        print(f"🔗 Planning {planning['id']} → Meeting {equipo}")

    return True

async def launch():
    sprint = get_sprint_activo()
    if not sprint:
        print("❌ launch cancelado: no hay sprint")
        return

    sprint_id = sprint["id"]
    print(f"🚀 Ejecutando launch para sprint {sprint_id}")

    procesados = 0

    for equipo in Config.EQUIPOS_CONFIG:
        if equipo in EQUIPOS_OMITIDOS:
            continue

        ok = procesar_equipo_en_sprint(equipo, sprint_id)
        if ok:
            procesados += 1

    print(f"✅ Launch finalizado | Equipos procesados: {procesados}")
