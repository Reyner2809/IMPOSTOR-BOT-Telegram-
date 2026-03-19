"""Script para probar Gemini AI sin necesidad de iniciar el bot."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


async def main():
    from gemini_manager import gemini_manager

    print("=" * 50)
    print("  TEST GEMINI AI - El Impostor Bot")
    print("=" * 50)

    stats = gemini_manager.get_stats()
    print(f"\nEstado inicial:")
    print(f"  Configurado : {stats['configured']}")
    print(f"  Uso hoy     : {stats['daily_count']}/{stats['daily_limit']}")
    print(f"  Redis configurado : {stats['redis_configured']}")

    if not stats["configured"]:
        print("\n❌ Gemini NO está configurado. Revisa GEMINI_API_KEY en .env")
        return

    print(f"\nGenerando 1 palabra...\n")

    palabra, pista = await gemini_manager.get_word_and_hint("todas")
    print(f"  palabra = '{palabra}'  |  pista impostor = '{pista}'")

    print()
    stats = gemini_manager.get_stats()
    print(f"Uso final hoy: {stats['daily_count']}/{stats['daily_limit']}")
    print("\n✅ Test completado.")


if __name__ == "__main__":
    asyncio.run(main())
