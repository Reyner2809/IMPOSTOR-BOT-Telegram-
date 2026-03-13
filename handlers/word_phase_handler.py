"""Handler para la fase de palabras (turnos) y control de mensajes en partida."""

import asyncio
import logging
from telegram import Update, Bot
from telegram.ext import ContextTypes, MessageHandler, filters
from models import GameState
from game_manager import game_manager

logger = logging.getLogger(__name__)


async def start_word_phase(bot: Bot, chat_id: int, game):
    """Inicia la fase de palabras: anuncia las reglas y el primer turno."""
    alive_count = len(game.alive_players)

    msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🎯 <b>Ronda {game.round_number} — Fase de palabras</b>\n\n"
            f"Cada jugador dirá una palabra relacionada con su palabra secreta.\n"
            f"👥 Jugadores: {alive_count}\n\n"
            f"Espera tu turno para escribir."
        ),
        parse_mode="HTML"
    )
    game.bot_message_ids.append(msg.message_id)
    await announce_turn(bot, chat_id, game)


async def announce_turn(bot: Bot, chat_id: int, game):
    """Anuncia de quién es el turno actual."""
    current = game_manager.get_current_turn_player(chat_id)
    if not current:
        return

    turn_num = game.current_turn_index + 1
    total = len(game.turn_order)
    name = current.first_name
    if current.username:
        name += f" (@{current.username})"

    msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🎤 <b>Turno {turn_num}/{total}</b>\n\n"
            f"Le toca a <b>{name}</b>\n"
            f"Escribe una palabra relacionada con tu palabra secreta."
        ),
        parse_mode="HTML"
    )
    game.bot_message_ids.append(msg.message_id)


async def _safe_delete_message(message):
    """Intenta borrar un mensaje, ignora errores."""
    try:
        await message.delete()
    except Exception:
        pass


async def handle_game_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captura mensajes de texto en grupo durante una partida activa.
    - Eliminados: siempre se borran sus mensajes.
    - processing=True: se borran todos los mensajes (transición en curso).
    - WORD_PHASE: solo habla quien tiene el turno.
    - PLAYING: discusión libre para jugadores vivos.
    """
    if not update.effective_chat or not update.effective_user or not update.message:
        return
    if update.effective_chat.type == "private":
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    game = game_manager.get_game(chat_id)

    if not game or game.state not in (GameState.WORD_PHASE, GameState.PLAYING):
        return

    # Solo afecta a jugadores de la partida
    if user_id not in game.players:
        return

    player = game.players[user_id]

    # ── Jugador eliminado → borrar siempre ──
    if not player.is_alive:
        await _safe_delete_message(update.message)
        return

    # ── Procesando transición → borrar todo ──
    if game.processing:
        await _safe_delete_message(update.message)
        return

    # ── Estado PLAYING → discusión libre para vivos ──
    if game.state == GameState.PLAYING:
        return

    # ── Estado WORD_PHASE → controlar turnos ──
    current = game_manager.get_current_turn_player(chat_id)
    if not current:
        return

    # No es su turno → borrar
    if current.user_id != user_id:
        await _safe_delete_message(update.message)
        warn_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ No es tu turno. Es el turno de <b>{current.first_name}</b>.",
            parse_mode="HTML"
        )
        game.bot_message_ids.append(warn_msg.message_id)
        return

    # Es su turno: registrar que habló
    word_text = update.message.text.strip()
    try:
        result = await game_manager.mark_player_spoke(chat_id, user_id, word_text)
    except ValueError:
        return

    # Si la palabra es duplicada, rechazar y pedir otra
    if result.get("duplicate"):
        dup_name = result["duplicate_player"].first_name if result.get("duplicate_player") else "otro jugador"
        await _safe_delete_message(update.message)
        dup_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ <b>{current.first_name}</b>, esa palabra ya fue dicha por <b>{dup_name}</b>. Escribe otra.",
            parse_mode="HTML"
        )
        game.bot_message_ids.append(dup_msg.message_id)
        return

    # Confirmar
    confirm_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ <b>{current.first_name}</b> dijo: <i>{word_text}</i>",
        parse_mode="HTML"
    )
    game.bot_message_ids.append(confirm_msg.message_id)

    if result["all_done"]:
        # Bloquear mensajes durante la transición
        game.processing = True
        try:
            await _cleanup_turn_messages(context.bot, chat_id, game)
            await _start_discussion_phase(context.bot, chat_id, game, context)
        finally:
            game.processing = False
    else:
        await announce_turn(context.bot, chat_id, result["game"])


async def _cleanup_turn_messages(bot: Bot, chat_id: int, game):
    """Borra los mensajes del bot de la fase de turnos (en paralelo)."""
    if not game.bot_message_ids:
        return

    async def _safe_delete(msg_id):
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass

    tasks = [_safe_delete(mid) for mid in game.bot_message_ids]
    game.bot_message_ids.clear()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _start_discussion_phase(bot: Bot, chat_id: int, game, context: ContextTypes.DEFAULT_TYPE):
    """Inicia la fase de discusión después de que todos dijeron su palabra."""
    from handlers.start_game import start_round_in_group
    await start_round_in_group(bot, chat_id, game, context)


def get_handler():
    return MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
        handle_game_message
    )
