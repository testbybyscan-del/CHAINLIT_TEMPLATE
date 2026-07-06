import os
from dotenv import load_dotenv

load_dotenv()

# Ollama
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "akdengi/saiga-llama3-8b")
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/chat")
MULTIMODAL_IMAGE_MODEL = os.getenv("MULTIMODAL_IMAGE_MODEL", "llava:13b")

# Генерация ответа
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
NUM_CTX = int(os.getenv("NUM_CTX", "4096"))
NUM_PREDICT = int(os.getenv("NUM_PREDICT", "4096"))

# Роли
ASSISTANT_ROLE = os.getenv("ASSISTANT_ROLE", "default")
ROLES_FILE = os.getenv("ROLES_FILE", "roles.json")
SYSTEM_PROMPT_OVERRIDE = os.getenv("SYSTEM_PROMPT")

# Файлы
MAX_FILE_TEXT_LENGTH = int(os.getenv("MAX_FILE_TEXT_LENGTH", "2500"))
AUTO_CLEAR_ON_FILE = os.getenv("AUTO_CLEAR_ON_FILE", "true").lower() == "true"

# Таймауты
TIMEOUT_TOTAL = int(os.getenv("TIMEOUT_TOTAL", "300"))
TIMEOUT_SOCK_READ = int(os.getenv("TIMEOUT_SOCK_READ", "150"))

# OCR и мультимодальность
OCR_LANGUAGE = os.getenv("OCR_LANGUAGE", "rus+eng")
ENABLE_IMAGE_DESCRIPTION = os.getenv("ENABLE_IMAGE_DESCRIPTION", "true").lower() == "true"

# ========== НОВЫЙ БЛОК: Аудио/видео транскрипция ==========
AUDIO_TRANSCRIBER_API_URL = os.getenv("AUDIO_TRANSCRIBER_API_URL", "http://<localhost>:<port>/api/v1/transcribe") # УКАЖИТЕ ВАШ URL
AUDIO_TRANSCRIBER_BATCH_URL = os.getenv("AUDIO_TRANSCRIBER_BATCH_URL", "http://<localhost>:<port>/api/v1/transcribe/batch") # УКАЖИТЕ ВАШ URL
AUDIO_LANGUAGE = os.getenv("AUDIO_LANGUAGE", "ru")
AUDIO_PROCESS_AUDIO = os.getenv("AUDIO_PROCESS_AUDIO", "true").lower() == "true"
SUPPORTED_AUDIO_EXTENSIONS = os.getenv("SUPPORTED_AUDIO_EXTENSIONS", ".mp3,.wav,.m4a,.ogg,.flac,.webm,.mp4,.avi,.mov,.mkv")
AUDIO_MAX_FILE_SIZE_MB = int(os.getenv("AUDIO_MAX_FILE_SIZE_MB", "100"))

# Если в системе есть ffmpeg, можно извлекать аудио из видео
FFMPEG_AVAILABLE = os.system("ffmpeg -version > /dev/null 2>&1") == 0

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app_user:strong_password_here@db:5432/chainlit_db")
