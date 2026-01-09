# ==========================================
# 1. IMPORTS
# ==========================================
 
# Librerías Estándar
import asyncio
import ctypes
import html
import inspect
import json
import logging
import os
import re
import subprocess
import sys
import traceback
import warnings
import aiohttp
import requests
import time as _time
import unicodedata
import dateutil.parser  
import base64

from collections import defaultdict
from datetime import datetime, timedelta, date, time, timezone
from functools import wraps
from math import ceil
from zoneinfo import ZoneInfo
from pathlib import Path

# Librerías de Terceros
import ntplib
import tzdata
import win32api
import win32con
import pdfplumber
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputFile, Bot
from telegram.constants import ParseMode
from telegram.error import RetryAfter, NetworkError, TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
    JobQueue,
    CallbackContext
)

# ==========================================
# 2. CONSTANTES
# ==========================================

ARG_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
  
NOTION_TOKEN = 'ntn_z56874457011Hz0DyovlmyTUziM3ZwHBROzP8npgSgJ5gB'
DATABASE_ID = '246152ff88c58000aff8fe2a4b2e25b6'       # BURN
DATABASE_ID_PLAN = "238152ff88c580aaa659d59eba57e932"  # PLAN
DATABASE_ID_SPRINTS = "24e152ff88c58044a30bcf52a44f2ecd" #SPRINTS
DATABASE_ID_MEETINGS = "1b2152ff88c580e0b64ae09ea79f1391" #TEAM MEETINGS

DATABASE_ID_CALENDAR = '7eb7b4c654f14203ac8dcd7d864dc722' # CALENDARIO
DATABASE_ID_MT = '246152ff88c5809f87eefc99c62f5911' # METEGOL
TEMPLATE_DEPLOY_PAGE_ID = "2e1152ff88c580d591dfeb0c5fa77028"
TEMPLATE_TEAM_MEET_PAGE_ID = "2e2152ff88c580f28ca6cf90765d12f9"

CHAT_ID_TEST = '-1001549489769'
CHAT_ID_EPROC = '-1001304930938'
CHAT_ID_TEAM = '-539474368'
CHAT_ID_MALAMIA = '-1001393573862'
CHAT_ID_LOG =  '-1003024191085'
CHAT_ID_ADMIN = "-1001164975360"
CHAT_ID_DEBUG = '-1001708770323'



#TELEGRAM_TOKEN = '1844138684:AAExApDRm2UkC1bD5lTRGhgH5fl6rKJWw7E' #Bot Zz
#TELEGRAM_TOKEN = '8366578234:AAH3uUYpndGXlhslfSQdl6Brid_GEkAPTjA' #Bot Godcito

QA_TEST = True
if QA_TEST : 
    TELEGRAM_TOKEN = '8366578234:AAH3uUYpndGXlhslfSQdl6Brid_GEkAPTjA' #Bot Godcito 
    THREAD_IDS = { 
        "Caimanes": 2821,   # ID del tópico Caimán en DEBUG
        "Zorros": 2825,      # ID del tópico Zorros en DEBUG
        "Huemules": 2823,    # ID del tópico Huemules en DEBUG
        "Preliminar Agenda": 16
    }
else:
    TELEGRAM_TOKEN = '1844138684:AAExApDRm2UkC1bD5lTRGhgH5fl6rKJWw7E' #Bot Zz
    THREAD_IDS = { 
        "Caimanes": 14,   # ID del tópico Caimán en LOG
        "Zorros": 4,      # ID del tópico Zorros en LOG
        "Huemules": 2,    # ID del tópico Huemules en LOG
        "Preliminar Agenda": 16
    }

CHAT_ID = CHAT_ID_LOG

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

EQUIPOS_CONFIG= {
    "General": {
        "emoji": "",
        "display_name": "General",
        "integrantes": [],
        "chat_id": ''
    },
    "Admin": {
        "emoji": "",
        "display_name": "Admin",
        "integrantes": ["Bernardo Eppenstein", "Carla Carucci", "Victorua Lamas", "Darío De Cáneva", "Emiliano Ruiz"],
        "chat_id": '-1001708770323' #DEBUG
    },
    "Huemules": {
        "emoji": "",
        "display_name": "Huemules",
        "integrantes": ["Luciano Crovetto", "Baltasar Ollé"],
        "chat_id": '-1003646101971' # AS
    },
    "Zorros": {
        "emoji": "",
        "display_name": "Zorros",
        "integrantes": ["Federico Accurso", "Lisandro Luna"],
        "chat_id":'-1003621275522' # BT
    },
    "Caimanes": {
        "emoji": "",
        "display_name": "Caimanes",
        "integrantes": ["Ian Reyes", "Marcos Casas"],
        "chat_id": '-1003521233319' # DF
    },
    "Alpha Squad": {
        "emoji": "",
        "display_name": "Alpha Squad",
        "integrantes": ["Baltasar Ollé", "Lisandro Luna"],
        "chat_id": '' # AS
    },
    "Bravo Team": {
        "emoji": "",
        "display_name": "Bravo Team",
        "integrantes": ["Luciano Crovetto", "Marcos Casas"],
        "chat_id": '' # BT
    },
    "Delta Force": {
        "emoji": "",
        "display_name": "Delta Force",
        "integrantes": ["Federico Accurso", "Ian Reyes"],
        "chat_id": '' # DF
    },

}

# Defaults
DEFAULT_TEAM_EMOJI = ""
DEFAULT_SEPARATOR = "-" * 46
NO_REGISTROS_TEXT = "      - No hay registros"

NOTION_USERS = {
    "Bernardo Eppenstein": "65f8c40d-05bd-4301-ae40-430ad00cdded",
    "Carla Carucci": "1c930f56-2dc6-4ebe-93d8-663217024664",
    "Victorua Lamas": "7ac8dcdf-3314-4d55-89d5-bed04b502349",
    "Darío De Cáneva": "89c3b717-73dc-46fb-9acc-c55a5d140e1e",
    "Emiliano Ruiz": "3fca3f03-2f21-49b6-862f-f0323f251e69",
    "Luciano Crovetto": "1dd45f0d-c60b-408b-a9ea-7b64711a893b",
    "Baltasar Ollé": "119d872b-594c-810b-b6da-00021084f745",
    "Federico Accurso": "5c758767-b8fb-4161-b733-5930cf9618a5",
    "Lisandro Luna": "151d872b-594c-815d-93d7-0002bfc82915",
    "Ian Reyes": "1f9d872b-594c-8174-87c1-0002445ac1f8",
    "Marcos Casas": "1f9d872b-594c-8132-ad62-0002ff600999",
}

# --- Diccionario de alias ---
ALIAS_PERSONAS = {
    "Emiliano Ruiz": "EMR",
    "Dario De Caneva": "DPD",
    "Darío De Caneva": "DPD",
    "Victoria ": "MVL",
    "Luciano Crovetto": "LCR",
    "Federico Accurso": "FAC",
    "Baltasar Olle": "BOL",
    "Baltasar Ollé": "BOL",
    "Lisandro Luna": "LDL",
    "Marcos Casas": "MAC",
    "Ian Reyes": "IDR",
    "Bernardo Eppenstein": "BPE",
    "Carla Carucci": "CCA"
}

# Lista de feriados (ejemplo, completala según tu caso)
FERIADOS = {   
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


TIPOS_SIN_CLIENTE = [
    "Franco", "Cumpleaños", "Día de estudio", "Vacaciones",
    "Licencia", "Evento Personal", "Evento EPROC", "Enfermo", "Reunión interna", "Home Office"
]

TIPOS_SIN_ARRANQUE_NORMAL = [
    "Franco", "Día de estudio", "Vacaciones",
    "Licencia", "Evento Personal", "Enfermo"
]

TIPOS_ARRANQUE_REMOTO = [
    "Home Office", "Evento EPROC"
]

TIPOS_GUARDIA = [
    "Guardia 60%", "Guardia 40%", "Guardia 100%"
]

# ⏱️ Margen en minutos para considerar que un evento temprano significa "No inicia jornada"
MARGEN_MINUTOS = 15

DONE_STATUS_NAMES = {"done", "hecho", "finalizado", "listo", "completado", "closed", "cerrado"}

DEBUG = True  # Cambiar a False en producción

CONFIRMAR = 999

# ==========================================
# HELPERS GENERALES
# ==========================================

def wrap_handler(func):
    """Wrapper para mostrar mensaje de ejecución"""
    async def wrapper(update: Update, context: CallbackContext):
        if update.message:
            await update.message.reply_text(
                "⚡ Ejecutando tarea...",
                parse_mode=ParseMode.HTML,
            )
        return await func(update, context)
    return wrapper


# ==========================================
# CANCELAR / GENERIC
# ==========================================

async def cancelar(update: Update, context: CallbackContext):
    if update.message:
        await update.message.reply_text("❌ Conversación cancelada.")
    elif update.callback_query:
        await update.callback_query.message.reply_text("❌ Conversación cancelada.")
    return ConversationHandler.END


async def generic_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("⚡ Comando no reconocido. Usa /help")


# ==========================================
# CONFIRMACIÓN GLOBAL
# ==========================================

async def manejar_confirmacion(update: Update, context: CallbackContext):
    respuesta = update.message.text.strip().lower()

    if respuesta in ("sí", "si"):
        if "pendiente" in context.user_data:
            funcion_real = context.user_data.pop("pendiente")
            return await funcion_real(update, context)
        else:
            await update.message.reply_text("⚠️ No hay ninguna acción pendiente.")
    else:
        await update.message.reply_text("❌ Acción cancelada.")

    return ConversationHandler.END


def confirmar_handler(comando: str, funcion_real):
    async def handler(update: Update, context: CallbackContext):
        context.user_data["pendiente"] = funcion_real
        await update.message.reply_text(
            f"⚠️ Vas a ejecutar <b>{comando}</b>.\n¿Confirmás? (sí/no)",
            parse_mode=ParseMode.HTML,
        )
        return CONFIRMAR

    return ConversationHandler(
        entry_points=[CommandHandler(comando, handler)],
        states={
            CONFIRMAR: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    manejar_confirmacion,
                )
            ]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )


async def maybe_await(job_func, context=None):
    
    sig = inspect.signature(job_func)
    num_params = len(sig.parameters)
    
    def run_sync():
        if num_params == 0: return job_func()
        if num_params == 1: return job_func(context)
        return job_func(context, None)

    if inspect.iscoroutinefunction(job_func):
        if num_params == 0: return await job_func()
        if num_params == 1: return await job_func(context)
        return await job_func(context, None)
    
    return await asyncio.get_running_loop().run_in_executor(None, run_sync)

