"""Handler para iniciar la partida y gestionar rondas."""

import logging
from telegram import Update, Bot
from telegram.ext import ContextTypes, CommandHandler
from telegram.error import Forbidden
from models import GameState, PlayerRole
from game_manager import game_manager

logger = logging.getLogger(__name__)


async def send_words_to_players(bot: Bot, game) -> list[str]:
    """Envía las palabras secretas por privado a todos los jugadores vivos.
    Retorna lista de nombres que fallaron."""
    failed = []
    for player in game.alive_players.values():
        try:
            if player.role == PlayerRole.IMPOSTOR:
                await bot.send_message(
                    chat_id=player.user_id,
                    text=(
                        f"🔴 <b>¡Eres el IMPOSTOR!</b> (Ronda {game.round_number})\n\n"
                        f"📌 Tu pista: <b>{player.word}</b>\n\n"
                        f"Los demás tienen una palabra específica.\n"
                        f"Intenta descubrir cuál es sin delatarte."
                    ),
                    parse_mode="HTML"
                )
            else:
                await bot.send_message(
                    chat_id=player.user_id,
                    text=(
                        f"🟢 <b>Eres un CIUDADANO</b> (Ronda {game.round_number})\n\n"
                        f"🔑 Tu palabra secreta: <b>{player.word}</b>\n\n"
                        f"Hay impostores entre ustedes.\n"
                        f"Descúbrelos durante la discusión."
                    ),
                    parse_mode="HTML"
                )
        except (Forbidden, Exception):
            failed.append(player.first_name)
    return failed


async def start_round_in_group(bot: Bot, chat_id: int, game, context: ContextTypes.DEFAULT_TYPE):
    """Anuncia una nueva ronda en el grupo y programa timers."""
    discussion_time = game.config.discussion_time
    alive_count = len(game.alive_players)
    impostor_count = len(game.alive_impostors)

    # Resumen de palabras dichas en la fase de palabras
    word_summary_lines = []
    for pid in game.turn_order:
        player = game.players.get(pid)
        if player and pid in game.spoken_words:
            word_summary_lines.append(f"  💬 <b>{player.first_name}</b>: <i>{game.spoken_words[pid]}</i>")
    word_summary = "\n".join(word_summary_lines) if word_summary_lines else "  (sin palabras)"

    msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            f"💬 <b>Ronda {game.round_number} — Discusión</b>\n\n"
            f"📝 <b>Resumen de palabras:</b>\n{word_summary}\n\n"
            f"👥 Jugadores vivos: {alive_count}\n"
            f"🔴 Impostores restantes: {impostor_count}\n\n"
            f"Tienen <b>{discussion_time} segundos</b> para discutir.\n\n"
            f"🗳️ Usa /votar cuando quieras votar.\n"
            f"Si todos votan, la ronda termina automáticamente.\n\n"
            f"⏳ El tiempo corre..."
        ),
        parse_mode="HTML"
    )
    game.bot_message_ids.append(msg.message_id)

    # Enviar botones de votación
    from handlers.vote_handler import send_vote_buttons
    await send_vote_buttons(bot, chat_id, game)

    # Programar timers
    if context.job_queue is None:
        logger.warning("JobQueue no disponible, los timers de ronda no se programarán.")
    else:
        context.job_queue.run_once(
            _discussion_timer_callback,
            when=discussion_time,
            chat_id=chat_id,
            name=f"discussion_{chat_id}",
        )

        if discussion_time > 60:
            half = discussion_time // 2
            context.job_queue.run_once(
                _halfway_callback,
                when=half,
                chat_id=chat_id,
                name=f"halfway_{chat_id}",
                data={"remaining": discussion_time - half}
            )

        if discussion_time > 30:
            context.job_queue.run_once(
                _thirty_seconds_callback,
                when=discussion_time - 30,
                chat_id=chat_id,
                name=f"thirty_{chat_id}",
            )


async def iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /iniciar - inicia la partida."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("⚠️ Usa este comando en el grupo de la partida.")
        return

    try:
        game = await game_manager.start_game(chat_id=chat.id, user_id=user.id)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return

    await update.message.reply_text(
        f"🎮 <b>¡La partida ha comenzado!</b>\n\n"
        f"👥 Jugadores: {len(game.players)}\n"
        f"🔴 Impostores: {game.config.num_impostors}\n"
        f"📂 Categoría: {game.config.category}\n\n"
        f"📩 <b>Revisa tu mensaje privado</b> para ver tu palabra.\n"
        f"Si no recibiste mensaje, envía /start al bot en privado.",
        parse_mode="HTML"
    )

    # Enviar palabras
    failed = await send_words_to_players(context.bot, game)
    if failed:
        names = ", ".join(failed)
        await update.message.reply_text(
            f"⚠️ No pude enviar mensaje privado a: {names}\n"
            f"Deben enviar /start al bot en privado primero."
        )
        await game_manager.cancel_game(chat.id)
        return

    # Iniciar fase de palabras (turnos)
    from handlers.word_phase_handler import start_word_phase
    await start_word_phase(context.bot, chat.id, game)


# ── Timer callbacks ────────────────────────────────────────────

def _pending_voters_text(game) -> str:
    """Retorna texto con los nombres de quienes no han votado."""
    pending = [p.first_name for p in game.alive_players.values() if not p.has_voted]
    if not pending:
        return ""
    return "\n👤 Faltan: " + ", ".join(pending)


async def _halfway_callback(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    game = game_manager.get_game(chat_id)
    if not game or game.state != GameState.PLAYING:
        return
    remaining = context.job.data["remaining"]
    voted = game_manager.get_vote_count(chat_id)
    total = game_manager.get_alive_count(chat_id)
    pending = _pending_voters_text(game)
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏰ <b>Quedan {remaining} segundos</b>\n🗳️ Votos: {voted}/{total}{pending}",
        parse_mode="HTML"
    )
    game.bot_message_ids.append(msg.message_id)


async def _thirty_seconds_callback(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    game = game_manager.get_game(chat_id)
    if not game or game.state != GameState.PLAYING:
        return
    voted = game_manager.get_vote_count(chat_id)
    total = game_manager.get_alive_count(chat_id)
    pending = _pending_voters_text(game)
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏰ <b>¡Quedan 30 segundos!</b>\n🗳️ Votos: {voted}/{total}{pending}\n\nUsa /votar si no has votado.",
        parse_mode="HTML"
    )
    game.bot_message_ids.append(msg.message_id)


async def _discussion_timer_callback(context: ContextTypes.DEFAULT_TYPE):
    """Tiempo agotado → procesar ronda."""
    chat_id = context.job.chat_id
    game = game_manager.get_game(chat_id)
    if not game or game.state != GameState.PLAYING:
        return

    voted = game_manager.get_vote_count(chat_id)
    total = game_manager.get_alive_count(chat_id)

    pending = _pending_voters_text(game)
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏰ <b>¡Se acabó el tiempo!</b>\n🗳️ Votos: {voted}/{total}{pending}",
        parse_mode="HTML"
    )
    game.bot_message_ids.append(msg.message_id)

    from handlers.vote_handler import process_and_continue
    await process_and_continue(context.bot, chat_id, context)


def get_handler():
    return CommandHandler("iniciar", iniciar)
