# ==========================================
# DEPLOY.PY
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
    "Alpha Squad",
    "Delta Force",
    "Bravo Team",
    "General",
    "Admin"
}
SPRINT_RELATION_PROP = "SPRINT"

# ==========================================
# HELPERS
# ==========================================
def set_relation(page_id, prop_id, ids):
    payload = {
        "properties": {
            prop_id: {
                "relation": [{"id": i} for i in ids]
            }
        }
    }
    return Config.requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=Config.HEADERS,
        json=payload
    )

def es_dia_habil(fecha):
    # weekday(): 0=lunes ... 6=domingo
    if fecha.weekday() >= 5:
        return False

    if fecha in Config.FERIADOS:
        return False

    return True

def primer_dia_habil(fecha):
    d = fecha
    while not es_dia_habil(d):
        d += Config.timedelta(days=1)
    return d

def hoy_es_primer_dia_habil_del_sprint(sprint):
    hoy = Config.datetime.now(Config.ARG_TZ).date()

    sprint_start = Config.datetime.fromisoformat(
        sprint['properties']['Date']['date']['start']
    ).date()

    primer_habil = primer_dia_habil(sprint_start)

    print(f"📅 Sprint start: {sprint_start}")
    print(f"📅 Primer hábil: {primer_habil}")
    print(f"📅 Hoy: {hoy}")

    return hoy == primer_habil

async def deploy_con_sprint(sprint):
    print("🚀 Deploy iniciado")

    template = get_template_deploy()
    template_meet = get_template_meeting_deploy()

    if not template:
        print("❌ Deploy cancelado: no hay template burn")
        return
    
    if not template_meet:
        print("❌ Deploy cancelado: no hay template meet")
        return

    sprint_id = sprint['id']
    sprint_nombre = sprint['properties']['Name']['title'][0]['plain_text']
    sprint_date = sprint['properties']['Date']['date']

    for equipo in Config.EQUIPOS_CONFIG:
        if equipo in EQUIPOS_OMITIDOS:
            continue

        hab_days = get_formula_value(sprint, "HabDays")

        if hab_days is None:
            print("❌ Sprint sin HabDays, deploy cancelado")
            return

        burn = crear_registro_equipo(
            template=template,
            equipo=equipo,
            sprint_id=sprint_id,
            sprint_nombre=sprint_nombre,
            sprint_date=sprint_date,
            hab_days=hab_days
        )

        if not burn:
            print(f"❌ No se creó burn para {equipo}")
            continue

        vincular_registro_a_sprint(sprint_id, burn["id"])

        meeting = crear_registro_meet_equipo(
            template=template_meet,
            equipo=equipo,
            sprint_nombre=sprint_nombre,
            sprint_date=sprint_date,
            sprint_id=sprint_id,
        )

        if meeting:
            vincular_burn_a_meeting(burn["id"], meeting["id"])

        

    print("✅ Deploy finalizado")

def get_attendees_for_equipo(equipo):
    integrantes = Config.EQUIPOS_CONFIG.get(equipo, {}).get("integrantes", [])
    people = []

    for nombre in integrantes:
        user_id = Config.NOTION_USERS.get(nombre)
        if user_id:
            people.append({"id": user_id})
        else:
            print(f"⚠️ Usuario Notion no encontrado para: {nombre}")

    return people

# ==========================================
# FETCH NOTION
# ==========================================
def debug_db_props(database_id):
    r = Config.requests.get(
        f"https://api.notion.com/v1/databases/{database_id}",
        headers=Config.HEADERS
    )
    db = r.json()
    print("📋 PROPIEDADES DE LA DB: MEETINGS")
    for name, prop in db["properties"].items():
        pid = prop.get("id")
        print(f"- {name} ({prop['type']}) -> id: {pid}")

def get_formula_value(page, prop_name):
    prop = page["properties"].get(prop_name)
    if not prop or prop["type"] != "formula":
        return None

    formula = prop["formula"]
    return formula.get(formula["type"])

def get_sprint_para_deploy_manual(database_id=Config.DATABASE_ID_SPRINTS):
    """
    Pensado para /deploy manual.
    Busca:
    - sprint que empieza hoy
    - si no existe, el próximo sprint (próximo lunes)
    """
    hoy = Config.datetime.now(Config.ARG_TZ).date()

    def query_por_fecha(fecha):
        return {
            "filter": {
                "property": "Date",
                "date": {"equals": fecha.strftime('%Y-%m-%d')}
            }
        }

    # Sprint que empieza hoy
    r = Config.requests.post(
        f"https://api.notion.com/v1/databases/{database_id}/query",
        headers=Config.HEADERS,
        json=query_por_fecha(hoy)
    )
    results = r.json().get('results', [])
    if results:
        return results[0]

    # Próximo lunes
    dias_hasta_lunes = (7 - hoy.weekday()) % 7
    if dias_hasta_lunes == 0:
        dias_hasta_lunes = 7
    proximo_lunes = hoy + Config.timedelta(days=dias_hasta_lunes)

    r = Config.requests.post(
        f"https://api.notion.com/v1/databases/{database_id}/query",
        headers=Config.HEADERS,
        json=query_por_fecha(proximo_lunes)
    )
    results = r.json().get('results', [])
    if results:
        return results[0]

    return None

def get_sprint_activo_para_job(database_id=Config.DATABASE_ID_SPRINTS):
    """
    Pensado para job_deploy.
    Devuelve el sprint cuyo Date.start sea <= hoy,
    tomando el más reciente.
    """
    hoy = Config.datetime.now(Config.ARG_TZ).date()

    payload = {
        "filter": {
            "property": "Date",
            "date": {
                "on_or_before": hoy.strftime('%Y-%m-%d')
            }
        },
        "sorts": [
            {
                "property": "Date",
                "direction": "descending"
            }
        ],
        "page_size": 1
    }

    r = Config.requests.post(
        f"https://api.notion.com/v1/databases/{database_id}/query",
        headers=Config.HEADERS,
        json=payload
    )

    results = r.json().get("results", [])
    if results:
        return results[0]

    return None

def get_template_deploy(page_id=Config.TEMPLATE_DEPLOY_PAGE_ID):
    r = Config.requests.get(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=Config.HEADERS
    )

    if r.status_code != 200:
        print("❌ No se pudo obtener template deploy:", r.text)
        return None

    return r.json()

def get_template_meeting_deploy(page_id=Config.TEMPLATE_TEAM_MEET_PAGE_ID):
    r = Config.requests.get(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=Config.HEADERS
    )

    if r.status_code != 200:
        print("❌ No se pudo obtener template deploy:", r.text)
        return None

    return r.json()

# ==========================================
# WRITE NOTION
# ==========================================

def crear_registro_equipo(template, equipo, sprint_id, sprint_nombre, sprint_date, hab_days):

    """Crea un registro nuevo para un equipo específico"""

    props_base = template['properties']
    nuevas_props = {}


    for key, value in props_base.items():
        tipo = value['type']

        if key == SPRINT_RELATION_PROP:
            nuevas_props[key] = {
                "relation": [{"id": sprint_id}]
            }

        elif key == 'Equipo':
            nuevas_props[key] = {
                'select': {'name': equipo}
            }

        elif key == 'Cant. Integrantes':
            nuevas_props[key] = {
                'number': len(Config.EQUIPOS_CONFIG.get(equipo, {}).get('integrantes', []))
            }
        
        elif key == 'Target':
            integrantes = len(Config.EQUIPOS_CONFIG.get(equipo, {}).get('integrantes', []))
            nuevas_props[key] = {
                'number': round(integrantes * 0.8 * hab_days, 2)
            }

        elif key == 'Type':
            nuevas_props[key] = {
                'multi_select': [
                    {'name': 'SPR'},
                    {'name': 'SPC'}
                ]
            }

        elif tipo == 'title':
            texto = value['title'][0]['plain_text'] if value['title'] else ''
            nuevas_props[key] = {
                'title': [{'text': {'content': f"RD {equipo}"}}]
            }

        elif key == 'Date':
            nuevas_props[key] = {
                'date': {
                    'start': sprint_date.get('start'),
                }
            }


        elif tipo in ['rich_text','number','select','multi_select','date','relation']:
            nuevas_props[key] = {tipo: value[tipo]}



    data = {
        "parent": {"database_id": Config.DATABASE_ID},
        "properties": nuevas_props
    }

    if template.get('icon'):
        data['icon'] = template['icon']

    r = Config.requests.post(
        "https://api.notion.com/v1/pages",
        headers=Config.HEADERS,
        json=data
    )

    if r.status_code != 200:
        print("❌ Error creando página:", r.text)
        return None

    nueva = r.json()

    if not nueva or 'id' not in nueva:
        print("❌ Página creada sin ID:", nueva)
        return None
    
    print(f"📄 Copiando contenido del TEMPLATE_MEETING {template['id']} → {nueva['id']}")

    copiar_bloques_recursivo_completo(template['id'], nueva['id'])
    agregar_comentario_notion(nueva['id'], f"Registro inicial {sprint_nombre} {equipo} creado!")

    return nueva

def crear_registro_meet_equipo(template, equipo, sprint_nombre, sprint_date, sprint_id):

    attendees = get_attendees_for_equipo(equipo)

    nuevas_props = {
        "Meeting name": {
            "title": [{
                "text": {
                    "content": f"Planning {equipo} – {sprint_nombre}"
                }
            }]
        },
        "Date": {
            "date": {
                "start": sprint_date["start"]
            }
        },
        "Equipo": {
            "select": {
                "name": equipo
            }
        },
        "Category": {
            "multi_select": [
                {"name": "Planning"}
            ]
        },
    }

    if attendees:
        nuevas_props["Attendees"] = {
            "people": attendees
        }

    data = {
        "parent": {"database_id": Config.DATABASE_ID_MEETINGS},
        "properties": nuevas_props
    }

    if template.get("icon"):
        data["icon"] = template["icon"]

    r = Config.requests.post(
        "https://api.notion.com/v1/pages",
        headers=Config.HEADERS,
        json=data
    )

    if r.status_code != 200:
        print("❌ Error creando meeting:", r.text)
        return None

    nueva = r.json()

    copiar_bloques_recursivo_completo(template["id"], nueva["id"])
    agregar_comentario_notion(
        nueva["id"],
        f"Registro inicial {sprint_nombre} {equipo} creado!"
    )

    return nueva


def agregar_comentario_notion(page_id, texto):
    payload = {
        "parent": {"page_id": page_id},
        "rich_text": [{"type": "text", "text": {"content": texto}}]
    }
    r = Config.requests.post(
        "https://api.notion.com/v1/comments",
        headers=Config.HEADERS,
        json=payload
    )
    if r.status_code != 200:
        print("Error agregando comentario:", r.text)

def copiar_bloques_recursivo_completo(orig_id, target_id):
    print(f"📦 Copiando bloques desde {orig_id}")
    r = Config.requests.get(
        f"https://api.notion.com/v1/blocks/{orig_id}/children",
        headers=Config.HEADERS
    )
    bloques = r.json().get('results', [])

    for bloque in bloques:
        tipo = bloque['type']
        bloque_nuevo = {"type": tipo}

        if tipo in [
            'paragraph','heading_1','heading_2','heading_3',
            'bulleted_list_item','numbered_list_item','to_do',
            'quote','callout','code','toggle'
        ]:
            bloque_nuevo[tipo] = bloque.get(tipo, {})

        elif tipo in ['divider','breadcrumb','table_of_contents']:
            bloque_nuevo[tipo] = {}

        elif tipo in ['image','file','video','pdf','audio','embed','bookmark']:
            bloque_nuevo[tipo] = bloque.get(tipo)

        else:
            continue

        post = Config.requests.patch(
            f"https://api.notion.com/v1/blocks/{target_id}/children",
            headers=Config.HEADERS,
            json={"children": [bloque_nuevo]}
        )

        if post.status_code != 200:
            print("Error copiando bloque:", post.text)
            continue

        if bloque.get('has_children'):
            nuevo_id = post.json()['results'][0]['id']
            copiar_bloques_recursivo_completo(bloque['id'], nuevo_id)

def vincular_burn_a_meeting(burn_id, meeting_id):
    payload = {
        "properties": {
            "SPRINTS GENERAL ": {   
                "relation": [{"id": burn_id}]
            }
        }
    }

    r = Config.requests.patch(
        f"https://api.notion.com/v1/pages/{meeting_id}",
        headers=Config.HEADERS,
        json=payload
    )

    if r.status_code != 200:
        print("❌ Error vinculando meeting a burn:", r.text)

def vincular_registro_a_sprint(sprint_id, burn_id):
    # 1️⃣ Traer sprint actual
    r = Config.requests.get(
        f"https://api.notion.com/v1/pages/{sprint_id}",
        headers=Config.HEADERS
    )

    if r.status_code != 200:
        print("❌ Error leyendo sprint:", r.text)
        return

    sprint = r.json()

    actuales = (
        sprint["properties"]
        .get("BURNDOWN", {})
        .get("relation", [])
    )

    # 2️⃣ Agregar el nuevo burn si no está
    ids = {rel["id"] for rel in actuales}
    if burn_id not in ids:
        actuales.append({"id": burn_id})

    # 3️⃣ Reescribir la relación completa
    payload = {
        "properties": {
            "BURNDOWN": {
                "relation": actuales
            }
        }
    }

    r = Config.requests.patch(
        f"https://api.notion.com/v1/pages/{sprint_id}",
        headers=Config.HEADERS,
        json=payload
    )

    if r.status_code != 200:
        print("❌ Error vinculando burn al sprint:", r.text)


# ==========================================
# SERVICIO DE DOMINIO
# ==========================================

async def deploy_handler(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    """Handler Telegram para ejecutar Deploy con confirmación"""
    print(f"[CMD] {Config.datetime.now(Config.ARG_TZ).strftime('%d/%m/%y %H:%M')} - Deploy manual")
    debug_db_props(Config.DATABASE_ID_MEETINGS)
    if update.message:
        reply = update.message.reply_text
    else:
        reply = update.callback_query.message.reply_text

    await deploy()
    

    await reply(
        "🚀 <b>Deploy ejecutado</b>\n"
        "Se crearon registros por equipo para el sprint correspondiente.",
        parse_mode=Config.ParseMode.HTML
    )

    return Config.ConversationHandler.END



async def deploy():




    sprint = get_sprint_para_deploy_manual()
    if not sprint:
        print("❌ Deploy cancelado: no hay sprint")
        return

    await deploy_con_sprint(sprint)



# ==========================================
# JOB DEPLOY
# ==========================================

async def job_deploy(context):
    hoy = Config.datetime.now(Config.ARG_TZ).date()

    if not es_dia_habil(hoy):
        print("⏭ job_deploy: hoy no es día hábil")
        return

    sprint = get_sprint_activo_para_job()
    if not sprint:
        print("⏭ job_deploy: no hay sprint activo")
        return

    if not hoy_es_primer_dia_habil_del_sprint(sprint):
        print("⏭ job_deploy: hoy no es el primer día hábil del sprint")
        return

    print("🚀 job_deploy ejecutado correctamente")
    await deploy_con_sprint(sprint)

