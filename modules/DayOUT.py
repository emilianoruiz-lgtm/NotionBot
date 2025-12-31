import asyncio
import aiohttp
from datetime import datetime
from telegram import Bot,InputFile
from telegram.constants import ParseMode
import html
from collections import defaultdict
import json
import re
import base64
from modules.CurvaParcial import generar_curva_parcial_equipo

# --- CONFIGURACIONES ---
import Config

# --- UTILIDADES ---

async def upload_image_temporal(buf, bot, chat_id):
    """
    Sube la imagen a Telegram y devuelve un link público.
    Usa el chat del bot como almacenamiento temporal.
    """
    sent_photo = await bot.send_photo(chat_id=chat_id, photo=InputFile(buf, filename="curva.png"))
    file_id = sent_photo.photo[-1].file_id
    file_info = await bot.get_file(file_id)
    return file_info.file_path  # URL público


def telegram_escape(text: str) -> str:
    return html.escape(text)

def notion_page_url(page_id: str) -> str:
    return f"https://www.notion.so/{page_id.replace('-', '')}"

# --- NOTION API ---
async def fetch_json(session, url, method="GET", payload=None, desc=""):
    try:
        if method == "POST":
            async with session.post(url, headers=Config.HEADERS, json=payload) as resp:
                text = await resp.text()
        else:
            async with session.get(url, headers=Config.HEADERS) as resp:
                text = await resp.text()
        data = json.loads(text)
        if resp.status >= 300:
            print(f"[HTTP {resp.status}] {desc}\nResponse: {text}")
        return data
    except Exception as e:
        print(f"[ERROR fetch_json] {desc} -> {e}")
        return {}

async def post_comment(session, page_id, comentario):
    payload = {
        "parent": {"page_id": page_id},
        "object": "comment",
        "rich_text": [{"type": "text", "text": {"content": comentario}}]
    }
    url = "https://api.notion.com/v1/comments"
    async with session.post(url, headers=Config.HEADERS, json=payload) as resp:
        return await resp.json()

async def get_registros_hoy(session):
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
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

# --- TAREAS ---
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
                if date_info["start"][:10] == datetime.now().strftime('%Y-%m-%d'):
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

    # --- recolectamos las tasks relacionadas ---
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

    # --- acá recién llamamos al gather (una sola vez) ---
    results = await asyncio.gather(*(fetch_task(tid) for tid in tasks_ids))
    lines_icono, lines_sin_icono, fibs_vals, fibs_done_vals, done_today_flags, is_done_flags, ids, titles = zip(*results)

    total_fibs = sum(fibs_vals)
    total_fibs_done = sum(fibs_done_vals)
    done_today_list = [line for line, flag in zip(lines_sin_icono, done_today_flags) if flag]

    return lines_icono, lines_sin_icono, total_fibs, total_fibs_done, done_today_list, []


# --- TELEGRAM ---
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

# --- ACTUALIZAR NOTION ---
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



# --- PROCESO PRINCIPAL ---
async def DayOutEquipo(session, equipo_objetivo):
    registros = await get_registros_hoy(session)
    if Config.DEBUG: print(f"[DEBUG] {equipo_objetivo} - Registros hoy: {len(registros)}")

    for registro in registros:
        relaciones_pl = registro['properties'].get('TEAM MEETING NOTES', {}).get('relation', [])
        if not relaciones_pl:
            continue

        procesar = False
        for rel in relaciones_pl:
            pl_id = rel.get('id')
            if not pl_id:
                continue
            equipo_pl = await get_page_equipo(session, pl_id)
            if equipo_pl == equipo_objetivo:
                procesar = True
                break
        if not procesar:
            continue

        nombre_registro_text = registro['properties'].get('Name', {}).get('title', [])
        nombre_registro_text = nombre_registro_text[0]['plain_text'] if nombre_registro_text else "Sin nombre"
        fecha_registro = await get_page_date(session, registro['id'])
        page_link = notion_page_url(registro['id'])

        mensaje_short = f"{nombre_registro_text} ({fecha_registro})\n\n"
        registro_total_fibs = 0
        registro_total_fibs_done = 0
        done_today_overall = []
        fibs_por_epica = {}
        total_fibs_done_parcial = 0

        for rel in relaciones_pl:
            pl_id = rel.get('id')
            if not pl_id:
                continue
            equipo_pl = await get_page_equipo(session, pl_id)
            if equipo_pl != equipo_objetivo:
                continue

            registros_plan = await get_registros_plan_por_pl(session, pl_id)
            total_fibs_done_epica = 0

            for plan in registros_plan:
                fibs_por_epica.setdefault(pl_id, []).append(plan)
                tasks_icono, tasks_sin_icono, total_fibs_plan, total_fibs_done_plan, done_today_list, _ = await get_tasks_from_plan(session, plan)
                await set_page_fibact(session, plan['id'], total_fibs_done_plan)
                if Config.DEBUG:
                    print(f"[OK] Fibact actualizado PLAN {plan['id']} => {total_fibs_done_plan}")

                registro_total_fibs += total_fibs_plan
                registro_total_fibs_done += total_fibs_done_plan
                total_fibs_done_epica += total_fibs_done_plan
                total_fibs_done_parcial += total_fibs_done_plan

                # recolectar tareas con FIBS y responsable
                for task_line, fibs_val, flag in zip(tasks_icono,
                                                     [re.search(r"\((\d+) Fibs\)", t) for t in tasks_icono],
                                                     [("—" in t) for t in tasks_icono]):
                    if flag and fibs_val:
                        fibs_num = int(fibs_val.group(1))
                        done_today_overall.append((task_line, fibs_num))
                

        # --- SETEAR PARCIAL en el registro RD ---
        await set_page_parcial(session, registro['id'], total_fibs_done_parcial)
        if Config.DEBUG:
            print(f"[OK] PARCIAL actualizado REGISTRO {registro['id']} => {total_fibs_done_parcial}")

        # --- ARMADO MENSAJE TELEGRAM (HTML) ---
        mensaje_html = f"📢 {equipo_objetivo} Cierre del día {fecha_registro}\n"
        # ---------- MENSAJE PARA NOTION (PLANO) ----------
        mensaje_notion = f"{nombre_registro_text} ({fecha_registro})\n\n"

        for pl_id, registros_plan in fibs_por_epica.items():
            if registros_plan:
                plan_con_valor = [(plan, await get_page_formula(session, plan['id'])) for plan in registros_plan]
                plan_con_valor_sorted = sorted(plan_con_valor, key=lambda x: x[1], reverse=True)
                for plan, formula_valor in plan_con_valor_sorted:
                    nombre_plan = await get_page_title(session, plan['id'])
                    nombre_plan_short = nombre_plan if len(nombre_plan) <= 30 else nombre_plan[:30] + "…"
                    plan_link = notion_page_url(plan["id"])

                    # HTML para telegram
                    mensaje_html += f"\n    🧩 <a href='{plan_link}'>{telegram_escape(nombre_plan_short)}</a> %{formula_valor}\n"

                    # Texto plano para Notion (sin tags)
                    mensaje_notion += f"\n    🧩 {nombre_plan_short} %{formula_valor}\n"

                    tasks_icono, _ , _, _, _, _ = await get_tasks_from_plan(session, plan)

                    if not tasks_icono or tasks_icono == ["- Sin TASK"]:
                        mensaje_html += f"        • Sin tareas asociadas\n"
                        mensaje_notion += f"        • Sin tareas asociadas\n"
                    else:
                        for task in tasks_icono:
                            # task tiene HTML (<a>...), eliminamos tags para Notion
                            tarea_plana = re.sub(r"<[^>]+>", "", task).strip()
                            mensaje_html += f"        • {task}\n"
                            mensaje_notion += f"        • {tarea_plana}\n"


        # --- ANÁLISIS ---
        props = registro.get("properties", {})
        cant_integrantes = props.get("Cant. Integrantes", {}).get("number") or 0
        ultima_velocidad = props.get("Última Velocidad", {}).get("number") or 0.0
        day_number_val = props.get("DayNumber", {}).get("formula", {}).get("number") or 0
        fibs_esperados = cant_integrantes * day_number_val * ultima_velocidad

        mensaje_analisis = f"\n------------------------------------------------\n💰 Total {equipo_objetivo}: {registro_total_fibs_done}/{registro_total_fibs} FIBS\n"
        # --- DÍA DE LA SEMANA ---
        dia_semana = datetime.now().weekday()  # Lunes=0 ... Domingo=6

        if dia_semana in (0, 1):  # Lunes o Martes
            mensaje_analisis += "------------------------------------------------\n🟦 Esperando tendencia\n\n"
        else:
            # Seguimos como siempre (no toco tu lógica)
            mensaje_analisis += "------------------------------------------------\n📊 Estimación vs Realidad\n      • {cant_integrantes} Personas | Día: {day_number_val}\n"
            mensaje_analisis += f"      • Vel. Sprint anterior: {ultima_velocidad}\n"
            mensaje_analisis += f"      • FIBS esperados: {fibs_esperados:.2f} \n      • FIBS cerrados: {registro_total_fibs_done}\n\n"
            # (mismo código de evaluación de velocidad que ya tenías...)
            if registro_total_fibs_done >= fibs_esperados * 1.1:
                mensaje_analisis += "Vel: +110% 🔥😎 Excelente!\n"
            elif registro_total_fibs_done >= fibs_esperados:
                mensaje_analisis += "Vel: 100-110% ☺️ Muy bien!\n"
            elif registro_total_fibs_done >= fibs_esperados * 0.85:
                mensaje_analisis += "Vel: 85-100% 🙂\n"
            elif registro_total_fibs_done >= fibs_esperados * 0.7:
                mensaje_analisis += "Vel: 70-85% 😐 Meehhh \n"
            elif registro_total_fibs_done >= fibs_esperados * 0.6:
                mensaje_analisis += "Vel: 60-70% 🙃 Baja velocidad\n"
            elif registro_total_fibs_done >= fibs_esperados * 0.5:
                mensaje_analisis += "Vel: 50-60% 😖 Muy baja velocidad\n"
            else:
                mensaje_analisis += "Vel: -50% 🚨☠️ Problemas!\n"

        tareas_por_responsable = defaultdict(list)
        for line, fibs in done_today_overall:
            if "—" in line:
                titulo_html, resp = line.split("—", 1)
                resp = resp.strip()
            else:
                titulo_html, resp = line, "Sin responsable"
            match = re.search(r'<a href="([^"]+)">([^<]+)</a>', titulo_html)
            link, texto = (match.group(1), match.group(2)) if match else ("#", titulo_html)
            tareas_por_responsable[resp].append((texto, link, fibs))


        mensaje_analisis_short = mensaje_analisis + "------------------------------------------------\n🧐 Tareas finalizadas hoy:\n"
        mensaje_analisis_short_notion = mensaje_analisis + "------------------------------------------------\n🧐 Tareas finalizadas hoy:\n"

        for resp, tareas in tareas_por_responsable.items():
            mensaje_analisis_short += f"\n{resp}:\n"
            mensaje_analisis_short_notion += f"\n{resp}:\n"
            for texto, link, fibs in tareas:
                fib_label = "FIB" if fibs == 1 else "FIBS"
                mensaje_analisis_short += f"       • {fibs} {fib_label}<a href='{link}'> {texto}</a>\n"
                mensaje_analisis_short_notion += f"       • {fibs} {fib_label} {texto}\n"


        # añadimos el análisis al mensaje para Notion
        mensaje_notion_final = mensaje_notion +  mensaje_analisis_short_notion +"\n"  

        # DEBUG: ver qué vamos a postear
        if Config.DEBUG:
            print("=== CONTENIDO A POSTEAR EN NOTION ===")
            print(mensaje_notion_final)
            print("=== FIN CONTENIDO ===")

        # --- ENVÍO A NOTION ---
        await post_comment(session, registro['id'], mensaje_notion_final)
        await enviar_a_telegram(mensaje_html + mensaje_analisis_short, equipo_objetivo)    

        try:
            buf = await generar_curva_parcial_equipo(equipo_objetivo)
            caption = f"📈 Curva burndown actual de {equipo_objetivo} ({fecha_registro})"

            # Subir imagen a Notion
            bot = Bot(token=Config.TELEGRAM_TOKEN)
            await post_image_to_page(session, registro['id'], buf, caption, bot, Config.CHAT_ID)

            # Enviar imagen al grupo de Telegram (en el hilo del equipo)
            bot = Bot(token=Config.TELEGRAM_TOKEN)
            thread_id = Config.THREAD_IDS.get(equipo_objetivo)
            await bot.send_photo(
                chat_id=Config.CHAT_ID,
                photo=buf,
                caption=caption,
                parse_mode=ParseMode.HTML,
                message_thread_id=thread_id
            )

            if Config.DEBUG:
                print(f"[OK] Imagen enviada y publicada correctamente para {equipo_objetivo}")

        except Exception as e:
            print(f"[ERROR] No se pudo generar o subir la curva para {equipo_objetivo}: {e}")

 

async def DayOutProcesar(session, equipos: list[str]) -> list[str]:
    """Procesa una lista de equipos y devuelve un log con el estado."""
    resultados = []
    for equipo in equipos:
        try:
            await DayOutEquipo(session, equipo)
            resultados.append(f"✅ {equipo} procesado")
        except Exception as e:
            err = f"❌ Error procesando {equipo}: {e}"
            print(err)
            resultados.append(err)
    return resultados


# --- MAIN ---
async def DayOUT():
    async with aiohttp.ClientSession() as session:
        resultados = await DayOutProcesar(session, Config.EQUIPOS)
    return "\n".join(resultados)




async def enviar_a_usuario(update, mensaje_html):
    """Envía un mensaje de vuelta al mismo chat que inició la conversación."""
    bot = Bot(token=Config.TELEGRAM_TOKEN)
    try:
        chat_id = update.effective_chat.id  # obtiene el chat de origen
        await bot.send_message(
            chat_id=chat_id,
            text=mensaje_html,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print("Error enviando mensaje al usuario:", e)


async def DayOutTest(update, session, equipo_objetivo):
    registros = await get_registros_hoy(session)
    if Config.DEBUG: print(f"[DEBUG] {equipo_objetivo} - Registros hoy: {len(registros)}")

    for registro in registros:
        relaciones_pl = registro['properties'].get('TEAM MEETING NOTES', {}).get('relation', [])
        if not relaciones_pl:
            continue

        procesar = False
        for rel in relaciones_pl:
            pl_id = rel.get('id')
            if not pl_id:
                continue
            equipo_pl = await get_page_equipo(session, pl_id)
            if equipo_pl == equipo_objetivo:
                procesar = True
                break
        if not procesar:
            continue

        nombre_registro_text = registro['properties'].get('Name', {}).get('title', [])
        nombre_registro_text = nombre_registro_text[0]['plain_text'] if nombre_registro_text else "Sin nombre"
        fecha_registro = await get_page_date(session, registro['id'])
        page_link = notion_page_url(registro['id'])

        mensaje_short = f"{nombre_registro_text} ({fecha_registro})\n\n"
        registro_total_fibs = 0
        registro_total_fibs_done = 0
        done_today_overall = []
        fibs_por_epica = {}
        total_fibs_done_parcial = 0

        for rel in relaciones_pl:
            pl_id = rel.get('id')
            if not pl_id:
                continue
            equipo_pl = await get_page_equipo(session, pl_id)
            if equipo_pl != equipo_objetivo:
                continue

            registros_plan = await get_registros_plan_por_pl(session, pl_id)
            total_fibs_done_epica = 0

            for plan in registros_plan:
                fibs_por_epica.setdefault(pl_id, []).append(plan)
                tasks_icono, tasks_sin_icono, total_fibs_plan, total_fibs_done_plan, done_today_list, _ = await get_tasks_from_plan(session, plan)
                await set_page_fibact(session, plan['id'], total_fibs_done_plan)
                if Config.DEBUG:
                    print(f"[OK] Fibact actualizado PLAN {plan['id']} => {total_fibs_done_plan}")

                registro_total_fibs += total_fibs_plan
                registro_total_fibs_done += total_fibs_done_plan
                total_fibs_done_epica += total_fibs_done_plan
                total_fibs_done_parcial += total_fibs_done_plan

                for task_line, fibs_val, flag in zip(tasks_icono,
                                                     [re.search(r"\((\d+) Fibs\)", t) for t in tasks_icono],
                                                     [("—" in t) for t in tasks_icono]):
                    if flag and fibs_val:
                        fibs_num = int(fibs_val.group(1))
                        done_today_overall.append((task_line, fibs_num))
                        

        await set_page_parcial(session, registro['id'], total_fibs_done_parcial)
        if Config.DEBUG:
            print(f"[OK] PARCIAL actualizado REGISTRO {registro['id']} => {total_fibs_done_parcial}")

        # --- ARMADO MENSAJE TELEGRAM (HTML) ---
        mensaje_html = f"📢 {equipo_objetivo} Cierre del día {fecha_registro}\n"
        for pl_id, registros_plan in fibs_por_epica.items():
            if registros_plan:
                plan_con_valor = [(plan, await get_page_formula(session, plan['id'])) for plan in registros_plan]
                plan_con_valor_sorted = sorted(plan_con_valor, key=lambda x: x[1], reverse=True)
                for plan, formula_valor in plan_con_valor_sorted:
                    nombre_plan = await get_page_title(session, plan['id'])
                    nombre_plan_short = nombre_plan if len(nombre_plan) <= 35 else nombre_plan[:35] + "…"
                    plan_link = notion_page_url(plan["id"])
                    mensaje_html += f"\n    🧩  <a href='{plan_link}'>{telegram_escape(nombre_plan_short)}</a> %{formula_valor}\n"
                    tasks_icono, _ , _, _, _, _ = await get_tasks_from_plan(session, plan)
                    if not tasks_icono or tasks_icono == ["- Sin TASK"]:
                        mensaje_html += f"        • Sin tareas asociadas\n"
                    else:
                        for task in tasks_icono:
                            mensaje_html += f"        • {task}\n"

        # --- ANÁLISIS ---
        props = registro.get("properties", {})
        cant_integrantes = props.get("Cant. Integrantes", {}).get("number") or 0
        ultima_velocidad = props.get("Última Velocidad", {}).get("number") or 0.0
        day_number_val = props.get("DayNumber", {}).get("formula", {}).get("number") or 0
        fibs_esperados = cant_integrantes * day_number_val * ultima_velocidad

        mensaje_analisis = f"\n------------------------------------------------\n💰 Total {equipo_objetivo}: {registro_total_fibs_done}/{registro_total_fibs} FIBS\n"
        # --- DÍA DE LA SEMANA ---
        dia_semana = datetime.now().weekday()  # Lunes=0 ... Domingo=6

        if dia_semana in (0, 1):  # Lunes o Martes
            mensaje_analisis += "------------------------------------------------\n🟦 Esperando tendencia\n\n"
        else:
            # Seguimos como siempre (no toco tu lógica)
            mensaje_analisis += "------------------------------------------------\n📊 Estimación vs Realidad\n      • {cant_integrantes} Personas | Día: {day_number_val}\n"
            mensaje_analisis += f"      • Vel. Sprint anterior: {ultima_velocidad}\n"
            mensaje_analisis += f"      • FIBS esperados: {fibs_esperados:.2f} \n      • FIBS cerrados: {registro_total_fibs_done}\n\n"
            if registro_total_fibs_done >= fibs_esperados * 1.1:
                mensaje_analisis += "Vel: +110% 🔥😎 Excelente!\n"
            elif registro_total_fibs_done >= fibs_esperados:
                mensaje_analisis += "Vel: 100-110% ☺️ Muy bien!\n"
            elif registro_total_fibs_done >= fibs_esperados * 0.85:
                mensaje_analisis += "Vel: 85-100% 🙂\n"
            elif registro_total_fibs_done >= fibs_esperados * 0.7:
                mensaje_analisis += "Vel: 70-85% 😐 Meehhh \n"
            elif registro_total_fibs_done >= fibs_esperados * 0.6:
                mensaje_analisis += "Vel: 60-70% 🙃 Baja velocidad\n"
            elif registro_total_fibs_done >= fibs_esperados * 0.5:
                mensaje_analisis += "Vel: 50-60% 😖 Muy baja velocidad\n"
            else:
                mensaje_analisis += "Vel: -50% 🚨☠️ Problemas!\n"

        tareas_por_responsable = defaultdict(list)
        for line, fibs in done_today_overall:
            if "—" in line:
                titulo_html, resp = line.split("—", 1)
                resp = resp.strip()
            else:
                titulo_html, resp = line, "Sin responsable"
            match = re.search(r'<a href="([^"]+)">([^<]+)</a>', titulo_html)
            link, texto = (match.group(1), match.group(2)) if match else ("#", titulo_html)
            tareas_por_responsable[resp].append((texto, link, fibs))

        mensaje_analisis_short = mensaje_analisis + "------------------------------------------------\n🧐 Tareas finalizadas hoy:\n"
        for resp, tareas in tareas_por_responsable.items():
            mensaje_analisis_short += f"\n{resp}:\n"
            for texto, link, fibs in tareas:
                fib_label = "FIB" if fibs == 1 else "FIBS"
                mensaje_analisis_short += f"       • {fibs} {fib_label}<a href='{link}'> {texto}</a>\n"

        # --- ENVÍO ---
        await enviar_a_usuario(update, mensaje_html + mensaje_analisis_short)

        try:
            buf = await generar_curva_parcial_equipo(equipo_objetivo)
            caption = f"📈 Curva burndown actual de {equipo_objetivo} ({fecha_registro})"

            await post_image_to_page(session, registro['id'], buf, caption, update.get_bot(), update.effective_chat.id)

            if Config.DEBUG:
                print(f"[OK] Imagen insertada en Notion para {equipo_objetivo}")

        except Exception as e:
            print(f"[ERROR] No se pudo generar o subir la curva para {equipo_objetivo}: {e}")
