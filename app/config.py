"""
Application Configuration

Manages environment variables and application settings using Pydantic.
Settings are loaded from environment variables or .env file.

Environment Variables:
- DATABASE_URL: PostgreSQL connection string
- REDIS_URL: Redis connection string for Celery
- FILE_STORAGE_PATH: Directory for uploaded and converted files
- APP_NAME: Application name
- DEBUG: Debug mode flag
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Pydantic automatically validates types and provides defaults.
    In Docker, these are set in docker-compose.yml.
    For local development, create a .env file.
    """
    
    APP_NAME: str = "Bulk DOCX to PDF Service"
    DEBUG: bool = False
    
    # Database Configuration
    # Default is SQLite for local testing, but Docker uses PostgreSQL
    DATABASE_URL: str = "sqlite:///./test.db"
    
    # Redis Configuration
    # Used by Celery as message broker and result backend
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # File Storage Configuration
    # This directory is shared between API and worker containers via Docker volume
    FILE_STORAGE_PATH: str = "storage"
    
    model_config = SettingsConfigDict(
        env_file=".env",              # Load from .env file if present
        env_file_encoding="utf-8",
        case_sensitive=True,          # Environment variable names are case-sensitive
        extra="ignore"                # Ignore extra environment variables
    )


# Global settings instance
# Import this in other modules: from app.config import settings
settings = Settings()
