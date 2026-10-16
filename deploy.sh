#!/usr/bin/env bash
set -e

echo "=== 🚀 Подготовка и деплой Reels Bot ==="

# 1. Проверяем наличие Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Ошибка: Docker не установлен. Пожалуйста, установите Docker и Docker Compose."
    exit 1
fi

# 2. Создаем необходимые директории на хосте
mkdir -p data downloads credentials

# 3. Проверяем конфигурацию .env
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "⚠️ Файл .env не найден! Создаю из .env.example..."
        cp .env.example .env
        echo "❗ Пожалуйста, отредактируйте .env (nano .env) и запустите скрипт снова."
        exit 1
    else
        echo "❌ Ошибка: Отсутствует .env и .env.example"
        exit 1
    fi
fi

# 4. Проверяем наличие JSON-ключа для Google Drive
if [ ! -f credentials/service_account.json ]; then
    echo "⚠️ Внимание: credentials/service_account.json не найден!"
    echo "   Положите ваш JSON-ключ сервисного аккаунта в credentials/service_account.json"
fi

# 5. Сборка и запуск контейнера
echo "🔨 Собираем Docker-образ и запускаем бота в фоне..."
docker compose down || true
docker compose up -d --build

echo ""
echo "✅ Бот успешно запущен!"
echo "📜 Посмотреть логи: docker compose logs -f"
echo "🛑 Остановить бота: docker compose down"
