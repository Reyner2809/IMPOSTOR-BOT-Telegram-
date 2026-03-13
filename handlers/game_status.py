"""Handler para consultar estado, cancelar y finalizar partidas."""

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from models import GameState, PlayerRole
from game_manager import game_manager


async def estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    game = game_manager.get_game(chat.id)

    if not game:
        await update.message.reply_text(
            "ℹ️ No hay una partida activa en este grupo.\n"
            "Usa /crear_partida para iniciar una."
        )
        return

    state_emojis = {
        GameState.LOBBY: "🏠 Esperando jugadores",
        GameState.WORD_PHASE: "🎤 Fase de palabras",
        GameState.PLAYING: "💬 En juego",
        GameState.FINISHED: "🏁 Finalizada",
    }

    player_lines = []
    for i, player in enumerate(game.players.values(), 1):
        name = player.first_name
        if player.username:
            name += f" (@{player.username})"
        if not player.is_alive:
            name += " 💀"
        elif game.state in (GameState.PLAYING, GameState.WORD_PHASE):
            voted = "✅" if player.has_voted else "⏳"
            name += f" {voted}"
        if player.user_id == game.creator_id:
            name += " 👑"
        player_lines.append(f"  {i}. {name}")

    players_text = "\n".join(player_lines)

    text = (
        f"📊 *Estado de la partida*\n\n"
        f"🆔 ID: `{game.game_id}`\n"
        f"📍 Estado: {state_emojis.get(game.state, game.state.value)}\n"
        f"🔄 Ronda: {game.round_number}\n\n"
        f"👥 Jugadores:\n{players_text}\n\n"
        f"⚙️ Configuración:\n"
        f"  • Impostores: {game.config.num_impostors}\n"
        f"  • Tiempo discusión: {game.config.discussion_time}s\n"
        f"  • Categoría: {game.config.category}"
    )

    if game.state == GameState.PLAYING:
        voted = sum(1 for p in game.alive_players.values() if p.has_voted)
        alive = len(game.alive_players)
        text += f"\n\n🗳️ Votos: {voted}/{alive}"
        text += f"\n👥 Vivos: {alive} | 💀 Eliminados: {len(game.players) - alive}"

    await update.message.reply_text(text, parse_mode="Markdown")


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    game = game_manager.get_game(chat.id)

    if not game:
        await update.message.reply_text("⚠️ No hay una partida activa.")
        return

    if user.id != game.creator_id:
        await update.message.reply_text("⚠️ Solo el creador puede cancelar la partida.")
        return

    from handlers.vote_handler import cancel_all_timers
    cancel_all_timers(context, chat.id)
    await game_manager.cancel_game(chat.id)
    await update.message.reply_text("🚫 Partida cancelada.")


async def finalizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /finalizar - termina la partida actual forzosamente."""
    chat = update.effective_chat
    user = update.effective_user
    game = game_manager.get_game(chat.id)

    if not game:
        await update.message.reply_text("⚠️ No hay una partida activa en este grupo.")
        return

    if user.id != game.creator_id:
        await update.message.reply_text("⚠️ Solo el creador puede finalizar la partida.")
        return

    from handlers.vote_handler import cancel_all_timers
    cancel_all_timers(context, chat.id)

    # Mostrar info si estaba en juego
    if game.state in (GameState.PLAYING, GameState.WORD_PHASE):
        all_impostors = [p for p in game.players.values() if p.role == PlayerRole.IMPOSTOR]
        impostor_names = []
        for imp in all_impostors:
            n = imp.first_name
            if imp.username:
                n += f" (@{imp.username})"
            impostor_names.append(n)

        await update.message.reply_text(
            f"🛑 *Partida finalizada por el creador.*\n\n"
            f"🔴 Los impostores eran: {', '.join(impostor_names)}\n"
            f"🔑 Última palabra: *{game.secret_word}*\n"
            f"Rondas jugadas: {game.round_number}\n\n"
            f"Usa /crear\\_partida para iniciar una nueva.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🛑 *Partida finalizada.*\n\n"
            "Usa /crear\\_partida para iniciar una nueva.",
            parse_mode="Markdown"
        )

    try:
        await game_manager.force_finish(chat.id)
    except ValueError:
        pass  # Ya fue limpiada


def get_handlers():
    return [
        CommandHandler("estado", estado),
        CommandHandler("cancelar", cancelar),
        CommandHandler("finalizar", finalizar),
    ]
