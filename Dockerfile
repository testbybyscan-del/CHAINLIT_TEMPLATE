FROM python:3.10-slim-bookworm

WORKDIR /app

# Копируем предварительно скачанные deb-пакеты (если есть)
COPY apt_cache/*.deb /tmp/debs/

# Устанавливаем пакеты из локальных deb-файлов + добавляем ffmpeg и tesseract из репозитория
RUN dpkg -i /tmp/debs/*.deb || true && \
    apt-get update && \
    apt-get install -f -y --no-install-recommends && \
    # Устанавливаем ffmpeg и Tesseract (русский язык)
    apt-get install -y --no-install-recommends ffmpeg tesseract-ocr tesseract-ocr-rus && \
    rm -rf /tmp/debs /var/lib/apt/lists/*

# Копируем кэш pip
COPY pip_cache /tmp/pip_cache
COPY requirements.txt .

# Устанавливаем Python-зависимости из локального кэша
RUN pip install --no-cache-dir --no-index --find-links=/tmp/pip_cache -r requirements.txt && \
    rm -rf /tmp/pip_cache

# Копируем остальной код приложения
COPY . .

EXPOSE 8090

# Запускаем Chainlit с правильным файлом и портом
CMD ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "8090"]
