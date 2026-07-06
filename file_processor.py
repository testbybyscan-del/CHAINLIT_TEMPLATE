# file_processor.py – финальная версия с принудительной конвертацией аудио в единый формат
# @Bybyscan 2026
import os
import time
import logging
import tempfile
import subprocess
from PIL import Image
import pytesseract
import aiohttp
from .config import (
    MAX_FILE_TEXT_LENGTH, OCR_LANGUAGE, ENABLE_IMAGE_DESCRIPTION,
    MULTIMODAL_IMAGE_MODEL, AUDIO_TRANSCRIBER_API_URL, AUDIO_LANGUAGE,
    AUDIO_PROCESS_AUDIO, SUPPORTED_AUDIO_EXTENSIONS, AUDIO_MAX_FILE_SIZE_MB,
    FFMPEG_AVAILABLE
)
from .ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# Опциональные библиотеки
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None
try:
    from docx import Document
except ImportError:
    Document = None

SUPPORTED_AUDIO_LIST = [ext.strip() for ext in SUPPORTED_AUDIO_EXTENSIONS.split(',')]
logger.info(f"Поддерживаемые аудио/видео расширения: {SUPPORTED_AUDIO_LIST}")

def is_audio_or_video(ext: str) -> bool:
    return ext in SUPPORTED_AUDIO_LIST

async def convert_to_standard_wav(input_path: str) -> str:
    """
    Конвертирует любой аудио/видеофайл в стандартный WAV (16 kHz, mono, PCM).
    Возвращает путь к временному файлу.
    """
    fd, temp_wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    cmd = [
        "ffmpeg", "-i", input_path, "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1", temp_wav, "-y"
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        return temp_wav
    except subprocess.CalledProcessError as e:
        if os.path.exists(temp_wav):
            os.unlink(temp_wav)
        raise RuntimeError(f"Ошибка конвертации в WAV: {e.stderr.decode()}")

async def transcribe_audio_file(file_path: str) -> str:
    """
    Конвертирует файл в стандартный WAV (если нужно) и отправляет в API транскрипции.
    """
    temp_wav = None
    try:
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > AUDIO_MAX_FILE_SIZE_MB:
            return f"[Ошибка: файл превышает {AUDIO_MAX_FILE_SIZE_MB} МБ]"

        ext = os.path.splitext(file_path)[1].lower()
        # Для видео и неподдерживаемых аудиоформатов – конвертируем
        need_conversion = True
        # Если это уже WAV, но неизвестного качества, всё равно лучше сконвертировать для единообразия
        # Однако можно попробовать отправить оригинал, если конвертация не удастся
        if ext == '.wav':
            # Пробуем использовать оригинал, но если API его отвергнет – конвертируем
            need_conversion = False

        if need_conversion:
            if not FFMPEG_AVAILABLE:
                return "[Ошибка: ffmpeg не установлен, не могу конвертировать аудио]"
            logger.info(f"Конвертация файла {file_path} в стандартный WAV...")
            temp_wav = await convert_to_standard_wav(file_path)
            audio_path = temp_wav
            mime_type = 'audio/wav'
        else:
            audio_path = file_path
            mime_type = 'audio/wav'

        # Читаем файл в память
        with open(audio_path, 'rb') as f:
            file_data = f.read()

        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('file', file_data,
                           filename=os.path.basename(audio_path),
                           content_type=mime_type)
            data.add_field('process_audio', str(AUDIO_PROCESS_AUDIO).lower())
            if AUDIO_LANGUAGE and AUDIO_LANGUAGE != 'auto':
                data.add_field('language', AUDIO_LANGUAGE)

            headers = {'Accept': 'application/json'}
            logger.info(f"Отправка запроса к {AUDIO_TRANSCRIBER_API_URL}, "
                        f"размер файла: {len(file_data)} байт, MIME: {mime_type}")
            async with session.post(AUDIO_TRANSCRIBER_API_URL, data=data, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Ошибка транскрипции: HTTP {resp.status} - {error_text}")
                    # Если оригинал не прошёл, а мы его не конвертировали, можно попробовать сконвертировать
                    if not need_conversion and temp_wav is None:
                        logger.info("Пробуем сконвертировать файл и повторить...")
                        return await transcribe_audio_file(file_path)  # рекурсивный вызов с конвертацией
                    return f"[Ошибка API: {resp.status} - {error_text[:100]}]"
                result = await resp.json()
                logger.debug(f"Ответ API: {result}")
                text = (result.get("text") or result.get("transcription") or
                        result.get("result") or result.get("transcribed_text") or "")
                if not text and isinstance(result.get("data"), dict):
                    text = result["data"].get("text", "")
                if not text:
                    logger.warning(f"Неизвестный формат ответа: {result}")
                    return "[API не вернул текст]"
                logger.info(f"Транскрипция успешна, длина текста: {len(text)} символов")
                return text[:MAX_FILE_TEXT_LENGTH]

    except Exception as e:
        logger.error(f"Ошибка транскрипции: {e}", exc_info=True)
        return f"[Ошибка распознавания: {e}]"
    finally:
        if temp_wav and os.path.exists(temp_wav):
            os.unlink(temp_wav)

# ---------- Остальные функции (OCR, изображения, PDF, DOCX, TXT) без изменений ----------
def extract_text_from_image(file_path: str) -> str:
    try:
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang=OCR_LANGUAGE)
        return text[:MAX_FILE_TEXT_LENGTH]
    except Exception as e:
        logger.error(f"OCR ошибка: {e}")
        return "[Ошибка распознавания текста на изображении]"

async def describe_image_multimodal(file_path: str, ollama_client: OllamaClient) -> str:
    import base64
    with open(file_path, "rb") as f:
        img_base64 = base64.b64encode(f.read()).decode()
    payload = {
        "model": MULTIMODAL_IMAGE_MODEL,
        "prompt": "Опиши это изображение подробно на русском языке.",
        "images": [img_base64],
        "stream": False
    }
    try:
        resp = await ollama_client.generate(payload)
        return resp.get("response", "").strip()
    except Exception as e:
        logger.error(f"Мультимодальное описание не удалось: {e}")
        return ""

async def extract_text_from_file(file_path: str, original_filename: str = None, ollama_client: OllamaClient = None) -> str:
    if original_filename:
        ext = os.path.splitext(original_filename)[1].lower()
    else:
        ext = os.path.splitext(file_path)[1].lower()
    logger.info(f"Обработка файла: {file_path} (ориг. имя: {original_filename}, расширение: {ext})")
    start = time.time()

    if is_audio_or_video(ext):
        logger.info("Файл определён как аудио/видео, вызываем транскрипцию")
        text = await transcribe_audio_file(file_path)
        logger.info(f"Транскрипция завершена за {time.time()-start:.2f} сек, длина текста: {len(text)}")
        return text

    if ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']:
        ocr_text = extract_text_from_image(file_path)
        result = f"[OCR распознанный текст]:\n{ocr_text}\n"
        if ENABLE_IMAGE_DESCRIPTION and ollama_client:
            description = await describe_image_multimodal(file_path, ollama_client)
            if description:
                result += f"\n[Описание изображения через LLaVA]:\n{description}\n"
        return result[:MAX_FILE_TEXT_LENGTH]

    if ext == '.pdf':
        if PdfReader is None:
            return "[PDF обработка недоступна: установите pypdf]"
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text += page_text
            if len(text) > MAX_FILE_TEXT_LENGTH:
                text = text[:MAX_FILE_TEXT_LENGTH]
                break
        return text

    if ext == '.docx':
        if Document is None:
            return "[DOCX обработка недоступна: установите python-docx]"
        doc = Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])[:MAX_FILE_TEXT_LENGTH]
        return text

    if ext == '.txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read(MAX_FILE_TEXT_LENGTH)
        return text

    return f"[Неподдерживаемый тип файла: {ext}]"
