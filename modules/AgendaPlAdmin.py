# -*- coding: utf-8 -*-
import asyncio
import requests
import unicodedata
from datetime import datetime, timedelta
from telegram import Bot
from telegram.constants import ParseMode

# --- CONFIGURACIONES ---
import Config

# Orden sugerido de equipos (si existen); el resto se ordena alfabéticamente
TEAM_ORDER = {"Huemules": 0, "Zorros": 1, "Caimanes": 2}

# Días en español (evitamos locale)
DIAS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

def dia_es(d):
    """Devuelve 'Lunes 25/08/2025' para una fecha date/datetime."""
    return f"{DIAS_ES[d.weekday()]} {d.strftime('%d/%m/%Y')}"

# --- CALCULO DEL MARTES SIGUIENTE Y SEGUNDO DOMINGO ---
hoy = datetime.now().date()
# weekday(): lunes=0 ... domingo=6
dias_hasta_martes = (1 - hoy.weekday() + 7) % 7
dias_hasta_martes = dias_hasta_martes or 7  # si hoy ya es martes, ir al próximo
martes_siguiente = hoy + timedelta(days=dias_hasta_martes)

# segundo domingo siguiente (13 días después)
fin_domingo = martes_siguiente + timedelta(days=13)

# --- FUNCIONES NOTION ---
def get_registros_semana_calendar():
    registros = []
    has_more = True
    next_cursor = None

    while has_more:
        query = {"page_size": 100}
        if next_cursor:
            query["start_cursor"] = next_cursor

        response = requests.post(
            f"https://api.notion.com/v1/databases/{Config.DATABASE_ID_CALENDAR}/query",
            headers=Config.HEADERS,
            json=query
        )
        data = response.json()
        registros.extend(data.get('results', []))
        has_more = data.get('has_more', False)
        next_cursor = data.get('next_cursor')

    registros_filtrados = []
    for r in registros:
        date_prop = r['properties'].get('Date', {}).get('date')
        if not date_prop or not date_prop.get('start'):
            continue
        # Convertir a naive datetime
        start_dt = datetime.fromisoformat(date_prop['start'].replace("Z", "+00:00")).replace(tzinfo=None)
        end_dt = datetime.fromisoformat(date_prop['end'].replace("Z", "+00:00")).replace(tzinfo=None) if date_prop.get('end') else start_dt
        # Mantener solo lo que se solapa con la semana objetivo
        if start_dt.date() <= fin_domingo and end_dt.date() >= martes_siguiente:
            registros_filtrados.append(r)

    print(f"Registros filtrados para la semana {martes_siguiente} - {fin_domingo}: {len(registros_filtrados)}")
    return registros_filtrados

# --- FUNCIONES AUXILIARES ---
def _alias_nombre(nombre):
    """Normaliza y mapea a alias si existe."""
    if not nombre:
        return ""
    n = unicodedata.normalize('NFKC', nombre).strip()
    return Config.ALIAS_PERSONAS.get(n, n)

def format_linea(r):
    props = r['properties']
    tipo = props.get('Tipo', {}).get('select', {}).get('name', '').strip()
    tipo_lower = tipo.lower()

    # --- Título visible ---
    if tipo in Config.TIPOS_SIN_INICIO_OFICINA:
        titulo_prop = props.get('Name', {}).get('title', [])
        titulo = "".join([t.get('plain_text', '') for t in titulo_prop]) if titulo_prop else tipo
    else:
        titulo = tipo

    # Cliente
    cliente_texto = ""
    if tipo_lower not in [t.lower() for t in Config.TIPOS_SIN_CLIENTE]:
        cliente_prop = props.get('Cliente', {})
        if cliente_prop.get('type') == 'rollup':
            rollup = cliente_prop.get('rollup', {})
            if 'array' in rollup:
                nombres = []
                for item in rollup['array']:
                    if 'name' in item:
                        nombres.append(item['name'])
                    elif item.get('type') == 'select' and item.get('select'):
                        nombres.append(item['select'].get('name', ''))
                if nombres:
                    cliente_texto = ', '.join([n for n in nombres if n])
            elif 'string' in rollup:
                cliente_texto = rollup['string']
        elif cliente_prop.get('type') == 'select':
            cliente_texto = cliente_prop.get('select', {}).get('name', '')
        elif cliente_prop.get('type') == 'multi_select':
            nombres = [sel['name'] for sel in cliente_prop.get('multi_select', [])]
            if nombres:
                cliente_texto = ', '.join(nombres)

    # Hora (solo si no es 00:00)
    date_prop = props.get('Date', {}).get('date')
    hora_texto = ""
    if date_prop and date_prop.get('start'):
        dt_start = datetime.fromisoformat(date_prop['start'].replace("Z", "+00:00")).replace(tzinfo=None)
        if dt_start.hour != 0 or dt_start.minute != 0:
            hora_texto = dt_start.strftime("%H:%M")

    # Personas -> alias
    personas = props.get('Person', {}).get('people', [])
    nombres = [_alias_nombre(p.get('name', '')) for p in personas]
    nombres = [n for n in nombres if n]
    persona_texto = ", ".join(nombres) if nombres else "Sin persona"

    # Confirmado
    confirmado = props.get('Confirmado', {}).get('checkbox', False)
    confirmado_texto = "         ▪️" if confirmado else "         [?]"

    # Línea compacta final
    linea = f"{confirmado_texto} {titulo}"
    if cliente_texto:
        linea += f"\n             <b>{cliente_texto}</b>"
    if hora_texto:
        linea += f" <b>({hora_texto})</b>"
    linea += f" - {persona_texto}"
    return linea

def _fecha_inicio(r):
    date_prop = r['properties'].get('Date', {}).get('date', {})
    if date_prop and date_prop.get('start'):
        try:
            return datetime.fromisoformat(date_prop['start'].replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return datetime.max
    return datetime.max

# --- RESUMEN PRINCIPAL ---
def resumen_calendar(registros):
    resumen_lines = [f"📅 <b>AGENDA SEMANA {martes_siguiente.strftime('%d/%m/%Y')} - {fin_domingo.strftime('%d/%m/%Y')}</b>"]

    registros.sort(key=_fecha_inicio)

    # --- Agrupamos por día (rango start->end) y por equipo ---
    agenda = {}

    for r in registros:
        date_prop = r['properties'].get('Date', {}).get('date', {})
        if not date_prop or not date_prop.get('start'):
            continue

        start_dt = datetime.fromisoformat(date_prop['start'].replace("Z", "+00:00")).replace(tzinfo=None)
        end_dt = datetime.fromisoformat(date_prop['end'].replace("Z", "+00:00")).replace(tzinfo=None) if date_prop.get('end') else start_dt

        dia = max(start_dt.date(), martes_siguiente)
        ultimo = min(end_dt.date(), fin_domingo)

        props = r['properties']
        tipo = props.get('Tipo', {}).get('select', {}).get('name', '').strip().lower()

        while dia <= ultimo:
            if tipo in Config.TIPOS_SIN_INICIO_OFICINA:
                equipos_destino = ["No inicia jornada en la oficina"]
            else:
                equipos = props.get('Equipo', {}).get('multi_select', [])
                equipos_destino = [e['name'] for e in equipos] or ["General"]

            agenda.setdefault(dia, {})
            for eq in equipos_destino:
                agenda[dia].setdefault(eq, []).append(r)

            dia += timedelta(days=1)

    # --- Construcción del texto final ---
    for dia in sorted(agenda.keys()):
        resumen_lines.append(f"\n\n📆 <u>{dia_es(dia)}</u>")
        equipos_dict = agenda[dia]

        presentes = list(equipos_dict.keys())
        orden_equipos = []

        # Prioridades
        if "No inicia jornada en la oficina" in presentes:
            orden_equipos.append("No inicia jornada en la oficina")

        for eq in TEAM_ORDER:
            if eq in presentes:
                orden_equipos.append(eq)

        for eq in sorted(presentes):
            if eq not in orden_equipos and eq != "General":
                orden_equipos.append(eq)

        if "General" in presentes:
            orden_equipos.append("General")

        # Render por equipo
        for eq in orden_equipos:
            if eq == "General":
                emojiteam = "      📌"
                nombre_mostrar = eq
            elif eq == "No inicia jornada en la oficina":
                emojiteam = "      📍"
                nombre_mostrar = "No inicia jornada\n        en la oficina"
            else:
                emojiteam = {"Huemules": "      🫎", "Zorros": "      🦊", "Caimanes": "      🐊"}.get(eq, "      🤌")
                nombre_mostrar = eq
            resumen_lines.append(f"\n{emojiteam} {nombre_mostrar}")
            for r in equipos_dict[eq]:
                resumen_lines.append(format_linea(r))

    return "\n".join(resumen_lines)

# --- FUNCIONES TELEGRAM ---
async def enviar_a_telegram(comentario):
    if comentario:
        bot = Bot(token=Config.TELEGRAM_TOKEN)
        try:
            msg = await bot.send_message(chat_id=Config.CHAT_ID, text=comentario, parse_mode=ParseMode.HTML)
            print("Mensaje enviado:", msg.message_id)
        except Exception as e:
            print("Error enviando mensaje a Telegram:", e)

# --- SCRIPT PRINCIPAL ---
async def AgendaPlAdmin():
    registros_semana = get_registros_semana_calendar()
    resumen_semana = resumen_calendar(registros_semana)
    return resumen_semana



