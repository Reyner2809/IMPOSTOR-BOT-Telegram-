"""Configuración global del bot."""

import os
from pathlib import Path

# Cargar .env si existe
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())

# Token del bot (obtener de @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "TU_TOKEN_AQUI")

# Base de datos
DB_PATH = os.getenv("DB_PATH", "data/impostor.db")

# Configuración por defecto de partidas
DEFAULT_MIN_PLAYERS = 3
DEFAULT_MAX_PLAYERS = 20
DEFAULT_IMPOSTORS = 1
DEFAULT_DISCUSSION_TIME = 180  # segundos (3 minutos)
DEFAULT_VOTE_TIME = 60  # segundos
DEFAULT_CATEGORY = "todas"
DEFAULT_LANGUAGE = "es"

# Ruta de palabras
WORDS_PATH = os.getenv("WORDS_PATH", "data/words.json")
