import requests
from datetime import datetime, timedelta
import dateutil.parser  # Para parsear fechas con o sin zona horaria

# --- CONFIGURACIONES ---
import Config


fecha_manana_dt = datetime.now(Config.ARG_TZ) + timedelta(days=1)
fecha_manana = fecha_manana_dt.strftime('%d-%m-%Y')

# --- FUNCIONES NOTION ---
def get_registros_manana_calendar():
    """Obtiene los registros que incluyen el día de mañana desde Notion"""
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

    # Filtrar por fecha de mañana
    registros_filtrados = []
    for r in registros:
        date_prop = r['properties'].get('Date', {}).get('date')
        if not date_prop or not date_prop.get('start'):
            continue
        start_dt = dateutil.parser.isoparse(date_prop['start']).replace(tzinfo=None)
        end_dt = dateutil.parser.isoparse(date_prop['end']).replace(tzinfo=None) if date_prop.get('end') else start_dt
        if start_dt.date() <= fecha_manana_dt.date() <= end_dt.date():
            registros_filtrados.append(r)

    print(f"Registros de calendario para mañana ({fecha_manana}): {len(registros_filtrados)}")
    return registros_filtrados

# --- FUNCIONES AUXILIARES ---
def format_linea(r):
    props = r['properties']

    # --- Tipo base (sirve para clasificar en resumen_calendar) ---
    tipo = "Sin tipo"
    tipo_prop = props.get('Tipo')
    if tipo_prop:
        if tipo_prop.get('select'):
            tipo = tipo_prop['select'].get('name', 'Sin tipo')
        elif tipo_prop.get('multi_select') and len(tipo_prop['multi_select']) > 0:
            tipo = tipo_prop['multi_select'][0].get('name', 'Sin tipo')
        elif tipo_prop.get('rollup'):
            rollup = tipo_prop['rollup']
            if 'array' in rollup and len(rollup['array']) > 0:
                tipo = rollup['array'][0].get('name', 'Sin tipo')

    # --- Título visible ---
    titulo = tipo
    if tipo in Config.TIPOS_SIN_INICIO_OFICINA:
        titulo_prop = props.get('Name', {}).get('title', [])
        if titulo_prop:
            titulo = "".join([t['plain_text'] for t in titulo_prop])

    # --- Cliente ---
    cliente_texto = ""
    if tipo not in Config.TIPOS_SIN_CLIENTE:
        cliente_prop = props.get('Cliente', {})
        if cliente_prop.get('type') == 'rollup':
            rollup = cliente_prop.get('rollup', {})
            if 'array' in rollup:
                nombres = []
                for item in rollup['array']:
                    if 'name' in item:
                        nombres.append(item['name'])
                    elif item.get('type') == 'select':
                        nombres.append(item['select']['name'])
                if nombres:
                    cliente_texto = ', '.join(nombres)
            elif 'string' in rollup:
                cliente_texto = rollup['string']
        elif cliente_prop.get('type') == 'select':
            cliente_texto = cliente_prop.get('select', {}).get('name', '')
        elif cliente_prop.get('type') == 'multi_select':
            nombres = [sel['name'] for sel in cliente_prop.get('multi_select', [])]
            if nombres:
                cliente_texto = ', '.join(nombres)

    # --- Hora desde Date ---
    date_prop = props.get('Date', {}).get('date', {})
    hora_texto = ""
    if date_prop and date_prop.get('start'):
        try:
            dt_start = dateutil.parser.isoparse(date_prop['start']).replace(tzinfo=None)
            if not (dt_start.hour == 0 and dt_start.minute == 0):
                hora_texto = dt_start.strftime("%H:%M")
        except Exception:
            hora_texto = ""

    # --- Personas ---
    personas = props.get('Person', {}).get('people', [])
    persona_texto = "\n".join([f"      - {p.get('name', '')}" for p in personas]) if personas else "      - Sin persona"

    # --- Confirmado ---
    confirmado = props.get('Confirmado', {}).get('checkbox', False)
    confirmado_texto = "▪️" if confirmado else "[?]\n"

    # --- Línea principal ---
    linea_principal = f"{confirmado_texto} {titulo}"
    if cliente_texto:
        linea_principal += f"\n        {cliente_texto}"
    if hora_texto:
        linea_principal += f" ({hora_texto})"

    # --- Línea final ---
    linea = f"<b>{linea_principal}</b>\n{persona_texto}"
    return linea

# --- RESUMEN PRINCIPAL ---
def resumen_calendar(registros):
    """Genera un resumen completo con apartados por equipo, General y No inicia jornada"""
    resumen_lines = [f"📅 <b>AGENDA DEL DÍA {fecha_manana}</b>"]

    # --- Función auxiliar para obtener fecha/hora ---
    def fecha_inicio(r):
        date_prop = r['properties'].get('Date', {}).get('date', {})
        if date_prop and date_prop.get('start'):
            try:
                return dateutil.parser.isoparse(date_prop['start']).replace(tzinfo=None)
            except:
                return datetime.max
        return datetime.max

    registros.sort(key=fecha_inicio)

    equipos_dict = {}

    for r in registros:
        props = r['properties']

        # --- Extraer tipo ---
        tipo = "Sin tipo"
        tipo_prop = props.get('Tipo')
        if tipo_prop:
            if tipo_prop.get('select'):
                tipo = tipo_prop['select'].get('name', 'Sin tipo')
            elif tipo_prop.get('multi_select') and len(tipo_prop['multi_select']) > 0:
                tipo = tipo_prop['multi_select'][0].get('name', 'Sin tipo')
            elif tipo_prop.get('rollup'):
                rollup = tipo_prop['rollup']
                if 'array' in rollup and len(rollup['array']) > 0:
                    tipo = rollup['array'][0].get('name', 'Sin tipo')

        tipo_lower = tipo.lower()

        # --- 1️⃣ Si está en TIPOS_SIN_INICIO_OFICINA → siempre va a "No inicia jornada" ---
        if tipo in Config.TIPOS_SIN_INICIO_OFICINA:
            equipos_dict.setdefault("No inicia jornada en la oficina", []).append(r)
            continue

        # --- 2️⃣ Si es Evento Personal o Evento EPROC, evaluar hora de inicio ---
        if tipo_lower in [t.lower() for t in ["Evento Personal", "Evento EPROC"]]:
            date_prop = props.get('Date', {}).get('date', {})
            hora_ok = None
            if date_prop and date_prop.get('start'):
                try:
                    dt_start = dateutil.parser.isoparse(date_prop['start'])
                    # Convertir siempre a hora de Argentina
                    if dt_start.tzinfo is None:
                        dt_start = Config.ARG_TZ.localize(dt_start)
                    else:
                        dt_start = dt_start.astimezone(Config.ARG_TZ)
                    hora_ok = dt_start.hour * 60 + dt_start.minute
                except:
                    hora_ok = None

            # Si empieza temprano → “No inicia jornada”
            if hora_ok is None or hora_ok <= (8 * 60 + Config.MARGEN_MINUTOS):
                equipos_dict.setdefault("No inicia jornada en la oficina", []).append(r)
                continue

        # --- 3️⃣ En cualquier otro caso, agrupar por equipo o General ---
        equipos = props.get('Equipo', {}).get('multi_select', [])
        equipos_nombres = [e['name'] for e in equipos] or ["General"]
        for eq in equipos_nombres:
            equipos_dict.setdefault(eq, []).append(r)

    # --- Asegurar categorías base ---
    equipos_dict.setdefault("No inicia jornada en la oficina", [])
    equipos_dict.setdefault("General", [])

    # --- Orden de apartados ---
    apartados_orden = ["No inicia jornada en la oficina"] + \
                      [e for e in equipos_dict if e not in ["No inicia jornada en la oficina", "General"]] + \
                      ["General"]

    # --- Construcción del resumen ---
    for equipo in apartados_orden:
        regs = equipos_dict[equipo]
        if equipo == "General":
            emojiteam = "📌"
            nombre_mostrar = equipo
        elif equipo == "No inicia jornada en la oficina":
            emojiteam = "📍"
            nombre_mostrar = "No inicia jornada\n        en la oficina"
        else:
            emojiteam = {"Huemules": "🫎", "Zorros": "🦊", "Caimanes": "🐊"}.get(equipo, "🤌")
            nombre_mostrar = equipo

        resumen_lines.append(f"\n<b>{emojiteam} {nombre_mostrar}</b>\n----------------------------------------------")
        if regs:
            regs.sort(key=fecha_inicio)
            for r in regs:
                resumen_lines.append(format_linea(r))
        else:
            resumen_lines.append("      - No hay registros")

    return "\n".join(resumen_lines)



# --- SCRIPT PRINCIPAL ---
async def generar_resumen_manana():
    registros_manana = get_registros_manana_calendar()
    resumen = resumen_calendar(registros_manana)
    return resumen


