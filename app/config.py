from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database — MySQL only (set DATABASE_URL in your .env to override)
    DATABASE_URL: str = "mysql+pymysql://root:password@localhost:3306/zambia_fraud"

    # JWT
    SECRET_KEY: str = "zambia-fraud-detection-secret-key-2024-cbu-group20"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 hours

    # App
    APP_NAME: str = "Zambia Mobile Money Fraud Detection System"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    # ML Models
    MODEL_PATH: str = "./models"
    FRAUD_THRESHOLD: float = 0.5
    RISK_HIGH_THRESHOLD: int = 60
    RISK_MEDIUM_THRESHOLD: int = 30

    # Retraining
    RETRAIN_SCHEDULE_CRON: str = "0 2 1 * *"  # 1st of every month at 2am
    MIN_SAMPLES_FOR_RETRAIN: int = 500

    class Config:
        env_file = ".env"


settings = Settings()
