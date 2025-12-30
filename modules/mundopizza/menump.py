import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import os

# Estados para el ConversationHandler
ELEGIR_ITEM, ELEGIR_PRECIO = range(2)

# Ruta relativa al directorio del archivo .py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_PRECIOS = os.path.join(BASE_DIR, "precios.json")

def cargar_precios():
    """Carga los precios desde precios.json, creando un archivo vacío si no existe."""
    if not os.path.exists(RUTA_PRECIOS):
        with open(RUTA_PRECIOS, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2, ensure_ascii=False)
        return {}
    with open(RUTA_PRECIOS, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error al leer precios.json: {e}")
            return {}

def guardar_precios(precios):
    """Guarda los precios en precios.json."""
    with open(RUTA_PRECIOS, "w", encoding="utf-8") as f:
        json.dump(precios, f, indent=4, ensure_ascii=False)


def get_menu_text():
    """Devuelve el texto del menú con precios, recorriendo precios.json directamente."""
    precios = cargar_precios()  # esto debería devolver el dict del JSON

    texto = "<b>🍕 Menúes Mundo Pizza:</b>\n\n"
    for nombre, precio in precios.items():
        texto += f" 🍽️ {nombre}: <b>${precio}</b>\n"

    return texto


async def mostrar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el menú con los precios actuales."""
    texto = get_menu_text()
    await update.message.reply_text(texto, parse_mode="HTML")
    

async def setmp_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo de /setmp mostrando botones con los ítems y sus precios."""
    precios = cargar_precios()
    
    # Crear botones inline para cada ítem
    keyboard = [
        [InlineKeyboardButton(f"{nombre} (${precios[nombre]})", callback_data=nombre)]
        for nombre in precios.keys()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    texto = "🛠 Seleccioná el ítem que querés modificar:"
    await update.message.reply_text(texto, parse_mode="HTML", reply_markup=reply_markup)
    return ELEGIR_ITEM

async def elegir_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa la selección del ítem desde el botón inline."""
    query = update.callback_query
    await query.answer()
    
    item = query.data
    precios = cargar_precios()
    if item not in precios:
        await query.message.edit_text("⚠️ El ítem seleccionado no existe. Iniciá de nuevo con /setmp.", parse_mode="HTML")
        return ConversationHandler.END

    context.user_data["item"] = item
    await query.message.edit_text(
        f"⏰ Elegiste <b>{item}</b>.\n\nIngresá el nuevo precio (solo números, ej: 3000):",
        parse_mode="HTML"
    )
    return ELEGIR_PRECIO

async def elegir_precio(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        return ConversationHandler.END

    precios = cargar_precios()
    precios[item] = nuevo_precio
    guardar_precios(precios)

    await update.message.reply_text(
        f"✅ Precio de <b>{item}</b> actualizado a ${nuevo_precio}",
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def cancelar_setmp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela el flujo de seteo de precios."""
    await update.message.reply_text("❌ Operación cancelada.", parse_mode="HTML")
    return ConversationHandler.END