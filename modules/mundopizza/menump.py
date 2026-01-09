# ==========================================
# IMPORTS
# ==========================================

# Módulos Locales
import Config


# ==========================================
# CONFIGURACIÓN Y CONSTANTES
# ==========================================

ELEGIR_ITEM, ELEGIR_PRECIO = range(2)
BASE_DIR = Config.os.path.dirname(Config.os.path.abspath(__file__))
RUTA_PRECIOS = Config.os.path.join(BASE_DIR, "preciConfig.os.json")
ahora = Config.datetime.now(Config.ARG_TZ)


# ==========================================
# UTILIDADES DE SISTEMA Y TIEMPO
# ==========================================




# ==========================================
# HELPERS DEL DOMINIO
# ==========================================

async def mostrar_menu(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    """Muestra el menú con los precios actuales."""
    texto = get_menu_text()
    await update.message.reply_text(texto, parse_mode="HTML")

def is_weekday(date_to_check: Config.datetime) -> bool:
    return date_to_check.weekday() in (0, 1, 2, 3, 4)

def is_friday(date_to_check: Config.datetime) -> bool:
    return date_to_check.weekday() == 4

# ==========================================
# FETCH TXT
# ==========================================

def cargar_precios():
    if not Config.os.path.exists(RUTA_PRECIOS):
        with open(RUTA_PRECIOS, "w", encoding="utf-8") as f:
            Config.json.dump({}, f, indent=2, ensure_ascii=False)
        return {}
    with open(RUTA_PRECIOS, "r", encoding="utf-8") as f:
        try:
            return Config.json.load(f)
        except Config.json.JSONDecodeError as e:
            print(f"Error al leer preciConfig.os.json: {e}")
            return {}

def get_menu_text():
    """Devuelve el texto del menú con precios, recorriendo preciConfig.os.json directamente."""
    precios = cargar_precios()  # esto debería devolver el dict del JSON

    texto = "<b>🍕 Menúes Mundo Pizza:</b>\n\n"
    for nombre, precio in precios.items():
        texto += f" 🍽️ {nombre}: <b>${precio}</b>\n"

    return texto

# ==========================================
# WRITE TXT
# ==========================================

def guardar_precios(precios):
    with open(RUTA_PRECIOS, "w", encoding="utf-8") as f:
        Config.json.dump(precios, f, indent=4, ensure_ascii=False)

# ==========================================
# SERVICIO DE DOMINIO
# ==========================================




# ==========================================
# MENÚES TELEGRAM
# ==========================================



# ==========================================
# CONVERSATION HANDLERS
# ==========================================

async def setmp_start(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo de /setmp mostrando botones con los ítems y sus preciConfig.os."""
    precios = cargar_precios()
    
    # Crear botones inline para cada ítem
    keyboard = [
        [Config.InlineKeyboardButton(f"{nombre} (${precios[nombre]})", callback_data=nombre)]
        for nombre in precios.keys()
    ]
    reply_markup = Config.InlineKeyboardMarkup(keyboard)
    
    texto = "🛠 Seleccioná el ítem que querés modificar:"
    await update.message.reply_text(texto, parse_mode="HTML", reply_markup=reply_markup)
    return ELEGIR_ITEM

async def elegir_item(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    """Procesa la selección del ítem desde el botón inline."""
    query = update.callback_query
    await query.answer()
    
    item = query.data
    precios = cargar_precios()
    if item not in precios:
        await query.message.edit_text("⚠️ El ítem seleccionado no existe. Iniciá de nuevo con /setmp.", parse_mode="HTML")
        return Config.ConversationHandler.END

    context.user_data["item"] = item
    await query.message.edit_text(
        f"⏰ Elegiste <b>{item}</b>.\n\nIngresá el nuevo precio (solo números, ej: 3000):",
        parse_mode="HTML"
    )
    return ELEGIR_PRECIO

async def elegir_precio(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    """Procesa el nuevo precio ingresado por el usuario."""
    try:
        nuevo_precio = int(update.message.text.strip())
        if nuevo_precio < 0:
            raise ValueError("El precio no puede ser negativo.")
    except ValueError:
        await update.message.reply_text(
            "⚠️ Ingresá un número válido (ej: 3000).",
            parse_mode="HTML"
        )
        return ELEGIR_PRECIO

    item = context.user_data.get("item")
    if not item:
        await update.message.reply_text(
            "⚠️ No se seleccionó ningún ítem. Iniciá de nuevo con /setmp.",
            parse_mode="HTML"
        )
        return Config.ConversationHandler.END

    precios = cargar_precios()
    precios[item] = nuevo_precio
    guardar_precios(precios)

    await update.message.reply_text(
        f"✅ Precio de <b>{item}</b> actualizado a ${nuevo_precio}",
        parse_mode="HTML"
    )
    return Config.ConversationHandler.END

async def cancelar_setmp(update: Config.Update, context: Config.ContextTypes.DEFAULT_TYPE):
    """Cancela el flujo de seteo de preciConfig.os."""
    await update.message.reply_text("❌ Operación cancelada.", parse_mode="HTML")
    return Config.ConversationHandler.END

conv_setmp = Config.ConversationHandler(
    entry_points=[Config.CommandHandler("setmp", setmp_start)],
    states={
        ELEGIR_ITEM: [Config.CallbackQueryHandler(elegir_item)],
        ELEGIR_PRECIO: [Config.MessageHandler(Config.filters.TEXT & ~Config.filters.COMMAND, elegir_precio)],
    },
    fallbacks=[Config.CommandHandler("cancelar", cancelar_setmp)],
)

# ==========================================
# LÓGICA 
# ==========================================




# ============================
# JOB FOOD REMINDER
# ============================
async def job_food(context: Config.CallbackContext):
    if not is_weekday(ahora) or ahora.date() in Config.FERIADOS:
        print(f"⚠️[DEBUG] food no ejecutada: hoy ({ahora.strftime('%Y-%m-%d')}) no es un día hábil o es feriado.")
        return

    try:
        print(f"📤 job_food disparado a las {ahora.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Primer mensaje: recordatorio
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_TEAM,
            text="¡Acuérdense de pedir comida!!",
            parse_mode="HTML"
        )
        print("📤 Mensaje de food reminder enviado")

        # Segundo mensaje: menú
        menu_text = get_menu_text()
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_TEAM,
            text=menu_text,
            parse_mode="HTML"
        )
        print("📤 Menú enviado")
        
    except Exception as e:
        print(f"❌ Error en job_food: {e}")

# ============================
# JOB PAY REMINDER
# ============================

async def job_pay(context: Config.CallbackContext):
    if not is_weekday(ahora) or ahora.date() in Config.FERIADOS:
        print(f"⚠️[DEBUG] pay no ejecutada: hoy ({ahora.strftime('%Y-%m-%d')}) no es un día hábil o es feriado.")
        return

    try:
        print(f"📤 job_pay disparado a las {ahora.strftime('%Y-%m-%d %H:%M:%S')}")
        await context.bot.send_message(
            chat_id=Config.CHAT_ID_TEAM,
            text=f"Acuerdensé de pagar la comida 💵!",
            parse_mode="HTML"
        )
        print("📤 Mensaje de pay reminder enviado")
    except Exception as e:
        print(f"❌ Error en job_pay: {e}")

 












    

