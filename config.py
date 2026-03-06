from functools import lru_cache

from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    bot_token: str = Field(..., alias='BOT_TOKEN')
    webhook_base_url: str | None = Field(None, alias='WEBHOOK_BASE_URL')
    webhook_path: str = Field('/webhook', alias='WEBHOOK_PATH')
    webhook_secret: str = Field(..., alias='WEBHOOK_SECRET')

    # Railway-compatible binding: PORT is auto-injected on deployments.
    webhook_host: str = Field('0.0.0.0', alias='WEBHOOK_HOST')
    webhook_port: int = Field(8080, validation_alias=AliasChoices('PORT', 'WEBHOOK_PORT'))

    # Railway public-domain hints (optional). We support multiple common env names.
    railway_public_domain: str | None = Field(None, alias='RAILWAY_PUBLIC_DOMAIN')
    railway_static_url: str | None = Field(None, alias='RAILWAY_STATIC_URL')

    mongo_uri: str = Field(..., alias='MONGO_URI')
    mongo_db_name: str = Field('anonymalous', alias='MONGO_DB_NAME')

    redis_url: str = Field('redis://redis:6379/0', alias='REDIS_URL')

    gemini_api_key: str = Field(..., alias='GEMINI_API_KEY')
    gemini_embed_model: str = Field('models/text-embedding-004', alias='GEMINI_EMBED_MODEL')
    gemini_moderation_model: str = Field('gemini-1.5-flash', alias='GEMINI_MODERATION_MODEL')

    queue_ttl_seconds: int = Field(180, alias='QUEUE_TTL_SECONDS')
    chat_session_ttl_seconds: int = Field(3600, alias='CHAT_SESSION_TTL_SECONDS')
    throttle_seconds: int = Field(1, alias='THROTTLE_SECONDS')

    superlike_token_cost: int = Field(1, alias='SUPERLIKE_TOKEN_COST')

    @computed_field
    @property
    def resolved_webhook_base_url(self) -> str:
        if self.webhook_base_url:
            return self.webhook_base_url.rstrip('/')
        if self.railway_static_url:
            return self.railway_static_url.rstrip('/')
        if self.railway_public_domain:
            return f'https://{self.railway_public_domain.strip().lstrip("https://").lstrip("http://")}'.rstrip('/')
        raise ValueError(
            'Missing webhook base URL. Set WEBHOOK_BASE_URL or Railway env vars RAILWAY_STATIC_URL/RAILWAY_PUBLIC_DOMAIN.'
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
