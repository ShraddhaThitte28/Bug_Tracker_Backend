import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

# Resolve path to backend directory and load .env file
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH)

# Frontend origins allowed by default (local Vite dev server)
DEFAULT_ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


class Settings:
    """Application, Database, and Security configuration settings."""
    PROJECT_NAME: str = "Bug Tracker / Issue Tracker API"
    PROJECT_VERSION: str = "1.0.0"

    # Hosted PostgreSQL connection string (e.g. provided by Railway).
    # When set, it takes priority over the individual DB_* values below.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()

    # PostgreSQL Database Credentials (local development fallback)
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "bug_tracker_db")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    # JWT Authentication Settings
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # CORS: comma-separated list of allowed frontend origins
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "")

    def validate_jwt_secret(self) -> None:
        """Ensure JWT_SECRET_KEY is loaded from .env and not empty."""
        if not self.JWT_SECRET_KEY:
            raise ValueError(
                "JWT_SECRET_KEY is not set. Please define JWT_SECRET_KEY in backend/.env"
            )

    @property
    def allowed_origins(self) -> list[str]:
        """Parse ALLOWED_ORIGINS into a list of explicit origins.

        A wildcard ("*") entry is ignored because credentials are enabled.
        Falls back to the local Vite dev origins when nothing is configured.
        """
        origins = [
            origin.strip().rstrip("/")
            for origin in self.ALLOWED_ORIGINS.split(",")
            if origin.strip() and origin.strip() != "*"
        ]
        return origins or list(DEFAULT_ALLOWED_ORIGINS)

    @property
    def database_url(self) -> URL:
        """Construct the SQLAlchemy database URL using the psycopg driver.

        Uses DATABASE_URL when provided (normalizing postgres:// and
        postgresql:// to postgresql+psycopg://), otherwise the DB_* values.
        """
        if self.DATABASE_URL:
            url = make_url(self.DATABASE_URL)
            if url.drivername in ("postgres", "postgresql", "postgresql+psycopg2"):
                url = url.set(drivername="postgresql+psycopg")
            return url

        return URL.create(
            drivername="postgresql+psycopg",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
        )


settings = Settings()
settings.validate_jwt_secret()
