# beenative/db/engine.py
import shutil
from pathlib import Path

from alembic import command
from settings import settings
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class DatabaseManager:
    def __init__(self):
        # The SINGLE source of truth for the async engine
        self.engine = create_async_engine(settings.async_database_url, echo=settings.debug, future=True)
        self.session_factory = async_sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)

    def initialize_db(self):
        """Handle seed data and migrations on startup."""
        if not settings.db_path.exists():
            seed_source = settings.initial_db_path
            if seed_source.exists():
                shutil.copy(seed_source, settings.db_path)
        self._run_migrations()

    def _run_migrations(self):
        """Programmatically runs alembic upgrade head."""
        # Resolve the path to alembic.ini relative to this file's location
        # (Going up two levels from beenative/db/engine.py to the root)
        base_path = Path(__file__).parent.parent.parent
        ini_path = base_path / "alembic.ini"

        if not ini_path.exists():
            print(f"Error: Could not find alembic.ini at {ini_path}")
            return

        alembic_cfg = Config(str(ini_path))

        # Ensure the script_location inside the config is also absolute
        # This prevents the "Path doesn't exist" error regardless of where you launch from
        script_location = base_path / "beenative" / "db"
        alembic_cfg.set_main_option("script_location", str(script_location))

        alembic_cfg.set_main_option("sqlalchemy.url", settings.sync_database_url)
        command.upgrade(alembic_cfg, "head")

    # This replaces your old asynccontextmanager
    def get_session(self):
        return self.session_factory()


# Unified instance
db_manager = DatabaseManager()
