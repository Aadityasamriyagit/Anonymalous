from __future__ import annotations

import hashlib
from functools import lru_cache

from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Minimal-env configuration for a Telegram bot deployment.

    Required env vars (only 4):
    - BOT_TOKEN
    - MONGO_URI
    - REDIS_URL
    - GEMINI_API_KEY

    Optional:
    - WEBHOOK_BASE_URL (recommended), or Railway public URL vars.
    - PORT (Railway auto-injected).
    """

    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # Core required runtime credentials/URIs.
    bot_token: str = Field(..., alias='BOT_TOKEN')
    mongo_uri: str = Field(..., alias='MONGO_URI')
    redis_url: str = Field(..., alias='REDIS_URL')
    gemini_api_key: str = Field(..., alias='GEMINI_API_KEY')

    # Webhook hosting resolution.
    webhook_base_url: str | None = Field(None, alias='WEBHOOK_BASE_URL')
    railway_public_domain: str | None = Field(None, alias='RAILWAY_PUBLIC_DOMAIN')
    railway_static_url: str | None = Field(None, alias='RAILWAY_STATIC_URL')

    # Internal defaults keep env surface small.
    webhook_path: str = '/webhook'
    webhook_host: str = '0.0.0.0'
    webhook_port: int = Field(8080, validation_alias=AliasChoices('PORT', 'WEBHOOK_PORT'))

    mongo_db_name: str = 'anonymalous'
    gemini_embed_model: str = 'models/text-embedding-004'
    gemini_moderation_model: str = 'gemini-1.5-flash'

    queue_ttl_seconds: int = 180
    chat_session_ttl_seconds: int = 3600
    throttle_seconds: int = 1
    superlike_token_cost: int = 1

    @computed_field
    @property
    def webhook_secret(self) -> str:
        # Deterministic secret derived from BOT_TOKEN; avoids extra required env var.
        return hashlib.sha256(self.bot_token.encode('utf-8')).hexdigest()[:48]

    @computed_field
    @property
    def resolved_webhook_base_url(self) -> str:
        if self.webhook_base_url:
            return self.webhook_base_url.rstrip('/')
        if self.railway_static_url:
            return self.railway_static_url.rstrip('/')
        if self.railway_public_domain:
            domain = self.railway_public_domain.strip().removeprefix('https://').removeprefix('http://')
            return f'https://{domain}'.rstrip('/')
        raise ValueError('Missing webhook base URL. Set WEBHOOK_BASE_URL or Railway public URL env var.')


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
