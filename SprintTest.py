import requests
import Config
from datetime import date

NOTION_SPRINTS_DB = Config.DATABASE_ID_SPRINTS  # asegurate de tener esto en Config

async def debug_sprints():
    """Imprime los sprints con su propiedad 'Dete' completa para analizar el formato Notion."""
    r = requests.post(
        f"https://api.notion.com/v1/databases/{NOTION_SPRINTS_DB}/query",
        headers=Config.HEADERS
    )
    data = r.json().get("results", [])
    print(f"🔍 {len(data)} sprints encontrados.\n")

    for sprint in data:
        nombre = sprint.get("properties", {}).get("Name", {}).get("title", [])
        nombre_txt = nombre[0].get("plain_text") if nombre else "(sin nombre)"

        dete = sprint.get("properties", {}).get("Dete", {})
        print(f"📘 Sprint: {nombre_txt}")
        print("Propiedad 'Dete':")
        print(dete)
        print("-" * 80)

# para probar:
if __name__ == "__main__":
    import asyncio
    asyncio.run(debug_sprints())
