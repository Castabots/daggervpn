# 🔧 Исправление ошибки подключения к базе данных

## Ошибка
```
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "daggervpn"
```

## Причина
Пароль в `.env` файле не совпадает с паролем в базе данных PostgreSQL.

## Решение

### Вариант 1: Узнать текущий пароль базы данных

Если база данных запущена через Docker, проверьте docker-compose.yml:

```bash
grep POSTGRES_PASSWORD docker-compose.yml
```

Или проверьте переменные окружения контейнера:

```bash
docker inspect daggervpn_db | grep POSTGRES_PASSWORD
```

### Вариант 2: Сбросить пароль базы данных

#### Если используете Docker:

1. **Остановите контейнеры:**
```bash
docker compose down
```

2. **Удалите том базы данных (⚠️ ЭТО УДАЛИТ ВСЕ ДАННЫЕ!):**
```bash
docker volume rm daggervpn_pgdata
# или
docker volume ls | grep pgdata
docker volume rm [имя_тома]
```

3. **Убедитесь, что пароль в docker-compose.yml совпадает с .env:**

В `docker-compose.yml`:
```yaml
db:
  environment:
    POSTGRES_PASSWORD: changeme
```

В `.env`:
```env
DATABASE_URL=postgresql+asyncpg://daggervpn:changeme@db:5432/daggervpn
```

4. **Запустите заново:**
```bash
docker compose up -d
```

#### Если используете локальную PostgreSQL:

1. **Смените пароль пользователя daggervpn:**

```bash
sudo -u postgres psql
```

В psql выполните:
```sql
ALTER USER daggervpn WITH PASSWORD 'changeme';
\q
```

2. **Или создайте пользователя заново:**

```bash
sudo -u postgres psql
```

```sql
DROP DATABASE IF EXISTS daggervpn;
DROP USER IF EXISTS daggervpn;
CREATE USER daggervpn WITH PASSWORD 'changeme';
CREATE DATABASE daggervpn OWNER daggervpn;
\q
```

3. **Обновите .env с правильным паролем:**
```env
DATABASE_URL=postgresql+asyncpg://daggervpn:ВАШ_ПАРОЛЬ@localhost:5432/daggervpn
```

### Вариант 3: Использовать другой пароль

Просто обновите пароль в `.env` на тот, который используется в базе:

```env
DATABASE_URL=postgresql+asyncpg://daggervpn:РЕАЛЬНЫЙ_ПАРОЛЬ@localhost:5432/daggervpn
```

---

## После исправления

### 1. Запустите миграции (если база новая):

```bash
alembic upgrade head
```

### 2. Запустите бота:

```bash
python -m app.main
```

### 3. В отдельном терминале запустите webhook (если используете Platega):

```bash
python -m app.webhook
```

---

## Проверка подключения

Вы можете проверить подключение к базе данных Python скриптом:

```bash
python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.config.settings import settings

async def test():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        result = await conn.execute('SELECT version()')
        print('✅ Подключение успешно!')
        print(result.scalar())
    await engine.dispose()

asyncio.run(test())
"
```

---

## Для Docker

Если вы планируете использовать Docker, убедитесь что:

1. **В .env хост должен быть `db`:**
```env
DATABASE_URL=postgresql+asyncpg://daggervpn:changeme@db:5432/daggervpn
```

2. **Запускайте через docker compose:**
```bash
docker compose up -d
```

3. **Проверьте логи:**
```bash
docker compose logs -f bot
```

---

## Текущий статус вашего .env

Я обновил ваш `.env` файл:
- Изменил `@db:5432` на `@localhost:5432` (для локального запуска)
- Пароль остался `changeme`

**Если ваш реальный пароль другой, обновите его в .env файле!**
