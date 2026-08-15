from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: str = ""
    SUPPORT_URL: str = "https://t.me/daggerVPN_support"

    DATABASE_URL: str = "postgresql+asyncpg://daggervpn:changeme@db:5432/daggervpn"
    REDIS_URL: str | None = None

    REMNAWAVE_API_URL: str = ""
    REMNAWAVE_API_TOKEN: str = ""

    PAYMENT_PROVIDER: str = "none"

    LOG_LEVEL: str = "INFO"
    BOT_USERNAME: str = "daggerVPN_bot"

    PRIVACY_POLICY_URL: str = "https://telegra.ph/Politika-konfidencialnosti-08-15-60"
    TERMS_OF_SERVICE_URL: str = "https://telegra.ph/Polzovatelskoe-soglashenie-08-15-20"
    SETUP_GUIDE_URL: str = ""

    @property
    def admin_ids_list(self) -> list[int]:
        if not self.ADMIN_IDS.strip():
            return []
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
