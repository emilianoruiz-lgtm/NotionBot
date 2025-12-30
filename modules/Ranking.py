import asyncio
import aiohttp
from datetime import datetime, timedelta
import html
from collections import defaultdict

# --- CONFIGURACIONES ---
import Config

async def fetch_all_notion(session: aiohttp.ClientSession, url: str, payload: dict = None):
    """Devuelve la lista completa de resultados de una query Notion.
       session: aiohttp.ClientSession()
       url: endpoint (string)
       payload: dict o None
    """
    if payload is None:
        payload = {}

    all_results = []
    has_more = True
    start_cursor = None

    while has_more:
        if start_cursor:
            payload["start_cursor"] = start_cursor
        async with session.post(url, headers=Config.HEADERS, json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
        results = data.get("results", [])
        all_results.extend(results)
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")
    return all_results


async def generar_equipos(jugadores_elo, ausentes):
    """
    Genera equipos equilibrados según ELO.
    jugadores_elo: dict {nombre_completo: elo}
    ausentes: lista de ALIAS a excluir (ej: ["EMR", "DPD"])
    """
    ausentes_set = set(a.upper() for a in ausentes)

    # Filtrar jugadores usando alias
    jugadores_filtrados = {
        j: e for j, e in jugadores_elo.items() if j.upper() not in ausentes_set
    }

    # Ordenar por ELO descendente
    sorted_jugadores = sorted(jugadores_filtrados.items(), key=lambda x: x[1], reverse=True)

    equipos = []
    while len(sorted_jugadores) >= 2:
        jugador_alto = sorted_jugadores.pop(0)
        jugador_bajo = sorted_jugadores.pop(-1)
        equipos.append((jugador_alto, jugador_bajo))

    if sorted_jugadores:
        equipos.append((sorted_jugadores[0], ("—", 0)))

    # Construir mensaje con alias y ELO
    msg = ""
    for i, (j1, j2) in enumerate(equipos, 1):
        alias1 = Config.ALIAS_PERSONAS.get(j1[0], j1[0])
        alias2 = Config.ALIAS_PERSONAS.get(j2[0], j2[0])
        elo1 = int(j1[1])
        elo2 = int(j2[1])

        # 👉 Si el equipo es de un solo jugador, no dividir por 2
        if j2[0] == "—" or elo2 == 0:
            poder = elo1
        else:
            poder = (elo1 + elo2) / 2

        num = Config.NUM_EMOJIS.get(i, f"{i}️⃣")
        msg += f"\n{num} ⚡{poder} \n <b>{alias1}</b> {elo1} | <b>{alias2}</b> {elo2}\n"

    return msg


# --- FUNCIONES NOTION ---
# --- Función global para ajustar ELO individual ---
def ajustar_elo_individual(jugadores_equipo, jugadores_del_dia, elo, gana, segundo):
    K = 32
    S = 1 if gana else 0.5 if segundo else 0
    rivales = [j for j in jugadores_del_dia if j not in jugadores_equipo]

    for j in jugadores_equipo:
        elo_j = elo[j]
        if rivales:
            # Tomar el ELO del rival más fuerte (mayor ELO)
            elo_rivales = max(elo[r] for r in rivales)
        else:
            elo_rivales = 1200
        E = 1 / (1 + 10 ** ((elo_rivales - elo_j) / 400))
        elo[j] += int(K * (S - E))
    return elo


# --- FUNCIONES AUXILIARES ---
def ajustar_elo_simple(elo_actual: int, elo_rival: int, resultado: float, K: int = 32) -> int:
    """
    elo_actual: ELO del jugador
    elo_rival: ELO del rival (promedio o máximo según tu criterio)
    resultado: 1 (win), 0.5 (second), 0 (loss)
    """
    E = 1 / (1 + 10 ** ((elo_rival - elo_actual) / 400))
    delta = int(K * (resultado - E))
    return elo_actual + delta


async def generar_elo_metegol():
    """
    Calcula todo el historial de torneos en Notion,
    ajusta ELO usando promedio de rivales y sin actualizar secuencialmente,
    y devuelve puntos, torneos jugados, torneos puntuados, logros, registros y ELO final.
    """
    async with aiohttp.ClientSession() as session:
        url = f"https://api.notion.com/v1/databases/{Config.DATABASE_ID_MT}/query"
        registros_raw = await fetch_all_notion(session, url, payload={})

    # Parseo de registros por fecha
    registros_por_fecha = defaultdict(list)
    for r in registros_raw:
        props = r.get("properties", {})
        fecha_raw = props.get("Fecha", {}).get("date", {}).get("start")
        if not fecha_raw:
            continue
        fecha = fecha_raw[:10]
        who_data = props.get("Who", {}).get("people", [])
        gana = props.get("Gana", {}).get("checkbox", False)
        segundo = props.get("Segundo", {}).get("checkbox", False)
        jugadores = [p.get("name", "Sin nombre") for p in who_data]

        registros_por_fecha[fecha].append({
            "jugadores": jugadores,
            "gana": gana,
            "segundo": segundo
        })

    # Inicializar estructuras
    puntos_total = defaultdict(int)
    torneos_jugados = defaultdict(int)
    torneos_puntuados = defaultdict(int)
    logros = defaultdict(list)
    elo = defaultdict(lambda: 1200)  # ELO inicial
    K = 32

    # Procesar torneos por fecha
    for fecha, torneo in registros_por_fecha.items():
        jugadores_del_dia = set(j for eq in torneo for j in eq["jugadores"])
        for j in jugadores_del_dia:
            if j not in elo:
                elo[j] = 1200

        # Definir grupos
        grupo_ganadores = set(j for eq in torneo if eq.get("gana") for j in eq["jugadores"])
        grupo_segundos = set(j for eq in torneo if eq.get("segundo") for j in eq["jugadores"])
        grupo_perdedores = jugadores_del_dia - grupo_ganadores - grupo_segundos

        # Calcular cambios de ELO del día en paralelo
        deltas = defaultdict(int)
        for equipo in torneo:
            jugadores_equipo = set(equipo["jugadores"])
            if equipo.get("gana"):
                rivales = (grupo_segundos | grupo_perdedores) - jugadores_equipo
                resultado = 1
            elif equipo.get("segundo"):
                rivales = (grupo_ganadores | grupo_perdedores) - jugadores_equipo
                resultado = 0.5
            else:
                rivales = jugadores_del_dia - jugadores_equipo
                resultado = 0

            if rivales:
                elo_rivales = sum(elo[r] for r in rivales)/len(rivales)
            else:
                elo_rivales = 1200

            for j in jugadores_equipo:
                E = 1 / (1 + 10 ** ((elo_rivales - elo[j]) / 400))
                deltas[j] += int(K * (resultado - E))

        # Aplicar los deltas al final del día
        for j, delta in deltas.items():
            elo[j] += delta

        # Actualizar puntos, torneos y logros
        total_jugadores = len(jugadores_del_dia)
        if total_jugadores <= 4:
            pts_ganador, pts_segundo, tipo = 300, 0, "CH"
        elif total_jugadores <= 6:
            pts_ganador, pts_segundo, tipo = 1000, 150, "ATP"
        elif total_jugadores <= 8:
            pts_ganador, pts_segundo, tipo = 2000, 500, "MS"
        else:
            pts_ganador, pts_segundo, tipo = 4000, 1000, "GS"

        fecha_formateada = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m")

        for j in jugadores_del_dia:
            torneos_jugados[j] += 1

        for equipo in torneo:
            for j in equipo["jugadores"]:
                if equipo.get("gana"):
                    puntos_total[j] += pts_ganador
                    torneos_puntuados[j] += 1
                    logros[j].append(f"🥇 {tipo} {pts_ganador} pts {fecha_formateada}")
                elif equipo.get("segundo"):
                    puntos_total[j] += pts_segundo
                    torneos_puntuados[j] += 1
                    logros[j].append(f"🥈 {tipo} {pts_segundo} pts {fecha_formateada}")

    return puntos_total, torneos_jugados, torneos_puntuados, logros, registros_por_fecha, dict(elo)




def generar_ranking_metegol(puntos_total, torneos_jugados, torneos_puntuados, logros, registros_por_fecha, elo, ausentes):
    import html

    MIN_TORNEOS = 5
    total_fechas = len(registros_por_fecha)
    
    # Ranking de puntos ponderado
    ranking = sorted(
        puntos_total.items(),
        key=lambda x: (
            (puntos_total[x[0]] / torneos_jugados[x[0]]) * min(1, torneos_jugados[x[0]] / MIN_TORNEOS)
            if torneos_jugados[x[0]] > 0 else 0
        ),
        reverse=True
    )

    # Ranking ELO
    ranking_elo = sorted(elo.items(), key=lambda x: x[1], reverse=True)

    resumen = "🏆 <b>Medallero últimos 30 días</b>\n"

    for i, (jugador, total) in enumerate(ranking, start=1):
        if jugador in ausentes:
            continue
        alias = Config.ALIAS_PERSONAS.get(jugador, jugador)
        jugados = torneos_jugados[jugador]
        puntuados = torneos_puntuados[jugador]
        promedio_ponderado = (total / jugados if jugados > 0 else 0) * min(1, jugados / MIN_TORNEOS)
        efectividad = (puntuados / jugados * 100) if jugados > 0 else 0
        participacion = (jugados / total_fechas * 100) if total_fechas > 0 else 0

        resumen += f"\n{i}. <b>{html.escape(alias)} {int(promedio_ponderado)} pts. pond.</b>\n     --------------------\n"
        resumen += f"   • {efectividad:.0f}% efectividad\n"
        resumen += f"   • {participacion:.0f}% participación\n     --------------------\n"

        for logro in logros[jugador]:
            resumen += f"   {html.escape(logro)}\n"

    return resumen


async def generar_cambio_elo():
    """
    Devuelve un diccionario con el cambio de ELO de cada jugador respecto a no considerar el día de hoy.
    Se calcula sin actualizar ELO de manera secuencial: todos usan el ELO al inicio del día.
    """
    # 1. Calcular ELO con todos los días
    _, _, _, _, registros_por_fecha, elo_con_hoy = await generar_elo_metegol()

    hoy = datetime.now().date().isoformat()
    torneo_hoy = registros_por_fecha.get(hoy, [])

    if not torneo_hoy:
        return {}

    # 2. ELO base al inicio del día (no secuencial)
    elo_base = elo_con_hoy.copy()
    # Para calcular ELO sin considerar hoy, empezamos desde 1200
    elo_sin_hoy = defaultdict(lambda: 1200)
    K = 32

    # Recalcular ELO sin hoy
    registros_sin_hoy = {f: t for f, t in registros_por_fecha.items() if f != hoy}
    for fecha, torneo in registros_sin_hoy.items():
        jugadores_del_dia = set(j for eq in torneo for j in eq["jugadores"] if eq["jugadores"])
        for j in jugadores_del_dia:
            if j not in elo_sin_hoy:
                elo_sin_hoy[j] = 1200

        grupo_ganadores = set(j for eq in torneo if eq.get("gana") for j in eq["jugadores"])
        grupo_segundos = set(j for eq in torneo if eq.get("segundo") for j in eq["jugadores"])
        grupo_perdedores = jugadores_del_dia - grupo_ganadores - grupo_segundos

        for equipo in torneo:
            jugadores_equipo = set(equipo["jugadores"])
            if not jugadores_equipo:
                continue

            if equipo.get("gana"):
                rivales = (grupo_segundos | grupo_perdedores) - jugadores_equipo
                S = 1
            elif equipo.get("segundo"):
                rivales = (grupo_ganadores | grupo_perdedores) - jugadores_equipo
                S = 0.5
            else:
                rivales = jugadores_del_dia - jugadores_equipo
                S = 0

            elo_rivales = max(elo_sin_hoy[r] for r in rivales) if rivales else 1200
            for j in jugadores_equipo:
                E = 1 / (1 + 10 ** ((elo_rivales - elo_sin_hoy[j]) / 400))
                elo_sin_hoy[j] += int(K * (S - E))

    # 3. Calcular cambios hoy sin actualizar secuencialmente
    jugadores_del_dia = set(j for eq in torneo_hoy for j in eq["jugadores"])
    grupo_ganadores = set(j for eq in torneo_hoy if eq.get("gana") for j in eq["jugadores"])
    grupo_segundos = set(j for eq in torneo_hoy if eq.get("segundo") for j in eq["jugadores"])
    grupo_perdedores = jugadores_del_dia - grupo_ganadores - grupo_segundos

    cambios = defaultdict(int)
    for equipo in torneo_hoy:
        jugadores_equipo = set(equipo["jugadores"])
        if equipo.get("gana"):
            rivales = (grupo_segundos | grupo_perdedores) - jugadores_equipo
            resultado = 1
        elif equipo.get("segundo"):
            rivales = (grupo_ganadores | grupo_perdedores) - jugadores_equipo
            resultado = 0.5
        else:
            rivales = jugadores_del_dia - jugadores_equipo
            resultado = 0

        # ELO promedio de rivales
        if rivales:
            elo_rivales = sum(elo_sin_hoy[r] for r in rivales)/len(rivales)
        else:
            elo_rivales = 1200

        for j in jugadores_equipo:
            E = 1 / (1 + 10 ** ((elo_rivales - elo_sin_hoy[j]) / 400))
            delta = int(K * (resultado - E))
            cambios[j] += delta

    # 4. ELO final al día de hoy
    elo_final = elo_sin_hoy.copy()
    for j, delta in cambios.items():
        elo_final[j] += delta

    return cambios, elo_final


async def generar_mensaje_cambio_elo(): 
    """
    Genera un resumen en Telegram del cambio de ELO respecto al día de hoy,
    usando la lógica no secuencial y ELO promedio de rivales.
    """
    cambios, elo_final = await generar_cambio_elo()
    _, _, _, logros, registros_por_fecha, _ = await generar_elo_metegol()
    
    hoy = datetime.now().date().isoformat()
    torneo_hoy = registros_por_fecha.get(hoy, [])

    if not torneo_hoy:
        return "No hubo juegos hoy."

    mensaje = "📊 <b>Cambios de ELO hoy</b>\n--------------------\n"

    jugadores_del_dia = set(j for eq in torneo_hoy for j in eq["jugadores"])
    grupo_ganadores = set(j for eq in torneo_hoy if eq.get("gana") for j in eq["jugadores"])
    grupo_segundos = set(j for eq in torneo_hoy if eq.get("segundo") for j in eq["jugadores"])
    grupo_perdedores = jugadores_del_dia - grupo_ganadores - grupo_segundos

    lista_final = []
    for equipo in torneo_hoy:
        jugadores_equipo = set(equipo["jugadores"])
        if equipo.get("gana"):
            rivales = (grupo_segundos | grupo_perdedores) - jugadores_equipo
            resultado_texto = "🥇 Ganó contra"
        elif equipo.get("segundo"):
            rivales = (grupo_ganadores | grupo_perdedores) - jugadores_equipo
            resultado_texto = "🥈 Segundo contra"
        else:
            rivales = jugadores_del_dia - jugadores_equipo
            resultado_texto = "❌ Perdió contra"

        rivales_alias = [Config.ALIAS_PERSONAS.get(r,r) for r in rivales]

        for j in jugadores_equipo:
            delta = cambios.get(j, 0)
            if delta > 0:
                emoji = "📈"
                signo = f"+{delta}"
            elif delta < 0:
                emoji = "📉"
                signo = f"{delta}"
            else:
                emoji = "🟰"
                signo = "0"

            alias = Config.ALIAS_PERSONAS.get(j, j)
            lista_final.append({
                "texto": f"{emoji} <b>{html.escape(alias)}</b>: {signo} pts\n{resultado_texto} {', '.join(rivales_alias)}\n",
                "delta": delta
            })

    lista_final.sort(key=lambda x: x["delta"], reverse=True)
    mensaje += "\n".join(item["texto"] for item in lista_final)

    return mensaje





# --- RANK ELO ---
async def RankingELO():
    # Reutiliza la lógica de elo_metegol
    puntos_total, torneos_jugados, torneos_puntuados, logros, registros_por_fecha, elo_dict = await generar_elo_metegol()

    # --- Ranking ELO ---
    ranking_elo = sorted(elo_dict.items(), key=lambda x: x[1], reverse=True)

    # --- Construir mensaje ---
    resumen = "\n\n📊 <b>Ranking ELO</b>\n----------------------------------\n"
    for i, (jugador, rating) in enumerate(ranking_elo, start=1):
        alias = Config.ALIAS_PERSONAS.get(jugador, jugador)
        resumen += f"• {i}. <b>{html.escape(alias)}</b> {int(rating)}\n"

    return resumen




# --- FUNCIÓN SOLO PARA TEXTO ---
async def generar_resumen_metegol():
    _, _, resumen = await medal()
    return resumen




# --- FUNCIÓN INTERNA COMPARTIDA ---
async def medal():
    async with aiohttp.ClientSession() as session:
        hoy = datetime.now().date()
        fecha_inicio = hoy - timedelta(days=30)
        fecha_fin = hoy

        query = {
            "filter": {
                "and": [
                    {"property": "Fecha", "date": {"on_or_after": fecha_inicio.isoformat()}},
                    {"property": "Fecha", "date": {"on_or_before": fecha_fin.isoformat()}}
                ]
            }
        }

        registros = await fetch_all_notion(session, f"https://api.notion.com/v1/databases/{Config.DATABASE_ID_MT}/query", payload=query)

        if not registros:
            return {}, {}, "⚠️ No se encontraron registros en los últimos 30 días."

        registros_por_fecha = defaultdict(list)
        for r in registros:
            props = r["properties"]
            fecha_raw = props.get("Fecha", {}).get("date", {}).get("start")
            if not fecha_raw:
                continue
            fecha = fecha_raw[:10]
            who_data = props.get("Who", {}).get("people", [])
            gana = props.get("Gana", {}).get("checkbox", False)
            segundo = props.get("Segundo", {}).get("checkbox", False)
            jugadores = [p.get("name", "Sin nombre") for p in who_data]

            registros_por_fecha[fecha].append({
                "jugadores": jugadores,
                "gana": gana,
                "segundo": segundo
            })

        puntos_total = defaultdict(int)
        torneos_jugados = defaultdict(int)
        torneos_puntuados = defaultdict(int)
        logros = defaultdict(list)

        for fecha, torneo in registros_por_fecha.items():
            jugadores_del_dia = set()
            for equipo in torneo:
                jugadores_del_dia.update(equipo["jugadores"])
            total_jugadores = len(jugadores_del_dia)

            if total_jugadores <= 4:
                puntos_1ro, puntos_2do, tipo = 300, 0, "CH"
            elif total_jugadores <= 6:
                puntos_1ro, puntos_2do, tipo = 1000, 150, "ATP"
            elif total_jugadores <= 8:
                puntos_1ro, puntos_2do, tipo = 2000, 500, "MS"
            else:
                puntos_1ro, puntos_2do, tipo = 4000, 1000, "GS"

            fecha_formateada = datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m")

            for j in jugadores_del_dia:
                torneos_jugados[j] += 1

            for equipo in torneo:
                for j in equipo["jugadores"]:
                    if equipo["gana"]:
                        puntos_total[j] += puntos_1ro
                        torneos_puntuados[j] += 1
                        logros[j].append(f"🥇 {tipo} {puntos_1ro} pts {fecha_formateada}")
                    elif equipo["segundo"]:
                        puntos_total[j] += puntos_2do
                        torneos_puntuados[j] += 1
                        logros[j].append(f"🥈 {tipo} {puntos_2do} pts {fecha_formateada}")

        MIN_TORNEOS = 5
        ranking = sorted(
            puntos_total.items(),
            key=lambda x: (
                (puntos_total[x[0]] / torneos_jugados[x[0]]) * min(1, torneos_jugados[x[0]] / MIN_TORNEOS)
                if torneos_jugados[x[0]] > 0 else 0
            ),
            reverse=True
        )

        resumen = "🏆 <b>Medallero últimos 30 días</b>\n"
        total_fechas = len(registros_por_fecha)
        for i, (jugador, total) in enumerate(ranking, start=1):
            alias = Config.ALIAS_PERSONAS.get(jugador, jugador)
            jugados = torneos_jugados[jugador]
            puntuados = torneos_puntuados[jugador]
            promedio_ponderado = (total / jugados if jugados > 0 else 0) * min(1, jugados / MIN_TORNEOS)
            efectividad = (puntuados / jugados * 100) if jugados > 0 else 0
            participacion = (jugados / total_fechas * 100) if total_fechas > 0 else 0

            resumen += f"\n{i}. <b>{html.escape(alias)} {int(promedio_ponderado)} pts. pond.</b>\n"
            resumen += f"   • {efectividad:.0f}% efectividad\n"
            resumen += f"   • {participacion:.0f}% participación\n"

            for logro in logros[jugador]:
                resumen += f"   {html.escape(logro)}\n"

        return puntos_total, torneos_jugados, resumen
