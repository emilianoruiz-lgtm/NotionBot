# ==========================================
# IMPORTS
# ==========================================

# Módulos Locales
import Config


# ==========================================
# CONFIGURACIÓN Y CONSTANTES
# ==========================================



# ==========================================
# UTILIDADES DE SISTEMA Y TIEMPO
# ==========================================




# ==========================================
# HELPERS DEL DOMINIO
# ==========================================
def agregar_comentario_notion(page_id, texto):
    payload = {
        "parent": {"page_id": page_id},
        "rich_text": [{"type": "text", "text": {"content": texto}}]
    }
    response = Config.requests.post("https://api.notion.com/v1/comments", headers=Config.HEADERS, json=payload)
    if response.status_code == 200:
        print(f"Comentario agregado a la página {page_id}")
    else:
        print(f"Error agregando comentario a la página {page_id}:", response.text)

async def enviar_a_telegram(mensaje_html, equipo=None):
    bot = Config.Bot(token=Config.TELEGRAM_TOKEN)
    try:
        thread_id = Config.THREAD_IDS.get(equipo)
        kwargs = {"chat_id": Config.CHAT_ID, "text": mensaje_html, "parse_mode": Config.ParseMode.HTML}
        if thread_id: kwargs["message_thread_id"] = thread_id
        await bot.send_message(**kwargs)
    except Exception as e:
        print("Error enviando mensaje a Telegram:", e)

async def enviar_a_telegram(mensaje_html, equipo: str):
    print(f"Enviando comentario a Telegram para {equipo}...")
    bot = Config.Bot(token=Config.TELEGRAM_TOKEN)
    try:
        thread_id = Config.THREAD_IDS.get(equipo)
        if not thread_id:
            print(f"⚠️ No se encontró thread_id para {equipo}, se enviará al chat principal.")
            await bot.send_message(chat_id=Config.CHAT_ID_DEBUG, text=mensaje_html, parse_mode=Config.ParseMode.HTML)
        else:
            await bot.send_message(
                chat_id=Config.CHAT_ID,
                text=mensaje_html,
                parse_mode=Config.ParseMode.HTML,
                message_thread_id=thread_id
            )
    except Exception as e:
        print("Error enviando mensaje a Telegram:", e)

# ==========================================
# FETCH NOTION
# ==========================================
def get_registros_hoy(database_id=Config.DATABASE_ID):
    """Obtiene registros RD del día actual."""
    fecha_hoy = Config.datetime.now().strftime('%Y-%m-%d')
    query = {"filter": {"property": "Date","date":{"equals": fecha_hoy}}}
    r = Config.requests.post(f"https://api.notion.com/v1/databases/{database_id}/query",
                      headers=Config.HEADERS, json=query)
    data = r.json()
    return data.get('results', [])

def copiar_bloques_recursivo_completo(orig_id, target_id):
    r = Config.requests.get(f"https://api.notion.com/v1/blocks/{orig_id}/children", headers=Config.HEADERS)
    bloques = r.json().get('results', [])
    for bloque in bloques:
        bloque_nuevo = {"type": bloque['type']}
        tipo = bloque['type']

        if tipo in ['paragraph','heading_1','heading_2','heading_3',
                     'bulleted_list_item','numbered_list_item','to_do','quote','callout','code','toggle']:
            if bloque[tipo].get('text') is not None:
                bloque_nuevo[tipo] = bloque[tipo]
            else:
                continue
        elif tipo in ['image','file','video','pdf','audio','embed','bookmark']:
            contenido = bloque.get(tipo)
            if contenido:
                bloque_nuevo[tipo] = contenido
            else:
                continue
        elif tipo in ['divider','breadcrumb','table_of_contents','synced_block','template']:
            bloque_nuevo[tipo] = {}
        elif tipo in ['table','column_list','column','table_row']:
            bloque_nuevo[tipo] = bloque.get(tipo, {})
        else:
            continue

        post = Config.requests.patch(f"https://api.notion.com/v1/blocks/{target_id}/children",
                              headers=Config.HEADERS, json={"children":[bloque_nuevo]})
        if post.status_code != 200:
            print("Error copiando bloque:", post.text)
            continue

        if bloque.get('has_children', False):
            nuevo_bloque_id = post.json()['results'][0]['id']
            copiar_bloques_recursivo_completo(bloque['id'], nuevo_bloque_id)


# ==========================================
# WRITE NOTION
# ==========================================

def duplicar_registro_completo(registro):
    propiedades_orig = registro['properties']
    propiedades_nuevas = {}

    for key, value in propiedades_orig.items():
        tipo = value['type']
        if key == 'Type':
            propiedades_nuevas[key] = {'multi_select': [{'name': 'SPC'}, {'name': 'SPR'}]}
        elif tipo == 'title':
            propiedades_nuevas[key] = {'title': [{'text': {'content': value['title'][0]['plain_text']}}]}
        elif tipo in ['rich_text', 'number', 'select', 'multi_select', 'date', 'relation']:
            propiedades_nuevas[key] = {tipo: value[tipo]}

    # --- Fecha duplicado ---
    hoy = Config.datetime.now()
    if hoy.weekday() == 4:  # viernes
        dias_hasta_lunes = (7 - hoy.weekday()) % 7 or 7
        fecha_duplicado = hoy + Config.timedelta(days=dias_hasta_lunes)
    else:
        fecha_duplicado = hoy + Config.timedelta(days=1)
    fecha_duplicado_str = fecha_duplicado.strftime('%Y-%m-%d')

    if 'Date' in propiedades_nuevas:
        propiedades_nuevas['Date']['date']['start'] = fecha_duplicado_str
        if 'end' in propiedades_nuevas['Date']['date'] and propiedades_nuevas['Date']['date']['end']:
            try:
                end_dt = Config.datetime.fromisoformat(propiedades_nuevas['Date']['date']['end'])
                delta = end_dt.date() - hoy.date()
                propiedades_nuevas['Date']['date']['end'] = (fecha_duplicado + Config.timedelta(days=delta.days)).strftime('%Y-%m-%d')
            except Exception as e:
                print("No se pudo mantener la duración del registro:", e)

    icono = registro.get('icon', None)
    data = {"parent": {"database_id": Config.DATABASE_ID}, "properties": propiedades_nuevas}
    if icono:
        data['icon'] = icono

    response = Config.requests.post("https://api.notion.com/v1/pages", headers=Config.HEADERS, json=data)
    nueva_pagina = response.json()
    nueva_page_id = nueva_pagina['id']

    copiar_bloques_recursivo_completo(registro['id'], nueva_page_id)

    # Agregar comentario "Actualizado!"
    agregar_comentario_notion(nueva_page_id, "Registro creado!")

    # Obtener equipo (select)
    equipo_select = propiedades_nuevas.get('Equipo', {}).get('select', {}).get('name', None)


    print("Registro duplicado con todo el contenido:", nueva_page_id)
    return nueva_pagina, equipo_select

def actualizar_type_spc(registro):
    propiedades = {"Type": {"multi_select": [{"name": "SPC"}]}}
    page_id = registro['id']
    response = Config.requests.patch(f"https://api.notion.com/v1/pages/{page_id}",
                              headers=Config.HEADERS, json={"properties": propiedades})
    print(f"Registro {page_id} actualizado a solo 'SPC':", response.status_code)
    return response.json()

# ==========================================
# SERVICIO DE DOMINIO
# ==========================================




# ==========================================
# MENÚES TELEGRAM
# ==========================================



# ==========================================
# CONVERSATION HANDLERS
# ==========================================
async def newburnreg(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(Config.ARG_TZ).strftime('%d/%m/%y %H:%M')} - Newday manual")

    if update.message:
        reply = update.message.reply_text
    else:
        reply = update.callback_query.message.reply_text
    await newday()
    await reply("✔️ Nuevos registros de Burndown creados en Notion", parse_mode=Config.ParseMode.HTML)

    return Config.ConversationHandler.END




# ==========================================
# LÓGICA DE NEWDAY
# ==========================================
async def newday():
    registros = get_registros_hoy()

    equipos_procesados = set()

    for registro in registros:
        print(f"Borrando SPC en registro")
        actualizar_type_spc(registro)
        print(f"Duplicando registro, actualizando fecha/SPC ")
        nueva_pagina, equipo = duplicar_registro_completo(registro)
        
        if equipo:
            equipos_procesados.add(equipo)
        print("Registro duplicado correctamente")
        equipos_texto = equipo if equipo else "Sin equipo"

        # Obtener fecha del registro duplicado
        fecha_rd = None
        date_prop = nueva_pagina.get('properties', {}).get('Date', {}).get('date')
        if date_prop and 'start' in date_prop:
            fecha_rd = date_prop['start']

        comentario = f"\n<b>Registro RD creado para {equipos_texto}"
        if fecha_rd:
            comentario += f" (fecha: {fecha_rd})"
        comentario += "</b>"

        await enviar_a_telegram(comentario, equipo)

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









