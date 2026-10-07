from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MONGODB_URL: str
    MONGODB_NAME: str = "onbingo"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    VERIFICATION_CODE_EXPIRE_MINUTES: int = 10
    MAX_VERIFICATION_ATTEMPTS: int = 5
    IS_PRODUCTION: bool = False
    MEDIA_ROOT: str = "media"
    MEDIA_BASE_URL: str = "http://localhost:8000/media"
    AUTO_DISTRIBUTE_INTERVAL_SECONDS: int = 3600
    # Username of the Shop notification bot, shown to shop owners when linking.
    SHOP_TELEGRAM_BOT_USERNAME: str = "@HagereBingoBot"

    class Config:
        env_file = ".env"

settings = Settings()
