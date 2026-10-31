"""
Configuration management for the AI service.
Loads settings from the root .env file shared with the Node.js app.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # MongoDB connection (shared with Node app)
    ATLAS_URL: str

    DB_NAME: str
    
    # Groq API key for LLM operations (replacing Gemini)
    GROQ_API_KEY: str
    
    # Optional: AI service port (for Phase 4 FastAPI)
    AI_PORT: int = 8000
    
    # Optional: Environment
    NODE_ENV: str = "development"
    
    model_config = SettingsConfigDict(
        # Load from root .env (one level up from ai/)
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignore extra env vars from Node app
    )


# Global settings instance
settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get or create the global settings instance.
    Lazy loading to avoid errors if .env is missing during import.
    """
    global settings
    if settings is None:
        settings = Settings()
    return settings


def validate_config() -> bool:
    """
    Validate that all required configuration is present.
    Returns True if valid, raises an exception otherwise.
    """
    try:
        settings = get_settings()
        
        # Check MongoDB URL
        if not settings.ATLAS_URL:
            raise ValueError("ATLAS_URL is not set in .env")
        
        # Check Groq API key
        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not set in .env")
        
        return True
    except Exception as e:
        raise RuntimeError(f"Configuration validation failed: {e}") from e


if __name__ == "__main__":
    # Test configuration loading
    print("Testing configuration loading...")
    try:
        validate_config()
        settings = get_settings()
        print("✓ Configuration loaded successfully")
        print(f"  - MongoDB URL Loaded")
        print(f"  - Groq API Key: {'*' * 20}")
        print(f"  - AI Port: {settings.AI_PORT}")
        print(f"  - Environment: {settings.NODE_ENV}")
    except Exception as e:
        print(f"✗ Configuration failed: {e}")
