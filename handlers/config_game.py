"""Handlers de configuración de partida."""

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from game_manager import game_manager
from word_manager import word_manager


async def config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    game = game_manager.get_game(chat.id)

    if not game:
        await update.message.reply_text("⚠️ No hay una partida activa.")
        return

    categories = ", ".join(word_manager.get_categories() + ["todas"])
    await update.message.reply_text(
        f"⚙️ *Configuración actual*\n\n"
        f"• Impostores: {game.config.num_impostors}\n"
        f"• Tiempo de discusión: {game.config.discussion_time}s\n"
        f"• Categoría: {game.config.category}\n\n"
        f"*Comandos de configuración:*\n"
        f"/set\\_impostores `<número>`\n"
        f"/set\\_tiempo `<segundos>`\n"
        f"/set\\_categoria `<nombre>`\n\n"
        f"Categorías disponibles: {categories}",
        parse_mode="Markdown"
    )


async def set_impostores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if not context.args:
        await update.message.reply_text("Uso: /set_impostores <número>")
        return

    try:
        count = int(context.args[0])
        game = await game_manager.set_impostors(chat.id, user.id, count)
        await update.message.reply_text(f"✅ Impostores configurados: {game.config.num_impostors}")
    except (ValueError, IndexError) as e:
        await update.message.reply_text(f"⚠️ {e}")


async def set_tiempo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if not context.args:
        await update.message.reply_text("Uso: /set_tiempo <segundos>")
        return

    try:
        seconds = int(context.args[0])
        game = await game_manager.set_discussion_time(chat.id, user.id, seconds)
        await update.message.reply_text(f"✅ Tiempo de discusión: {game.config.discussion_time}s")
    except (ValueError, IndexError) as e:
        await update.message.reply_text(f"⚠️ {e}")


async def set_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if not context.args:
        await update.message.reply_text("Uso: /set_categoria <nombre>")
        return

    try:
        category = context.args[0].lower()
        game = await game_manager.set_category(chat.id, user.id, category)
        await update.message.reply_text(f"✅ Categoría: {game.config.category}")
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")


def get_handlers():
    return [
        CommandHandler("config", config),
        CommandHandler("set_impostores", set_impostores),
        CommandHandler("set_tiempo", set_tiempo),
        CommandHandler("set_categoria", set_categoria),
    ]
