"""Gestor principal de partidas. Mantiene el estado en memoria y persiste en SQLite."""

import random
import uuid
from models import Game, GameConfig, GameState, Player, PlayerRole
from word_manager import word_manager
from gemini_manager import gemini_manager
from database import save_game, save_vote, save_stats, delete_game


class GameManager:
    def __init__(self):
        # chat_id -> Game  (una partida activa por grupo)
        self._games: dict[int, Game] = {}

    # ── Consultas ──────────────────────────────────────────────

    def get_game(self, chat_id: int) -> Game | None:
        return self._games.get(chat_id)

    def has_active_game(self, chat_id: int) -> bool:
        game = self._games.get(chat_id)
        return game is not None and game.state != GameState.FINISHED

    # ── Crear partida ──────────────────────────────────────────

    async def create_game(self, chat_id: int, creator_id: int, creator_username: str, creator_name: str) -> Game:
        if self.has_active_game(chat_id):
            raise ValueError("Ya hay una partida activa en este grupo. Usa /finalizar para terminarla.")

        game = Game(
            game_id=str(uuid.uuid4())[:8],
            chat_id=chat_id,
            creator_id=creator_id,
        )
        game.players[creator_id] = Player(
            user_id=creator_id,
            username=creator_username,
            first_name=creator_name,
        )
        self._games[chat_id] = game
        await save_game(game)
        return game

    # ── Unirse / Salir ─────────────────────────────────────────

    async def join_game(self, chat_id: int, user_id: int, username: str, first_name: str) -> Game:
        game = self._require_game(chat_id, [GameState.LOBBY])
        if user_id in game.players:
            raise ValueError("Ya estás en la partida.")
        if len(game.players) >= game.config.max_players:
            raise ValueError("La partida está llena.")

        game.players[user_id] = Player(
            user_id=user_id, username=username, first_name=first_name
        )
        await save_game(game)
        return game

    async def leave_game(self, chat_id: int, user_id: int) -> Game:
        game = self._require_game(chat_id, [GameState.LOBBY])
        if user_id not in game.players:
            raise ValueError("No estás en la partida.")
        del game.players[user_id]

        if user_id == game.creator_id:
            await self.cancel_game(chat_id)
            raise ValueError("El creador abandonó. Partida cancelada.")

        await save_game(game)
        return game

    # ── Configuración ──────────────────────────────────────────

    async def set_impostors(self, chat_id: int, user_id: int, count: int) -> Game:
        game = self._require_game(chat_id, [GameState.LOBBY])
        self._require_creator(game, user_id)
        if count < 1:
            raise ValueError("Debe haber al menos 1 impostor.")
        game.config.num_impostors = count
        await save_game(game)
        return game

    async def set_discussion_time(self, chat_id: int, user_id: int, seconds: int) -> Game:
        game = self._require_game(chat_id, [GameState.LOBBY])
        self._require_creator(game, user_id)
        if seconds < 30 or seconds > 600:
            raise ValueError("El tiempo debe estar entre 30 y 600 segundos.")
        game.config.discussion_time = seconds
        await save_game(game)
        return game

    async def set_category(self, chat_id: int, user_id: int, category: str) -> Game:
        game = self._require_game(chat_id, [GameState.LOBBY])
        self._require_creator(game, user_id)
        valid = word_manager.get_categories() + ["todas"]
        if category not in valid:
            raise ValueError(f"Categoría inválida. Opciones: {', '.join(valid)}")
        game.config.category = category
        await save_game(game)
        return game

    # ── Iniciar partida (primera ronda) ────────────────────────

    async def start_game(self, chat_id: int, user_id: int) -> Game:
        game = self._require_game(chat_id, [GameState.LOBBY])
        self._require_creator(game, user_id)

        player_count = len(game.players)
        if player_count < 3:
            raise ValueError("Se necesitan al menos 3 jugadores.")
        if game.config.num_impostors >= player_count:
            raise ValueError("Los impostores deben ser menos que los jugadores.")

        # Asignar roles (solo una vez al inicio de la partida)
        player_ids = list(game.players.keys())
        impostor_ids = set(random.sample(player_ids, game.config.num_impostors))

        for pid, player in game.players.items():
            if pid in impostor_ids:
                player.role = PlayerRole.IMPOSTOR
            else:
                player.role = PlayerRole.NORMAL
            player.is_alive = True

        # Obtener palabra y pista (Gemini AI, con fallback a word_manager)
        word, hint = await gemini_manager.get_word_and_hint(game.config.category)

        # Iniciar primera ronda
        self._start_new_round(game, first_round=True, word=word, hint=hint)
        game.state = GameState.WORD_PHASE
        await save_game(game)
        return game

    # ── Rondas ─────────────────────────────────────────────────

    def _start_new_round(self, game: Game, first_round: bool = False, word: str = "", hint: str = ""):
        """Prepara una nueva ronda: resetea votos. Solo asigna palabra en la primera ronda."""
        game.round_number += 1

        if first_round:
            # Asignar palabra (ya obtenida de Gemini AI o fallback)
            game.secret_word = word
            game.impostor_hint = hint

            for player in game.players.values():
                if player.is_alive:
                    if player.role == PlayerRole.IMPOSTOR:
                        player.word = hint
                    else:
                        player.word = word

        # Resetear votos y turnos
        for player in game.players.values():
            if player.is_alive:
                player.has_voted = False
                player.vote_target = None
                player.has_spoken = False

        game.votes.clear()
        game.spoken_words.clear()

        # Preparar orden de turnos aleatorio (solo jugadores vivos)
        alive_ids = list(game.alive_players.keys())
        random.shuffle(alive_ids)
        game.turn_order = alive_ids
        game.current_turn_index = 0

    # ── Fase de palabras (turnos) ───────────────────────────────

    def get_current_turn_player(self, chat_id: int) -> Player | None:
        """Retorna el jugador que tiene el turno actual."""
        game = self._games.get(chat_id)
        if not game or game.state != GameState.WORD_PHASE:
            return None
        if game.current_turn_index >= len(game.turn_order):
            return None
        pid = game.turn_order[game.current_turn_index]
        return game.players.get(pid)

    async def mark_player_spoke(self, chat_id: int, user_id: int, word: str = "") -> dict:
        """Marca que un jugador dijo su palabra y avanza al siguiente turno.
        Retorna dict con info del estado: next_player, all_done, duplicate."""
        game = self._require_game(chat_id, [GameState.WORD_PHASE])
        current_player = self.get_current_turn_player(chat_id)
        if not current_player or current_player.user_id != user_id:
            raise ValueError("No es tu turno.")

        # Verificar palabra duplicada (comparar en minúsculas)
        word_lower = word.strip().lower()
        for pid, spoken in game.spoken_words.items():
            if spoken.lower() == word_lower:
                duplicate_player = game.players.get(pid)
                return {"all_done": False, "next_player": None, "game": game,
                        "duplicate": True, "duplicate_player": duplicate_player}

        current_player.has_spoken = True
        current_player.spoken_word = word.strip()
        game.spoken_words[user_id] = word.strip()
        game.current_turn_index += 1

        all_done = game.current_turn_index >= len(game.turn_order)
        next_player = None
        if not all_done:
            next_pid = game.turn_order[game.current_turn_index]
            next_player = game.players.get(next_pid)

        if all_done:
            game.state = GameState.PLAYING

        await save_game(game)
        return {"all_done": all_done, "next_player": next_player, "game": game, "duplicate": False}

    # ── Votación ───────────────────────────────────────────────

    async def cast_vote(self, chat_id: int, voter_id: int, target_id: int) -> tuple[Game, bool]:
        """Registra o cambia el voto. Retorna (game, changed) donde changed=True si fue cambio de voto."""
        game = self._require_game(chat_id, [GameState.PLAYING])
        if voter_id not in game.players:
            raise ValueError("No estás en esta partida.")
        if not game.players[voter_id].is_alive:
            raise ValueError("Has sido eliminado, no puedes votar.")
        if target_id not in game.players or not game.players[target_id].is_alive:
            raise ValueError("Jugador objetivo inválido.")
        if voter_id == target_id:
            raise ValueError("No puedes votar por ti mismo.")

        changed = game.players[voter_id].has_voted
        game.players[voter_id].has_voted = True
        game.players[voter_id].vote_target = target_id
        game.votes[voter_id] = target_id
        await save_vote(game.game_id, voter_id, target_id, game.round_number)
        await save_game(game)
        return game, changed

    def all_alive_voted(self, chat_id: int) -> bool:
        game = self._games.get(chat_id)
        if not game:
            return False
        return all(p.has_voted for p in game.alive_players.values())

    def get_vote_count(self, chat_id: int) -> int:
        game = self._games.get(chat_id)
        if not game:
            return 0
        return sum(1 for p in game.alive_players.values() if p.has_voted)

    def get_alive_count(self, chat_id: int) -> int:
        game = self._games.get(chat_id)
        if not game:
            return 0
        return len(game.alive_players)

    # ── Procesar fin de ronda ──────────────────────────────────

    async def process_round_end(self, chat_id: int) -> dict:
        """
        Procesa el fin de una ronda:
        - Cuenta votos
        - Elimina al más votado (o nadie si hay empate)
        - Verifica condición de victoria
        - Si el juego continúa, prepara nueva ronda

        Retorna un dict con toda la info de la ronda.
        """
        game = self._require_game(chat_id, [GameState.PLAYING])

        # Contar votos
        vote_counts: dict[int, int] = {}
        for target_id in game.votes.values():
            vote_counts[target_id] = vote_counts.get(target_id, 0) + 1

        # Determinar más votado
        eliminated_player = None
        is_tie = False
        if vote_counts:
            max_votes = max(vote_counts.values())
            most_voted_ids = [pid for pid, count in vote_counts.items() if count == max_votes]

            if len(most_voted_ids) == 1:
                # Un solo más votado → eliminado
                eliminated_id = most_voted_ids[0]
                eliminated_player = game.players[eliminated_id]
                eliminated_player.is_alive = False
            else:
                # Empate → nadie eliminado
                is_tie = True
        else:
            # Nadie votó
            is_tie = True

        # Verificar condición de victoria
        alive_impostors = game.alive_impostors
        alive_citizens = game.alive_citizens
        game_over = False
        winner = None

        if len(alive_impostors) == 0:
            # Todos los impostores eliminados
            game_over = True
            winner = "ciudadanos"
        elif len(alive_impostors) >= len(alive_citizens):
            # Impostores igualan o superan a ciudadanos
            game_over = True
            winner = "impostores"

        result = {
            "vote_counts": vote_counts,
            "eliminated": eliminated_player,
            "is_tie": is_tie,
            "game_over": game_over,
            "winner": winner,
            "secret_word": game.secret_word,
            "impostor_hint": game.impostor_hint,
            "round_number": game.round_number,
            "alive_impostors": alive_impostors,
            "alive_citizens": alive_citizens,
            "all_impostors": [p for p in game.players.values() if p.role == PlayerRole.IMPOSTOR],
            "game": game,
            "total_votes": len(game.votes),
            "total_alive": len(game.alive_players) + (1 if eliminated_player else 0),
        }

        if game_over:
            game.state = GameState.FINISHED
            await save_stats(game, winner)
            del self._games[chat_id]
        else:
            # Preparar nueva ronda (vuelve a fase de palabras)
            self._start_new_round(game)
            game.state = GameState.WORD_PHASE
            await save_game(game)

        return result

    # ── Forzar votación ───────────────────────────────────────

    async def force_to_voting(self, chat_id: int, user_id: int) -> Game:
        """El creador fuerza el paso a votación saltando los turnos pendientes."""
        game = self._require_game(chat_id, [GameState.WORD_PHASE])
        self._require_creator(game, user_id)
        game.current_turn_index = len(game.turn_order)
        game.state = GameState.PLAYING
        await save_game(game)
        return game

    # ── Finalizar / Cancelar ──────────────────────────────────

    async def force_finish(self, chat_id: int):
        """Fuerza el fin de la partida completa, sin importar el estado."""
        game = self._games.pop(chat_id, None)
        if not game:
            raise ValueError("No hay una partida activa en este grupo.")
        await delete_game(game.game_id)

    async def cancel_game(self, chat_id: int):
        game = self._games.pop(chat_id, None)
        if game:
            await delete_game(game.game_id)

    # ── Helpers privados ───────────────────────────────────────

    def _require_game(self, chat_id: int, valid_states: list[GameState]) -> Game:
        game = self._games.get(chat_id)
        if not game:
            raise ValueError("No hay una partida activa en este grupo.")
        if game.state not in valid_states:
            raise ValueError("La partida no está en un estado válido para esta acción.")
        return game

    @staticmethod
    def _require_creator(game: Game, user_id: int):
        if user_id != game.creator_id:
            raise ValueError("Solo el creador de la partida puede hacer esto.")


# Instancia global
game_manager = GameManager()
