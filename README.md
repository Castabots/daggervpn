# 🚀 DaggerVPN Bot - Полная инструкция по установке и исправлению

## ⚠️ ВАЖНО: Исправление ошибки базы данных

### Проблема
```
password authentication failed for user "daggervpn"
```

### Решение

**Шаг 1: Сбросьте пароль базы данных**

Выполните эту команду на сервере:

```bash
su - postgres -c "psql -c \"ALTER USER daggervpn WITH PASSWORD 'changeme';\""
```

Или войдите в psql:

```bash
su - postgres
psql
```

В psql выполните:
```sql
ALTER USER daggervpn WITH PASSWORD 'changeme';
\q
```

**Шаг 2: Убедитесь, что в .env правильный пароль**

Файл `.env` должен содержать:
```env
DATABASE_URL=postgresql+asyncpg://daggervpn:changeme@localhost:5432/daggervpn
```

**Шаг 3: Если база не существует, создайте её**

```bash
su - postgres -c "psql" << EOF
CREATE USER daggervpn WITH PASSWORD 'changeme';
CREATE DATABASE daggervpn OWNER daggervpn;
GRANT ALL PRIVILEGES ON DATABASE daggervpn TO daggervpn;
\q
EOF
```

**Шаг 4: Запустите миграции**

```bash
cd /root/daggervpn
alembic upgrade head
```

---

## 📋 Настройка .env файла

### Обязательные параметры

```env
# Telegram Bot
BOT_TOKEN=8938241930:AAGin5bmqhscPr5M0phN8BGBAbvS2PB8VvA
ADMIN_IDS=8108649608
SUPPORT_URL=https://t.me/daggerVPN_support
BOT_USERNAME=daggerVPN_bot

# Database
DATABASE_URL=postgresql+asyncpg://daggervpn:changeme@localhost:5432/daggervpn

# Redis
REDIS_URL=redis://localhost:6379/0

# Remnawave API
REMNAWAVE_API_URL=https://panel.daggervpn.ru/api
REMNAWAVE_API_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1dWlkIjoiOGExZDZlNDEtYjNlYi00YjQ1LThhZjgtMjFmYmUwNmE1MGY5IiwidXNlcm5hbWUiOm51bGwsInJvbGUiOiJBUEkiLCJpYXQiOjE3ODY3OTgzOTEsImV4cCI6MjY1MDcxMTk5MX0.wHHDqvqizbuQmMj0FptIuqaaSyoaLiMb0rRhc2FK0sM
REMNAWAVE_PANEL_COOKIE=

# Payment Provider (Platega)
PAYMENT_PROVIDER=platega
PLATEGA_API_URL=https://app.platega.io/api/v1
PLATEGA_MERCHANT_ID=ПОЛУЧИТЕ_В_ЛИЧНОМ_КАБИНЕТЕ_PLATEGA
PLATEGA_SECRET=ПОЛУЧИТЕ_В_ЛИЧНОМ_КАБИНЕТЕ_PLATEGA

# App
LOG_LEVEL=INFO
```

### Где взять данные Platega?

1. Зарегистрируйтесь на https://platega.io/
2. Войдите в личный кабинет
3. Перейдите в "Настройки" → "API"
4. Скопируйте **Merchant ID** и **Secret Key**
5. Вставьте их в `.env`

---

## 🔧 Установка и запуск

### 1. Установите зависимости

```bash
cd /root/daggervpn
pip install -r requirements.txt
```

### 2. Настройте базу данных

```bash
# Сбросьте пароль (если нужно)
su - postgres -c "psql -c \"ALTER USER daggervpn WITH PASSWORD 'changeme';\""

# Или создайте базу заново
su - postgres -c "psql" << 'EOF'
DROP DATABASE IF EXISTS daggervpn;
DROP USER IF EXISTS daggervpn;
CREATE USER daggervpn WITH PASSWORD 'changeme';
CREATE DATABASE daggervpn OWNER daggervpn;
GRANT ALL PRIVILEGES ON DATABASE daggervpn TO daggervpn;
EOF

# Запустите миграции
alembic upgrade head
```

### 3. Проверьте подключение

```bash
python test_db_connection.py
```

Если видите `✅ Успешное подключение` - всё работает!

### 4. Запустите бота

```bash
python -m app.main
```

### 5. Запустите webhook сервер (в отдельном терминале)

```bash
python -m app.webhook
```

Или используйте screen/tmux:

```bash
# Терминал 1: Бот
screen -S bot
python -m app.main
# Нажмите Ctrl+A, затем D для выхода

# Терминал 2: Webhook
screen -S webhook
python -m app.webhook
# Нажмите Ctrl+A, затем D для выхода

# Вернуться в screen:
screen -r bot      # вернуться к боту
screen -r webhook  # вернуться к webhook
```

---

## 🆕 Что нового

### 1. ✅ Ссылка на ключ кликабельная
- Кнопка "🔗 Открыть подписку" в карточке ключа
- Кнопка "📋 Скопировать ключ"

### 2. ✅ Напоминания приходят за 3 дня
- Раньше: за 7, 3 и 1 день
- Теперь: за 3 и 1 день

### 3. ✅ Админка для управления ключами
- Раздел "🔑 Все ключи" в админке
- Просмотр всех ключей с деталями
- **Кнопка "➕ Добавить дни"** - продление подписки
- Синхронизация с панелью Remnawave

**Как использовать:**
1. Админка → "🔑 Все ключи"
2. Выбрать ключ
3. "➕ Добавить дни"
4. Ввести количество дней
5. Готово!

### 4. ✅ Интеграция Platega
- Создание платежей через Platega
- Webhook для автоматической выдачи ключей
- Поддержка промокодов и скидок

---

## 🌐 Настройка webhook для Platega

### Вариант 1: Через nginx (рекомендуется)

Создайте конфигурацию nginx:

```nginx
server {
    listen 80;
    server_name ваш-домен.com;

    location /webhook/ {
        proxy_pass http://localhost:8000/webhook/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Активируйте и перезапустите nginx:

```bash
ln -s /etc/nginx/sites-available/webhook /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

### Вариант 2: Через ngrok (для тестирования)

```bash
ngrok http 8000
```

Используйте полученный URL в настройках Platega.

### Настройка в Platega

1. Войдите в личный кабинет Platega
2. Перейдите в "Настройки" → "Webhooks"
3. Добавьте URL: `https://ваш-домен.com/webhook/platega`
4. Сохраните

---

## 🐳 Запуск через Docker

### 1. Остановите текущие процессы

```bash
pkill -f "python -m app.main"
pkill -f "python -m app.webhook"
```

### 2. Запустите через Docker

```bash
docker compose down
docker compose up -d
```

### 3. Проверьте логи

```bash
docker compose logs -f bot
docker compose logs -f webhook
```

---

## 🔍 Проверка работы

### Проверка бота

```bash
# Логи бота
tail -f /root/daggervpn/logs/bot.log

# Или если в screen
screen -r bot
```

### Проверка webhook

```bash
# Проверка доступности
curl http://localhost:8000/health

# Должен вернуть: {"status":"ok"}
```

### Проверка базы данных

```bash
python test_db_connection.py
```

---

## ❗ Частые проблемы

### 1. Ошибка подключения к базе данных

**Проблема:**
```
password authentication failed for user "daggervpn"
```

**Решение:**
```bash
su - postgres -c "psql -c \"ALTER USER daggervpn WITH PASSWORD 'changeme';\""
```

### 2. Модуль не найден

**Проблема:**
```
ModuleNotFoundError: No module named 'fastapi'
```

**Решение:**
```bash
pip install -r requirements.txt
```

### 3. Порт 8000 занят

**Проблема:**
```
Address already in use
```

**Решение:**
```bash
lsof -ti:8000 | xargs kill -9
```

### 4. Remnawave API не работает

**Проблема:**
```
Server disconnected without sending a response
```

**Решение:**
Проверьте, нужен ли `REMNAWAVE_PANEL_COOKIE`:

```bash
curl -H "Authorization: Bearer ВАШ_ТОКЕН" \
     https://panel.daggervpn.ru/api/internal-squads
```

Если пустой ответ - нужен cookie от администратора панели.

---

## 📁 Структура файлов

```
/root/daggervpn/
├── app/
│   ├── bot/
│   │   ├── handlers/
│   │   │   ├── admin.py          # ✨ Управление ключами
│   │   │   ├── purchase.py       # ✨ Интеграция Platega
│   │   │   └── ...
│   │   └── keyboards/
│   │       └── inline.py         # ✨ Новые клавиатуры
│   ├── services/
│   │   ├── platega_provider.py   # 🆕 Провайдер Platega
│   │   ├── payment_service.py    # ✨ Обновлён
│   │   ├── notification_service.py # ✨ Напоминания за 3 дня
│   │   └── remnawave_service.py  # ✨ Добавление дней
│   ├── webhook.py                # 🆕 Webhook сервер
│   └── main.py
├── .env                          # Конфигурация
├── requirements.txt
├── README.md                     # Этот файл
├── test_db_connection.py         # Тестирование БД
└── docker-compose.yml

✨ = Обновлено
🆕 = Новый файл
```

---

## 🆘 Поддержка

Если что-то не работает:

1. **Проверьте логи:**
   ```bash
   tail -f logs/bot.log
   ```

2. **Проверьте базу данных:**
   ```bash
   python test_db_connection.py
   ```

3. **Проверьте webhook:**
   ```bash
   curl http://localhost:8000/health
   ```

4. **Перезапустите всё:**
   ```bash
   pkill -f "python -m app"
   python -m app.main &
   python -m app.webhook &
   ```

---

## 🎯 Быстрый старт (TL;DR)

```bash
cd /root/daggervpn

# Исправьте базу данных
su - postgres -c "psql -c \"ALTER USER daggervpn WITH PASSWORD 'changeme';\""

# Установите зависимости
pip install -r requirements.txt

# Запустите миграции
alembic upgrade head

# Настройте .env (добавьте Platega API)
nano .env

# Запустите
screen -S bot -dm python -m app.main
screen -S webhook -dm python -m app.webhook

# Проверьте
screen -ls
curl http://localhost:8000/health
```

Готово! 🚀
