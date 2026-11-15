from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "Indar"
    APP_ENV: str = "development"

    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_JWT_SECRET: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_STORAGE_URL: str

    DATABASE_URL: str

    HUGGINGFACE_API_KEY: str = ""
    COMFYUI_URL: str = ""          # ← add this

    AMAZON_BASE_CART_URL: str = "https://www.amazon.in/gp/aws/cart/add.html"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()