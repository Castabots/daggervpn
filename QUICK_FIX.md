# 🚨 БЫСТРОЕ ИСПРАВЛЕНИЕ ОШИБКИ БАЗЫ ДАННЫХ

## Проблема
```
password authentication failed for user "daggervpn"
```

## Быстрое решение

### Шаг 1: Найдите правильный пароль

Запустите тестовый скрипт:

```bash
python test_db_connection.py
```

Или с конкретным паролем:

```bash
python test_db_connection.py ВАШ_ПАРОЛЬ
```

### Шаг 2: Обновите .env

Когда скрипт найдёт правильный пароль, обновите `.env`:

```env
DATABASE_URL=postgresql+asyncpg://daggervpn:ПРАВИЛЬНЫЙ_ПАРОЛЬ@localhost:5432/daggervpn
```

### Шаг 3: Запустите бота

```bash
python -m app.main
```

---

## Если ничего не помогло

### Сбросить пароль PostgreSQL:

```bash
sudo -u postgres psql -c "ALTER USER daggervpn WITH PASSWORD 'changeme';"
```

Затем обновите `.env`:

```env
DATABASE_URL=postgresql+asyncpg://daggervpn:changeme@localhost:5432/daggervpn
```

---

## Или создать базу заново:

```bash
sudo -u postgres psql << EOF
DROP DATABASE IF EXISTS daggervpn;
DROP USER IF EXISTS daggervpn;
CREATE USER daggervpn WITH PASSWORD 'changeme';
CREATE DATABASE daggervpn OWNER daggervpn;
EOF
```

Запустите миграции:

```bash
alembic upgrade head
```

Запустите бота:

```bash
python -m app.main
```

---

## Полная документация

См. `DATABASE_FIX.md` для подробной информации.
