# ollama_client.py
import aiohttp
import json
import logging
import os
from .config import (
    OLLAMA_API_URL, TIMEOUT_TOTAL, TIMEOUT_SOCK_READ,
    OLLAMA_MODEL, TEMPERATURE, NUM_CTX, NUM_PREDICT
)

logger = logging.getLogger(__name__)

class OllamaClient:
    def __init__(self):
        self.model = OLLAMA_MODEL
        self.api_url = OLLAMA_API_URL

    async def chat_stream(self, messages, temperature=None):
        if temperature is None:
            temperature = TEMPERATURE

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_ctx": NUM_CTX,
                "num_predict": NUM_PREDICT
            }
        }
        logger.info(f"Запрос к Ollama: model={self.model}, num_predict={NUM_PREDICT}, "
                    f"температура={temperature}, контекст в токенах={NUM_CTX}, "
                    f"длина истории сообщений={len(str(messages))} символов")

        timeout = aiohttp.ClientTimeout(total=TIMEOUT_TOTAL, sock_read=TIMEOUT_SOCK_READ)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.api_url, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Ошибка Ollama: статус {resp.status}, тело: {error_text}")
                    raise Exception(f"Ollama error {resp.status}: {error_text}")

                token_count = 0
                full_response = ""
                async for line in resp.content:
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line.decode())
                        if "message" in chunk and "content" in chunk["message"]:
                            token = chunk["message"]["content"]
                            token_count += 1
                            full_response += token
                            yield token
                        if chunk.get("done"):
                            logger.info(f"Генерация завершена. Всего токенов: {token_count}, "
                                        f"символов в ответе: {len(full_response)}. "
                                        f"Лимит NUM_PREDICT={NUM_PREDICT}")
                            if token_count >= NUM_PREDICT:
                                logger.warning(f"Внимание: достигнут лимит токенов NUM_PREDICT={NUM_PREDICT}, "
                                               f"ответ может быть обрезан моделью. Увеличьте NUM_PREDICT в .env")
                            break
                    except json.JSONDecodeError:
                        logger.debug(f"Ошибка декодирования JSON: {line}")
                        continue

    async def generate(self, payload):
        # Используем переменную окружения OLLAMA_GENERATE_URL, если она задана,
        # иначе стандартный URL для сервиса ollama в Docker-сети
        url = os.getenv("OLLAMA_GENERATE_URL", "http://ollama:11434/api/generate")
        logger.info(f"Мультимодальный запрос к Ollama: {url}")
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Generate error {resp.status}: {error_text}")
                    raise Exception(f"Generate error {resp.status}: {error_text}")
                result = await resp.json()
                logger.info(f"Мультимодальный generate завершён, длина ответа: {len(result.get('response', ''))} символов")
                return result
