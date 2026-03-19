"""Handler de votación y procesamiento de rondas."""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from models import GameState, PlayerRole
from game_manager import game_manager

logger = logging.getLogger(__name__)


def _escape_md(text: str) -> str:
    """Escapa caracteres especiales de Markdown v1."""
    for ch in ("_", "*", "[", "]", "`"):
        text = text.replace(ch, f"\\{ch}")
    return text


def _player_display_name(player) -> str:
    """Nombre para mostrar (sin Markdown)."""
    name = player.first_name
    if player.username:
        name += f" (@{player.username})"
    return name


def _build_vote_keyboard(game) -> InlineKeyboardMarkup:
    """Construye botones inline solo con jugadores vivos."""
    keyboard = []
    for player in game.alive_players.values():
        name = _player_display_name(player)
        keyboard.append([
            InlineKeyboardButton(
                text=name,
                callback_data=f"vote_{game.chat_id}_{player.user_id}"
            )
        ])
    return InlineKeyboardMarkup(keyboard)


async def send_vote_buttons(bot: Bot, chat_id: int, game=None):
    """Envía los botones de votación al grupo."""
    if game is None:
        game = game_manager.get_game(chat_id)
    if not game or game.state != GameState.PLAYING:
        return

    reply_markup = _build_vote_keyboard(game)
    voted = game_manager.get_vote_count(chat_id)
    total = len(game.alive_players)

    # Resumen de palabras dichas
    word_lines = []
    for pid in game.turn_order:
        player = game.players.get(pid)
        if player and pid in game.spoken_words:
            word_lines.append(f"  💬 <b>{player.first_name}</b>: <i>{game.spoken_words[pid]}</i>")
    word_summary = "\n".join(word_lines) if word_lines else ""
    word_block = f"\n📝 <b>Palabras dichas:</b>\n{word_summary}\n" if word_summary else ""

    msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            "🗳️ <b>¡Vota por el impostor!</b>\n"
            f"{word_block}\n"
            "Selecciona a quién quieres eliminar.\n"
            f"📊 Votos: {voted}/{total}\n\n"
            "⚠️ Tu voto es secreto. Puedes cambiarlo votando de nuevo."
        ),
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    game.bot_message_ids.append(msg.message_id)


async def votar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /votar - muestra botones de votación."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("⚠️ Usa este comando en el grupo de la partida.")
        return

    game = game_manager.get_game(chat.id)
    if not game:
        await update.message.reply_text("⚠️ No hay una partida activa en este grupo.")
        return

    if game.state == GameState.WORD_PHASE:
        await update.message.reply_text("⚠️ Aún estamos en la fase de palabras. Espera a que todos digan su palabra.")
        return

    if game.state != GameState.PLAYING:
        await update.message.reply_text("⚠️ La partida no está en fase de juego.")
        return

    if user.id not in game.players:
        await update.message.reply_text("⚠️ No estás en esta partida.")
        return

    if not game.players[user.id].is_alive:
        await update.message.reply_text("⚠️ Has sido eliminado, no puedes votar.")
        return

    await send_vote_buttons(context.bot, chat.id)


async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el voto de un jugador (callback de inline keyboard)."""
    query = update.callback_query
    user = query.from_user

    parts = query.data.split("_")
    if len(parts) != 3 or parts[0] != "vote":
        await query.answer("❌ Voto inválido.")
        return

    try:
        chat_id = int(parts[1])
        target_id = int(parts[2])
    except ValueError:
        await query.answer("❌ Datos de voto inválidos.")
        return

    try:
        game, changed = await game_manager.cast_vote(chat_id, user.id, target_id)
        target_player = game.players.get(target_id)
        target_name = target_player.first_name if target_player else "?"

        if changed:
            await query.answer(f"🔄 Cambiaste tu voto a {target_name}")
        else:
            await query.answer(f"✅ Votaste por {target_name}")

        voted = game_manager.get_vote_count(chat_id)
        total = len(game.alive_players)
        status_text = "🔄 Voto cambiado" if changed else "🗳️ Voto registrado"
        vote_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"{status_text} ({voted}/{total})",
        )
        game.bot_message_ids.append(vote_msg.message_id)

        # Si todos los vivos votaron → procesar ronda (solo si es voto nuevo)
        if not changed and game_manager.all_alive_voted(chat_id):
            cancel_all_timers(context, chat_id)
            try:
                await process_and_continue(context.bot, chat_id, context)
            except Exception as exc:
                logger.exception(f"Error en process_and_continue para {chat_id}: {exc}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ Error procesando resultados: {exc}"
                )

    except ValueError as e:
        await query.answer(f"⚠️ {e}", show_alert=True)


async def _cleanup_bot_messages(bot: Bot, chat_id: int, game):
    """Borra mensajes acumulados del bot (en paralelo, sin bloquear)."""
    if not game.bot_message_ids:
        return

    async def _safe_delete(msg_id):
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass

    tasks = [_safe_delete(mid) for mid in game.bot_message_ids]
    game.bot_message_ids.clear()
    # Ejecutar en paralelo sin esperar; si falla alguno no importa
    await asyncio.gather(*tasks, return_exceptions=True)


async def process_and_continue(bot: Bot, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el resultado de la votación, elimina jugador, y continúa o termina."""
    # Bloquear mensajes durante la transición
    game_pre = game_manager.get_game(chat_id)
    if not game_pre:
        return
    game_pre.processing = True

    try:
        await _cleanup_bot_messages(bot, chat_id, game_pre)
        result = await game_manager.process_round_end(chat_id)
    except ValueError as e:
        logger.error(f"Error procesando ronda en {chat_id}: {e}")
        await bot.send_message(chat_id=chat_id, text=f"⚠️ Error: {e}")
        game_pre.processing = False
        return

    game = result["game"]

    # ── Construir resumen de votación ──────────────────────────
    vote_counts = result["vote_counts"]
    vote_lines = []
    for player in game.players.values():
        if not player.is_alive and player != result["eliminated"]:
            continue
        if player == result["eliminated"] or player.is_alive:
            count = vote_counts.get(player.user_id, 0)
            bar = "🟥" * count if count > 0 else "—"
            vote_lines.append(f"  {player.first_name}: {count} votos {bar}")

    votes_text = "\n".join(vote_lines)

    # ── Resultado de eliminación ───────────────────────────────
    eliminated = result["eliminated"]
    if result["is_tie"]:
        elim_text = "⚖️ <b>¡Empate!</b> Nadie es eliminado esta ronda."
    elif eliminated:
        role_text = "🔴 IMPOSTOR" if eliminated.role == PlayerRole.IMPOSTOR else "🟢 CIUDADANO"
        ename = _player_display_name(eliminated)
        elim_text = (
            f"🎯 <b>{ename}</b> fue eliminado con {vote_counts.get(eliminated.user_id, 0)} votos.\n"
            f"Era: {role_text}"
        )
    else:
        elim_text = "🤷 Nadie fue eliminado."

    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"📊 <b>Resultados de la Ronda {result['round_number']}</b>\n\n"
            f"<b>Votación:</b>\n{votes_text}\n\n"
            f"{elim_text}"
        ),
        parse_mode="HTML"
    )

    # ── ¿Fin del juego o nueva ronda? ──────────────────────────
    if result["game_over"]:
        all_impostors = result["all_impostors"]
        impostor_names = []
        for imp in all_impostors:
            n = _player_display_name(imp)
            status = "💀 eliminado" if not imp.is_alive else "😈 sobrevivió"
            impostor_names.append(f"  {n} — {status}")

        if result["winner"] == "ciudadanos":
            winner_text = "🎉 <b>¡LOS CIUDADANOS GANAN!</b>\nTodos los impostores fueron eliminados."
        else:
            winner_text = "😈 <b>¡LOS IMPOSTORES GANAN!</b>\nLos impostores dominan el grupo."

        survivors = [p for p in game.players.values() if p.is_alive]
        survivor_lines = []
        for s in survivors:
            role = "🔴" if s.role == PlayerRole.IMPOSTOR else "🟢"
            survivor_lines.append(f"  {role} {s.first_name}")

        await bot.send_message(
            chat_id=chat_id,
            text=(
                "🏁 <b>¡FIN DE LA PARTIDA!</b>\n\n"
                f"{winner_text}\n\n"
                f"🔑 <b>Palabra secreta:</b> {result['secret_word']}\n"
                f"📌 <b>Pista del impostor:</b> {result['impostor_hint']}\n\n"
                "🔴 <b>Impostores eran:</b>\n" + "\n".join(impostor_names) + "\n\n"
                "👥 <b>Sobrevivientes:</b>\n" + "\n".join(survivor_lines) + "\n\n"
                f"Rondas jugadas: {result['round_number']}\n\n"
                "Usa /crear_partida para jugar de nuevo."
            ),
            parse_mode="HTML"
        )
    else:
        alive_count = len(game.alive_players)
        imp_count = len(game.alive_impostors)
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "▶️ <b>¡Nueva ronda!</b>\n\n"
                f"👥 Jugadores vivos: {alive_count}\n"
                f"🔴 Impostores restantes: {imp_count}\n\n"
                "Recuerda tu palabra y sigue buscando al impostor."
            ),
            parse_mode="HTML"
        )

        # Iniciar fase de palabras de la nueva ronda
        from handlers.word_phase_handler import start_word_phase
        game.processing = False
        await start_word_phase(bot, chat_id, game)


def cancel_all_timers(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Cancela todos los timers activos de una partida."""
    if context.job_queue is None:
        logger.warning("JobQueue no disponible, no se pueden cancelar timers.")
        return
    for prefix in ["discussion_", "halfway_", "thirty_"]:
        jobs = context.job_queue.get_jobs_by_name(f"{prefix}{chat_id}")
        for job in jobs:
            job.schedule_removal()


async def forzar_voto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /forzar_voto - el creador salta la fase de palabras y fuerza la votación."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("⚠️ Usa este comando en el grupo de la partida.")
        return

    game = game_manager.get_game(chat.id)
    if not game:
        await update.message.reply_text("⚠️ No hay una partida activa en este grupo.")
        return

    if game.state == GameState.PLAYING:
        await update.message.reply_text("⚠️ Ya estás en fase de votación.")
        return

    try:
        game = await game_manager.force_to_voting(chat.id, user.id)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return

    await update.message.reply_text("⏭️ <b>Fase de palabras saltada.</b> Pasando a votación...", parse_mode="HTML")

    from handlers.word_phase_handler import _cleanup_turn_messages
    await _cleanup_turn_messages(context.bot, chat.id, game)

    from handlers.start_game import start_round_in_group
    await start_round_in_group(context.bot, chat.id, game, context)


def get_handlers():
    return [
        CommandHandler("votar", votar),
        CommandHandler("forzar_voto", forzar_voto),
        CallbackQueryHandler(vote_callback, pattern=r"^vote_"),
    ]
