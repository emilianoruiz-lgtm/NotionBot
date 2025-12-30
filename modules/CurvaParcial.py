import io
import matplotlib.pyplot as plt
import aiohttp
from datetime import date, datetime, timedelta
import requests
import Config

FERIADOS_API_URL = "https://api.argentinadatos.com/v1/feriados"


# --- Función auxiliar para obtener feriados ---
async def fetch_feriados(año: int) -> set[date]:
    url = f"{FERIADOS_API_URL}/{año}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return set()
            feriados_json = await resp.json()

    feriados = set()
    for item in feriados_json:
        fecha_str = item.get("fecha")
        if fecha_str:
            try:
                feriados.add(datetime.strptime(fecha_str, "%Y-%m-%d").date())
            except ValueError:
                pass
    return feriados


async def get_sprint_actual():
    hoy = date.today()

    query = {
        "filter": {
            "property": "Date",
            "date": {"on_or_before": hoy.strftime("%Y-%m-%d")}
        },
        "sorts": [{"property": "Date", "direction": "descending"}]
    }

    r = requests.post(
        f"https://api.notion.com/v1/databases/{Config.DATABASE_ID_SPRINTS}/query",
        headers=Config.HEADERS,
        json=query
    )

    data = r.json().get("results", [])
    print(f"🔎 {len(data)} sprints encontrados en Notion")

    for sprint in data:
        props = sprint.get("properties", {})
        date_field = props.get("Date", {}).get("date", None)
        print(f"📅 Sprint detectado: {props.get('Name', {}).get('title', [{}])[0].get('plain_text', 'Sin nombre')}, fechas={date_field}")

        if not date_field:
            continue

        if "start" in date_field and "end" in date_field:
            inicio = datetime.strptime(date_field["start"], "%Y-%m-%d").date()
            fin = datetime.strptime(date_field["end"], "%Y-%m-%d").date()
            if inicio <= hoy <= fin:
                sprint_id = sprint["id"]
                sprint_name = props.get("Name", {}).get("title", [{}])[0].get("plain_text", "Sin nombre")
                print(f"✅ Sprint actual: {sprint_name} ({inicio} → {fin})")
                return {"id": sprint_id, "nombre": sprint_name, "inicio": inicio, "fin": fin}

    print("⚠️ Ningún sprint en curso encontrado.")
    return None



# --- Tu función para obtener datos desde Notion ---
async def get_parciales_rango(fecha_inicio: date, fecha_fin: date):
    dias = (fecha_fin - fecha_inicio).days + 1
    resultados = []

    for i in range(dias):
        fecha = fecha_inicio + timedelta(days=i)
        query = {
            "filter": {
                "property": "Date",
                "date": {"equals": fecha.strftime('%Y-%m-%d')}
            }
        }

        r = requests.post(
            f"https://api.notion.com/v1/databases/{Config.DATABASE_ID}/query",
            headers=Config.HEADERS,
            json=query
        )
        data = r.json().get("results", [])
        if not data:
            continue

        for rd in data:
            props = rd.get("properties", {})

            parcial_key = next((k for k in props if k.lower().strip() == "parcial"), None)
            target_key = next((k for k in props if k.lower().strip() == "target"), None)
            equipo_key = next((k for k in props if k.lower().strip() == "equipo"), None)

            parcial_val = props.get(parcial_key, {}).get("number") if parcial_key else 0
            target_val = props.get(target_key, {}).get("number") if target_key else 0
            equipo_val = ""
            if equipo_key:
                eq_field = props[equipo_key]
                if "select" in eq_field and eq_field["select"]:
                    equipo_val = eq_field["select"]["name"]
                elif "rich_text" in eq_field and eq_field["rich_text"]:
                    equipo_val = eq_field["rich_text"][0].get("plain_text", "")
                elif "title" in eq_field and eq_field["title"]:
                    equipo_val = eq_field["title"][0].get("plain_text", "")

            resultados.append({
                "fecha": fecha,
                "parcial": parcial_val or 0,
                "target": target_val or 0,
                "diferencia": (target_val or 0) - (parcial_val or 0),
                "Equipo": equipo_val
            })

    return resultados


# --- Función principal con diseño moderno ---
async def generar_curva_parcial():
    sprint = await get_sprint_actual()
    if not sprint:
        raise ValueError("No se encontró un Sprint en curso en Notion.")

    inicio = sprint["inicio"]
    fin = sprint["fin"]

    datos = await get_parciales_rango(inicio, fin)
    if not datos:
        raise ValueError("No se encontraron datos para el rango especificado.")

    # Obtener feriados
    años = {d["fecha"].year for d in datos}
    feriados_todos = set()
    for a in años:
        feriados_todos |= await fetch_feriados(a)

    equipos = ["Caimanes", "Huemules", "Zorros"]

    # --- ESTILO MODERNO ---
    plt.style.use("seaborn-v0_8-darkgrid")  # fondo moderno
    fig, axes = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
    fig.patch.set_facecolor("#1e1e1e")  # fondo oscuro general
    for ax in axes:
        ax.set_facecolor("#2b2b2b")  # fondo de cada subgráfico

    fig.subplots_adjust(hspace=0.4)
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.labelcolor": "white",
        "axes.edgecolor": "#555",
        "text.color": "white",
        "xtick.color": "#ccc",
        "ytick.color": "#ccc",
        "legend.frameon": False
    })

    # --- Determinar días hábiles ---
    dias_habiles = sorted([
        d["fecha"] for d in datos
        if d["fecha"].weekday() < 5 and d["fecha"] not in feriados_todos
    ])
    planning_day = grooming_day = None
    if dias_habiles:
        semana_planning = dias_habiles[0].isocalendar().week
        planning_day = dias_habiles[0]
        grooming_day = next((f for f in dias_habiles if f.isocalendar().week > semana_planning), None)

    fechas_global = None

    # --- Graficar por equipo ---
    for ax, equipo in zip(axes, equipos):
        datos_equipo = [
            d for d in datos
            if d.get("Equipo", "").strip().lower() == equipo.lower()
            and d["fecha"].weekday() < 5
            and d["fecha"] not in feriados_todos
        ]

        if not datos_equipo:
            ax.text(0.5, 0.5, f"Sin datos para {equipo}", ha='center', va='center', fontsize=12, color='white')
            ax.set_title(f"{equipo}", color="white")
            ax.axis("off")
            continue

        datos_equipo.sort(key=lambda x: x["fecha"])
        fechas = [d["fecha"].strftime("%d-%b") for d in datos_equipo]
        fechas_global = fechas
        fechas_f = [d["fecha"] for d in datos_equipo]
        diferencias = [d["diferencia"] for d in datos_equipo]
        targets = [d["target"] for d in datos_equipo]

        target_inicial = targets[0] if targets else 0
        n = len(diferencias)
        # --- Calcular curva esperada realista ---
        dias_habiles_sprint = []
        fecha_aux = inicio
        while fecha_aux <= fin:
            if fecha_aux.weekday() < 5 and fecha_aux not in feriados_todos:
                dias_habiles_sprint.append(fecha_aux)
            fecha_aux += timedelta(days=1)

        if len(dias_habiles_sprint) > 1:
            total_dias_habiles = len(dias_habiles_sprint)
            esperado = []
            for f in fechas_f:
                if f in dias_habiles_sprint:
                    i = dias_habiles_sprint.index(f)
                    valor = target_inicial * (1 - i / (total_dias_habiles - 1))
                    esperado.append(valor)
                else:
                    # si hay una fecha que no es hábil o no está en el rango, repetimos el último valor
                    esperado.append(esperado[-1] if esperado else target_inicial)
        else:
            esperado = [target_inicial]

        # --- Curvas modernas con degradado y suavizado ---
        ax.plot(diferencias, color="#8CE7E7", linewidth=2.5, marker='o',
                markersize=6, markerfacecolor="#8CE7E7", label="Real")
        ax.plot(esperado, color="#8CE7E74E", linewidth=2, linestyle='--',
                marker='s', markersize=5, markerfacecolor="#8CE7E74E", label="Esperado")
        
        # --- Mostrar valores sobre cada punto ---
        for i, val in enumerate(diferencias):
            ax.text(i, val, f"{val:.0f}", ha='center', va='bottom', color="#8CE7E7",
                    fontsize=8, fontweight='bold', alpha=0.9, zorder=10)

        for i, val in enumerate(esperado):
            ax.text(i, val, f"{val:.0f}", ha='center', va='top', color="#8CE7E7AA",
                    fontsize=8, fontweight='bold', alpha=0.8, zorder=10)

        # --- Detectar mesetas (2 puntos) y problemas (3 o más puntos) ---
        meseta_inicio = None
        for i in range(1, len(diferencias)):
            if diferencias[i] == diferencias[i - 1]:
                if meseta_inicio is None:
                    meseta_inicio = i - 1
            else:
                # Si termina una meseta, clasificar internamente
                if meseta_inicio is not None:
                    longitud = i - meseta_inicio
                    if longitud >= 2:
                        for j in range(meseta_inicio + 1, i):
                            if longitud == 2 and j == meseta_inicio + 1:
                                # Solo una meseta corta (2 puntos)
                                color, texto = "#E4D580", "Demora"
                            elif longitud >= 3:
                                # Primer punto repetido → meseta, resto problema
                                if j == meseta_inicio + 1:
                                    color, texto = "#E4D580", "Demora"
                                else:
                                    color, texto = "#D89797", "Problema"
                            else:
                                continue

                            ax.scatter(j, diferencias[j], s=120, color=color, edgecolors="black",
                                       linewidths=1.2, zorder=6, label="_nolegend_")
                            ax.text(j, diferencias[j] + (max(diferencias) * 0.02 if max(diferencias) != 0 else 1),
                                    texto, ha='center', va='bottom', color=color,
                                    fontsize=8, fontweight='bold', alpha=0.9, zorder=7)
                    meseta_inicio = None

        # Si la meseta llega hasta el último punto
        if meseta_inicio is not None:
            longitud = len(diferencias) - meseta_inicio
            if longitud >= 2:
                for j in range(meseta_inicio + 1, len(diferencias)):
                    if longitud == 2 and j == meseta_inicio + 1:
                        color, texto = "#E4D580", "Demora"
                    elif longitud >= 3:
                        if j == meseta_inicio + 1:
                            color, texto = "#E4D580", "Demora"
                        else:
                            color, texto = "#D89797", "Problema"
                    else:
                        continue

                    ax.scatter(j, diferencias[j], s=120, color=color, edgecolors="black",
                               linewidths=1.2, zorder=6, label="_nolegend_")
                    ax.text(j, diferencias[j] + (max(diferencias) * 0.02 if max(diferencias) != 0 else 1),
                            texto, ha='center', va='bottom', color=color,
                            fontsize=8, fontweight='bold', alpha=0.9, zorder=7)



        # Líneas de referencia
        if planning_day in fechas_f:
            x_plan = fechas_f.index(planning_day)
            ax.axvline(x=x_plan, color="#B8B8B8", linestyle=':', linewidth=1.5, alpha=0.8)
        if grooming_day and grooming_day in fechas_f:
            x_groom = fechas_f.index(grooming_day)
            ax.axvline(x=x_groom, color="#B8B8B8", linestyle=':', linewidth=1.5, alpha=0.8)

        ax.set_title(f"{equipo}", color="white", fontsize=12, fontweight="bold")
        ax.set_ylabel("Burndown", color="white")
        ax.grid(True, linestyle='--', alpha=0.3)
        ax.legend(loc="upper right", facecolor="#2b2b2b", labelcolor="white")

    if fechas_global:
        etiquetas = []
        for i, f in enumerate(fechas_global):
            f_date = [d for d in datos if d["fecha"].strftime("%d-%b") == f][0]["fecha"]
            etiqueta = f
            if f_date == planning_day:
                etiqueta += "\nPlanning"
            elif grooming_day and f_date == grooming_day:
                etiqueta += "\nGrooming"
            etiquetas.append(etiqueta)

    axes[-1].set_xticks(range(len(fechas_global)))
    axes[-1].set_xticklabels(etiquetas, rotation=45, ha='right', color="white", fontsize=9)

    axes[-1].set_xlabel("Fecha", color="white")

    fig.suptitle(
        f"{sprint['nombre']} – Curvas de ejecución del Plan por Equipo\n"
        "(sin fines de semana ni feriados nacionales)",
        fontsize=14, color="white", fontweight="bold"
    )

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf


async def generar_curva_parcial_equipo(equipo: str):
    sprint = await get_sprint_actual()
    if not sprint:
        raise ValueError("No se encontró un Sprint en curso en Notion.")

    inicio, fin = sprint["inicio"], sprint["fin"]
    datos = await get_parciales_rango(inicio, fin)
    if not datos:
        raise ValueError("No se encontraron datos para el rango especificado.")

    # Obtener feriados
    años = {d["fecha"].year for d in datos}
    feriados_todos = set()
    for a in años:
        feriados_todos |= await fetch_feriados(a)

    # --- FILTRAR DATOS DEL EQUIPO ---
    datos_equipo = [
        d for d in datos
        if d.get("Equipo", "").strip().lower() == equipo.lower()
        and d["fecha"].weekday() < 5
        and d["fecha"] not in feriados_todos
    ]
    if not datos_equipo:
        raise ValueError(f"No se encontraron datos para el equipo {equipo}.")
    datos_equipo.sort(key=lambda x: x["fecha"])

    # --- ESTILO MODERNO COINCIDENTE ---
    plt.style.use("seaborn-v0_8-darkgrid")
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("#1e1e1e")
    ax.set_facecolor("#2b2b2b")

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.labelcolor": "white",
        "axes.edgecolor": "#555",
        "text.color": "white",
        "xtick.color": "#ccc",
        "ytick.color": "#ccc",
        "legend.frameon": False
    })

    # --- Determinar días hábiles ---
    dias_habiles = sorted([
        d["fecha"] for d in datos
        if d["fecha"].weekday() < 5 and d["fecha"] not in feriados_todos
    ])
    planning_day = grooming_day = None
    if dias_habiles:
        semana_planning = dias_habiles[0].isocalendar().week
        planning_day = dias_habiles[0]
        grooming_day = next((f for f in dias_habiles if f.isocalendar().week > semana_planning), None)

    # --- Preparar datos ---
    fechas = [d["fecha"].strftime("%d-%b") for d in datos_equipo]
    fechas_f = [d["fecha"] for d in datos_equipo]
    diferencias = [d["diferencia"] for d in datos_equipo]
    targets = [d["target"] for d in datos_equipo]

    target_inicial = targets[0] if targets else 0
    n = len(diferencias)
    # --- Calcular curva esperada realista ---
    dias_habiles_sprint = []
    fecha_aux = inicio
    while fecha_aux <= fin:
        if fecha_aux.weekday() < 5 and fecha_aux not in feriados_todos:
            dias_habiles_sprint.append(fecha_aux)
        fecha_aux += timedelta(days=1)

    if len(dias_habiles_sprint) > 1:
        total_dias_habiles = len(dias_habiles_sprint)
        esperado = []
        for f in fechas_f:
            if f in dias_habiles_sprint:
                i = dias_habiles_sprint.index(f)
                valor = target_inicial * (1 - i / (total_dias_habiles - 1))
                esperado.append(valor)
            else:
                # si hay una fecha que no es hábil o no está en el rango, repetimos el último valor
                esperado.append(esperado[-1] if esperado else target_inicial)
    else:
        esperado = [target_inicial]

    # --- Curvas ---
    ax.plot(diferencias, color="#8CE7E7", linewidth=2.5, marker='o',
            markersize=6, markerfacecolor="#8CE7E7", label="Real")
    ax.plot(esperado, color="#8CE7E74E", linewidth=2, linestyle='--',
            marker='s', markersize=5, markerfacecolor="#8CE7E74E", label="Esperado")
    
    # --- Mostrar valores sobre cada punto ---
    for i, val in enumerate(diferencias):
        ax.text(i, val, f"{val:.0f}", ha='center', va='bottom', color="#8CE7E7",
                fontsize=8, fontweight='bold', alpha=0.9, zorder=10)

    for i, val in enumerate(esperado):
        ax.text(i, val, f"{val:.0f}", ha='center', va='top', color="#8CE7E7AA",
                fontsize=8, fontweight='bold', alpha=0.8, zorder=10)

    # --- Detectar mesetas (2 puntos) y problemas (3 o más puntos) ---
    meseta_inicio = None
    for i in range(1, len(diferencias)):
        if diferencias[i] == diferencias[i - 1]:
            if meseta_inicio is None:
                meseta_inicio = i - 1
        else:
            # Si termina una meseta, clasificar internamente
            if meseta_inicio is not None:
                longitud = i - meseta_inicio
                if longitud >= 2:
                    for j in range(meseta_inicio + 1, i):
                        if longitud == 2 and j == meseta_inicio + 1:
                            # Solo una meseta corta (2 puntos)
                            color, texto = "#E4D580", "Demora"
                        elif longitud >= 3:
                            # Primer punto repetido → meseta, resto problema
                            if j == meseta_inicio + 1:
                                color, texto = "#E4D580", "Demora"
                            else:
                                color, texto = "#D89797", "Problema"
                        else:
                            continue

                        ax.scatter(j, diferencias[j], s=120, color=color, edgecolors="black",
                                    linewidths=1.2, zorder=6, label="_nolegend_")
                        ax.text(j, diferencias[j] + (max(diferencias) * 0.02 if max(diferencias) != 0 else 1),
                                texto, ha='center', va='bottom', color=color,
                                fontsize=8, fontweight='bold', alpha=0.9, zorder=7)
                meseta_inicio = None

    # Si la meseta llega hasta el último punto
    if meseta_inicio is not None:
        longitud = len(diferencias) - meseta_inicio
        if longitud >= 2:
            for j in range(meseta_inicio + 1, len(diferencias)):
                if longitud == 2 and j == meseta_inicio + 1:
                    color, texto = "#E4D580", "Demora"
                elif longitud >= 3:
                    if j == meseta_inicio + 1:
                        color, texto = "#E4D580", "Demora"
                    else:
                        color, texto = "#D89797", "Problema"
                else:
                    continue

                ax.scatter(j, diferencias[j], s=120, color=color, edgecolors="black",
                            linewidths=1.2, zorder=6, label="_nolegend_")
                ax.text(j, diferencias[j] + (max(diferencias) * 0.02 if max(diferencias) != 0 else 1),
                        texto, ha='center', va='bottom', color=color,
                        fontsize=8, fontweight='bold', alpha=0.9, zorder=7)

    # --- Líneas verticales de referencia (Planning y Grooming) ---
    if planning_day in fechas_f:
        x_plan = fechas_f.index(planning_day)
        ax.axvline(x=x_plan, color="#B8B8B8", linestyle=':', linewidth=1.5, alpha=0.8)
    if grooming_day and grooming_day in fechas_f:
        x_groom = fechas_f.index(grooming_day)
        ax.axvline(x=x_groom, color="#B8B8B8", linestyle=':', linewidth=1.5, alpha=0.8)

    # --- Etiquetas de eje X (con texto Planning/Grooming debajo) ---
    etiquetas = []
    for i, f in enumerate(fechas):
        f_date = fechas_f[i]
        etiqueta = f
        if f_date == planning_day:
            etiqueta += "\nPlanning"
        elif grooming_day and f_date == grooming_day:
            etiqueta += "\nGrooming"
        etiquetas.append(etiqueta)
    ax.set_xticks(range(len(fechas)))
    ax.set_xticklabels(etiquetas, rotation=45, ha='right', color="white", fontsize=9)

    # --- Detalles visuales finales ---
    ax.grid(True, linestyle='--', alpha=0.3)
    ax.set_xlabel("Fecha", color="white")
    ax.set_ylabel("Burndown", color="white")
    ax.legend(loc="upper right", facecolor="#2b2b2b", labelcolor="white")

    fig.suptitle(
        f"{sprint['nombre']} – Curva de ejecución ({equipo})\n"
        "(sin fines de semana ni feriados nacionales)",
        fontsize=14, color="white", fontweight="bold"
    )

    plt.tight_layout(rect=[0, 0, 1, 0.93])

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf
