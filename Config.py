from datetime import date
from zoneinfo import ZoneInfo

ARG_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


# --- CONFIGURACIONES ---  
NOTION_TOKEN = 'ntn_z56874457011Hz0DyovlmyTUziM3ZwHBROzP8npgSgJ5gB'
DATABASE_ID = '246152ff88c58000aff8fe2a4b2e25b6'       # BURN
DATABASE_ID_PLAN = "238152ff88c580aaa659d59eba57e932"  # PLAN
DATABASE_ID_SPRINTS = "24e152ff88c58044a30bcf52a44f2ecd" #SPRINTS
DATABASE_ID_CALENDAR = '7eb7b4c654f14203ac8dcd7d864dc722' # CALENDARIO
DATABASE_ID_MT = '246152ff88c5809f87eefc99c62f5911' # METEGOL

TELEGRAM_TOKEN = '1844138684:AAExApDRm2UkC1bD5lTRGhgH5fl6rKJWw7E' #Bot Zz
#TELEGRAM_TOKEN = '8366578234:AAH3uUYpndGXlhslfSQdl6Brid_GEkAPTjA' #Bot DMP

CHAT_ID_TEST = '-1001549489769'
CHAT_ID_EPROC = '-1001304930938'
CHAT_ID_TEAM = '-539474368'
CHAT_ID_MALAMIA = '-1001393573862'
CHAT_ID_LOG =  '-1003024191085'
CHAT_ID_ADMIN = "-1001164975360"
CHAT_ID_DEBUG = '-1001708770323'


#THREAD_IDS = { 
#    "Caimanes": 14,   # ID del tópico Caimán en LOG
#    "Zorros": 4,      # ID del tópico Zorros en LOG
#    "Huemules": 2,    # ID del tópico Huemules en LOG
#    "Preliminar Agenda": 16
#}

THREAD_IDS = { 
    "Caimanes": 2821,   # ID del tópico Caimán en DEBUG
    "Zorros": 2825,      # ID del tópico Zorros en DEBUG
    "Huemules": 2823,    # ID del tópico Huemules en DEBUG
    "Preliminar Agenda": 16
}

CHAT_ID = CHAT_ID_DEBUG

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

TASK_FIELDS = [
    "BLINKI (BD)", "CCU (BD)", "MOLINOS (BD)", "ELECTROLUX (BD)",
    "FUNDEMAP (BD)", "PERFORMA (BD)", "VAPOX (BD)", "GENERAL (BD)",
    "GERDAU L. (BD)", "GERDAU P. (BD)", "ITURROSPE (BD)",
    "SIDERSA (BD)", "TPR (BD)", "WIENER LAB (BD)"
    ]

EQUIPOS_CONFIG = {
    "General": {
        "emoji": "📌",
        "display_name": "General",
    },
    "No inicia jornada en la oficina": {
        "emoji": "📍",
        "display_name": "No inicia jornada\n        en la oficina",
    },
    "Huemules": {
        "emoji": "🫎",
        "display_name": "Huemules",
    },
    "Zorros": {
        "emoji": "🦊",
        "display_name": "Zorros",
    },
    "Caimanes": {
        "emoji": "🐊",
        "display_name": "Caimanes",
    },
}

# Defaults
DEFAULT_TEAM_EMOJI = "🤌"
DEFAULT_SEPARATOR = "-" * 46
NO_REGISTROS_TEXT = "      - No hay registros"

EQUIPOS = ["Caimanes", "Zorros", "Huemules"]

# Emojis por equipo
EMOJIS = {
    "Caimanes": "🐊",
    "caimanes": "🐊",
    "Zorros": "🦊",
    "zorros": "🦊",
    "Huemules": "🦌",
    "huemules": "🦌"
}

PERSONAS_CAIMANES = ["Ian Reyes", "Marcos Casas"]
PERSONAS_ZORROS = ["Federico Accurso", "Lisandro Luna"]
PERSONAS_HUEMULES = ["Luciano Crovetto", "Baltasar Ollé"]


# --- Diccionario de alias ---
ALIAS_PERSONAS = {
    "Emiliano Ruiz": "EMR",
    "Dario De Caneva": "DPD",
    "Darío De Caneva": "DPD",
    "Victoria ": "MVL",
    "Luciano Crovetto": "LCR",
    "Valentin Bellini": "VAB",
    "Valentín Bellini": "VAB",
    "Federico Accurso": "FAC",
    "Baltasar Olle": "BOL",
    "Baltasar Ollé": "BOL",
    "Lisandro Luna": "LDL",
    "Marcos Casas": "MAC",
    "Ian Reyes": "IDR",
    "Nicolas Cappello": "NKP",
    "Nicolás Cappello": "NKP",
    "Bernardo Eppenstein": "BPE",
    "Carla Carucci": "CCA"
}

# Lista de feriados (ejemplo, completala según tu caso)
FERIADOS = {
    # Feriados 2025 (ya existentes)
    date(2025, 1, 1), date(2025, 3, 24), date(2025, 5, 1),
    date(2025, 5, 25), date(2025, 6, 20), date(2025, 7, 9),
    date(2025, 10, 10), date(2025, 12, 25),
    
    # Feriados de Argentina 2026 🇦🇷
    date(2026, 1, 1),   # Año Nuevo
    date(2026, 2, 16),  # Lunes de Carnaval
    date(2026, 2, 17),  # Martes de Carnaval
    date(2026, 3, 24),  # Día Nacional de la Memoria por la Verdad y la Justicia
    date(2026, 4, 2),   # Día del Veterano y de los Caídos en la Guerra de Malvinas (y opcional Jueves Santo)
    date(2026, 4, 3),   # Viernes Santo
    date(2026, 5, 1),   # Día del Trabajador
    date(2026, 5, 25),  # Día de la Revolución de Mayo
    date(2026, 6, 17),  # Día del Paso a la Inmortalidad del General Martín Miguel de Güemes
    date(2026, 6, 20),  # Día de la Bandera
    date(2026, 7, 9),   # Día de la Independencia
    date(2026, 8, 17),  # Día del Paso a la Inmortalidad del General José de San Martín
    date(2026, 10, 12), # Día del Respeto por la Diversidad Cultural
    date(2026, 11, 23), # Día de la Soberanía Nacional
    date(2026, 12, 8),  # Día de la Inmaculada Concepción
    date(2026, 12, 25), # Navidad
}

FRASES_VARIADAS = [
    "🤔 Sería útil comentar/recordar en la RD si hay algún impedimento o apoyo necesario para avanzar más rápido en esta tarea.",
    "💡 Tal vez convenga mencionar/recordar en la RD si hay algún bloqueo o ayuda que pueda destrabar el avance.",
    "🔎 No estaría de más revisar/recordar en la RD si esta tarea requiere algún tipo de apoyo adicional.",
    "📌 Podría ser valioso señalar/recordar en la RD si hay factores que estén demorando el progreso.",
    "🛠️ Recordar comentar/recordar en la RD si necesitan soporte o hay algún impedimento que dificulte continuar.",
    "🚧 Conviene aclarar/recordar en la RD si existen obstáculos que estén frenando el avance.",
    "🗣️ Sería bueno mencionar/recordar en la RD si se requiere colaboración de alguien para poder seguir.",
    "📣 Vale la pena destacar/recordar en la RD si hay dependencias externas que estén trabando esta actividad.",
    "🕵️‍♂️ Podría ser útil comentar/recordar en la RD si se identificó algún punto crítico que afecte el progreso.",
    "🤝 No olvidemos mencionar/recordar en la RD si se necesita apoyo del equipo o de otra área para avanzar."
]


TIPOS_SIN_CLIENTE = [
    "Franco", "Cumpleaños", "Día de estudio", "Vacaciones",
    "Licencia", "Evento Personal", "Evento EPROC", "Enfermo", "Reunión interna", "Home Office"
]

TIPOS_SIN_INICIO_OFICINA = [
    "Franco", "Día de estudio", "Vacaciones",
    "Licencia", "Evento Personal", "Evento EPROC", "Enfermo", "Home Office"
]

# ⏱️ Margen en minutos para considerar que un evento temprano significa "No inicia jornada"
MARGEN_MINUTOS = 15


DONE_STATUS_NAMES = {"done", "hecho", "finalizado", "listo", "completado", "closed", "cerrado"}


DEBUG = True  # Cambiar a False en producción




