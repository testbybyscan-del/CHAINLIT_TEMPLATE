# app.py
# @Bybyscan 2026
import chainlit as cl
import logging
import uuid
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from modules.config import ASSISTANT_ROLE, OLLAMA_MODEL
from modules.ollama_client import OllamaClient
from modules.chat_handlers import start_chat_handler, handle_message
from modules.db_history import HistorySaver
from modules.ntfy_notifier import send_ntfy_notification   # импорт общей функции

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальные объекты
ollama_client = OllamaClient()
history_saver = HistorySaver()

# ============================================================
#  АУТЕНТИФИКАЦИЯ
# ============================================================
@cl.password_auth_callback
def auth_callback(username: str, password: str):
    """Проверка учётных данных (синхронная, без уведомлений)."""
    if username == "admin" and password == "123":
        return cl.User(identifier=username, metadata={"role": "admin"})
    return None

# ============================================================
#  ПРИВЕДЕНИЕ ТИПА ШАГА К ВАЛИДНОМУ ENUM В БД
# ============================================================
def _normalize_step_type(step_type: str) -> str:
    """
    Сопоставляет внутренние типы ('user', 'assistant') с реальными значениями
    в колонке type таблицы Step (enum StepType в БД).
    """
    mapping = {
        "user": "user_message",
        "assistant": "assistant_message",
    }
    return mapping.get(step_type.lower(), step_type.lower())

# ============================================================
#  ИНИЦИАЛИЗАЦИЯ ЧАТА
# ============================================================
@cl.on_chat_start
async def start():
    """Вызывается при старте нового чата."""
    logger.info(f"Инициализация чата. Модель: {OLLAMA_MODEL}, роль: {ASSISTANT_ROLE}")

    try:
        await history_saver.init_pool()
    except Exception as e:
        logger.exception("Ошибка инициализации пула БД")
        await send_ntfy_notification(
            f"Failed to init DB pool: {str(e)[:200]}",
            title="Chainlit DB Error",
            priority="high"
        )
        await cl.Message(
            content="❌ Ошибка подключения к базе данных. Обратитесь к администратору."
        ).send()
        return

    user = cl.user_session.get("user")
    if user and hasattr(user, "identifier"):
        identifier = user.identifier
    else:
        identifier = "dev_user"
        logger.warning("Аутентификация не настроена, используется dev_user")

    try:
        user_id = await history_saver.get_or_create_user(identifier)
    except Exception as e:
        logger.exception("Ошибка создания/получения пользователя")
        await send_ntfy_notification(
            f"User error for {identifier}: {str(e)[:200]}",
            title="Chainlit User Error",
            priority="high"
        )
        await cl.Message(content="❌ Ошибка идентификации пользователя.").send()
        return

    thread_id = cl.context.session.thread_id
    if not thread_id:
        thread_id = str(uuid.uuid4())
        logger.warning(f"thread_id не найден, создан новый: {thread_id}")

    try:
        await history_saver.get_or_create_thread(thread_id, user_id, name="Новый чат")
    except Exception as e:
        logger.exception("Ошибка создания треда")
        await send_ntfy_notification(
            f"Thread creation error {thread_id}: {str(e)[:200]}",
            title="Chainlit Thread Error",
            priority="high"
        )
        await cl.Message(content="❌ Ошибка создания чата.").send()
        return

    cl.user_session.set("thread_id", thread_id)
    cl.user_session.set("user_id", user_id)

    await start_chat_handler()

    logger.info(f"Чат инициализирован: пользователь {identifier} (id={user_id}), тред {thread_id}")

    # Отправляем уведомление о новом чате
    await send_ntfy_notification(
        message=f"New chat: user {identifier}, thread {thread_id[:8]}",
        title="Chainlit: chat started",
        priority="default"
    )

# ============================================================
#  ОБРАБОТКА СООБЩЕНИЙ
# ============================================================
@cl.on_message
async def main(message: cl.Message):
    """Обрабатывает каждое сообщение пользователя с обработкой ошибок."""
    logger.info(f"Получено сообщение: {message.content[:80]}...")

    thread_id = cl.user_session.get("thread_id")
    if not thread_id:
        thread_id = cl.context.session.thread_id
        if not thread_id:
            logger.error("Нет thread_id ни в сессии, ни в контексте")
            await send_ntfy_notification(
                "No thread_id in session or context",
                title="Chainlit Internal Error",
                priority="high"
            )
            await cl.Message(content="❌ Ошибка: потеря контекста чата. Обновите страницу.").send()
            return
        cl.user_session.set("thread_id", thread_id)

    # Сохраняем сообщение пользователя
    step_user_id = f"step_{uuid.uuid4()}"
    try:
        await history_saver.save_step(
            thread_id=thread_id,
            step_id=step_user_id,
            name="user_message",
            type=_normalize_step_type("user"),
            content=message.content,
            parent_id=None
        )
    except Exception as e:
        logger.exception("Ошибка сохранения сообщения пользователя в БД")
        await send_ntfy_notification(
            f"DB save user step error: {str(e)[:200]}",
            title="Chainlit DB Save Error",
            priority="high"
        )
        await cl.Message(content="⚠️ Сообщение сохранено, но произошла внутренняя ошибка.").send()

    # Обрабатываем сообщение через основную логику с защитой от исключений
    try:
        await handle_message(message, ollama_client)
    except Exception as e:
        logger.exception("Критическая ошибка в handle_message")
        await send_ntfy_notification(
            f"Error in handle_message: {str(e)[:300]}",
            title="Chainlit Processing Error",
            priority="high"
        )
        await cl.Message(content="❌ Произошла внутренняя ошибка при обработке сообщения. Администратор уведомлён.").send()
        return

    # Извлекаем последний ответ ассистента
    history = cl.user_session.get("history", [])
    last_assistant_msg = None
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            last_assistant_msg = msg.get("content")
            break

    if last_assistant_msg:
        step_assistant_id = f"step_{uuid.uuid4()}"
        try:
            await history_saver.save_step(
                thread_id=thread_id,
                step_id=step_assistant_id,
                name="assistant_response",
                type=_normalize_step_type("assistant"),
                content=last_assistant_msg,
                parent_id=step_user_id
            )
            logger.info("Ответ ассистента сохранён в БД")
        except Exception as e:
            logger.exception("Ошибка сохранения ответа ассистента")
            await send_ntfy_notification(
                f"DB save assistant step error: {str(e)[:200]}",
                title="Chainlit DB Save Error",
                priority="high"
            )
    else:
        logger.warning("Не удалось найти ответ ассистента в истории сессии")

# ============================================================
#  ЗАВЕРШЕНИЕ ЧАТА
# ============================================================
@cl.on_chat_end
async def on_chat_end(*args, **kwargs):
    """Универсальный обработчик завершения чата."""
    user = None
    if args and len(args) > 0:
        user = args[0]
    if not user and 'user' in kwargs:
        user = kwargs['user']
    if not user:
        user = cl.user_session.get("user")

    identifier = user.identifier if user else "unknown"
    logger.info(f"Чат завершён для пользователя {identifier}")

    await send_ntfy_notification(
        message=f"Chat ended for {identifier}",
        title="Chainlit: chat ended",
        priority="default"
    )

    await history_saver.close()
