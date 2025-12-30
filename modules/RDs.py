import asyncio
import aiohttp
from datetime import datetime, timedelta
from telegram import Bot
from telegram.constants import ParseMode
import html
import Config

# --- FUNCIONES TELEGRAM ---
def telegram_escape(text: str) -> str:
    return html.escape(text or "")

async def enviar_a_telegram(mensaje_html, equipo: str):
    print(f"Enviando comentario a Telegram para {equipo}...")
    bot = Bot(token=Config.TELEGRAM_TOKEN)
    try:
        thread_id = Config.THREAD_IDS.get(equipo)
        if not thread_id:
            print(f"⚠️ No se encontró thread_id para {equipo}, se enviará al chat principal.")
            await bot.send_message(chat_id=Config.CHAT_ID, text=mensaje_html, parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(
                chat_id=Config.CHAT_ID,
                text=mensaje_html,
                parse_mode=ParseMode.HTML,
                message_thread_id=thread_id
            )
    except Exception as e:
        print("Error enviando mensaje a Telegram:", e)

# --- FUNCIONES NOTION ---
async def fetch_json(session, url, method="GET", payload=None):
    if method == "POST":
        async with session.post(url, headers=Config.HEADERS, json=payload) as resp:
            return await resp.json()
    else:
        async with session.get(url, headers=Config.HEADERS) as resp:
            return await resp.json()

# --- MAPEO DE USUARIOS ---
async def get_users_map(session):
    url = "https://api.notion.com/v1/users"
    data = await fetch_json(session, url)
    users = data.get("results", [])
    return {user["id"]: user.get("name", "Desconocido") for user in users}

# --- GET COMMENTS ---
async def get_comments(session, page_id, users_map):
    """
    Devuelve una lista de tuplas (contenido, autor) de todos los comentarios de la página,
    ignorando comentarios de usuarios llamados 'Zz'.
    """
    url = f"https://api.notion.com/v1/comments?block_id={page_id}"
    data = await fetch_json(session, url)
    results = data.get("results", [])
    comentarios_validos = []

    for comment in results:
        created_by = comment.get("created_by", {})
        autor_id = created_by.get("id")
        autor_nombre = users_map.get(autor_id, "Desconocido")

        if autor_nombre.lower() == "zz":
            continue  # ignorar comentarios de Zz

        rich_text = comment.get("rich_text", [])
        if not rich_text:
            continue

        partes = []
        for t in rich_text:
            if t.get("type") == "text":
                txt = t.get("text", {})
                plain = html.escape(txt.get("content", ""))
                link = txt.get("link")
                href = link.get("url") if isinstance(link, dict) else None
                if href:
                    partes.append(f'<a href="{href}">{plain}</a>')
                else:
                    partes.append(plain)
            elif t.get("type") == "mention":
                mention = t.get("mention", {})
                if "page" in mention:
                    linked_page_id = mention["page"]["id"]
                    title = await get_page_title(session, linked_page_id)
                    link = f"https://www.notion.so/{linked_page_id.replace('-', '')}"
                    partes.append(f'<a href="{link}">{html.escape(title)}</a>')
                else:
                    partes.append(html.escape(t.get("plain_text", "")))
            elif t.get("type") == "link_preview":
                url = t.get("href", "")
                partes.append(f'<a href="{url}">🔗</a>' if url else "🔗")
            else:
                partes.append(html.escape(t.get("plain_text", "")))

        contenido = "".join(partes).strip()
        if contenido:
            comentarios_validos.append((contenido, autor_nombre))

    return comentarios_validos


# --- OBTENER TODOS LOS COMENTARIOS VÁLIDOS ---
async def get_all_comments(session, page_id, users_map):
    url = f"https://api.notion.com/v1/comments?block_id={page_id}"
    data = await fetch_json(session, url)
    results = data.get("results", [])
    comentarios_validos = []

    for comment in results:
        created_by = comment.get("created_by", {})
        autor_id = created_by.get("id")
        autor_nombre = users_map.get(autor_id, "Desconocido")
        if autor_nombre.lower() == "zz":
            continue  # ignorar Zz

        rich_text = comment.get("rich_text", [])
        if not rich_text:
            continue

        partes = []
        for t in rich_text:
            if t.get("type") == "text":
                txt = t.get("text", {})
                plain = html.escape(txt.get("content", ""))
                link = txt.get("link")
                href = link.get("url") if isinstance(link, dict) else None
                partes.append(f'<a href="{href}">{plain}</a>' if href else plain)
            elif t.get("type") == "mention":
                mention = t.get("mention", {})
                if "page" in mention:
                    linked_page_id = mention["page"]["id"]
                    title = await get_page_title(session, linked_page_id)
                    link = f"https://www.notion.so/{linked_page_id.replace('-', '')}"
                    partes.append(f'<a href="{link}">{html.escape(title)}</a>')
                else:
                    partes.append(html.escape(t.get("plain_text", "")))
            elif t.get("type") == "link_preview":
                url = t.get("href", "")
                partes.append(f'<a href="{url}">🔗</a>' if url else "🔗")
            else:
                partes.append(html.escape(t.get("plain_text", "")))

        contenido = "".join(partes).strip()
        if contenido:
            comentarios_validos.append((autor_nombre, contenido))

    return comentarios_validos

# --- FUNCIONES AUXILIARES DE NOTION ---
async def get_page_title(session, page_id):
    data = await fetch_json(session, f"https://api.notion.com/v1/pages/{page_id}")
    for prop in data.get("properties", {}).values():
        if prop.get("type") == "title":
            title_list = prop.get("title", [])
            if title_list:
                return title_list[0].get("plain_text", "Sin nombre")
    return "Sin nombre"

async def get_page_equipo(session, page_id):
    data = await fetch_json(session, f"https://api.notion.com/v1/pages/{page_id}")
    equipo_prop = data.get("properties", {}).get("Equipo")
    if equipo_prop and equipo_prop.get("type") == "select":
        return equipo_prop.get("select", {}).get("name", "Sin equipo")
    return "Sin equipo"

async def get_page_date(session, page_id):
    data = await fetch_json(session, f"https://api.notion.com/v1/pages/{page_id}")
    date_prop = data.get("properties", {}).get("Date")
    if date_prop and date_prop.get("type") == "date":
        start = date_prop["date"].get("start", "")
        end = date_prop["date"].get("end", "")
        if start and end:
            return f"{start[:10]} → {end[:10]}"
        elif start:
            return start[:10]
    return "Sin fecha"

# --- SCRIPT PRINCIPAL ---
async def RDs_comments(concatenado: bool = True):
    mensajes = []
    async with aiohttp.ClientSession() as session:
        # Mapeo de usuarios
        users_map = await get_users_map(session)

        fecha_hoy = (datetime.now() + timedelta(days=0)).strftime('%Y-%m-%d')
        query = {"filter": {"property": "Date", "date": {"equals": fecha_hoy}}}
        data = await fetch_json(
            session,
            f"https://api.notion.com/v1/databases/{Config.DATABASE_ID}/query",
            method="POST",
            payload=query
        )
        registros = data.get('results', [])

        for equipo in Config.EQUIPOS:
            print(f"\n= Revisando comentarios RD equipo {equipo} ({fecha_hoy}) =")
            equipo_tiene_comentarios = False  # Flag para saber si hay comentarios válidos
            comentarios_equipo = []

            for registro in registros:
                relaciones_pl = registro['properties'].get('TEAM MEETING NOTES', {}).get('relation', [])
                if not relaciones_pl:
                    continue

                # Verifico si este registro corresponde al equipo actual
                procesar = False
                for pl in relaciones_pl:
                    pl_id = pl.get('id')
                    if not pl_id:
                        continue
                    equipo_pl = await get_page_equipo(session, pl_id)
                    if equipo_pl and equipo_pl.lower() == equipo.lower():
                        procesar = True
                        break
                if not procesar:
                    continue

                # Nombre y fecha del registro
                nombre_registro = registro['properties'].get('Name', {}).get('title', [])
                nombre_registro_text = nombre_registro[0]['plain_text'] if nombre_registro else "Sin nombre"
                fecha_registro = await get_page_date(session, registro['id'])
                nombre_html = telegram_escape(nombre_registro_text)
                if "MN" in nombre_registro_text.upper():
                    nombre_html = f"<b>{nombre_html}</b>"

                comentario_html = f" {nombre_html} ({fecha_registro})\n"

                # Obtengo todos los comentarios válidos
                comentarios = await get_comments(session, registro['id'], users_map)
                for contenido, autor in comentarios:
                    equipo_tiene_comentarios = True
                    comentarios_equipo.append(f"{comentario_html}<b>{html.escape(autor)} comentó:</b>\n{contenido}")

            # Genero el mensaje para el equipo
            emoji = Config.EMOJIS.get(equipo.capitalize(), "❓")
            if equipo_tiene_comentarios:
                mensaje = (
                    f"--------------------------------------------------------\n"
                    f"📌 Comentarios <b>{equipo.capitalize()} {emoji}</b>\n"
                    + "\n\n".join(comentarios_equipo)
                )
            else:
                mensaje = (
                    f"--------------------------------------------------------\n"
                    f"📌 Comentarios <b>{equipo.capitalize()} {emoji}</b>\n"
                    f"⚠️ Ningún miembro del equipo posteó un comentario de reunión diaria hoy."
                )

            if concatenado:
                mensajes.append(mensaje)
            else:
                await enviar_a_telegram(mensaje, equipo.capitalize())

        if concatenado:
            return "\n\n".join(mensajes) if mensajes else "⚠️ No se encontraron comentarios para ningún equipo."
        else:
            return "✅ Comentarios enviados a Telegram."


