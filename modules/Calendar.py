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


# ==========================================
# HELPERS
# ==========================================
def get_equipos_validos():
    return [
        equipo for equipo in Config.EQUIPOS_CONFIG.keys()
        if equipo not in EQUIPOS_OMITIDOS
    ]

def people_from_integrantes(integrantes: list[str]):
    """
    Convierte nombres de personas a formato Notion people[]
    Requiere un mapping nombre -> notion_user_id
    """
    people = []
    for nombre in integrantes:
        user_id = Config.NOTION_USERS.get(nombre)
        if user_id:
            people.append({"id": user_id})
    return people

def feriados_en_sprint(start: str, end: str):
    inicio = Config.datetime.fromisoformat(start).date()
    fin = Config.datetime.fromisoformat(end).date()

    return sorted(
        f for f in Config.FERIADOS
        if inicio <= f <= fin
    )

def build_meet_payload(nombre, fecha, equipo, people, tipo):
    return {
        "parent": {"database_id": Config.DATABASE_ID_CALENDAR},
        "properties": {
            "Name": {
                "title": [{"text": {"content": nombre}}]
            },
            "Date": {
                "date": {"start": fecha}
            },
            "Tipo": {
                "select": {"name": tipo}
            },
            "Equipo": {
                "multi_select": [{"name": equipo}]
            },
            "Person": {
                "people": people
            },
            "Confirmado": {
                "checkbox": False
            }
        }
    }


# ==========================================
# FETCH NOTION
# ==========================================
def get_proximo_sprint_desde_notion():
    today = Config.datetime.now(Config.ARG_TZ).date().isoformat()

    payload = {
        "filter": {
            "property": "Date",
            "date": {"after": today}
        },
        "sorts": [
            {
                "property": "Date",
                "direction": "ascending"
            }
        ],
        "page_size": 2   # ⬅️ clave
    }

    r = Config.requests.post(
        f"https://api.notion.com/v1/databases/{Config.DATABASE_ID_SPRINTS}/query",
        headers=Config.HEADERS,
        json=payload
    )

    if r.status_code != 200:
        raise RuntimeError(
            f"Error consultando sprints: {r.status_code} - {r.text}"
        )

    results = r.json().get("results", [])
    if not results:
        raise RuntimeError("No se encontró próximo sprint")

    sprint_actual = results[0]
    start = sprint_actual["properties"]["Date"]["date"]["start"]

    if len(results) > 1:
        siguiente = results[1]
        next_start = siguiente["properties"]["Date"]["date"]["start"]

        end = (
            Config.datetime.fromisoformat(next_start).date()
            - Config.timedelta(days=1)
        ).isoformat()
    else:
        # fallback defensivo
        end = start

    return {
        "id": sprint_actual["id"],
        "start": start,
        "end": end
    }




def crear_meet(payload: dict):
    r = Config.requests.post(
        "https://api.notion.com/v1/pages",
        headers=Config.HEADERS,
        json=payload
    )

    if r.status_code != 200:
        raise Exception(f"Error creando meet: {r.status_code} - {r.text}")

    return r.json()


def crear_feriado(fecha, nombre="Feriado"):
    payload = {
        "parent": {"database_id": Config.DATABASE_ID_CALENDAR},
        "properties": {
            "Name": {
                "title": [{"text": {"content": f"❌ {nombre}"}}]
            },
            "Date": {
                "date": {"start": fecha.isoformat()}
            },
            "Tipo": {
                "select": {"name": "Feriado"}
            },
            "Confirmado": {
                "checkbox": True
            }
        }
    }

    crear_meet(payload)



# ==========================================
# WRITE NOTION
# ==========================================
async def insertar_meets():
    sprint = get_proximo_sprint_desde_notion()
    fecha_inicio = sprint["start"]
    fecha_fin = sprint["end"]

    # ⬅️ PRIMERO convertir a date
    fecha_inicio_dt = Config.datetime.fromisoformat(fecha_inicio).date()

    # Derivadas
    fecha_gr = (fecha_inicio_dt + Config.timedelta(days=7)).isoformat()
    fecha_adm = (fecha_inicio_dt + Config.timedelta(days=1)).isoformat()
    fecha_burn = (fecha_inicio_dt + Config.timedelta(days=2)).isoformat()
    fecha_burn2 = (fecha_inicio_dt + Config.timedelta(days=9)).isoformat()

    # 1️⃣ Meets por equipo (PL + GR)
    for equipo in get_equipos_validos():
        integrantes = Config.EQUIPOS_CONFIG[equipo].get("integrantes", [])
        people = people_from_integrantes(integrantes)

        # PL
        crear_meet(
            build_meet_payload(
                nombre=f"📐 PL {equipo}",
                fecha=fecha_inicio,
                equipo=equipo,
                people=people,
                tipo= "Planning"
            )
        )

        # GR (+7 días)
        crear_meet(
            build_meet_payload(
                nombre=f"🔭 GR {equipo}",
                fecha=fecha_gr,
                equipo=equipo,
                people=people,
                tipo= "Grooming"
            )
        )

    # 2️⃣ Reunión ADM (global)
    crear_meet(
        build_meet_payload(
            nombre="📐 ADM",
            fecha=fecha_adm,
            equipo="Admin",
            people=people_from_integrantes([
                "Emiliano Ruiz",
                "Darío De Cáneva",
                "Carla Carucci",
                "Victoria "
            ]),
            tipo= "Planning"
        )
    )

    # 3️⃣ Reunión BURN (global)
    crear_meet(
        build_meet_payload(
            nombre="🔍 BURN CHECK",
            fecha=fecha_burn,
            equipo="Admin",
            people=people_from_integrantes([
                "Emiliano Ruiz",
                "Darío De Cáneva"
            ]),
            tipo="Reunión Interna"
        )
    )

    # 4️⃣ Reunión BURN2
    crear_meet(
        build_meet_payload(
            nombre="🔍 BURN CHECK",
            fecha=fecha_burn2,
            equipo="Admin",
            people=people_from_integrantes([
                "Emiliano Ruiz",
                "Darío De Cáneva"
            ]),
            tipo="Reunión Interna"
        )
    )


    # 4️⃣ Feriados del sprint
    feriados = feriados_en_sprint(fecha_inicio, fecha_fin)
    for feriado in feriados:
        crear_feriado(feriado)








# ==========================================
# CONVERSATION HANDLERS
# ==========================================

async def deploy_Calendar(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await insertar_meets()

    await query.edit_message_text(
        f"📅 <b>Calendar creado para todos los equipos</b>",
        parse_mode=Config.ParseMode.HTML
    )





async def deploy_calendar_handler(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(Config.ARG_TZ).strftime('%d/%m/%y %H:%M')} - Deploy Calendar manual")

    await insertar_meets()

    await update.message.reply_text(
        "📅 <b>Deploy Calendar ejecutado</b>\n"
        "Se crearon reuniones por equipo para el próximo sprint.",
        parse_mode=Config.ParseMode.HTML
    )

    return Config.ConversationHandler.END


# ==========================================
# SERVICIO DE DOMINIO
# ==========================================

