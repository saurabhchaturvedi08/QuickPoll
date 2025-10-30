from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    MONGO_URI: str = Field(...)
    MONGO_DB: str = Field("quickpoll")
    REDIS_URL: str = Field(...)


    JWT_SECRET: str = Field(...)
    JWT_ALGORITHM: str = Field("HS256")
    JWT_EXP_SECONDS: int = Field(3600)


    GOOGLE_CLIENT_ID: str = Field(...)


    APP_HOST: str = Field("0.0.0.0")
    APP_PORT: int = Field(8000)
    ENV: str = Field("development")


    class Config:
        env_file = ".env"


settings = Settings()