# ==========================================
# 1. IMPORTS
# ==========================================

# Módulos Locales
import Config



fecha_manana_dt = Config.datetime.now(Config.ARG_TZ) + Config.timedelta(days=1)
fecha_manana = fecha_manana_dt.strftime('%d-%m-%Y')


def get_team_config(equipo):
    cfg = Config.EQUIPOS_CONFIG.get(equipo, {})
    return (
        cfg.get("emoji", Config.DEFAULT_TEAM_EMOJI),
        cfg.get("display_name", equipo),
    )

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

        response = Config.requests.post(
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
        start_dt = Config.dateutil.parser.isoparse(date_prop['start']).replace(tzinfo=None)
        end_dt = Config.dateutil.parser.isoparse(date_prop['end']).replace(tzinfo=None) if date_prop.get('end') else start_dt
        if start_dt.date() <= fecha_manana_dt.date() <= end_dt.date():
            registros_filtrados.append(r)

    print(f"Registros de calendario para mañana ({fecha_manana}): {len(registros_filtrados)}")
    return registros_filtrados

# --- FUNCIONES AUXILIARES ---
def get_alias(nombre):
    return Config.ALIAS_PERSONAS.get(nombre, nombre)

def get_personas(props):
    personas = props.get('Person', {}).get('people', [])
    nombres = [p.get('name', '') for p in personas if p.get('name')]
    return [get_alias(n) for n in nombres]


def get_tipo(props):
    tipo = "Sin tipo"
    tipo_prop = props.get('Tipo')
    if tipo_prop:
        if tipo_prop.get('select'):
            tipo = tipo_prop['select'].get('name', 'Sin tipo')
        elif tipo_prop.get('multi_select'):
            if tipo_prop['multi_select']:
                tipo = tipo_prop['multi_select'][0].get('name', 'Sin tipo')
        elif tipo_prop.get('rollup'):
            arr = tipo_prop['rollup'].get('array', [])
            if arr:
                tipo = arr[0].get('name', 'Sin tipo')
    return tipo


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

    # Nombre de personas
    personas = props.get('Person', {}).get('people', [])
    nombres_personas = ", ".join([p.get('name', '') for p in personas if p.get('name')])

    # Caso AUSENTE → "Persona – Tipo"
    if tipo in Config.TIPOS_SIN_ARRANQUE_NORMAL:
        if nombres_personas:
            titulo = f"{nombres_personas} – {tipo}"
        else:
            titulo = tipo

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
            dt_start = Config.dateutil.parser.isoparse(date_prop['start']).replace(tzinfo=None)
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

def fecha_inicio(r):
        date_prop = r['properties'].get('Date', {}).get('date', {})
        if date_prop and date_prop.get('start'):
            try:
                return Config.dateutil.parser.isoparse(date_prop['start']).replace(tzinfo=None)
            except:
                return Config.datetime.max
        return Config.datetime.max

def titulo_con_guiones(nombre, total=30):
    base = f"{nombre} "
    return base + "-" * max(0, total - len(base))

# --- RESUMEN PRINCIPAL ---
def resumen_calendar(registros, fecha):
    fecha_str = fecha.strftime("%d-%m-%Y")
    resumen_lines = [f"📅 <b>AGENDA {fecha_str}</b>"]
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


        if tipo in Config.TIPOS_SIN_ARRANQUE_NORMAL:
            equipos_dict.setdefault("Ausente", []).append(r)
            continue

        if tipo in Config.TIPOS_ARRANQUE_REMOTO:
            equipos_dict.setdefault("Inicio remoto", []).append(r)
            continue

        if tipo in Config.TIPOS_GUARDIA:
                equipos_dict.setdefault("Guardia", []).append(r)
                continue

        if tipo_lower in [t.lower() for t in ["Evento Personal", "Evento EPROC"]]:
            date_prop = props.get('Date', {}).get('date', {})
            hora_ok = None
            if date_prop and date_prop.get('start'):
                try:
                    dt_start = Config.dateutil.parser.isoparse(date_prop['start'])
                    if dt_start.tzinfo is None:
                        dt_start = Config.ARG_TZ.localize(dt_start)
                    else:
                        dt_start = dt_start.astimezone(Config.ARG_TZ)
                    hora_ok = dt_start.hour * 60 + dt_start.minute
                except:
                    hora_ok = None
            if hora_ok is None or hora_ok <= (8 * 60 + Config.MARGEN_MINUTOS):
                equipos_dict.setdefault("Ausente", []).append(r)
                continue

        # --- 3️⃣ En cualquier otro caso, agrupar por equipo o General ---
        equipos = props.get('Equipo', {}).get('multi_select', [])
        equipos_nombres = [e['name'] for e in equipos] or ["General"]
        for eq in equipos_nombres:
            equipos_dict.setdefault(eq, []).append(r)

    # --- Asegurar categorías base ---
    equipos_dict.setdefault("Ausente", [])
    equipos_dict.setdefault("Inicio remoto", [])
    equipos_dict.setdefault("General", [])
    equipos_dict.setdefault("Guardia", [])

    # --- Orden de apartados ---
    apartados_orden = ["Ausente"] + ["Inicio remoto"] + \
                      [e for e in equipos_dict if e not in ["Ausente", "Inicio remoto", "General", "Guardia"]] + \
                      ["General"] + ["Guardia"]

    #  --- Construcción del resumen ---
    for equipo in apartados_orden:
        regs = equipos_dict.get(equipo, [])

        if equipo == "General" and not regs:
            continue

        emojiteam, nombre_mostrar = get_team_config(equipo)
        titulo = titulo_con_guiones(nombre_mostrar)

        resumen_lines.append(f"\n<b>{emojiteam} {titulo}</b>")

        if regs:
            regs.sort(key=fecha_inicio)

            for r in regs:
                props = r['properties']
                tipo = get_tipo(props)
                personas = get_personas(props)

                for p in personas or ["Sin persona"]:
                    resumen_lines.append(f"      {p} – {tipo}")
        else:
            resumen_lines.append(Config.NO_REGISTROS_TEXT)

    return "\n".join(resumen_lines)

async def generar_resumen_manana():
    registros_manana = get_registros_manana_calendar()
    resumen = resumen_calendar(registros_manana)
    return resumen

def get_registros_calendar_por_fecha(fecha_dt):
    registros = []
    has_more = True
    next_cursor = None

    while has_more:
        query = {"page_size": 100}
        if next_cursor:
            query["start_cursor"] = next_cursor

        response = Config.requests.post(
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

        start_dt = Config.dateutil.parser.isoparse(date_prop['start']).date()
        end_dt = (
            Config.dateutil.parser.isoparse(date_prop['end']).date()
            if date_prop.get('end')
            else start_dt
        )

        if start_dt <= fecha_dt <= end_dt:
            registros_filtrados.append(r)

    return registros_filtrados

async def AgendaMenu(fecha):
    registros = get_registros_calendar_por_fecha(fecha)
    resumen = resumen_calendar(registros, fecha)
    return resumen