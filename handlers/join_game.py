"""Handlers para unirse y salir de partidas."""

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from game_manager import game_manager


def _player_list(game) -> str:
    lines = []
    for i, player in enumerate(game.players.values(), 1):
        name = player.first_name
        if player.username:
            name += f" (@{player.username})"
        lines.append(f"  {i}. {name}")
    return "\n".join(lines)


async def unirse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("⚠️ Usa este comando en el grupo de la partida.")
        return

    try:
        game = await game_manager.join_game(
            chat_id=chat.id,
            user_id=user.id,
            username=user.username or "",
            first_name=user.first_name,
        )
        await update.message.reply_text(
            f"✅ *{user.first_name}* se unió a la partida.\n\n"
            f"👥 Jugadores ({len(game.players)}):\n{_player_list(game)}",
            parse_mode="Markdown"
        )
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")


async def salir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("⚠️ Usa este comando en el grupo de la partida.")
        return

    try:
        game = await game_manager.leave_game(chat_id=chat.id, user_id=user.id)
        await update.message.reply_text(
            f"👋 *{user.first_name}* abandonó la partida.\n\n"
            f"👥 Jugadores ({len(game.players)}):\n{_player_list(game)}",
            parse_mode="Markdown"
        )
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")


def get_handlers():
    return [
        CommandHandler("unirse", unirse),
        CommandHandler("salir", salir),
    ]
