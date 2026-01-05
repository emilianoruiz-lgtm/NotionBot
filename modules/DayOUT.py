# ==========================================
# 1. IMPORTS
# ==========================================

# Módulos Locales
import Config
from modules.CurvaParcial import generar_curva_parcial_equipo


# ==========================================
# CONFIGURACIÓN Y CONSTANTES
# ==========================================
ESPERANDO_EQUIPO_DAYOUT = 200
MODE_PROD = "prod"
MODE_TEST = "test"

# ==========================================
# UTILIDADES DE SISTEMA Y TIEMPO
# ==========================================




# ==========================================
# FUNCIONES DE DOMINIO (DAYOUT)
# ==========================================


async def upload_image_temporal(buf, bot, chat_id):
    sent_photo = await bot.send_photo(chat_id=chat_id, photo=Config.InputFile(buf, filename="curva.png"))
    file_id = sent_photo.photo[-1].file_id
    file_info = await bot.get_file(file_id)
    return file_info.file_path  

def telegram_escape(text: str) -> str:
    return Config.html.escape(text)

def notion_page_url(page_id: str) -> str:
    return f"https://www.notion.so/{page_id.replace('-', '')}"

async def enviar_a_telegram(mensaje_html, equipo: str):
    print(f"Enviando comentario a Telegram para {equipo}...")
    bot = Config.Bot(token=Config.TELEGRAM_TOKEN)
    try:
        thread_id = Config.THREAD_IDS.get(equipo)
        if not thread_id:
            print(f"⚠️ No se encontró thread_id para {equipo}, se enviará al chat principal.")
            await bot.send_message(chat_id=Config.CHAT_ID, text=mensaje_html, parse_mode=Config.ParseMode.HTML)
        else:
            await bot.send_message(
            chat_id=Config.CHAT_ID,
            text=mensaje_html,
            parse_mode=Config.ParseMode.HTML,
            message_thread_id=thread_id,
            disable_web_page_preview=True
        )
    except Exception as e:
        print("Error enviando mensaje a Telegram:", e)

async def enviar_a_usuario(update, mensaje_html):
    """Envía un mensaje de vuelta al mismo chat que inició la conversación."""
    bot = Config.Bot(token=Config.TELEGRAM_TOKEN)
    try:
        chat_id = update.effective_chat.id  # obtiene el chat de origen
        await bot.send_message(
        chat_id=chat_id,
        text=mensaje_html,
        parse_mode=Config.ParseMode.HTML,
        disable_web_page_preview=True
    )
    except Exception as e:
        print("Error enviando mensaje al usuario:", e)

async def dayout_procesar(session, equipos: list[str]) -> list[str]:
    """Procesa una lista de equipos y devuelve un log con el estado."""
    resultados = []
    for equipo in equipos:
        try:
            await dayout_equipo(session, equipo)
            resultados.append(f"✅ {equipo} procesado")
        except Exception as e:
            err = f"❌ Error procesando {equipo}: {e}"
            print(err)
            resultados.append(err)
    return resultados

async def cmd_dayout(update, context):
    return await start_dayout(update, context, mode=MODE_PROD)

async def cmd_dayout_test(update, context):
    return await start_dayout(update, context, mode=MODE_TEST)

# ==========================================
# FETCH NOTION
# ==========================================

async def fetch_json(session, url, method="GET", payload=None, desc=""):
    try:
        if method == "POST":
            async with session.post(url, headers=Config.HEADERS, json=payload) as resp:
                text = await resp.text()
        else:
            async with session.get(url, headers=Config.HEADERS) as resp:
                text = await resp.text()
        data = Config.json.loads(text)
        if resp.status >= 300:
            print(f"[HTTP {resp.status}] {desc}\nResponse: {text}")
        return data
    except Exception as e:
        print(f"[ERROR fetch_json] {desc} -> {e}")
        return {}

async def get_registros_hoy(session):
    fecha_hoy = Config.datetime.now().strftime('%Y-%m-%d')
    query = {"filter": {"property": "Date", "date": {"equals": fecha_hoy}}}
    data = await fetch_json(session, f"https://api.notion.com/v1/databases/{Config.DATABASE_ID}/query",
                            method="POST", payload=query, desc=f"Query BURN ({fecha_hoy})")
    if data.get("object") == "error":
        print("[ERROR Notion]", data)
        return []
    results = data.get("results", [])
    if not results and Config.DEBUG:
        probe = await fetch_json(session, f"https://api.notion.com/v1/databases/{Config.DATABASE_ID}/query",
                                 method="POST", payload={"page_size": 1}, desc="Probe BURN sin filtro")
        print("[DEBUG] Probe (sin filtro):", probe.get("object"), "| results:", bool(probe.get("results")))
    return results

async def get_page_title(session, page_id):
    data = await fetch_json(session, f"https://api.notion.com/v1/pages/{page_id}")
    for prop in data.get("properties", {}).values():
        if prop.get("type") == "title":
            title_list = prop.get("title", [])
            if title_list:
                # Concatenar todos los bloques
                return "".join([t.get("plain_text", "") for t in title_list]).strip() or "Sin nombre"
    return "Sin nombre"

async def get_page_formula(session, page_id, formula_name="%"):
    data = await fetch_json(session, f"https://api.notion.com/v1/pages/{page_id}")
    formula_prop = data.get("properties", {}).get(formula_name)
    if formula_prop and formula_prop.get("type") == "formula":
        valor = formula_prop.get("formula", {}).get("number") or 0
        return int(valor * 100)
    return 0

async def get_page_fibact(session, page_id):
    data = await fetch_json(session, f"https://api.notion.com/v1/pages/{page_id}")
    prop = data.get("properties", {}).get("Fibact")
    if prop and prop.get("type") == "number":
        return int(prop.get("number") or 0)
    return 0


async def get_page_fibs_target(session, page_id):
    data = await fetch_json(session, f"https://api.notion.com/v1/pages/{page_id}")
    prop = data.get("properties", {}).get("FIBS")
    if prop and prop.get("type") == "formula":
        val = prop.get("formula", {}).get("number")
        if isinstance(val, (int, float)):
            return int(val)
    return 0


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

async def get_registros_plan_por_pl(session, pl_id):
    planes_relacionados = []
    next_cursor = None
    while True:
        payload = {"page_size": 100}
        if next_cursor:
            payload["start_cursor"] = next_cursor
        data = await fetch_json(session, f"https://api.notion.com/v1/databases/{Config.DATABASE_ID_PLAN}/query",
                                method="POST", payload=payload, desc=f"Query planes para pl_id {pl_id}")
        results = data.get("results", [])
        for plan in results:
            for prop_value in plan.get("properties", {}).values():
                if prop_value.get("type") == "relation":
                    ids_rel = [r.get("id") for r in prop_value.get("relation", [])]
                    if pl_id in ids_rel:
                        planes_relacionados.append(plan)
                        print(f"[DEBUG] Plan encontrado: {plan['id']}")
                        break
        next_cursor = data.get("next_cursor")
        if not next_cursor:
            break
    print(f"[DEBUG] Total planes relacionados con pl_id {pl_id}: {len(planes_relacionados)}")
    return planes_relacionados

async def get_tasks_from_plan(session, plan):
    props = plan.get("properties", {})

    async def fetch_task(task_id):
        data = await fetch_json(session, f"https://api.notion.com/v1/pages/{task_id}")
        task_title = await get_page_title(session, task_id)
        if len(task_title) > 40:
            task_title = task_title[:40] + "…"
        task_title_escaped = telegram_escape(task_title)
        page_link = notion_page_url(task_id)
        task_title_link = f'<a href="{page_link}">{task_title_escaped}</a>'
        if "MN" in task_title.upper():
            task_title_link = f"<b>{task_title_link}</b>"

        # STATUS
        status_icon, status_name = "❓", ""
        status_prop = data.get("properties", {}).get("Status Task")
        if status_prop and status_prop.get("type") == "status":
            status_info = status_prop.get("status")
            if status_info and status_info.get("name"):
                status_name = str(status_info.get("name")).strip()
                icons = {"Done": "✅", "In progress": "▶️", "Next to do": "⏹", "To do": "⚪"}
                status_icon = icons.get(status_name, "❓")

        fibs_val = 0
        fibs_prop = data.get("properties", {}).get("FIBS")
        if fibs_prop and fibs_prop.get("type") == "number":
            fibs_val = fibs_prop.get("number") or 0

        done_today = False
        date_done_prop = data.get("properties", {}).get("Date Done")
        if date_done_prop and date_done_prop.get("type") == "date":
            date_info = date_done_prop.get("date")
            if date_info and date_info.get("start"):
                if date_info["start"][:10] == Config.datetime.now().strftime('%Y-%m-%d'):
                    done_today = True

        responsable = ""
        resp_prop = data.get("properties", {}).get("Responsable")
        if resp_prop and resp_prop.get("type") == "people":
            people_list = resp_prop.get("people", [])
            if people_list:
                responsable = people_list[0].get("name", "")

        line_con_icono = f"{status_icon} {task_title_link}"
        if fibs_val:
            line_con_icono += f" ({fibs_val} Fibs)"
        if done_today and responsable:
            line_con_icono += f" — {telegram_escape(responsable)}"

        line_sin_icono = f"{task_title_link}"
        if fibs_val:
            line_sin_icono += f" ({fibs_val} Fibs)"
        if done_today and responsable:
            line_sin_icono += f" — {telegram_escape(responsable)}"

        is_done = status_name.lower() in Config.DONE_STATUS_NAMES

        return line_con_icono, line_sin_icono, fibs_val, (fibs_val if is_done else 0), done_today, is_done, task_id, task_title

    tasks_ids = []
    for field in Config.TASK_FIELDS:
        field_prop = props.get(field)
        if field_prop and field_prop.get("type") == "relation":
            ids_rel = [r.get("id") for r in field_prop.get("relation", [])]
            tasks_ids.extend(ids_rel)

    seen = set()
    tasks_ids = [tid for tid in tasks_ids if not (tid in seen or seen.add(tid))]

    if not tasks_ids:
        return ["- Sin TASK"], ["- Sin TASK"], 0, 0, [], []

    results = await Config.asyncio.gather(*(fetch_task(tid) for tid in tasks_ids))
    lines_icono, lines_sin_icono, fibs_vals, fibs_done_vals, done_today_flags, is_done_flags, ids, titles = zip(*results)

    total_fibs = sum(fibs_vals)
    total_fibs_done = sum(fibs_done_vals)
    done_today_list = [line for line, flag in zip(lines_sin_icono, done_today_flags) if flag]

    return lines_icono, lines_sin_icono, total_fibs, total_fibs_done, done_today_list, []


# ==========================================
# NOTION MUTATIONS
# ==========================================

async def post_comment(session, page_id, comentario):
    payload = {
        "parent": {"page_id": page_id},
        "object": "comment",
        "rich_text": [{"type": "text", "text": {"content": comentario}}]
    }
    url = "https://api.notion.com/v1/comments"
    async with session.post(url, headers=Config.HEADERS, json=payload) as resp:
        return await resp.json()

async def set_page_parcial(session, page_id, valor):
    payload = {"properties": {"PARCIAL": {"number": valor}}}
    url = f"https://api.notion.com/v1/pages/{page_id}"
    async with session.patch(url, headers=Config.HEADERS, json=payload) as resp:
        return await resp.json()

async def set_page_fibact(session, page_id, valor):
    payload = {"properties": {"Fibact": {"number": valor}}}
    url = f"https://api.notion.com/v1/pages/{page_id}"
    async with session.patch(url, headers=Config.HEADERS, json=payload) as resp:
        return await resp.json()

async def post_image_to_page(session, page_id, image_buf, caption_text, bot, chat_id):
    image_url = await upload_image_temporal(image_buf, bot, chat_id)

    payload = {
        "children": [
            {
                "object": "block",
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {"url": image_url}
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": caption_text}}
                    ]
                }
            }
        ]
    }

    async with session.patch(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        headers=Config.HEADERS,
        json=payload
    ) as resp:
        if resp.status != 200:
            print("[ERROR] al subir imagen a Notion:", await resp.text())
        else:
            print("[OK] Imagen agregada a la página en Notion.")


# ==========================================
# SERVICIO DE DOMINIO
# ==========================================
async def dayout():
    async with Config.aiohttp.ClientSession() as session:
        resultados = await dayout_procesar(session, Config.EQUIPOS)
    return "\n".join(resultados)

# ==========================================
# MENÚES TELEGRAM
# ==========================================

def create_team_keyboard(include_todos=False):
    keyboard = [
        [
            Config.InlineKeyboardButton("Caimanes", callback_data="team_Caimanes"),
            Config.InlineKeyboardButton("Zorros", callback_data="team_Zorros"),
            Config.InlineKeyboardButton("Huemules", callback_data="team_Huemules"),
        ]
    ]

    if include_todos:
        keyboard.append([
            Config.InlineKeyboardButton("Todos", callback_data="team_Todos"),
        ])

    keyboard.append([
        Config.InlineKeyboardButton("Cancelar", callback_data="team_Cancelar"),
    ])

    return Config.InlineKeyboardMarkup(keyboard)

async def start_dayout(update, context, *, mode=MODE_PROD):
    context.user_data["dayout_mode"] = mode
    await update.message.reply_text(
        "📋 DayOUT:",
        reply_markup=create_team_keyboard(),
    )
    return ESPERANDO_EQUIPO_DAYOUT

async def start_dayout_test(update: Config.Update, context: Config.CallbackContext):
    await update.message.reply_text(
        "📋 DayOUT de prueba:",
        reply_markup=create_team_keyboard(),
    )
    return ESPERANDO_EQUIPO_DAYOUT

# ==========================================
# CONVERSATION HANDLERS
# ==========================================

async def recibir_equipo_dayout(update, context):
    query = update.callback_query
    await query.answer()

    equipo = query.data.replace("team_", "")
    mode = context.user_data.get("dayout_mode", MODE_PROD)

    if equipo == "Cancelar":
        await query.message.reply_text("❌ Operación cancelada.")
        return Config.ConversationHandler.END
    await query.message.reply_text(f"🔎 Revisando registros {equipo}...")
    async with Config.aiohttp.ClientSession() as session:
        if equipo == "Todos":
            for eq in Config.EQUIPOS:
                await dayout_equipo(session, eq, mode=mode, update=update)
        else:
            await dayout_equipo(session, equipo, mode=mode, update=update)

    return Config.ConversationHandler.END

conv_dayout = Config.ConversationHandler(
    entry_points=[
        Config.CommandHandler("dayout", start_dayout),
        Config.CommandHandler("dayout_test", lambda u, c: start_dayout(u, c, mode=MODE_TEST)),
    ],
    states={
        ESPERANDO_EQUIPO_DAYOUT: [
            Config.CallbackQueryHandler(recibir_equipo_dayout, pattern="^team_")
        ]
    },
    fallbacks=[Config.CommandHandler("cancelar", Config.cancelar)],
)

# ==========================================
# LÓGICA DE ARMADO DE DAYOUT
# ==========================================

async def dayout_equipo(session, equipo_objetivo, *, mode="prod", update=None):
    is_test = mode == MODE_TEST
    if mode == MODE_TEST and update is None:
        raise ValueError("MODE_TEST requiere 'update'")

    registros = await get_registros_hoy(session)
    if Config.DEBUG:
        print(f"[DEBUG] {equipo_objetivo} - Registros hoy: {len(registros)}")

    for registro in registros:
        relaciones_pl = registro['properties'].get('TEAM MEETING NOTES', {}).get('relation', [])
        if not relaciones_pl:
            continue

        match_equipo = False

        for rel in relaciones_pl:
            pl_id = rel.get("id")
            if not pl_id:
                continue

            equipo_pl = await get_page_equipo(session, pl_id)
            if equipo_pl == equipo_objetivo:
                match_equipo = True
                break

        if not match_equipo:
            continue

        nombre_registro_text = (
            registro['properties'].get('Name', {})
            .get('title', [{}])[0]
            .get('plain_text', 'Sin nombre')
        )
        fecha_registro = await get_page_date(session, registro['id'])

        # =====================
        # CÁLCULOS
        # =====================
        registro_total_fibs = 0
        registro_total_fibs_done = 0
        done_today_overall = []
        fibs_por_epica = {}
        total_fibs_done_parcial = 0

        for rel in relaciones_pl:
            pl_id = rel.get('id')
            if not pl_id:
                continue
            if await get_page_equipo(session, pl_id) != equipo_objetivo:
                continue

            registros_plan = await get_registros_plan_por_pl(session, pl_id)

            for plan in registros_plan:
                fibs_por_epica.setdefault(pl_id, []).append(plan)

                (
                    tasks_icono,
                    _,
                    total_fibs_plan,
                    total_fibs_done_plan,
                    _,
                    _
                ) = await get_tasks_from_plan(session, plan)

                if not is_test:
                    await set_page_fibact(session, plan['id'], total_fibs_done_plan)

                registro_total_fibs += total_fibs_plan
                registro_total_fibs_done += total_fibs_done_plan
                total_fibs_done_parcial += total_fibs_done_plan

                for t in tasks_icono:
                    m = Config.re.search(r"\((\d+) Fibs\)", t)
                    if "—" in t and m:
                        done_today_overall.append((t, int(m.group(1))))

        if not is_test:
            await set_page_parcial(session, registro['id'], total_fibs_done_parcial)

        # =====================
        # MENSAJES
        # =====================
        mensaje_html = f"📢 Cierre {equipo_objetivo} {fecha_registro}\n"
        mensaje_html += f"------------------------------------------------"
        mensaje_notion = f"{nombre_registro_text} ({fecha_registro})\n\n"
        
        for pl_id, planes in fibs_por_epica.items():
            planes_val = []
            for p in planes:
                porcentaje = await get_page_formula(session, p['id'])
                fibs = await get_page_fibact(session, p['id'])
                fibs_target = await get_page_fibs_target(session, p['id'])
                planes_val.append((p, porcentaje, fibs, fibs_target))
            for plan, porcentaje, fibs, fibs_target in sorted(planes_val, key=lambda x: x[1], reverse=True):
                nombre = await get_page_title(session, plan['id'])
                nombre_short = nombre[:30] + "…" if len(nombre) > 30 else nombre
                link = notion_page_url(plan['id'])

                mensaje_html += (
                    f"\n%{porcentaje} | {fibs}/{fibs_target} Fibs | "
                    f"<a href='{link}'>{telegram_escape(nombre_short)}</a>"
                )

                mensaje_notion += f"\n%{porcentaje} | {fibs}/{fibs_target} Fibs | {nombre_short}"

        # =====================
        # ANÁLISIS Y TAREAS HOY
        # =====================
        props = registro.get("properties", {})
        cant_integrantes = props.get("Cant. Integrantes", {}).get("number") or 0
        ultima_velocidad = props.get("Última Velocidad", {}).get("number") or 0.0
        day_number_val = props.get("DayNumber", {}).get("formula", {}).get("number") or 0
        fibs_esperados = cant_integrantes * day_number_val * ultima_velocidad

        mensaje_analisis = (
            f"\n------------------------------------------------\n"
            f"Total {equipo_objetivo}: {registro_total_fibs_done}/{registro_total_fibs} FIBS\n"
        )

        # =====================
        # TAREAS FINALIZADAS HOY
        # =====================
        tareas_por_responsable = Config.defaultdict(list)

        for line, fibs in done_today_overall:
            if "—" in line:
                titulo_html, resp = line.split("—", 1)
                resp = resp.strip()
            else:
                titulo_html, resp = line, "Sin responsable"

            match = Config.re.search(r'<a href="([^"]+)">([^<]+)</a>', titulo_html)
            link, texto = (match.group(1), match.group(2)) if match else ("#", titulo_html)
            tareas_por_responsable[resp].append((texto, link, fibs))

        mensaje_analisis += "------------------------------------------------\n"

        if not tareas_por_responsable:
            mensaje_analisis += "SIN TAREAS CERRADAS HOY\n"
        else:
            mensaje_analisis += "TAREAS CERRADAS HOY\n"
            for resp, tareas in tareas_por_responsable.items():
                mensaje_analisis += f"{resp}:\n"
                for texto, link, fibs in tareas:
                    fib_label = "FIB" if fibs == 1 else "FIBS"
                    mensaje_analisis += f"• {fibs} {fib_label} <a href='{link}'> {texto}</a>\n"

        dia_semana = Config.datetime.now().weekday()

        if dia_semana in (0, 1):
            mensaje_analisis += (
                "------------------------------------------------\n"
                "⌛ Esperando tendencia semanal \n       para analizar datos\n"
            )
        else:
            mensaje_analisis += (
                "------------------------------------------------\n"
                "Análisis de datos\n"
                f"      • {cant_integrantes} Personas | Día: {day_number_val}\n"
                f"      • Vel. referencia: {ultima_velocidad}\n"
                f"      • FIBS esperados: {fibs_esperados:.2f}\n"
                f"      • FIBS cerrados: {registro_total_fibs_done}\n\n"
            )

            # Evaluación velocidad
            if registro_total_fibs_done >= fibs_esperados * 1.1:
                mensaje_analisis += "Vel: +110% 🔥😎\n"
            elif registro_total_fibs_done >= fibs_esperados:
                mensaje_analisis += "Vel: 100-110% ☺️\n"
            elif registro_total_fibs_done >= fibs_esperados * 0.85:
                mensaje_analisis += "Vel: 85-100% 🙂\n"
            elif registro_total_fibs_done >= fibs_esperados * 0.7:
                mensaje_analisis += "Vel: 70-85% 😐\n"
            elif registro_total_fibs_done >= fibs_esperados * 0.6:
                mensaje_analisis += "Vel: 60-70% 🙃\n"
            elif registro_total_fibs_done >= fibs_esperados * 0.5:
                mensaje_analisis += "Vel: 50-60% 😖\n"
            else:
                mensaje_analisis += "Vel: -50% 🚨☠️\n"


        mensaje_html += mensaje_analisis
        mensaje_notion += mensaje_analisis

        # =====================
        # EFECTOS SEGÚN MODO
        # =====================
        if is_test:
            await enviar_a_usuario(update, mensaje_html)
            buf = await generar_curva_parcial_equipo(equipo_objetivo)
            caption = f"📈 Burndown {equipo_objetivo} | {fecha_registro}"
            chat_id = update.effective_chat.id  # obtiene el chat de origen
            await update.get_bot().send_photo(
                chat_id=chat_id,
                photo=buf,
                caption=caption,
            )
        else:
            await post_comment(session, registro['id'], mensaje_notion)
            await enviar_a_telegram(mensaje_html, equipo_objetivo)

            try:
                buf = await generar_curva_parcial_equipo(equipo_objetivo)
                caption = f"📈 Burndown {equipo_objetivo} | ({fecha_registro})"

                bot = Config.Bot(token=Config.TELEGRAM_TOKEN)
                await post_image_to_page(session, registro['id'], buf, caption, bot, Config.CHAT_ID)

                await bot.send_photo(
                    chat_id=Config.CHAT_ID,
                    photo=buf,
                    caption=caption,
                    message_thread_id=Config.THREAD_IDS.get(equipo_objetivo),
                )
            except Exception as e:
                print(f"[ERROR] Curva {equipo_objetivo}: {e}")



# ============================
# JOB DAYOUT
# ============================
async def job_dayout(context: Config.CallbackContext):
    print("📤 job_dayout disparado a las", Config.datetime.now(Config.ARG_TZ))
    try:
        resultado = await dayout()
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_LOG,
            text=f"[DayOUT automático]\n{resultado}",
            parse_mode="HTML"
        )
        print("📤 DayOUT automático enviado")
    except Exception as e:
        print(f"❌ Error en job_dayout: {e}")


