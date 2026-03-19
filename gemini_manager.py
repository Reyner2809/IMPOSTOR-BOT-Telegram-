"""Integración con Gemini AI para generación de palabras y pistas."""

import logging
import asyncio
from collections import deque
from datetime import datetime, date

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, UPSTASH_REDIS_URL
from word_manager import word_manager

logger = logging.getLogger(__name__)

MAX_RPM = 15
MAX_RPD = 500
GEMINI_MODEL = "gemini-flash-lite-latest"
REDIS_WORDS_KEY = "impostor_bot:used_words"


class GeminiManager:
    def __init__(self):
        self._configured = False
        self._client = None
        self._redis = None
        self._used_words_memory: set[str] = set()  # fallback si Redis no disponible
        self._request_times: deque = deque()
        self._daily_count = 0
        self._daily_date = date.today()
        self._lock = asyncio.Lock()

        # Configurar Gemini
        if GEMINI_API_KEY and GEMINI_API_KEY != "TU_GEMINI_API_KEY_AQUI":
            try:
                self._client = genai.Client(api_key=GEMINI_API_KEY)
                self._configured = True
                logger.info("Gemini AI configurado con modelo %s.", GEMINI_MODEL)
            except Exception as e:
                logger.error("Error configurando Gemini AI: %s", e)
        else:
            logger.warning("GEMINI_API_KEY no configurada. Se usarán palabras del sistema.")

        # Configurar Redis (Upstash)
        if UPSTASH_REDIS_URL:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(UPSTASH_REDIS_URL, decode_responses=True)
                logger.info("Redis (Upstash) configurado para tracking de palabras usadas.")
            except Exception as e:
                logger.warning("No se pudo inicializar Redis: %s. Tracking en memoria.", e)
        else:
            logger.warning("UPSTASH_REDIS_URL no configurada. Tracking de palabras usadas en memoria (se pierde al reiniciar).")

    # ── Redis helpers ───────────────────────────────────────────

    async def _is_word_used(self, word: str) -> bool:
        if self._redis:
            try:
                return bool(await self._redis.sismember(REDIS_WORDS_KEY, word))
            except Exception as e:
                logger.warning("Redis error (sismember): %s. Consultando memoria.", e)
        return word in self._used_words_memory

    async def _mark_word_used(self, word: str):
        if self._redis:
            try:
                await self._redis.sadd(REDIS_WORDS_KEY, word)
                return
            except Exception as e:
                logger.warning("Redis error (sadd): %s. Guardando en memoria.", e)
        self._used_words_memory.add(word)

    async def _get_used_words_for_prompt(self) -> str:
        if self._redis:
            try:
                members = await self._redis.smembers(REDIS_WORDS_KEY)
                recent = list(members)[-100:]
                return ", ".join(recent) if recent else "ninguna"
            except Exception as e:
                logger.warning("Redis error (smembers): %s.", e)
        recent = list(self._used_words_memory)[-100:]
        return ", ".join(recent) if recent else "ninguna"

    # ── Rate limiting ───────────────────────────────────────────

    def _check_daily_reset(self):
        today = date.today()
        if today != self._daily_date:
            self._daily_date = today
            self._daily_count = 0

    def _can_make_request(self) -> bool:
        self._check_daily_reset()

        if self._daily_count >= MAX_RPD:
            logger.warning("Límite diario alcanzado (%d/%d).", self._daily_count, MAX_RPD)
            return False

        now = datetime.now().timestamp()
        while self._request_times and now - self._request_times[0] > 60:
            self._request_times.popleft()

        if len(self._request_times) >= MAX_RPM:
            logger.warning("Límite por minuto alcanzado (%d RPM).", MAX_RPM)
            return False

        return True

    def _record_request(self):
        self._request_times.append(datetime.now().timestamp())
        self._daily_count += 1

    # ── API pública ─────────────────────────────────────────────

    async def get_word_and_hint(self, category: str = "todas") -> tuple[str, str]:
        """Obtiene palabra y pista. Intenta Gemini primero, fallback al sistema."""
        if not self._configured:
            word, hint = word_manager.get_random_word(category)
            logger.info("[PALABRAS DEL SISTEMA] Gemini no configurado. palabra='%s', pista='%s'.", word, hint)
            return word, hint

        async with self._lock:
            if not self._can_make_request():
                word, hint = word_manager.get_random_word(category)
                logger.warning(
                    "[PALABRAS DEL SISTEMA] Límite de API alcanzado (%d/%d). palabra='%s', pista='%s'.",
                    self._daily_count, MAX_RPD, word, hint
                )
                return word, hint

            try:
                result = await self._call_gemini(category)
                if result:
                    self._record_request()
                    logger.info(
                        "[PALABRAS DE IA] Gemini generó: palabra='%s', pista='%s'. Consultas hoy: %d/%d.",
                        result[0], result[1], self._daily_count, MAX_RPD
                    )
                    return result
                else:
                    word, hint = word_manager.get_random_word(category)
                    logger.warning(
                        "[PALABRAS DEL SISTEMA] Gemini no devolvió resultado válido. palabra='%s', pista='%s'.",
                        word, hint
                    )
                    return word, hint

            except Exception as e:
                word, hint = word_manager.get_random_word(category)
                logger.error(
                    "[PALABRAS DEL SISTEMA] API de Gemini falló: %s — el juego continúa. palabra='%s', pista='%s'.",
                    e, word, hint
                )
                return word, hint

    def get_stats(self) -> dict:
        self._check_daily_reset()
        now = datetime.now().timestamp()
        recent = sum(1 for t in self._request_times if now - t <= 60)
        return {
            "daily_count": self._daily_count,
            "daily_limit": MAX_RPD,
            "rpm_count": recent,
            "rpm_limit": MAX_RPM,
            "configured": self._configured,
            "redis_configured": self._redis is not None,
        }

    # ── Llamada a Gemini ────────────────────────────────────────

    async def _call_gemini(self, category: str) -> tuple[str, str] | None:
        used_str = await self._get_used_words_for_prompt()

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
- EVITA estas palabras ya usadas: {used_str}

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

        if await self._is_word_used(palabra):
            logger.warning("Gemini repitió palabra '%s'. Usando fallback.", palabra)
            return None

        await self._mark_word_used(palabra)
        return palabra, pista


# Instancia global
gemini_manager = GeminiManager()
