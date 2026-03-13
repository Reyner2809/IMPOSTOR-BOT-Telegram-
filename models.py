"""Modelos de datos del juego."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class GameState(str, Enum):
    LOBBY = "LOBBY"
    WORD_PHASE = "WORD_PHASE"
    PLAYING = "PLAYING"
    FINISHED = "FINISHED"


class PlayerRole(str, Enum):
    NORMAL = "NORMAL"
    IMPOSTOR = "IMPOSTOR"


@dataclass
class Player:
    user_id: int
    username: str
    first_name: str
    role: PlayerRole = PlayerRole.NORMAL
    word: str = ""
    has_voted: bool = False
    vote_target: Optional[int] = None
    is_alive: bool = True
    has_spoken: bool = False
    spoken_word: str = ""


@dataclass
class GameConfig:
    max_players: int = 20
    num_impostors: int = 1
    discussion_time: int = 180
    category: str = "todas"


@dataclass
class Game:
    game_id: str
    chat_id: int
    creator_id: int
    state: GameState = GameState.LOBBY
    config: GameConfig = field(default_factory=GameConfig)
    players: dict[int, Player] = field(default_factory=dict)
    secret_word: str = ""
    impostor_hint: str = ""
    votes: dict[int, int] = field(default_factory=dict)
    round_number: int = 0
    turn_order: list[int] = field(default_factory=list)
    current_turn_index: int = 0
    bot_message_ids: list[int] = field(default_factory=list)
    processing: bool = False
    spoken_words: dict[int, str] = field(default_factory=dict)

    @property
    def alive_players(self) -> dict[int, Player]:
        return {pid: p for pid, p in self.players.items() if p.is_alive}

    @property
    def alive_impostors(self) -> list[Player]:
        return [p for p in self.players.values() if p.is_alive and p.role == PlayerRole.IMPOSTOR]

    @property
    def alive_citizens(self) -> list[Player]:
        return [p for p in self.players.values() if p.is_alive and p.role == PlayerRole.NORMAL]
