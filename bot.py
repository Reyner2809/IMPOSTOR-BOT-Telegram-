"""
El Impostor - Bot de Telegram
=============================
Bot para jugar "El Impostor" (Spyfall-like) completamente dentro de Telegram.

Uso:
    BOT_TOKEN=tu_token python bot.py
"""

import logging
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import BOT_TOKEN
from database import init_db
from handlers import create_game, join_game, config_game, start_game, vote_handler, game_status, word_phase_handler

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - bienvenida."""
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text(
            "🎮 *¡Bienvenido a El Impostor!*\n\n"
            "Soy un bot para jugar El Impostor en grupos de Telegram.\n\n"
            "*¿Cómo jugar?*\n"
            "1. Agrégame a un grupo\n"
            "2. Usa /crear_partida en el grupo\n"
            "3. Los jugadores se unen con /unirse\n"
            "4. El creador inicia con /iniciar\n"
            "5. Revisa tu mensaje privado para tu palabra\n"
            "6. Discutan en el grupo quién es el impostor\n"
            "7. Voten y descubran la verdad\n\n"
            "*Comandos:*\n"
            "/crear\\_partida - Crear una partida\n"
            "/unirse - Unirse a una partida\n"
            "/salir - Salir de una partida\n"
            "/iniciar - Iniciar la partida\n"
            "/votar - Forzar votación\n"
            "/estado - Ver estado de la partida\n"
            "/config - Ver configuración\n"
            "/cancelar - Cancelar la partida\n"
            "/finalizar - Finalizar y ver resultados\n"
            "/ayuda - Ver esta ayuda",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🎮 *El Impostor*\n\n"
            "Usa /crear_partida para empezar una partida.\n"
            "Escribe /ayuda para ver todos los comandos.",
            parse_mode="Markdown"
        )


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def post_init(application):
    """Se ejecuta después de inicializar el bot."""
    await init_db()
    # Registrar comandos en el menú de Telegram
    commands = [
        BotCommand("crear_partida", "Crear una nueva partida"),
        BotCommand("unirse", "Unirse a la partida"),
        BotCommand("salir", "Salir de la partida"),
        BotCommand("iniciar", "Iniciar la partida"),
        BotCommand("votar", "Forzar votación"),
        BotCommand("estado", "Ver estado de la partida"),
        BotCommand("config", "Ver configuración"),
        BotCommand("cancelar", "Cancelar la partida"),
        BotCommand("finalizar", "Finalizar la partida actual"),
        BotCommand("ayuda", "Ver ayuda"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot inicializado correctamente.")


def main():
    if BOT_TOKEN == "TU_TOKEN_AQUI":
        print("ERROR: Configura BOT_TOKEN como variable de entorno.")
        print("  Ejemplo: BOT_TOKEN=123456:ABC-DEF python bot.py")
        return

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )

    # Registrar handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(create_game.get_handler())
    for h in join_game.get_handlers():
        app.add_handler(h)
    for h in config_game.get_handlers():
        app.add_handler(h)
    app.add_handler(start_game.get_handler())
    for h in vote_handler.get_handlers():
        app.add_handler(h)
    for h in game_status.get_handlers():
        app.add_handler(h)
    app.add_handler(word_phase_handler.get_handler())

    logger.info("Bot iniciando polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
