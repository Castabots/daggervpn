#!/usr/bin/env python3
"""Test database connection with different passwords."""

import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine


async def test_connection(password):
    """Test database connection with given password."""
    database_url = f"postgresql+asyncpg://daggervpn:{password}@localhost:5432/daggervpn"

    try:
        engine = create_async_engine(database_url, echo=False)
        async with engine.connect() as conn:
            result = await conn.execute("SELECT version()")
            version = result.scalar()
            print(f"✅ Успешное подключение с паролем: {password}")
            print(f"   PostgreSQL версия: {version[:50]}...")
            await engine.dispose()
            return True
    except Exception as e:
        print(f"❌ Ошибка с паролем '{password}': {str(e)[:60]}...")
        return False


async def main():
    """Try common passwords."""
    # Список распространённых паролей для тестирования
    passwords_to_try = [
        "changeme",
        "postgres",
        "daggervpn",
        "password",
        "",  # пустой пароль
    ]

    # Если пароль передан как аргумент
    if len(sys.argv) > 1:
        custom_password = sys.argv[1]
        print(f"Тестирую пароль из аргумента: {custom_password}\n")
        if await test_connection(custom_password):
            print(f"\n✅ Используйте этот пароль в .env:")
            print(f"DATABASE_URL=postgresql+asyncpg://daggervpn:{custom_password}@localhost:5432/daggervpn")
            return
        else:
            print("\n❌ Пароль не подошёл. Попробуйте другой.\n")

    print("Тестирую распространённые пароли...\n")

    for password in passwords_to_try:
        if await test_connection(password):
            print(f"\n✅ НАЙДЕН РАБОЧИЙ ПАРОЛЬ: {password}")
            print(f"\nОбновите ваш .env файл:")
            print(f"DATABASE_URL=postgresql+asyncpg://daggervpn:{password}@localhost:5432/daggervpn")
            return

    print("\n❌ Ни один из стандартных паролей не подошёл.")
    print("\nВозможные решения:")
    print("1. Запустите скрипт с вашим паролем: python test_db_connection.py ВАШ_ПАРОЛЬ")
    print("2. Сбросьте пароль через psql (см. DATABASE_FIX.md)")
    print("3. Проверьте, запущена ли PostgreSQL: sudo systemctl status postgresql")


if __name__ == "__main__":
    asyncio.run(main())
