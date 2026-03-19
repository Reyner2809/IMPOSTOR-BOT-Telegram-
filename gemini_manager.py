"""Integración con Gemini AI para generación de palabras y pistas."""

import json
import logging
import asyncio
import re
from collections import deque
from datetime import datetime, date
from pathlib import Path

from google import genai
from google.genai import types

from config import GEMINI_API_KEY
from word_manager import word_manager

logger = logging.getLogger(__name__)

USED_WORDS_PATH = Path("data/used_words.json")
MAX_RPM = 15
MAX_RPD = 500
GEMINI_MODEL = "gemini-flash-lite-latest"


class GeminiManager:
    def __init__(self):
        self._configured = False
        self._client = None
        self._request_times: deque = deque()  # timestamps últimos 60s (para RPM)
        self._daily_count = 0
        self._daily_date = date.today()
        self._used_words: set[str] = set()
        self._lock = asyncio.Lock()

        self._load_used_words()

        if GEMINI_API_KEY and GEMINI_API_KEY != "TU_GEMINI_API_KEY_AQUI":
            try:
                self._client = genai.Client(api_key=GEMINI_API_KEY)
                self._configured = True
                logger.info("Gemini AI configurado correctamente con modelo %s.", GEMINI_MODEL)
            except Exception as e:
                logger.error("Error configurando Gemini AI: %s", e)
        else:
            logger.warning(
                "GEMINI_API_KEY no encontrada. Usando word_manager como fallback."
            )

    # ── Persistencia de palabras usadas ────────────────────────

    def _load_used_words(self):
        if not USED_WORDS_PATH.exists():
            return
        try:
            with open(USED_WORDS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._used_words = set(data.get("words", []))
            self._daily_count = data.get("daily_count", 0)
            daily_date_str = data.get("daily_date", "")
            if daily_date_str:
                self._daily_date = date.fromisoformat(daily_date_str)
            if self._daily_date != date.today():
                self._daily_date = date.today()
                self._daily_count = 0
            logger.info(
                "Cargadas %d palabras usadas. Consultas hoy: %d/%d.",
                len(self._used_words), self._daily_count, MAX_RPD
            )
        except Exception as e:
            logger.error("Error cargando used_words.json: %s", e)

    def _save_used_words(self):
        try:
            USED_WORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(USED_WORDS_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "words": list(self._used_words),
                        "daily_count": self._daily_count,
                        "daily_date": self._daily_date.isoformat(),
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.error("Error guardando used_words.json: %s", e)

    # ── Rate limiting ───────────────────────────────────────────

    def _check_daily_reset(self):
        today = date.today()
        if today != self._daily_date:
            self._daily_date = today
            self._daily_count = 0

    def _can_make_request(self) -> bool:
        """Verifica límites: 15 RPM y 500 RPD."""
        self._check_daily_reset()

        if self._daily_count >= MAX_RPD:
            logger.warning("Límite diario alcanzado (%d/%d). Usando fallback.", self._daily_count, MAX_RPD)
            return False

        now = datetime.now().timestamp()
        while self._request_times and now - self._request_times[0] > 60:
            self._request_times.popleft()

        if len(self._request_times) >= MAX_RPM:
            logger.warning("Límite por minuto alcanzado (%d RPM). Usando fallback.", MAX_RPM)
            return False

        return True

    def _record_request(self):
        now = datetime.now().timestamp()
        self._request_times.append(now)
        self._daily_count += 1
        self._save_used_words()

    # ── API pública ─────────────────────────────────────────────

    async def get_word_and_hint(self, category: str = "todas") -> tuple[str, str]:
        """
        Obtiene una palabra secreta y pista del impostor usando Gemini AI.
        Si Gemini no está configurado o falla, usa word_manager como fallback.
        """
        if not self._configured:
            return word_manager.get_random_word(category)

        async with self._lock:
            if not self._can_make_request():
                return word_manager.get_random_word(category)

            try:
                result = await self._call_gemini(category)
                if result:
                    self._record_request()
                    logger.info(
                        "Gemini generó: palabra='%s', pista='%s'. Consultas hoy: %d/%d.",
                        result[0], result[1], self._daily_count, MAX_RPD
                    )
                    return result
            except Exception as e:
                logger.error("Error en llamada a Gemini: %s. Usando fallback.", e)

        return word_manager.get_random_word(category)

    def get_stats(self) -> dict:
        """Retorna estadísticas de uso de la API."""
        self._check_daily_reset()
        now = datetime.now().timestamp()
        recent = sum(1 for t in self._request_times if now - t <= 60)
        return {
            "daily_count": self._daily_count,
            "daily_limit": MAX_RPD,
            "rpm_count": recent,
            "rpm_limit": MAX_RPM,
            "used_words_count": len(self._used_words),
            "configured": self._configured,
        }

    # ── Llamada a Gemini ────────────────────────────────────────

    async def _call_gemini(self, category: str) -> tuple[str, str] | None:
        """Llama a la API de Gemini y parsea la respuesta."""
        used_list = (
            ", ".join(list(self._used_words)[-100:])
            if self._used_words
            else "ninguna"
        )

        category_hint = ""
        if category != "todas":
            CATEGORY_NAMES = {
                "animales": "animales",
                "comida": "comida y bebida",
                "lugares": "lugares y geografía",
                "objetos": "objetos cotidianos",
                "profesiones": "profesiones y oficios",
                "deportes": "deportes y actividades físicas",
                "tecnologia": "tecnología y dispositivos",
                "peliculas": "películas y entretenimiento",
            }
            cat_display = CATEGORY_NAMES.get(category, category)
            category_hint = f'\n- La categoría debe ser: {cat_display}.'

        prompt = f"""Eres un generador de palabras para el juego de mesa "El Impostor" en español.

Genera UNA palabra secreta y UNA pista vaga para el impostor con estas reglas:
- Palabra secreta: un sustantivo concreto y conocido.
- Pista del impostor: 1 a 3 palabras MUY VAGAS que insinúan la palabra sin revelarla.
- La pista NO debe contener la palabra ni sinónimos directos.
- Dificultad media. Apropiada para todo público.{category_hint}
- EVITA estas palabras ya usadas: {used_list}

Responde EXACTAMENTE en este formato (dos líneas, sin nada más):
PALABRA: <la palabra>
PISTA: <la pista>"""

        response = await self._client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.9,
                max_output_tokens=200,
            ),
        )

        if not response.text:
            logger.error("Gemini devolvió respuesta vacía.")
            return None

        text = response.text.strip()
        logger.debug("Respuesta cruda de Gemini: %r", text)

        # Parsear formato "PALABRA: x\nPISTA: y"
        palabra = ""
        pista = ""
        for line in text.splitlines():
            line = line.strip()
            if line.upper().startswith("PALABRA:"):
                palabra = line.split(":", 1)[1].strip().lower()
            elif line.upper().startswith("PISTA:"):
                pista = line.split(":", 1)[1].strip().lower()

        if not palabra or not pista:
            logger.error("Respuesta de Gemini no tiene formato esperado: %r", text)
            return None

        if not palabra or not pista:
            logger.error("Gemini devolvió palabra o pista vacía: %s", data)
            return None

        if palabra in self._used_words:
            logger.warning("Gemini repitió palabra '%s'. Usando fallback.", palabra)
            return None

        self._used_words.add(palabra)
        return palabra, pista


# Instancia global
gemini_manager = GeminiManager()
