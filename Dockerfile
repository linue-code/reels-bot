# Базовый образ Python 3.11
FROM python:3.11-slim

# Установка системных зависимостей (ffmpeg обязателен для yt-dlp, git для авто-обновления)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --global --add safe.directory '*'


# Создаем рабочую директорию
WORKDIR /app

# Отключаем буферизацию вывода Python и создание .pyc файлов
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Копируем список зависимостей и устанавливаем
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Создаем структуру папок
RUN mkdir -p /app/data /app/downloads /app/credentials

# Копируем исходный код бота
COPY bot/ /app/bot/

# Запуск бота
CMD ["python", "-m", "bot.main"]
