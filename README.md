# daggerVPN — Telegram Bot для продажи VPN

Production-ready Telegram-бот для автоматической продажи VPN-подписок с интеграцией платёжной системы и панели управления VPN.

## Стек технологий

- Python 3.12+
- aiogram 3.x (async Telegram bot framework)
- PostgreSQL 16 + SQLAlchemy 2.x (async)
- Alembic (миграции БД)
- httpx (HTTP-клиент для API)
- APScheduler (фоновые задачи)
- Pydantic Settings (конфигурация)
- Docker + Docker Compose
- Nginx (reverse proxy + SSL)

## Быстрый старт

### 1. Требования к VPS

- Ubuntu 22.04+ / Debian 12+
- Минимум 1 ГБ RAM, 1 vCPU
- Docker Engine 24+ и Docker Compose v2
- Доменное имя, привязанное к IP сервера
- Открытые порты 80, 443

### 2. Установка Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl enable docker && sudo systemctl start docker
sudo usermod -aG docker $USER
```

### 3. Клонирование и настройка

```bash
git clone <your-repo-url> daggervpn && cd daggervpn
cp .env.example .env
nano .env
```

### 4. Настройка .env

Заполните все переменные в `.env`:

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен бота от @BotFather |
| `ADMIN_IDS` | Telegram ID администраторов через запятую |
| `DATABASE_URL` | URL подключения к PostgreSQL |
| `REMNAWAVE_API_URL` | URL API панели VPN |
| `REMNAWAVE_API_TOKEN` | Токен доступа к API панели |
| `PAYMENT_PROVIDER` | Платёжный провайдер (yookassa) |
| `YOOKASSA_SHOP_ID` | ID магазина ЮKassa |
| `YOOKASSA_SECRET_KEY` | Секретный ключ ЮKassa |
| `WEBHOOK_BASE_URL` | HTTPS URL вашего домена |
| `BOT_USERNAME` | Username бота без @ |

### 5. Получение SSL-сертификата

```bash
# Временно замените nginx/conf.d/default.conf на HTTP-only конфиг
# Затем:
docker compose up -d nginx
certbot certonly --webroot -w ./certbot/www -d YOUR_DOMAIN
# Восстановите полный nginx конфиг и перезапустите
docker compose restart nginx
```

### 6. Запуск миграций

```bash
docker compose run --rm bot alembic upgrade head
```

### 7. Запуск бота

```bash
docker compose up -d
docker compose logs -f bot
```

### 8. Проверка работоспособности

```bash
curl https://YOUR_DOMAIN/health
# Должно вернуть: OK
```

### 9. Настройка вебхука в BotFather

Бот автоматически устанавливает вебхук при старте. Убедитесь, что `WEBHOOK_BASE_URL` в `.env` указывает на ваш HTTPS-домен.

### 10. Настройка webhook для ЮKassa

В личном кабинете ЮKassa укажите URL уведомлений:
```
https://YOUR_DOMAIN/webhook/bot
```

### 11. Создание первого тарифа

Напишите `/start` боту → Админка → Тарифы → Добавить тариф.

### 12. Управление администраторами

Администраторы определяются по Telegram ID в переменной `ADMIN_IDS`. Никогда не используйте username для проверки прав.

### 13. Мониторинг

```bash
# Логи бота
docker compose logs -f bot

# Статус сервисов
docker compose ps

# Здоровье БД
docker compose exec db pg_isready -U daggervpn
```

### 14. Обновление

```bash
git pull
docker compose build bot
docker compose run --rm bot alembic upgrade head
docker compose up -d
```

### 15. Резервное копирование БД

```bash
docker compose exec db pg_dump -U daggervpn daggervpn > backup_$(date +%Y%m%d).sql
```

## Архитектура проекта

```
tgbot/
├── app/
│   ├── main.py              # Точка входа, веб-сервер
│   ├── config/
│   │   └── settings.py      # Pydantic Settings конфигурация
│   ├── database/
│   │   ├── session.py       # Async engine + session factory
│   │   └── models/          # SQLAlchemy модели
│   ├── services/            # Бизнес-логика
│   │   ├── payment_service.py
│   │   ├── remnawave_service.py
│   │   ├── referral_service.py
│   │   ├── promo_service.py
│   │   ├── notification_service.py
│   │   ├── subscription_sync_service.py
│   │   └── user_service.py
│   ├── bot/
│   │   ├── handlers/        # Обработчики команд и callback
│   │   ├── keyboards/       # Inline-клавиатуры
│   │   └── middlewares/     # Rate limit, user middleware
│   ├── scheduler/           # Фоновые задачи (APScheduler)
│   └── utils/               # Утилиты форматирования
├── alembic/                 # Миграции БД
├── tests/                   # Тесты
├── nginx/                   # Конфиг Nginx
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── requirements.txt
└── .env.example
```

## Функциональность

### Для пользователей
- Покупка VPN-подписки с оплатой через ЮKassa
- Просмотр активных ключей и подписок
- Продление подписки
- Промокоды (процентные и фиксированные скидки)
- Реферальная программа со скидками
- Поддержка через Telegram

### Для администраторов
- Управление пользователями (просмотр, блокировка, сообщения)
- Управление тарифами (CRUD, активация/деактивация)
- Управление промокодами
- Управление реферальными кампаниями блогеров
- Статистика платежей и выручки
- Аудит действий администраторов

### Автоматизация
- Уведомления об истечении подписки (7, 3, 1 день, истекла)
- Синхронизация данных подписок с панелью VPN
- Повторная обработка невыполненных платежей
- Идемпотентная обработка вебхуков оплаты

## Безопасность

- Все секреты хранятся только в `.env`, никогда не логируются
- Деньги хранятся в копейках (целые числа)
- Проверка прав администратора по Telegram ID
- Rate limiting на все запросы
- Идемпотентная обработка вебхуков
- Транзакции БД для критических операций
- Валидация callback data

## Лицензия

Proprietary. Все права защищены.
