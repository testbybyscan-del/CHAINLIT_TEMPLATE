# chat_handlers.py
# @Bybyscan / Версия 12.06.2026
import logging
import chainlit as cl
import os
from .config import (
    AUTO_CLEAR_ON_FILE,
    ASSISTANT_ROLE,
    MAX_FILE_TEXT_LENGTH,
    NUM_PREDICT,
    SUPPORTED_AUDIO_EXTENSIONS
)
from .role_manager import get_system_prompt
from .ollama_client import OllamaClient
from .file_processor import extract_text_from_file
from .ntfy_notifier import send_ntfy_notification   # <-- импорт

logger = logging.getLogger(__name__)

def is_audio_or_video_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    audio_exts = [e.strip() for e in SUPPORTED_AUDIO_EXTENSIONS.split(',')]
    return ext in audio_exts

async def start_chat_handler():
    """Инициализация сессии при старте чата"""
    system_prompt = get_system_prompt(ASSISTANT_ROLE)
    cl.user_session.set("history", [{"role": "system", "content": system_prompt}])
    cl.user_session.set("role", ASSISTANT_ROLE)

    # ИСПРАВЛЕНО: единая f-строка с тройными кавычками
    msg = f"""ПЕРВЫЙ ДЕПЛОЙ: 10.02.2026 !!! Версия 0.0.4 - 12.06.2026 - РЕЖИМ РАЗРАБОТКИ !!!
разработчик: @Bybyscan

Здравствуйте! Я - **{ASSISTANT_ROLE}**. Задайте вопрос или поставьте задачу!

💡 **Команды:**
• `/role новая_роль` – сменить роль
• `/clear` – очистить историю диалога

📂 **Файлы:** Загрузите PDF, DOCX, TXT, изображение (PNG, JPG),
**аудио (MP3, WAV, OGG, M4A, FLAC) или видео (MP4, AVI, MOV, MKV)**.
Аудиодорожка будет автоматически извлечена и распознана через Whisper API.
Уточните задачу распознавания в сообщении!
по умолчанию обработка происходит в соответствии с РОЛЬЮ!"""
    await cl.Message(content=msg).send()

async def handle_message(message: cl.Message, ollama_client: OllamaClient):
    # --- Команда /clear ---
    cmd = message.content.strip()
    if cmd == "/clear":
        role = cl.user_session.get("role", ASSISTANT_ROLE)
        system_prompt = get_system_prompt(role)
        cl.user_session.set("history", [{"role": "system", "content": system_prompt}])
        await cl.Message(content="✅ История диалога очищена.").send()
        logger.info("Пользователь очистил историю")
        await send_ntfy_notification(
            message=f"Chat history cleared by user {cl.user_session.get('user', {}).identifier}",
            title="Chainlit: history cleared",
            priority="default"
        )
        return

    # --- Команда /role ---
    if cmd.startswith("/role "):
        new_role = cmd.split(maxsplit=1)[1].strip()
        new_prompt = get_system_prompt(new_role)
        if not new_prompt:
            await cl.Message(content=f"❌ Роль '{new_role}' не найдена.").send()
            return
        history = cl.user_session.get("history")
        if history and history[0]["role"] == "system":
            history[0]["content"] = new_prompt
        else:
            history.insert(0, {"role": "system", "content": new_prompt})
        cl.user_session.set("history", history)
        cl.user_session.set("role", new_role)
        await cl.Message(content=f"✅ Роль изменена на **{new_role}**.").send()
        logger.info(f"Роль изменена на {new_role}")
        await send_ntfy_notification(
            message=f"Role changed to '{new_role}' by user {cl.user_session.get('user', {}).identifier}",
            title="Chainlit: role changed",
            priority="default"
        )
        return

    # --- Автоочистка при новом файле ---
    has_file = message.elements and len(message.elements) > 0
    current_history = cl.user_session.get("history")
    if AUTO_CLEAR_ON_FILE and has_file and len(current_history) > 1:
        logger.info("Новый файл → очистка истории")
        role = cl.user_session.get("role", ASSISTANT_ROLE)
        system_prompt = get_system_prompt(role)
        cl.user_session.set("history", [{"role": "system", "content": system_prompt}])
        await cl.Message(content="🔄 Автоочистка истории (чтобы не смешивать разные файлы).").send()
        current_history = cl.user_session.get("history")

    # --- Индикация обработки аудио/видео ---
    audio_video_files = []
    status_msg = None
    if has_file:
        audio_video_files = [elem for elem in message.elements if is_audio_or_video_file(elem.name)]
        if audio_video_files:
            status_msg = await cl.Message(
                content="🎤 Обнаружен аудио/видео файл. Извлекаю речь и отправляю на распознавание...\nЭто может занять до минуты."
            ).send()
            # Уведомление о начале обработки аудио
            await send_ntfy_notification(
                message=f"Audio/video file detected: {audio_video_files[0].name}",
                title="Chainlit: audio processing started",
                priority="default"
            )

    # --- Извлечение содержимого файлов ---
    files_content = []
    if has_file:
        logger.info(f"Обработка {len(message.elements)} файлов")
        for elem in message.elements:
            if hasattr(elem, 'path') and os.path.exists(elem.path):
                try:
                    text = await extract_text_from_file(elem.path, elem.name, ollama_client)
                    files_content.append(f"Файл: {elem.name}\n{text}")
                    logger.info(f"Файл {elem.name} обработан, длина текста: {len(text)} символов")
                except Exception as e:
                    error_text = f"Ошибка обработки файла {elem.name}: {e}"
                    files_content.append(error_text)
                    logger.error(error_text)
                    await send_ntfy_notification(
                        message=f"File processing error: {elem.name} - {str(e)[:200]}",
                        title="Chainlit: file error",
                        priority="high"
                    )
            else:
                files_content.append(f"Файл: {elem.name} (не удалось прочитать)")

    if audio_video_files and status_msg:
        await status_msg.remove()
        # Уведомление о завершении обработки аудио
        await send_ntfy_notification(
            message=f"Audio processing finished for {audio_video_files[0].name}",
            title="Chainlit: audio processed",
            priority="default"
        )

    user_content = message.content.strip()
    history = cl.user_session.get("history")

    # --- Сохраняем пользовательское сообщение в историю ---
    if user_content:
        history.append({"role": "user", "content": user_content})
    elif files_content:
        history.append({"role": "user", "content": "[Загружен файл для анализа]"})

    # --- Формируем сообщения для API, подставляя содержимое файлов ---
    messages_for_api = history.copy()
    if files_content:
        combined_files = "\n\n---\n\n".join(files_content)
        if len(combined_files) > MAX_FILE_TEXT_LENGTH * 2:
            combined_files = combined_files[:MAX_FILE_TEXT_LENGTH * 2] + "\n[текст обрезан]"
        if user_content:
            temp_message = f"{user_content}\n\nСодержимое загруженных файлов:\n{combined_files}"
        else:
            temp_message = f"Пользователь загрузил файл(ы):\n{combined_files}\n\nПроанализируй содержимое и дай ответ."
        if messages_for_api and messages_for_api[-1]["role"] == "user":
            messages_for_api[-1]["content"] = temp_message
        else:
            messages_for_api.append({"role": "user", "content": temp_message})

    # --- Отправка запроса к Ollama ---
    msg = cl.Message(content="")
    await msg.send()
    logger.info("Начало генерации ответа от Ollama")

    full_response = ""
    try:
        async for token in ollama_client.chat_stream(messages_for_api):
            await msg.stream_token(token)
            full_response += token
    except Exception as e:
        error_msg = f"\n[Ошибка: {e}]"
        await msg.stream_token(error_msg)
        full_response = error_msg
        logger.error(f"Ошибка при генерации: {e}", exc_info=True)
        await send_ntfy_notification(
            message=f"Ollama generation error: {str(e)[:300]}",
            title="Chainlit: LLM error",
            priority="high"
        )

    # --- Логирование длины ответа ---
    logger.info(f"Итоговый ответ: длина = {len(full_response)} символов")
    estimated_tokens = len(full_response) // 4
    logger.info(f"Оценочное число токенов: {estimated_tokens} (лимит NUM_PREDICT={NUM_PREDICT})")
    if estimated_tokens >= NUM_PREDICT * 0.9:
        logger.warning(f"*** ВОЗМОЖНА ОБРЕЗКА ОТВЕТА: {estimated_tokens} >= 90% лимита {NUM_PREDICT} ***")
        await send_ntfy_notification(
            message=f"Response may be truncated: {estimated_tokens} tokens > 90% of limit {NUM_PREDICT}",
            title="Chainlit: token limit warning",
            priority="high"
        )

    if full_response and not full_response.startswith("[Ошибка"):
        history.append({"role": "assistant", "content": full_response})
        logger.info("Ответ сохранён в историю")
    else:
        logger.warning("Ответ не сохранён в историю из-за ошибки или пустого ответа")

    # ИСПРАВЛЕНО: удалён лишний комментарий и тире после строки
    cl.user_session.set("history", history)
