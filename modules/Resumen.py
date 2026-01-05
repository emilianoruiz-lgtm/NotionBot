# ==========================================
# IMPORTS
# ==========================================

# Módulos Locales
import Config


# ==========================================
# CONFIGURACIÓN Y CONSTANTES
# ==========================================

_PAGE_CACHE = {}


# ==========================================
# UTILIDADES DE SISTEMA Y TIEMPO
# ==========================================
async def safe_send_message(bot, chat_id, text, parse_mode=Config.ParseMode.HTML, **kwargs):
    MAX_LEN = 4000
    start = 0
    while start < len(text):
        end = start + MAX_LEN
        if end < len(text):
            newline_pos = text.rfind("\n", start, end)
            if newline_pos != -1: end = newline_pos + 1
        
        msg_chunk = text[start:end]
        while True:
            try:
                return await bot.send_message(chat_id, msg_chunk, parse_mode=parse_mode, **kwargs)
            except Config.RetryAfter as e:
                await Config.asyncio.sleep(e.retry_after)
        start = end



# ==========================================
# FUNCIONES DE DOMINIO (RESUMEN)
# ==========================================

def fetch_page(page_id):
    if page_id in _PAGE_CACHE:
        return _PAGE_CACHE[page_id]

    r = Config.requests.get(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=Config.HEADERS
    )
    if r.status_code != 200:
        return None

    data = r.json()
    _PAGE_CACHE[page_id] = data
    return data

def find_property(properties, name):
    name_clean = name.strip().lower()
    for k in properties:
        if k.strip().lower() == name_clean:
            return k
    return None

def _normalize_text(s):
    if not s:
        return ""
    s = s.strip().lower()
    s = Config.unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if Config.unicodedata.category(ch) != "Mn")

def construir_modelo_resumen(registros):
    equipos = {}

    for rd in registros:
        props = rd.get("properties", {})
        equipo = props.get("Equipo", {}).get("select", {}).get("name", "Sin equipo")

        equipo_data = equipos.setdefault(equipo, {
            "planes": [],
            "total_fibs": 0,
            "props": props
        })

        mn_key = find_property(props, "TEAM MEETING NOTES")
        if not mn_key:
            continue

        for mn_ref in props[mn_key].get("relation", []):
            mn = fetch_page(mn_ref["id"])
            if not mn:
                continue

            plan_key = find_property(mn.get("properties", {}), "PLANNING")
            if not plan_key:
                continue

            for plan_ref in mn["properties"][plan_key].get("relation", []):
                plan = fetch_page(plan_ref["id"])
                if not plan:
                    continue

                plan_props = plan.get("properties", {})

                title_key = find_property(plan_props, "Name") or find_property(plan_props, "Nombre")
                title = "".join(
                    t.get("plain_text", "") for t in plan_props.get(title_key, {}).get("title", [])
                ).strip() or "Plan desconocido"

                estado = ""
                estado_key = find_property(plan_props, "Estado") or find_property(plan_props, "Status")
                if estado_key:
                    p = plan_props.get(estado_key, {})
                    estado = (
                        p.get("status", {}).get("name")
                        or p.get("select", {}).get("name")
                        or ""
                    )

                # -------- FIBS ACTUALES --------
                fib_key = find_property(plan_props, "Fibact")
                fibs = plan_props.get(fib_key, {}).get("number", 0) if fib_key else 0

                # -------- FIBS TARGET (formula) --------
                fib_target_key = find_property(plan_props, "FIBS")
                fibs_target = 0

                if fib_target_key:
                    fib_target_prop = plan_props.get(fib_target_key, {})
                    if fib_target_prop.get("type") == "formula":
                        valor = fib_target_prop.get("formula", {}).get("number")
                        if isinstance(valor, (int, float)):
                            fibs_target = int(valor)

                # -------- PORCENTAJE (calculado) --------
                porcentaje = 0
                if fibs_target > 0:
                    porcentaje = int((fibs / fibs_target) * 100)

                equipo_data["planes"].append({
                    "id": plan_ref["id"],
                    "titulo": title,
                    "estado": estado,
                    "fibs": fibs,
                    "fibs_target": fibs_target,
                    "porcentaje": porcentaje
                })

                equipo_data["total_fibs"] += fibs or 0

    return equipos

# ==========================================
# FETCH NOTION
# ==========================================

def fetch_registros_hoy(database_id=Config.DATABASE_ID):
    fecha_hoy = Config.datetime.now().strftime('%Y-%m-%d')
    query = {"filter": {"property": "Date", "date": {"equals": fecha_hoy}}}

    r = Config.requests.post(
        f"https://api.notion.com/v1/databases/{database_id}/query",
        headers=Config.HEADERS,
        json=query
    )
    r.raise_for_status()
    return r.json().get("results", [])

def fetch_page(page_id):
    r = Config.requests.get(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=Config.HEADERS
    )
    if r.status_code != 200:
        return None
    return r.json()




# ==========================================
# SERVICIO DE DOMINIO
# ==========================================

def generar_resumen():
    registros = fetch_registros_hoy()
    modelo = construir_modelo_resumen(registros)
    return render_resumen_html(modelo)

# ==========================================
# MENÚES TELEGRAM
# ==========================================



# ==========================================
# CONVERSATION HANDLERS
# ==========================================
async def resumen(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    print(f"[CMD] {Config.datetime.now(Config.ARG_TZ).strftime('%d/%m/%y %H:%M')} - Épicas")
    await update.message.reply_text("🔎 Armando resumen...")

    try:
        msg = generar_resumen()
        if not msg:
            msg = "No se encontraron épicas para hoy."

        await safe_send_message(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            text=msg,
            parse_mode=Config.ParseMode.HTML
        )
    except Exception as e:
        Config.logging.exception("Error en resumen")
        await safe_send_message(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            text="⚠️ Error al generar el resumen de épicas.",
        )




# ==========================================
# LÓGICA DE ARMADO DE RESUMEN
# ==========================================
def render_resumen_html(equipos):
    if not equipos:
        return None

    bloques = []

    for equipo, data in sorted(equipos.items()):
        lineas = []

        for p in data["planes"]:
            link = f"https://www.notion.so/{p['id'].replace('-', '')}"
            titulo = Config.html.escape(p["titulo"])
            titulo_short = titulo[:30] + "…" if len(titulo) > 30 else titulo

            estado = _normalize_text(p["estado"])

            # Link base
            link_html = f"<a href='{link}'>{titulo_short}</a>"

            # Estados → tachado si corresponde
            if (
                "epica cerrada" in estado
                or "cancelada" in estado
                or "replanific" in estado
            ):
                link_html = f"<s>{link_html}</s>"

            fibs = p.get("fibs", 0)
            fibs_target = p.get("fibs_target", 0)
            avance = p.get("porcentaje", 0)

            lineas.append(f"%{avance} | {fibs}/{fibs_target} Fibs | {link_html}")

        if not lineas:
            continue

        emoji = Config.EMOJIS.get(equipo, "📋")
        bloques.append(
            f"{emoji} <b>{equipo}</b>\n"
            f"------------------------------------------------\n"
            + "\n".join(lineas)
        )

    return "<b>Resumen del sprint</b>\n\n" + "\n\n".join(bloques)




# ============================
# JOB RESUMEN
# ============================





