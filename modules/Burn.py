import asyncio
import requests
import subprocess
from datetime import datetime, timedelta
from telegram import Bot
from telegram.constants import ParseMode
from pathlib import Path
import aiohttp


# --- CONFIGURACIONES ---
import Config



# --- FUNCIONES AUXILIARES ---

def _task_is_done(task_props):
    """Determina si la tarea está completada."""
    posibles_claves = ("Status","Estado","status","Status Task")
    status_name = None
    for k in posibles_claves:
        key_found = next((key for key in task_props if key.lower() == k.lower()), None)
        if not key_found:
            continue
        p = task_props[key_found]
        if p.get("type") == "status":
            status_name = p.get("status", {}).get("name")
        elif p.get("type") == "select":
            status_name = p.get("select", {}).get("name")
        if status_name:
            break

    if not status_name:
        print(f"❌ TASK {task_props.get('Nombre', {}).get('title',[{}])[0].get('plain_text','?')} NO está completada, Status='None'")
        return False

    s = status_name.strip().lower().replace(" ","")
    return s == "done" or s.endswith(".done") or s in ("completado","completo")



def find_property(properties, name):
    """
    Busca una propiedad de Notion por nombre ignorando mayúsc/minúsc/espacios.
    """
    name_clean = name.strip().lower()
    for k in properties:
        if k.strip().lower() == name_clean:
            return k
    return None


# --- NOTION ---

def get_registros_hoy(database_id=Config.DATABASE_ID):
    """Obtiene registros RD del día actual."""
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    query = {"filter": {"property": "Date","date":{"equals": fecha_hoy}}}
    r = requests.post(f"https://api.notion.com/v1/databases/{database_id}/query",
                      headers=Config.HEADERS, json=query)
    data = r.json()
    return data.get('results', [])

# --- TELEGRAM ---

async def enviar_a_telegram(mensaje_html, equipo=None):
    bot = Bot(token=Config.TELEGRAM_TOKEN)
    try:
        thread_id = Config.THREAD_IDS.get(equipo)
        kwargs = {"chat_id": Config.CHAT_ID, "text": mensaje_html, "parse_mode": ParseMode.HTML}
        if thread_id: kwargs["message_thread_id"] = thread_id
        await bot.send_message(**kwargs)
    except Exception as e:
        print("Error enviando mensaje a Telegram:", e)



import unicodedata
import html

def _normalize_text(s):
    """Quita diacríticos y pasa a minúsculas para comparar strings de estado."""
    if not s:
        return ""
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


# --- ACTUALIZAR FIBACT --- 
def actualizar_fibact(plan_id):
    r = requests.get(f"https://api.notion.com/v1/pages/{plan_id}", headers=Config.HEADERS)
    if r.status_code != 200:
        print(f"⚠️ Error obteniendo Plan {plan_id}: {r.text}")
        return 0, None, "Plan desconocido", None  # <-- ahora devuelve 4 valores

    plan_json = r.json()
    plan_props = plan_json.get("properties", {})
    total_fib = 0

    # obtener título del plan
    title_prop = find_property(plan_props, "Name") or find_property(plan_props, "Nombre")
    plan_title = ""
    if title_prop:
        plan_title = "".join([t.get("plain_text","") for t in plan_props[title_prop].get("title",[])]).strip()
    if not plan_title:
        plan_title = "Plan desconocido"

    # --- NUEVO: obtener Estado del PLAN directamente desde sus propiedades ---
    plan_estado = None
    estado_key = find_property(plan_props, "Estado") or find_property(plan_props, "Status") or find_property(plan_props, "status")
    if estado_key:
        p = plan_props.get(estado_key, {})
        if p.get("type") == "status":
            plan_estado = p.get("status", {}).get("name")
        elif p.get("type") == "select":
            plan_estado = p.get("select", {}).get("name")
    if plan_estado:
        plan_estado = plan_estado.strip()
    # --------------------------------------------------------------------

    # valor anterior de Fibact
    fibact_key = find_property(plan_props, "Fibact")
    fibact_anterior = plan_props.get(fibact_key, {}).get("number") if fibact_key else None

    # recorrer todos los posibles campos de tareas
    for field in Config.TASK_FIELDS:
        field_key = find_property(plan_props, field)
        if not field_key: 
            continue
        tasks_relation = plan_props[field_key].get("relation", [])
        for t in tasks_relation:
            task_id = t["id"]
            r_task = requests.get(f"https://api.notion.com/v1/pages/{task_id}", headers=Config.HEADERS)
            if r_task.status_code != 200:
                print(f"⚠️ Error consultando tarea {task_id}: {r_task.text}")
                continue
            task_props = r_task.json().get("properties", {})

            title_key = find_property(task_props, "Name") or find_property(task_props, "Nombre")
            task_title = ""
            if title_key:
                task_title = "".join([t.get("plain_text", "") for t in task_props[title_key].get("title", [])]).strip()
            if not task_title:
                task_title = "Tarea sin nombre"

            status = None
            for k in ("Status","Estado","status"):
                if k in task_props:
                    p = task_props[k]
                    if p.get("type") == "status":
                        status = p.get("status", {}).get("name")
                    elif p.get("type") == "select":
                        status = p.get("select", {}).get("name")
                

            if _task_is_done(task_props):
                fib_key = find_property(task_props, "FIBS")
                fib_val = task_props.get(fib_key, {}).get("number", 0) if fib_key else 0
                total_fib += fib_val or 0
                print(f"✅ TASK {task_title} está completada, FIBS = {fib_val}")
            else:
                print(f"❌ TASK {task_title} NO está completada, Status='{status}'")

    # Actualizar Fibact en el PLAN
    if fibact_key:
        payload = {"properties": {fibact_key: {"number": total_fib}}}
        r_patch = requests.patch(f"https://api.notion.com/v1/pages/{plan_id}", headers=Config.HEADERS, json=payload)
        print(f"[DEBUG] {plan_title} → Fibact {fibact_anterior} → {total_fib}, resp={r_patch.status_code}")
    else:
        print(f"⚠️ {plan_title} no tiene propiedad 'Fibact'. Debe agregarse manualmente en la base de datos.")

    # Devuelvo también el estado del plan (puede ser None)
    return total_fib, fibact_anterior, plan_title, plan_estado

# --- ACTUALIZAR PARCIAL CORRECTAMENTE EN RD --- 
def actualizar_parcial(rd_registro):
    props_rd = rd_registro.get("properties", {})
    mn_key = find_property(props_rd, "TEAM MEETING NOTES")
    if not mn_key:
        print(f"⚠️ RD {rd_registro['id']} no tiene relación 'TEAM MEETING NOTES'")
        return "", 0

    # valor anterior de PARCIAL
    parcial_key = find_property(props_rd, "PARCIAL")
    parcial_anterior = props_rd.get(parcial_key, {}).get("number") if parcial_key else None

    total_parcial = 0
    resumen_planes = []

    mn_relations = props_rd[mn_key].get("relation", [])
    for mn_ref in mn_relations:
        r_mn = requests.get(f"https://api.notion.com/v1/pages/{mn_ref['id']}", headers=Config.HEADERS)
        if r_mn.status_code != 200:
            print(f"⚠️ Error obteniendo MN {mn_ref['id']}: {r_mn.text}")
            continue
        mn_registro = r_mn.json()
        
        # Recalcular Fibact de todos los PLANES del MN
        mn_props = mn_registro.get("properties", {})
        plan_key = find_property(mn_props, "PLANNING")
        if not plan_key:
            print(f"⚠️ MN {mn_ref['id']} no tiene relación 'PLANNING'")
            continue
        
        plan_relations = mn_props[plan_key].get("relation", [])
        for plan in plan_relations:
            plan_id = plan["id"]
            # ahora actualizar_fibact devuelve (fib_val, fib_anterior, plan_title, plan_estado)
            fib_val, fib_anterior, plan_title, plan_estado = actualizar_fibact(plan_id)
            total_parcial += fib_val or 0

            # normalizar y formatear título según estado (usamos plan_estado)
            estado_norm = _normalize_text(plan_estado)
            plan_title_esc = html.escape(plan_title)

            if "epica cerrada" in estado_norm:
                plan_title_fmt = f"<s>✅ {plan_title_esc}</s>"
            elif "cancelada" in estado_norm or "replanific" in estado_norm:
                plan_title_fmt = f"<s>❎ {plan_title_esc}</s>"
            elif "épica en riesgo" in estado_norm:
                plan_title_fmt = f"⚠️ {plan_title_esc}"
            else:
                plan_title_fmt = f"⚙️ {plan_title_esc}"

              
            if fib_anterior is None or fib_val == fib_anterior:
                resumen_planes.append(f"\n{plan_title_fmt} \n <b>{fib_val} Fibs (Sin cambios)</b>")
            else:
                resumen_planes.append(f"\n{plan_title_fmt} \n <b>{fib_anterior} → {fib_val} Fibs</b>")

    # Actualizar PARCIAL en el RD
    if parcial_key:
        payload = {"properties": {parcial_key: {"number": total_parcial}}}
        r_patch = requests.patch(f"https://api.notion.com/v1/pages/{rd_registro['id']}",
                                 headers=Config.HEADERS, json=payload)
        print(f"[DEBUG] RD {rd_registro['id']} → PARCIAL {parcial_anterior} → {total_parcial}, resp={r_patch.status_code}")
    else:
        print(f"⚠️ RD {rd_registro['id']} no tiene propiedad 'PARCIAL'")

    # resumen PARCIAL
    if parcial_anterior is None or parcial_anterior == total_parcial:
        resumen_parcial = f"----------------------------------------\n<B>TOTAL: {total_parcial} Fibs (Sin cambios)</B>"
    else:
        resumen_parcial = f"----------------------------------------\n<B>TOTAL: {parcial_anterior} → {total_parcial} Fibs</B>"

    resumen = "\n".join(resumen_planes + [resumen_parcial])
    return resumen, total_parcial

def actualizar_cant_integrantes(rd_registro, equipo):
    """
    Actualiza en Notion la cantidad de integrantes según el equipo.
    """
    props_rd = rd_registro.get("properties", {})
    cant_key = find_property(props_rd, "Cant. Integrantes")
    if not cant_key:
        print(f"⚠️ RD {rd_registro['id']} no tiene propiedad 'Cant. Integrantes'")
        return

    # Contar integrantes según equipo
    if equipo == "Caimanes":
        cantidad = len(Config.PERSONAS_CAIMANES)
    elif equipo == "Zorros":
        cantidad = len(Config.PERSONAS_ZORROS)
    elif equipo == "Huemules":
        cantidad = len(Config.PERSONAS_HUEMULES)
    else:
        cantidad = 0

    # Valor anterior
    cant_anterior = props_rd.get(cant_key, {}).get("number")

    # Actualizar en Notion
    payload = {"properties": {cant_key: {"number": cantidad}}}
    r_patch = requests.patch(f"https://api.notion.com/v1/pages/{rd_registro['id']}",
                             headers=Config.HEADERS, json=payload)
    print(f"[DEBUG] RD {rd_registro['id']} → Cant. Integrantes {cant_anterior} → {cantidad}, resp={r_patch.status_code}")

async def burndown():
    registros = get_registros_hoy()  # estos son RD
    equipos_procesados = set()

    for rd in registros:
        resumen, total_parcial = actualizar_parcial(rd)  # recalcula Fibact de MN → PLAN y actualiza PARCIAL en RD
        
        # obtener valor anterior de PARCIAL
        parcial_key = find_property(rd.get("properties", {}), "PARCIAL")
        parcial_anterior = rd.get("properties", {}).get(parcial_key, {}).get("number") if parcial_key else None

        equipo = rd.get("properties", {}).get("Equipo", {}).get("select", {}).get("name")

        # 🔹 Actualizar la cantidad de integrantes del equipo en el RD
        if equipo:
            actualizar_cant_integrantes(rd, equipo)

        # Chequear si hay cambios en total_parcial respecto al valor anterior
        if parcial_anterior is not None and parcial_anterior == total_parcial:
            print(f"ℹ️ No hay cambios en PARCIAL para RD {rd['id']}. No se envía mensaje.")
            continue  # saltar envío a telegram

        equipo = rd.get("properties", {}).get("Equipo", {}).get("select", {}).get("name")
        mensaje = f"📊 Burndown actualizado para {equipo or 'Sin equipo'}\n{resumen}"
        await enviar_a_telegram(mensaje, equipo)

        if equipo:
            equipos_procesados.add(equipo)

    print("✅ Burndown finalizado")
    return equipos_procesados

def copiar_bloques_recursivo_completo(orig_id, target_id):
    r = requests.get(f"https://api.notion.com/v1/blocks/{orig_id}/children", headers=Config.HEADERS)
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

        post = requests.patch(f"https://api.notion.com/v1/blocks/{target_id}/children",
                              headers=Config.HEADERS, json={"children":[bloque_nuevo]})
        if post.status_code != 200:
            print("Error copiando bloque:", post.text)
            continue

        if bloque.get('has_children', False):
            nuevo_bloque_id = post.json()['results'][0]['id']
            copiar_bloques_recursivo_completo(bloque['id'], nuevo_bloque_id)

def agregar_comentario_notion(page_id, texto):
    payload = {
        "parent": {"page_id": page_id},
        "rich_text": [{"type": "text", "text": {"content": texto}}]
    }
    response = requests.post("https://api.notion.com/v1/comments", headers=Config.HEADERS, json=payload)
    if response.status_code == 200:
        print(f"Comentario agregado a la página {page_id}")
    else:
        print(f"Error agregando comentario a la página {page_id}:", response.text)

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
    hoy = datetime.now()
    if hoy.weekday() == 4:  # viernes
        dias_hasta_lunes = (7 - hoy.weekday()) % 7 or 7
        fecha_duplicado = hoy + timedelta(days=dias_hasta_lunes)
    else:
        fecha_duplicado = hoy + timedelta(days=1)
    fecha_duplicado_str = fecha_duplicado.strftime('%Y-%m-%d')

    if 'Date' in propiedades_nuevas:
        propiedades_nuevas['Date']['date']['start'] = fecha_duplicado_str
        if 'end' in propiedades_nuevas['Date']['date'] and propiedades_nuevas['Date']['date']['end']:
            try:
                end_dt = datetime.fromisoformat(propiedades_nuevas['Date']['date']['end'])
                delta = end_dt.date() - hoy.date()
                propiedades_nuevas['Date']['date']['end'] = (fecha_duplicado + timedelta(days=delta.days)).strftime('%Y-%m-%d')
            except Exception as e:
                print("No se pudo mantener la duración del registro:", e)

    icono = registro.get('icon', None)
    data = {"parent": {"database_id": Config.DATABASE_ID}, "properties": propiedades_nuevas}
    if icono:
        data['icon'] = icono

    response = requests.post("https://api.notion.com/v1/pages", headers=Config.HEADERS, json=data)
    nueva_pagina = response.json()
    nueva_page_id = nueva_pagina['id']

    copiar_bloques_recursivo_completo(registro['id'], nueva_page_id)

    # Agregar comentario "Actualizado!"
    agregar_comentario_notion(nueva_page_id, "Registro creado!")

    # Obtener equipo (select)
    equipo_select = propiedades_nuevas.get('Equipo', {}).get('select', {}).get('name', None)


    print("Registro duplicado con todo el contenido:", nueva_page_id)
    return nueva_pagina, equipo_select

async def enviar_a_telegram(mensaje_html, equipo: str):
    print(f"Enviando comentario a Telegram para {equipo}...")
    bot = Bot(token=Config.TELEGRAM_TOKEN)
    try:
        thread_id = Config.THREAD_IDS.get(equipo)
        if not thread_id:
            print(f"⚠️ No se encontró thread_id para {equipo}, se enviará al chat principal.")
            await bot.send_message(chat_id=Config.CHAT_ID_DEBUG, text=mensaje_html, parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(
                chat_id=Config.CHAT_ID,
                text=mensaje_html,
                parse_mode=ParseMode.HTML,
                message_thread_id=thread_id
            )
    except Exception as e:
        print("Error enviando mensaje a Telegram:", e)

def actualizar_type_spc(registro):
    propiedades = {"Type": {"multi_select": [{"name": "SPC"}]}}
    page_id = registro['id']
    response = requests.patch(f"https://api.notion.com/v1/pages/{page_id}",
                              headers=Config.HEADERS, json={"properties": propiedades})
    print(f"Registro {page_id} actualizado a solo 'SPC':", response.status_code)
    return response.json()

# --- SCRIPT PRINCIPAL ---
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



        # --- NUEVA FUNCIÓN LISTADO DE PLANES ---

async def listar_planes():
    registros = get_registros_hoy()  # RDs del día actual
    mensajes_por_equipo = {}

    for rd in registros:
        equipo = rd.get("properties", {}).get("Equipo", {}).get("select", {}).get("name", "Sin equipo")
        
        props_rd = rd.get("properties", {})
        mn_key = find_property(props_rd, "TEAM MEETING NOTES")
        if not mn_key:
            continue

        resumen_planes = []
        mn_relations = props_rd[mn_key].get("relation", [])
        total_fibs = 0

        for mn_ref in mn_relations:
            r_mn = requests.get(f"https://api.notion.com/v1/pages/{mn_ref['id']}", headers=Config.HEADERS)
            if r_mn.status_code != 200:
                continue
            mn_registro = r_mn.json()

            plan_key = find_property(mn_registro.get("properties", {}), "PLANNING")
            if not plan_key:
                continue

            for plan in mn_registro["properties"][plan_key].get("relation", []):
                plan_id = plan["id"]
                # Obtener datos del plan directamente
                r_plan = requests.get(f"https://api.notion.com/v1/pages/{plan_id}", headers=Config.HEADERS)
                if r_plan.status_code != 200:
                    continue
                plan_json = r_plan.json()
                plan_props = plan_json.get("properties", {})

                # Obtener título del plan
                title_prop = find_property(plan_props, "Name") or find_property(plan_props, "Nombre")
                plan_title = "".join([t.get("plain_text", "") for t in plan_props.get(title_prop, {}).get("title", [])]).strip() or "Plan desconocido"
                plan_title_esc = html.escape(plan_title[:200]) + ("" if len(plan_title) > 200 else "")

                # Generar link clickeable
                plan_url = f"https://www.notion.so/{plan_id.replace('-', '')}"
                plan_link = f'<a href="{plan_url}">{plan_title_esc}</a>'

                # Estado del plan
                plan_estado = None
                estado_key = find_property(plan_props, "Estado") or find_property(plan_props, "Status") or find_property(plan_props, "status")
                if estado_key:
                    p = plan_props.get(estado_key, {})
                    if p.get("type") == "status":
                        plan_estado = p.get("status", {}).get("name")
                    elif p.get("type") == "select":
                        plan_estado = p.get("select", {}).get("name")
                plan_estado = plan_estado.strip() if plan_estado else ""

                # Fibact
                fibact_key = find_property(plan_props, "Fibact")
                fib_val = plan_props.get(fibact_key, {}).get("number", 0) if fibact_key else 0
                total_fibs += fib_val or 0

                # Formatear título según estado pero con link
                estado_norm = _normalize_text(plan_estado)
                if "epica cerrada" in estado_norm:
                    plan_title_fmt = f"<s>✅ {plan_link}</s>"
                elif "cancelada" in estado_norm or "replanific" in estado_norm:
                    plan_title_fmt = f"<s>❎ {plan_link}</s>"
                elif "epica en riesgo" in estado_norm:
                    plan_title_fmt = f"⚠️ {plan_link}"
                elif "epica sin empezar" in estado_norm:
                    plan_title_fmt = f"⏹️ {plan_link}"
                else:
                    plan_title_fmt = f"▶️ {plan_link}"

                resumen_planes.append(f"{plan_title_fmt} - <b>{fib_val} Fib</b>")

                # --- ANÁLISIS ---

 
                props = rd.get("properties", {})
                cant_integrantes = props.get("Cant. Integrantes", {}).get("number") or 0
                ultima_velocidad = props.get("Última Velocidad", {}).get("number") or 0.0
                day_number_val = props.get("DayNumber", {}).get("formula", {}).get("number") or 0
                fibs_esperados = cant_integrantes * day_number_val * ultima_velocidad
                registro_total_fibs = props.get("Target", {}).get("number") or 0.0
                registro_total_fibs_done = total_fibs

                mensaje_analisis = f"\n------------------------------------------------\n💰 Total {equipo}: {registro_total_fibs_done}/{registro_total_fibs} FIBS | "
                #mensaje_analisis += f"------------------------------------------------\n📊 Estimación vs Realidad\n      • {cant_integrantes} Personas | Día: {day_number_val}\n"
                #mensaje_analisis += f"      • Vel. Sprint anterior: {ultima_velocidad}\n      • FIBS esperados: {fibs_esperados:.2f} \n      • FIBS cerrados: {registro_total_fibs_done}\n\n"

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


        if resumen_planes:
            emoji = Config.EMOJIS.get(equipo, "📋")
            mensaje = f"{emoji} <b>{equipo}</b>\n------------------------------------------------\n" + "\n".join(resumen_planes) + f"{mensaje_analisis}\n\n"
            mensajes_por_equipo[equipo] = mensaje

    # Combinar todos los mensajes en uno solo
    if not mensajes_por_equipo:
        return "No se encontraron planes para el día de hoy."

    mensaje_final = "<b>ÉPICAS DEL SPRINT</b>\n\n" + "\n".join(
        mensajes_por_equipo[equipo] for equipo in sorted(mensajes_por_equipo.keys())
    )
    return mensaje_final
