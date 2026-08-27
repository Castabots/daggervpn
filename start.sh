#!/bin/bash

echo "🚀 DaggerVPN Bot - Быстрый старт"
echo "================================"
echo ""

# Проверка, что скрипт запущен из правильной директории
if [ ! -f "app/main.py" ]; then
    echo "❌ Ошибка: запустите скрипт из директории /root/daggervpn"
    exit 1
fi

# Шаг 1: Сброс пароля базы данных
echo "📦 Шаг 1: Настройка базы данных..."
su - postgres -c "psql -c \"ALTER USER daggervpn WITH PASSWORD 'changeme';\"" 2>/dev/null

if [ $? -ne 0 ]; then
    echo "⚠️  Не удалось сбросить пароль. Пытаюсь создать базу заново..."
    su - postgres -c "psql" << 'EOF'
DROP DATABASE IF EXISTS daggervpn;
DROP USER IF EXISTS daggervpn;
CREATE USER daggervpn WITH PASSWORD 'changeme';
CREATE DATABASE daggervpn OWNER daggervpn;
GRANT ALL PRIVILEGES ON DATABASE daggervpn TO daggervpn;
EOF
fi

echo "✅ База данных настроена"
echo ""

# Шаг 2: Установка зависимостей
echo "📦 Шаг 2: Установка зависимостей..."
pip install -q -r requirements.txt
echo "✅ Зависимости установлены"
echo ""

# Шаг 3: Миграции
echo "📦 Шаг 3: Запуск миграций..."
alembic upgrade head
echo "✅ Миграции выполнены"
echo ""

# Шаг 4: Проверка подключения
echo "📦 Шаг 4: Проверка подключения к базе данных..."
python test_db_connection.py
if [ $? -ne 0 ]; then
    echo "❌ Не удалось подключиться к базе данных"
    echo ""
    echo "Выполните вручную:"
    echo "su - postgres -c \"psql -c \\\"ALTER USER daggervpn WITH PASSWORD 'changeme';\\\"\""
    exit 1
fi
echo ""

# Шаг 5: Остановка старых процессов
echo "📦 Шаг 5: Остановка старых процессов..."
pkill -f "python -m app.main" 2>/dev/null
pkill -f "python -m app.webhook" 2>/dev/null
sleep 2
echo "✅ Старые процессы остановлены"
echo ""

# Шаг 6: Запуск бота
echo "📦 Шаг 6: Запуск бота..."
screen -S bot -dm bash -c "cd /root/daggervpn && python -m app.main"
sleep 2
echo "✅ Бот запущен (screen: bot)"
echo ""

# Шаг 7: Запуск webhook
echo "📦 Шаг 7: Запуск webhook сервера..."
screen -S webhook -dm bash -c "cd /root/daggervpn && python -m app.webhook"
sleep 2
echo "✅ Webhook запущен (screen: webhook)"
echo ""

# Проверка
echo "🔍 Проверка..."
sleep 3

# Проверка webhook
WEBHOOK_STATUS=$(curl -s http://localhost:8000/health 2>/dev/null)
if [ "$WEBHOOK_STATUS" = '{"status":"ok"}' ]; then
    echo "✅ Webhook работает: http://localhost:8000"
else
    echo "⚠️  Webhook не отвечает"
fi

echo ""
echo "================================"
echo "✨ Запуск завершён!"
echo ""
echo "📋 Полезные команды:"
echo "  screen -r bot      # подключиться к боту"
echo "  screen -r webhook  # подключиться к webhook"
echo "  screen -ls         # список screen сессий"
echo ""
echo "  curl http://localhost:8000/health  # проверка webhook"
echo ""
echo "📖 Полная документация: README.md"
echo ""
