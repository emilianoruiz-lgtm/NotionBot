import requests
from datetime import datetime, timedelta
from telegram import Bot
from telegram.constants import ParseMode
from modules.AgendaPlAdmin import format_linea



# --- CONFIGURACIONES ---
import Config


# Orden sugerido de equipos (si existen); el resto se ordena alfabéticamente
TEAM_ORDER = {"Huemules": 0, "Zorros": 1, "Caimanes": 2}

# Días en español (evitamos locale)
DIAS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

def dia_es(d):
    """Devuelve 'Lunes 25/08/2025' para una fecha date/datetime."""
    return f"{DIAS_ES[d.weekday()]} {d.strftime('%d/%m/%Y')}"


# --- FUNCIONES TELEGRAM ---
async def enviar_a_telegram(comentario):
    if comentario:
        bot = Bot(token=Config.TELEGRAM_TOKEN)
        try:
            msg = await bot.send_message(chat_id=Config.CHAT_ID, text=comentario, parse_mode=ParseMode.HTML)
            print("Mensaje enviado:", msg.message_id)
        except Exception as e:
            print("Error enviando mensaje a Telegram:", e)


def _fecha_inicio(r):
    date_prop = r['properties'].get('Date', {}).get('date', {})
    if date_prop and date_prop.get('start'):
        try:
            return datetime.fromisoformat(date_prop['start'].replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return datetime.max
    return datetime.max

# --- CÁLCULO DEL LUNES Y DOMINGO SIGUIENTE ---
hoy = datetime.now().date()
dias_hasta_lunes = (0 - hoy.weekday() + 7) % 7
dias_hasta_lunes = dias_hasta_lunes or 7  # si hoy ya es lunes, ir al próximo
lunes_siguiente = hoy + timedelta(days=dias_hasta_lunes)
domingo_siguiente = lunes_siguiente + timedelta(days=6)

# --- FUNCIONES NOTION PARA SEMANA SIGUIENTE ---
def get_registros_semana_siguiente():
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
        start_dt = datetime.fromisoformat(date_prop['start'].replace("Z", "+00:00")).replace(tzinfo=None)
        end_dt = datetime.fromisoformat(date_prop['end'].replace("Z", "+00:00")).replace(tzinfo=None) if date_prop.get('end') else start_dt

        # Mantener solo los registros que se solapan con lunes-domingo siguiente
        if start_dt.date() <= domingo_siguiente and end_dt.date() >= lunes_siguiente:
            registros_filtrados.append(r)

    print(f"Registros filtrados para la semana {lunes_siguiente} - {domingo_siguiente}: {len(registros_filtrados)}")
    return registros_filtrados


# --- FUNCIÓN PRINCIPAL SEMANA SIGUIENTE ---
async def AgendaPlAdminSemanaSiguiente():
    registros_semana = get_registros_semana_siguiente()
    resumen_semana = resumen_calendar_semana_siguiente(registros_semana)
    return resumen_semana


def resumen_calendar_semana_siguiente(registros):
    resumen_lines = [f"📅 <b>AGENDA SEMANA SIGUIENTE {lunes_siguiente.strftime('%d/%m/%Y')} - {domingo_siguiente.strftime('%d/%m/%Y')}</b>"]

    registros.sort(key=_fecha_inicio)
    agenda = {}

    for r in registros:
        date_prop = r['properties'].get('Date', {}).get('date', {})
        if not date_prop or not date_prop.get('start'):
            continue

        start_dt = datetime.fromisoformat(date_prop['start'].replace("Z", "+00:00")).replace(tzinfo=None)
        end_dt = datetime.fromisoformat(date_prop['end'].replace("Z", "+00:00")).replace(tzinfo=None) if date_prop.get('end') else start_dt

        dia = max(start_dt.date(), lunes_siguiente)
        ultimo = min(end_dt.date(), domingo_siguiente)

        props = r['properties']
        tipo = props.get('Tipo', {}).get('select', {}).get('name', '').strip().lower()

        while dia <= ultimo:
            if tipo in Config.TIPOS_SIN_INICIO_OFICINA:
                equipos_destino = ["No inicia jornada en la oficina"]
            else:
                equipos = props.get('Equipo', {}).get('multi_select', [])
                equipos_destino = [e['name'].capitalize() for e in equipos] if equipos else ["General"]

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