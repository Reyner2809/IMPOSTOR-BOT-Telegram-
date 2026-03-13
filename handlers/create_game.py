"""Handler para crear partidas."""

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from game_manager import game_manager


async def crear_partida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Crea una nueva partida en el grupo actual."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text(
            "⚠️ Este comando solo funciona en grupos.\n"
            "Agrega el bot a un grupo y usa /crear_partida ahí."
        )
        return

    try:
        game = await game_manager.create_game(
            chat_id=chat.id,
            creator_id=user.id,
            creator_username=user.username or "",
            creator_name=user.first_name,
        )
        await update.message.reply_text(
            f"🎮 *¡Partida creada!*\n\n"
            f"🆔 ID: `{game.game_id}`\n"
            f"👤 Creador: {user.first_name}\n\n"
            f"Los jugadores pueden unirse con /unirse\n"
            f"Cuando estén listos, el creador usa /iniciar\n\n"
            f"⚙️ Configuración:\n"
            f"  • Impostores: {game.config.num_impostors}\n"
            f"  • Tiempo de discusión: {game.config.discussion_time}s\n"
            f"  • Categoría: {game.config.category}\n\n"
            f"Usa /config para ver opciones de configuración.",
            parse_mode="Markdown"
        )
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")


def get_handler():
    return CommandHandler("crear_partida", crear_partida)
