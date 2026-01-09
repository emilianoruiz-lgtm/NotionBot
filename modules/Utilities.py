# ==========================================
# IMPORTS
# ==========================================

# Módulos Locales
import Config


# ==========================================
# CONFIGURACIÓN Y CONSTANTES
# ==========================================

ESPERANDO_LINK_NOTION = 801
ESPERANDO_LINK_NOTION_DB = 801

# ==========================================
# UTILIDADES DE SISTEMA Y TIEMPO
# ==========================================




# ==========================================
# HELPERS NOTION ID
# ==========================================
def detectar_tipo_notion(notion_id: str) -> str:
    """
    Devuelve: 'database', 'page' o 'unknown'
    """

    # Intentar como base de datos
    db_resp = Config.requests.get(
        f"https://api.notion.com/v1/databases/{notion_id}",
        headers=Config.HEADERS
    )
    if db_resp.status_code == 200:
        return "database"

    # Intentar como página
    page_resp = Config.requests.get(
        f"https://api.notion.com/v1/pages/{notion_id}",
        headers=Config.HEADERS
    )
    if page_resp.status_code == 200:
        return "page"

    return "unknown"

# ==========================================
# HELPERS NOTION DB PROPS
# ==========================================


# ==========================================
# FETCH  NOTION
# ==========================================
def fetch_notion_users() -> list:
    """
    Devuelve la lista cruda de usuarios del workspace Notion
    """
    r = Config.requests.get(
        "https://api.notion.com/v1/users",
        headers=Config.HEADERS
    )

    if r.status_code != 200:
        raise Exception(f"Error Notion users: {r.status_code} - {r.text}")

    return r.json().get("results", [])


def build_notion_users_map() -> dict:
    """
    Devuelve un dict:
    {
        "Nombre Apellido": "notion-user-id"
    }
    """
    users = fetch_notion_users()
    mapping = {}

    for u in users:
        name = u.get("name")
        uid = u.get("id")

        if name and uid:
            mapping[name] = uid

    return mapping


def print_notion_users_for_config():
    """
    Helper visual para copiar/pegar en Config.py
    """
    users = fetch_notion_users()

    print("\nNOTION_USERS = {")
    for u in users:
        name = u.get("name")
        uid = u.get("id")
        email = u.get("person", {}).get("email")

        if name and uid:
            print(f'    "{name}": "{uid}",  # {email}')
    print("}")



def debug_db_props(database_id: str) -> dict:
    r = Config.requests.get(
        f"https://api.notion.com/v1/databases/{database_id}",
        headers=Config.HEADERS
    )

    if r.status_code != 200:
        return {
            "ok": False,
            "error": f"Error Notion {r.status_code}: {r.text}"
        }

    db = r.json()

    props = {}
    for k, v in db["properties"].items():
        props[k] = v["type"]

    return {
        "ok": True,
        "properties": props
    }


def extraer_notion_id(url: str) -> str | None:
    """
    Extrae el ID de Notion (32 caracteres hex) desde una URL
    """
    match = Config.re.search(r"[0-9a-fA-F]{32}", url.replace("-", ""))
    return match.group(0) if match else None

# ==========================================
# WRITE  NOTION
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

# ==========================================
# SERVICIO DE DOMINIO
# ==========================================
def procesar_link_notion(url: str) -> dict:
    notion_id = extraer_notion_id(url)

    if not notion_id:
        return {
            "ok": False,
            "error": "No se pudo extraer un ID válido desde el link"
        }

    tipo = detectar_tipo_notion(notion_id)

    if tipo == "unknown":
        return {
            "ok": False,
            "error": "El ID no corresponde a una página o base de datos accesible"
        }

    return {
        "ok": True,
        "id": notion_id,
        "tipo": tipo
    }





# ==========================================
# MENÚES TELEGRAM
# ==========================================



# ==========================================
# CONVERSATION HANDLERS
# ==========================================

async def notion_id_start(update: Config.Update, context: Config.CallbackContext):
    await update.message.reply_text(
        "📎 Enviame el link de Notion\n\n"
        "Ejemplo:\n<code>https://www.notion.so/...</code>",
        parse_mode=Config.ParseMode.HTML
    )
    return ESPERANDO_LINK_NOTION

async def notion_id_recibir_link(update: Config.Update, context: Config.CallbackContext):
    url = update.message.text.strip()

    resultado = procesar_link_notion(url)

    if not resultado["ok"]:
        await update.message.reply_text(f"❌ {resultado['error']}")
        return Config.ConversationHandler.END

    tipo_emoji = "🗂️" if resultado["tipo"] == "database" else "📄"
    tipo_txt = "Base de datos" if resultado["tipo"] == "database" else "Página"

    await update.message.reply_text(
        f"{tipo_emoji} <b>{tipo_txt} detectada</b>\n\n"
        f"<b>ID:</b>\n<code>{resultado['id']}</code>",
        parse_mode=Config.ParseMode.HTML,
        disable_web_page_preview=True
    )


    return Config.ConversationHandler.END


conv_notion_id = Config.ConversationHandler(
    entry_points=[
        Config.CommandHandler("notion_id", notion_id_start)
    ],
    states={
        ESPERANDO_LINK_NOTION: [
            Config.MessageHandler(
                Config.filters.TEXT & ~Config.filters.COMMAND,
                notion_id_recibir_link
            )
        ]
    },
    fallbacks=[
        Config.CommandHandler("cancelar", Config.cancelar)
    ]
)




async def props_start(update: Config.Update, context: Config.CallbackContext):
    await update.message.reply_text(
        "📎 Enviame el link de Notion de tu BD\n\n"
        "Ejemplo:\n<code>https://www.notion.so/...</code>",
        parse_mode=Config.ParseMode.HTML
    )
    return ESPERANDO_LINK_NOTION_DB

async def props_recibir_link(update: Config.Update, context: Config.CallbackContext):
    url = update.message.text.strip()

    notion_id = extraer_notion_id(url)
    if not notion_id:
        await update.message.reply_text("❌ No se pudo extraer un ID válido")
        return Config.ConversationHandler.END

    tipo = detectar_tipo_notion(notion_id)
    if tipo != "database":
        await update.message.reply_text("❌ El link no corresponde a una base de datos")
        return Config.ConversationHandler.END

    resultado = debug_db_props(notion_id)

    if not resultado["ok"]:
        await update.message.reply_text(f"❌ {resultado['error']}")
        return Config.ConversationHandler.END

    texto = "📋 <b>Propiedades de la base</b>\n\n"
    for k, t in resultado["properties"].items():
        texto += f"• <b>{k}</b> ({t})\n"

    await update.message.reply_text(
        texto,
        parse_mode=Config.ParseMode.HTML,
        disable_web_page_preview=True
    )

    return Config.ConversationHandler.END



conv_props = Config.ConversationHandler(
    entry_points=[
        Config.CommandHandler("props", props_start)
    ],
    states={
        ESPERANDO_LINK_NOTION: [
            Config.MessageHandler(
                Config.filters.TEXT & ~Config.filters.COMMAND,
                props_recibir_link
            )
        ]
    },
    fallbacks=[
        Config.CommandHandler("cancelar", Config.cancelar)
    ]
)




async def notion_users_start(update: Config.Update, context: Config.CallbackContext):
    try:
        users = fetch_notion_users()
    except Exception as e:
        await update.message.reply_text(f"❌ Error leyendo usuarios Notion:\n{e}")
        return Config.ConversationHandler.END

    texto = (
        "👥 <b>Usuarios Notion (workspace)</b>\n\n"
        "📌 <b>USUARIOS ACTIVOS</b>\n"
        "────────────────────\n"
    )

    otros = []

    for u in users:
        name = u.get("name")
        uid = u.get("id")
        email = u.get("person", {}).get("email")

        if not name or not uid:
            continue

        if email:
            texto += (
                f'\n🙍🏻{name}:\n'
                f'      id:"{uid}",\n'
                f'      📧: "{email}"\n'
            )
        else:
            otros.append((name, uid))

    if otros:
        texto += (
            "\n\n📌 <b>OTROS USUARIOS</b>\n"
            "──────────────────────────\n"
        )
        for name, uid in otros:
            texto += f"🤖 {name}\n       id: {uid}\n\n"

    await update.message.reply_text(
        texto,
        parse_mode=Config.ParseMode.HTML,
        disable_web_page_preview=True
    )

    return Config.ConversationHandler.END





# ==========================================
# LÓGICA DE ARMADO DE AGENDA
# ==========================================




# ============================
# JOB AGENDA PRELIMINAR
# ============================


# ============================
# JOB AGENDA AUTOMÁTICA
# ============================
