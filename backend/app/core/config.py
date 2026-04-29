from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development")
    app_port: int = Field(default=8000)
    app_secret_key: str = Field(default="change-me")
    app_base_url: str = Field(default="http://localhost:3000")

    # JWT
    jwt_secret: str = Field(default="dev-jwt-secret-change-me")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=60 * 24 * 7)  # 7 days

    # DB / Cache
    database_url: str = Field(default="sqlite+aiosqlite:///./taiwan_stock.db")
    redis_url: str = Field(default="redis://localhost:6379/0")

    cors_origins: str = Field(default="http://localhost:3000,http://127.0.0.1:3000")

    # Data sources
    twse_base_url: str = Field(default="https://www.twse.com.tw")
    tpex_base_url: str = Field(default="https://www.tpex.org.tw")
    mops_base_url: str = Field(default="https://mops.twse.com.tw")

    # Stripe
    stripe_secret_key: str = Field(default="")
    stripe_webhook_secret: str = Field(default="")
    stripe_price_pro: str = Field(default="")
    stripe_price_elite: str = Field(default="")

    # LINE Messaging
    line_channel_token: str = Field(default="")
    line_channel_secret: str = Field(default="")

    # Scheduler
    scheduler_enabled: bool = Field(default=False)
    scheduler_timezone: str = Field(default="Asia/Taipei")

    # Email (Resend / SendGrid). If both empty, emails are logged only.
    resend_api_key: str = Field(default="")
    sendgrid_api_key: str = Field(default="")
    email_from: str = Field(default="Taiwan Stock AI <hello@taiwan-stock-ai.example.com>")

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
