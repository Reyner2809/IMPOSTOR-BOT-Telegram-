"""Gestión del diccionario de palabras."""

import json
import random
from config import WORDS_PATH


class WordManager:
    def __init__(self):
        self._words: dict[str, list[dict]] = {}
        self._load_words()

    def _load_words(self):
        with open(WORDS_PATH, "r", encoding="utf-8") as f:
            self._words = json.load(f)

    def get_categories(self) -> list[str]:
        return list(self._words.keys())

    def get_random_word(self, category: str = "todas") -> tuple[str, str]:
        """Retorna (palabra_secreta, pista_impostor)."""
        if category == "todas":
            category = random.choice(list(self._words.keys()))
        elif category not in self._words:
            category = random.choice(list(self._words.keys()))

        word_entry = random.choice(self._words[category])
        return word_entry["palabra"], word_entry["pista"]

    def reload(self):
        self._load_words()


# Instancia global
word_manager = WordManager()
