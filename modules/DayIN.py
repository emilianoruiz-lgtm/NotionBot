import asyncio
import aiohttp
from datetime import datetime, timedelta, date
from telegram import Bot
from telegram.constants import ParseMode
import html
import os
from openai import OpenAI
import random

# --- CONFIGURACIONES ---
import Config


# --- FUNCIONES EXTRA ---
def dias_habiles(inicio: date, fin: date) -> int:
    """
    Calcula días hábiles entre 'inicio' y 'fin' (inclusive de 'inicio', excluye 'fin'),
    sin contar fines de semana ni feriados.
    """
    dias = 0
    actual = inicio
    while actual < fin:
        if actual.weekday() < 5 and actual not in Config.FERIADOS:  # lunes=0, viernes=4
            dias += 1
        actual += timedelta(days=1)
    return dias

# --- FUNCIONES TELEGRAM ---
def telegram_escape(text: str) -> str:
    return html.escape(text or "")

async def enviar_a_telegram(mensaje_html, equipo: str):
    if not mensaje_html or not mensaje_html.strip():
        print(f"⚠️ Mensaje vacío para {equipo}, no se envía a Telegram.")
        return
    
    print(f"Enviando comentario a Telegram para {equipo}...")
    bot = Bot(token=Config.TELEGRAM_TOKEN)
    try:
        thread_id = Config.THREAD_IDS.get(equipo)
        if not thread_id:
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
async def fetch_json(session, url, method="GET", payload=None): #NUEVA CONSULTA A NOTION
    if method == "POST":
        async with session.post(url, headers=Config.HEADERS, json=payload) as resp:
            return await resp.json()
    else:
        async with session.get(url, headers=Config.HEADERS) as resp:
            return await resp.json()

async def post_comment(session, page_id, comentario):#POST COMENTARIO EN NOTION
    payload = {
        "parent": {"page_id": page_id},
        "object": "comment",
        "rich_text": [{"type": "text", "text": {"content": comentario}}]
    }
    url = "https://api.notion.com/v1/comments"
    async with session.post(url, headers=Config.HEADERS, json=payload) as resp:
        return await resp.json()

async def get_page_title(session, page_id): #OBTIENE NOMBRE DE LA TARJETA
    data = await fetch_json(session, f"https://api.notion.com/v1/pages/{page_id}")
    for prop in data.get("properties", {}).values():
        if prop.get("type") == "title":
            title_list = prop.get("title", [])
            if title_list:
                return title_list[0].get("plain_text", "Sin nombre")
    return "Sin nombre"

    print("Publicando comentario en Notion...")
async def get_page_equipo(session, page_id): #OBTIENE EQUIPO DE LA EPICA
    data = await fetch_json(session, f"https://api.notion.com/v1/pages/{page_id}")
    equipo_prop = data.get("properties", {}).get("Equipo")
    if equipo_prop and equipo_prop.get("type") == "select":
        return equipo_prop.get("select", {}).get("name", "Sin equipo")
    return "Sin equipo"

async def get_page_date_start(session, page_id): #OBTIENE FECHA DE INICIO DE LA TARJETA
    data = await fetch_json(session, f"https://api.notion.com/v1/pages/{page_id}")
    date_prop = data.get("properties", {}).get("Date Start")
    if date_prop and date_prop.get("type") == "date":
        date_val = date_prop.get("date")
        if date_val and date_val.get("start"):
            return datetime.fromisoformat(date_val["start"][:10]).date()
    return None

async def get_page_formula(session, page_id, formula_name="%"): #OBTIENE % DE LA ÉPICA
    data = await fetch_json(session, f"https://api.notion.com/v1/pages/{page_id}")
    formula_prop = data.get("properties", {}).get(formula_name)
    if formula_prop and formula_prop.get("type") == "formula":
        valor = formula_prop.get("formula", {}).get("number")
        return int((valor or 0) * 100)
    return 0

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
    payload = {"page_size": 100}
    while True:
        data = await fetch_json(session, f"https://api.notion.com/v1/databases/{Config.DATABASE_ID_PLAN}/query", method="POST", payload=payload)
        results = data.get("results", [])
        for plan in results:
            for prop_value in plan.get("properties", {}).values():
                if prop_value.get("type") == "relation":
                    ids_rel = [r.get("id") for r in prop_value.get("relation", [])]
                    if pl_id in ids_rel:
                        planes_relacionados.append(plan)
                        break
        next_cursor = data.get("next_cursor")
        if not next_cursor:
            break
        payload["start_cursor"] = next_cursor
    return planes_relacionados

async def get_task_responsable(data): #OBTIENE RESPONSABLE DE LA TARJETA
    responsable_prop = data.get("properties", {}).get("Responsable")
    responsables = []
    if responsable_prop and responsable_prop.get("type") == "people":
        for p in responsable_prop.get("people", []):
            if "name" in p:
                responsables.append(p["name"])
    return responsables

async def get_tasks_from_plan(session, plan): #OBTIENE TAREAS DE LA ÉPICA
    props = plan.get("properties", {})

    async def fetch_task(task_id):
        data = await fetch_json(session, f"https://api.notion.com/v1/pages/{task_id}")
        task_title = await get_page_title(session, task_id)
        if len(task_title) > 40:
            task_title = task_title[:40] + "…"
        task_title_escaped = telegram_escape(task_title)

        if "MN" in task_title.upper():
            task_title_bold = f"<b>{task_title_escaped}</b>"
        else:
            task_title_bold = task_title_escaped

        status_icon = "❓"
        status_name = ""
        status_prop = data.get("properties", {}).get("Status Task")
        if status_prop and status_prop.get("type") == "status":
            status_info = status_prop.get("status")
            if status_info and status_info.get("name"):
                status_name = str(status_info.get("name")).strip()
                icons = {"Done": "✅", "In progress": "▶️", "Next to do": "⏹", "To do": "⚪"}
                status_icon = icons.get(status_name, "❓")

        fibs_val = 0
        fibs_prop = data.get("properties", {}).get("FIBS")
        if fibs_prop and fibs_prop.get("type") == "number" and fibs_prop.get("number") is not None:
            fibs_val = fibs_prop.get("number")

        responsable = ""
        if status_name == "In progress":
            responsables = await get_task_responsable(data)
            if responsables:
                responsable = f"👤 {telegram_escape(responsables[0])}"

        line_plain = f"{status_icon} {task_title}"
        line_html = f"{status_icon} {task_title_bold}"
        if fibs_val:
            line_plain += f" ({fibs_val} Fibs)"
            line_html += f" ({fibs_val} Fibs)"
        if responsable:
            line_plain += f" — {responsable}"
            line_html += f" — {responsable}"

        return line_plain, line_html

    tasks_ids = []
    for field in Config.TASK_FIELDS:
        field_prop = props.get(field)
        if field_prop and field_prop.get("type") == "relation":
            ids_rel = [r.get("id") for r in field_prop.get("relation", [])]
            tasks_ids.extend(ids_rel)

    if not tasks_ids:
        return ["- Sin TASK"], ["- Sin TASK"]

    results = await asyncio.gather(*(fetch_task(tid) for tid in tasks_ids))
    lines_plain, lines_html = zip(*results)
    return list(lines_plain), list(lines_html)

async def verificar_responsables(session, registro, relaciones_pl): #REVISA QUE TODOS TENGAN UNA TASK ASIGNADA
    if EQUIPO_OBJETIVO == "Caimanes":
        PERSONAS_OBJETIVO = Config.PERSONAS_CAIMANES
    if EQUIPO_OBJETIVO == "Huemules":
        PERSONAS_OBJETIVO = Config.PERSONAS_HUEMULES
    if EQUIPO_OBJETIVO == "Zorros":
        PERSONAS_OBJETIVO = Config.PERSONAS_ZORROS

    asignados = {p: False for p in PERSONAS_OBJETIVO}
    tareas_next_to_do = []

    for rel in relaciones_pl:
        pl_id = rel.get('id')
        if not pl_id:
            continue

        registros_plan = await get_registros_plan_por_pl(session, pl_id)
        for plan in registros_plan:
            props = plan.get("properties", {})
            
            for field in Config.TASK_FIELDS:
                field_prop = props.get(field)
                if field_prop and field_prop.get("type") == "relation":
                    ids_rel = [r.get("id") for r in field_prop.get("relation", [])]

                    for task_id in ids_rel:
                        data_task = await fetch_json(session, f"https://api.notion.com/v1/pages/{task_id}")
                        status_prop = data_task.get("properties", {}).get("Status Task")
                        status_name = ""
                        if status_prop and status_prop.get("type") == "status":
                            status_info = status_prop.get("status")
                            if status_info:
                                status_name = status_info.get("name", "")

                        responsables = await get_task_responsable(data_task)

                        if status_name == "In progress":
                            for p in PERSONAS_OBJETIVO:
                                if p in responsables:
                                    asignados[p] = True

                        if status_name == "Next to do":
                            titulo_task = await get_page_title(session, task_id)
                            tareas_next_to_do.append(titulo_task)

    sin_asignar = [p for p, ok in asignados.items() if not ok]

    comentario2_plain = f"\n📋 Asignación de tareas {EQUIPO_OBJETIVO}:\n----------------------------------------------------\n"
    comentario2_html = f"\n📋 Asignación de tareas {EQUIPO_OBJETIVO}:\n----------------------------------------------------\n"

    if sin_asignar:
        comentario2_plain += "  ⚠️ Responsables sin tareas en progreso:\n"
        comentario2_html += "  ⚠️ Responsables sin tareas en progreso:\n"
        for p in sin_asignar:
            comentario2_plain += f"    👤 {p}\n"
            comentario2_html += f"    👤 {telegram_escape(p)}\n"

        if tareas_next_to_do:
            comentario2_plain += "\n  Posibles tareas para tomar:\n"
            comentario2_html += "\n  Posibles tareas para tomar:\n"
            for t in tareas_next_to_do:
                comentario2_plain += f"   ⏹ {t}\n"
                comentario2_html += f"   ⏹ {telegram_escape(t)}\n"
    else:
        comentario2_plain += "✅ Todos los responsables tienen al menos una tarea en progreso.\n"
        comentario2_html += "✅ Todos los responsables tienen al menos una tarea en progreso.\n"

    return comentario2_plain, comentario2_html


# --- SCRIPT PRINCIPAL ---
async def DayInEquipo(equipo: str):
    global EQUIPO_OBJETIVO
    EQUIPO_OBJETIVO = equipo
    print(f"\n================ Procesando equipo: {EQUIPO_OBJETIVO} ================\n")

    async with aiohttp.ClientSession() as session:

        # BUSCA REGISTROS DE BURNDOWN CORRESPONDIENTES A LA FECHA CONFIGURADA -> registros[]
        fecha_maniana = (datetime.now() + timedelta(days=0)).strftime('%Y-%m-%d')
        query = {"filter": {"property": "Date", "date": {"equals": fecha_maniana}}}
        data = await fetch_json(session, f"https://api.notion.com/v1/databases/{Config.DATABASE_ID}/query", method="POST", payload=query)
        registros = data.get('results', [])
        print(f"BUSCANDO REGISTRO BURNDOWN {EQUIPO_OBJETIVO} {fecha_maniana}") 
    

        # REVISA registros[] DE BURNDOWN PARA OBTENER REGISTROS DE PLANNING: registros[registro] <-> relaciones_pl[pl]
        print(f"   • Buscando relación con PLANNING")
        for registro in registros:
            relaciones_pl = registro['properties'].get('TEAM MEETING NOTES', {}).get('relation', [])
            if not relaciones_pl:
                continue


            # REVISA QUE EXISTAN ÉPICAS CORRESPONDIENTES AL EQUIPO OBJETIVO : relaciones_pl[pl] <-> EQUIPO_OBJETIVO 
            print(f"   • IDENTIFICANDO ÉPICAS {EQUIPO_OBJETIVO}")
            procesar = False
            for pl in relaciones_pl:
                pl_id = pl.get('id')
                if not pl_id:
                    continue
                equipo = await get_page_equipo(session, pl_id)
                if equipo == EQUIPO_OBJETIVO:
                    procesar = True
                    print(f"   • Épicas para {EQUIPO_OBJETIVO} encontradas\n")
                    break
            if not procesar:
                continue

            
            
            # RESUMEN PRINCIPAL DEL DÍA
            print(f"Generando resumen principal del día")
            nombre_registro = registro['properties'].get('Name', {}).get('title', [])
            nombre_registro_text = nombre_registro[0]['plain_text'] if nombre_registro else "Sin nombre"
            fecha_registro = await get_page_date(session, registro['id'])

            nombre_plain = nombre_registro_text
            nombre_html = telegram_escape(nombre_registro_text)
            if "MN" in nombre_registro_text.upper():
                nombre_html = f"<b>{nombre_html}</b>"

            comentario_plain = f"\n📌 {nombre_plain} ({fecha_registro})\n"
            comentario_html = f"\n📌 {nombre_html} ({fecha_registro})\n"
            print(f"\n📌 {nombre_html} ({fecha_registro})")

            # RECORRIENDO ÉPICAS
            for rel in relaciones_pl:
                pl_id = rel.get('id')
                if not pl_id:
                    continue
                nombre_pl = await get_page_title(session, pl_id)
                equipo_pl = await get_page_equipo(session, pl_id)
                if equipo_pl != EQUIPO_OBJETIVO:
                    continue

                comentario_plain += f"\n{nombre_pl} | {equipo_pl}\n"
                comentario_html += f"\n<b>{telegram_escape(nombre_pl)}</b> | {telegram_escape(equipo_pl)}\n"
                print(f"Buscando ÉPICAS EN {nombre_pl} | {equipo_pl}\n")

                registros_plan = await get_registros_plan_por_pl(session, pl_id)
                if registros_plan:
                    for plan in registros_plan:
                        formula_valor = await get_page_formula(session, plan['id'])
                        nombre_plan = await get_page_title(session, plan['id'])
                        if len(nombre_plan) > 40:
                            nombre_plan = nombre_plan[:40] + "…"

                        comentario_plain += f"\n   • {nombre_plan} %{formula_valor}\n"
                        comentario_html += f"\n   • {telegram_escape(nombre_plan)} %{formula_valor}\n"
                        
                        print(f"{nombre_plan} | %{formula_valor}")
                        tasks_plain, tasks_html = await get_tasks_from_plan(session, plan)
                       
                        print(f"   • Buscando Tasks\n")
                        for t1, t2 in zip(tasks_plain, tasks_html):
                            comentario_plain += f"       {t1}\n"
                            comentario_html += f"       {t2}\n"
                else:
                    comentario_plain += "   • Sin PLAN\n"
                    comentario_html += "   • Sin PLAN\n"
                print("🔎 Analizando todos los registros obtenidos")



            # --- Recolectar tareas en progreso por persona ---
            tareas_por_persona = {}
            print("   • Buscando tareas por persona")
            for rel in relaciones_pl:
                pl_id = rel.get('id')
                if not pl_id:
                    continue

                data_plans = await fetch_json(session, f"https://api.notion.com/v1/databases/{Config.DATABASE_ID_PLAN}/query", method="POST", payload={})
                for plan in data_plans.get("results", []):
                    for prop_value in plan.get("properties", {}).values():
                        if prop_value.get("type") == "relation":
                            ids_rel = [r.get("id") for r in prop_value.get("relation", [])]
                            if pl_id in ids_rel:
                                for field in Config.TASK_FIELDS:
                                    field_prop = plan["properties"].get(field)
                                    if field_prop and field_prop.get("type") == "relation":
                                        ids_tasks = [r.get("id") for r in field_prop.get("relation", [])]
                                        for task_id in ids_tasks:
                                            data_task = await fetch_json(session, f"https://api.notion.com/v1/pages/{task_id}")
                                            status_prop = data_task.get("properties", {}).get("Status Task")
                                            status_name = status_prop.get("status", {}).get("name", "") if status_prop and status_prop.get("type") == "status" else ""
                                            if status_name == "In progress":
                                                responsables = await get_task_responsable(data_task)
                                                title = await get_page_title(session, task_id)
                                                fibs_prop = data_task.get("properties", {}).get("FIBS")
                                                fibs_val = fibs_prop.get("number", 0) if fibs_prop else 0

                                                start_date = await get_page_date_start(session, task_id)
                                                if start_date:
                                                    dias = dias_habiles(start_date, datetime.now().date())
                                                else:
                                                    dias = 0

                                                for resp in responsables:
                                                    if resp not in tareas_por_persona:
                                                        tareas_por_persona[resp] = []
                                                    tareas_por_persona[resp].append((title, dias, fibs_val))
                                                    print(f"   • {resp} - {title} - {dias} días -{fibs_val} fibs ")   

            # --- Verificar responsables ---
            resp_plain, resp_html = await verificar_responsables(session, registro, relaciones_pl)

            comentario3_plain = f"{resp_plain} \n📊 Duración de tareas:\n----------------------------------------------------\n"
            comentario3_html = f"{resp_html} \n📊 Duración de tareas:\n----------------------------------------------------\n"

            advertencias = []
            revisar_rd = []

            for resp, tasks in tareas_por_persona.items():
                comentario3_plain += f"   👤 {resp}:\n"
                comentario3_html += f"   👤 {telegram_escape(resp)}:\n"
                for title, dias, fibs_val in tasks:
                    if dias <= fibs_val and dias > 0:
                        comentario3_plain += f"    • {title} (llevando {dias} días de trabajo en esta tarea de {fibs_val} FIBs)\n"
                        comentario3_html += f"    • {telegram_escape(title)} (llevando {dias} días de trabajo en esta tarea de {fibs_val} FIBs)\n"
                    elif dias == 0:
                        comentario3_plain += f"    • {title} empezando esta tarea de {fibs_val} FIBs)\n"
                        comentario3_html += f"    • {telegram_escape(title)} (llevando {dias} días de trabajo en esta tarea de {fibs_val} FIBs)\n"                  
                    else:
                        frase_random = random.choice(Config.FRASES_VARIADAS)
                        comentario3_plain += f"    • {title} (llevando {dias} días de trabajo en esta tarea de {fibs_val} FIBs)\n      {frase_random}\n"
                        comentario3_html += f"    • {telegram_escape(title)} (llevando {dias} días de trabajo en esta tarea de {fibs_val} FIBs)\n      {telegram_escape(frase_random)}\n"

                if len(tasks) > 1:
                    advertencias.append(
                        f"   👤 {resp} tiene {len(tasks)} tareas en progreso.\n Se recomienda, cuando sea posible, que cada persona se enfoque en una tarea a la vez."
                    )

                for title, dias, fibs_val in tasks:
                    if dias == 1 and fibs_val == 1:
                        revisar_rd.append(f" •{title} | Debería resolverse en 1 día aprox, y {resp} ya le dedicó ese tiempo.")

            if advertencias:
                comentario3_plain += "\n⚠️ Atención:\n----------------------------------------------------\n"
                comentario3_html += "\n⚠️ Atención:\n----------------------------------------------------\n"
                for a in advertencias:
                    comentario3_plain += f"{a}\n"
                    comentario3_html += f"{telegram_escape(a)}\n"

            if revisar_rd:
                comentario3_plain += "\n   📌 Revisar en detalle en la RD:\n----------------------------------------------------\n"
                comentario3_html += "\n   📌 Revisar en detalle en la RD:\n----------------------------------------------------\n"
                for r in revisar_rd:
                    comentario3_plain += f"- {r}\n"
                    comentario3_html += f"- {telegram_escape(r)}\n"

            if not comentario3_html.strip():
                comentario3_html = "⚠️ No se encontraron resultados para este equipo."

            # --- Publicar comentarios ---
            await post_comment(session, registro['id'], comentario_plain)
            #await enviar_a_telegram(comentario_html)
            await post_comment(session, registro['id'], comentario3_plain)
            
            #await enviar_a_telegram(comentario3_html, EQUIPO_OBJETIVO)
            
    for registro in registros:
            relaciones_pl = registro['properties'].get('TEAM MEETING NOTES', {}).get('relation', [])
            if not relaciones_pl:
                continue



async def DayIN():
    equipos = ["Caimanes", "Zorros", "Huemules"]
    for equipo in equipos:
        try:
            await DayInEquipo(equipo)
        except Exception as e:
            print(f"❌ Error procesando {equipo}: {e}")

