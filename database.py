"""Capa de persistencia con SQLite."""

import json
import aiosqlite
from config import DB_PATH
from models import Game, GameConfig, GameState, Player, PlayerRole


async def init_db():
    """Inicializa las tablas de la base de datos."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                creator_id INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'LOBBY',
                config TEXT NOT NULL DEFAULT '{}',
                secret_word TEXT DEFAULT '',
                impostor_hint TEXT DEFAULT '',
                round_number INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                game_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                role TEXT NOT NULL DEFAULT 'NORMAL',
                word TEXT DEFAULT '',
                is_alive INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (game_id, user_id),
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                game_id TEXT NOT NULL,
                voter_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                round_number INTEGER NOT NULL,
                PRIMARY KEY (game_id, voter_id, round_number),
                FOREIGN KEY (game_id) REFERENCES games(game_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                winner TEXT NOT NULL,
                impostor_ids TEXT NOT NULL,
                secret_word TEXT NOT NULL,
                player_count INTEGER NOT NULL,
                finished_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def save_game(game: Game):
    """Guarda o actualiza una partida en la base de datos."""
    config_json = json.dumps({
        "max_players": game.config.max_players,
        "num_impostors": game.config.num_impostors,
        "discussion_time": game.config.discussion_time,
        "category": game.config.category,
    })
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO games
            (game_id, chat_id, creator_id, state, config, secret_word, impostor_hint, round_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            game.game_id, game.chat_id, game.creator_id,
            game.state.value, config_json,
            game.secret_word, game.impostor_hint, game.round_number
        ))
        for player in game.players.values():
            await db.execute("""
                INSERT OR REPLACE INTO players
                (game_id, user_id, username, first_name, role, word, is_alive)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                game.game_id, player.user_id, player.username,
                player.first_name, player.role.value, player.word,
                1 if player.is_alive else 0
            ))
        await db.commit()


async def save_vote(game_id: str, voter_id: int, target_id: int, round_number: int):
    """Registra un voto."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO votes (game_id, voter_id, target_id, round_number)
            VALUES (?, ?, ?, ?)
        """, (game_id, voter_id, target_id, round_number))
        await db.commit()


async def save_stats(game: Game, winner: str):
    """Guarda estadísticas de la partida finalizada."""
    impostor_ids = json.dumps([
        p.user_id for p in game.players.values()
        if p.role == PlayerRole.IMPOSTOR
    ])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO game_stats
            (game_id, chat_id, winner, impostor_ids, secret_word, player_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            game.game_id, game.chat_id, winner,
            impostor_ids, game.secret_word, len(game.players)
        ))
        await db.commit()


async def delete_game(game_id: str):
    """Elimina una partida de la base de datos."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM votes WHERE game_id = ?", (game_id,))
        await db.execute("DELETE FROM players WHERE game_id = ?", (game_id,))
        await db.execute("DELETE FROM games WHERE game_id = ?", (game_id,))
        await db.commit()
