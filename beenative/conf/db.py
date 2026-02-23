import sys
import os
from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class DatabaseSettings(BaseSettings):
    db_filename: str = "beenative.db"
    init_db_filename: str = "seed_plants.db"
    debug: bool = False

    @property
    def db_path(self) -> Path:
        """Determines the correct path for the DB file."""
        if getattr(sys, "frozen", False):
            # Production: Use User's Local App Data to ensure write permissions
            path = Path(os.getenv("LOCALAPPDATA", os.getcwd())) / "BeeNative"
            path.mkdir(parents=True, exist_ok=True)
            return path / self.db_filename

        # Development: Use the project root
        return BASE_DIR / self.db_filename

    @property
    def initial_db_path(self) -> Path:
        # Try common bundle locations
        possible_paths = [
            BASE_DIR / "assets" / "data" / self.init_db_filename,
            BASE_DIR.parent / "assets" / "data" / self.init_db_filename,
            Path(f"assets/data/{self.init_db_filename}"),
            Path(f"./data/{self.init_db_filename}"),
        ]

        for p in possible_paths:
            if p.exists():
                return p
        return None

    @property
    def sync_init_database_url(self) -> str:
        """URL for Alembic and Sync operations."""
        return f"sqlite:///{self.init_db_filename}"

    @property
    def async_database_url(self) -> str:
        """URL for SQLAlchemy AsyncSession (aiosqlite)."""
        return f"sqlite+aiosqlite:///{self.db_path}"

    @property
    def sync_database_url(self) -> str:
        """URL for Alembic and Sync operations."""
        return f"sqlite:///{self.db_path}"
