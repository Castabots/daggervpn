# daggerVPN — Telegram Bot для продажи VPN

Telegram-бот для автоматической выдачи VPN-подписок через панель Remnawave.

## Стек

- Python 3.12+, aiogram 3.x (polling)
- PostgreSQL 16 + SQLAlchemy 2.x async + Alembic
- httpx, APScheduler, Pydantic Settings
- Docker + Docker Compose

## Что делает бот

**Пользователь:**
- Смотрит тарифы, нажимает «Купить» → видит заглушку «Оплата скоро будет» (платёжка пока не подключена)
- Просматривает свои ключи, копирует ссылку подписки
- Вводит промокоды
- Приглашает друзей по реферальной ссылке

**Администратор (по Telegram ID):**
- Управление пользователями (просмотр, блокировка, рассылка)
- CRUD тарифов
- Создание промокодов
- Реферальные кампании блогеров
- Статистика

**Автоматика:**
- Уведомления об истечении подписки (7/3/1 день)
- Синхронизация подписок с панелью Remnawave каждые 6 часов

---

## Установка на VPS

### 1. Требования

- Ubuntu 22.04+ / Debian 12+
- Минимум 1 ГБ RAM
- Docker Engine 24+ и Docker Compose v2

### 2. Установить Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl enable docker && sudo systemctl start docker
sudo usermod -aG docker $USER
```

Перезайди в терминал после `usermod` чтобы права применились.

### 3. Скачать проект

```bash
git clone https://github.com/ТВОЙ_НИК/daggervpn.git
cd daggervpn
```

### 4. Настроить .env

```bash
cp .env.example .env
nano .env
```

Заполни каждую переменную:

| Переменная | Где взять | Пример |
|---|---|---|
| `BOT_TOKEN` | @BotFather в Telegram → /newbot → скопировать токен | `8938241930:AAGin5bmq...` |
| `ADMIN_IDS` | Твой Telegram ID (узнай у @userinfobot) | `8108649608` |
| `SUPPORT_URL` | Ссылка на поддержку | `https://t.me/daggerVPN_support` |
| `DATABASE_URL` | Не меняй, если используешь docker-compose как есть | `postgresql+asyncpg://daggervpn:changeme@db:5432/daggervpn` |
| `REDIS_URL` | Не меняй, если используешь docker-compose как есть | `redis://redis:6379/0` |
| `REMNAWAVE_API_URL` | URL API панели Remnawave (без /dashboard) | `https://panel.daggervpn.ru/api` |
| `REMNAWAVE_API_TOKEN` | API-токен из панели Remnawave (Settings → API Keys) | `eyJhbGciOiJIUzI1NiIs...` |
| `LOG_LEVEL` | Уровень логов | `INFO` или `DEBUG` |
| `BOT_USERNAME` | Username бота без @ | `daggerVPN_bot` |

### 5. Сменить пароль базы данных

Открой `docker-compose.yml` и замени `changeme` на надёжный пароль в трёх местах:
- `POSTGRES_PASSWORD`
- Также обнови пароль в `DATABASE_URL` в `.env` (часть между `:` и `@`)

Пример: если новый пароль `MyStr0ngP@ss`, то:
```
# docker-compose.yml
POSTGRES_PASSWORD: MyStr0ngP@ss

# .env
DATABASE_URL=postgresql+asyncpg://daggervpn:MyStr0ngP@ss@db:5432/daggervpn
```

### 6. Положить картинку

Бот использует файл `1.png` для всех экранов. Положи его в корень проекта:
```
daggervpn/
├── 1.png          ← твоя картинка
├── app/
├── docker-compose.yml
└── ...
```

### 7. Запустить

```bash
# Собрать и запустить все сервисы
docker compose up -d --build

# Прогнать миграции БД (создаёт таблицы)
docker compose run --rm bot alembic upgrade head
```

### 8. Проверить

```bash
# Логи бота (должно быть "Bot started (polling mode)")
docker compose logs -f bot

# Статус контейнеров
docker compose ps
```

Напиши `/start` своему боту в Telegram. Должно появиться главное меню.

---

## Как получить данные для .env

### BOT_TOKEN
1. Открой @BotFather в Telegram
2. `/newbot` → придумай имя → придумай username
3. Скопируй токен

### ADMIN_IDS (твой Telegram ID)
1. Напиши @userinfobot в Telegram
2. Он ответит твоим числовым ID

### REMNAWAVE_API_URL
URL API твоей панели Remnawave. Обычно это адрес панели + `/api`:
```
Панель:   https://panel.daggervpn.ru/dashboard/home
API URL:  https://panel.daggervpn.ru/api
```

### REMNAWAVE_API_TOKEN
1. Зайди в панель Remnawave
2. Settings → API Keys (или раздел API)
3. Создай API-ключ с ролью API
4. Скопируй JWT-токен

---

## Команды управления

```bash
# Перезапустить бота
docker compose restart bot

# Обновить код и перезапустить
git pull
docker compose build bot
docker compose run --rm bot alembic upgrade head
docker compose up -d

# Посмотреть логи
docker compose logs -f bot

# Остановить всё
docker compose down

# Полный сброс (УДАЛИТ базу данных!)
docker compose down -v
```

---

## Структура проекта

```
daggervpn/
├── app/
│   ├── main.py                 # Точка входа, polling
│   ├── config/
│   │   └── settings.py         # Переменные окружения
│   ├── database/
│   │   ├── session.py          # Подключение к БД
│   │   └── models/             # Таблицы (User, Tariff, Subscription, ...)
│   ├── services/               # Бизнес-логика
│   │   ├── payment_service.py  # Платёжный провайдер (абстрактный, пока не подключён)
│   │   ├── remnawave_service.py # API панели VPN
│   │   ├── referral_service.py
│   │   ├── promo_service.py
│   │   ├── notification_service.py
│   │   ├── subscription_sync_service.py
│   │   └── user_service.py
│   ├── bot/
│   │   ├── handlers/           # Обработчики команд
│   │   ├── keyboards/          # Inline-клавиатуры
│   │   └── middlewares/        # Rate limit, авто-регистрация
│   ├── scheduler/              # Фоновые задачи
│   └── utils/                  # Форматтеры цен, дат, трафика
├── alembic/                    # Миграции БД
├── tests/                      # Тесты
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example                # Шаблон конфигурации
└── .env                        # Твои секреты (НЕ коммитить!)
```

---

## Как подключить платёжку (когда будешь готов)

1. Создай класс провайдера в `app/services/payment_service.py`:
```python
class MyPaymentProvider(PaymentProvider):
    async def create_payment(self, amount_kopeks, description, metadata):
        # Вызов API платёжки
        return {"payment_id": "...", "payment_url": "..."}

    async def get_payment_status(self, payment_id):
        # Проверка статуса
        return "succeeded"

    async def verify_webhook(self, payload):
        # Проверка вебхука
        return {"payment_id": "...", "status": "succeeded"}
```

2. Добавь в `get_payment_provider()`:
```python
def get_payment_provider():
    if settings.PAYMENT_PROVIDER == "myprovider":
        return MyPaymentProvider()
    raise NotImplementedError(...)
```

3. В `.env` добавь `PAYMENT_PROVIDER=myprovider` и нужные ключи.

4. Верни обработку оплаты в `app/bot/handlers/purchase.py` (замени заглушки на вызовы `payment_service.create_payment()`).

---

## Безопасность

- Все секреты только в `.env`, файл в `.gitignore`
- Права админа проверяются по Telegram ID, никогда по username
- Деньги хранятся в копейках (int), никаких float
- Rate limiting на все запросы (30/мин)
- Транзакции БД для критических операций

## Проблемы и решения

**Бот не реагирует на команды:**
```bash
docker compose logs bot
# Ищи ошибки в логах
```

**Ошибка миграций:**
```bash
docker compose run --rm bot alembic upgrade head
```

**База не создаётся:**
```bash
# Проверь что db контейнер здоров
docker compose ps
# Если unhealthy — смотри логи
docker compose logs db
```

**Нужно сбросить базу:**
```bash
docker compose down -v
docker compose up -d --build
docker compose run --rm bot alembic upgrade head
```
