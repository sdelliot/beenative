from logging.config import fileConfig
import sys
from pathlib import Path

root_path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_path))


from alembic import context
from sqlalchemy import engine_from_config, pool

# This has to be a wildcard in order to pull in all models for alembic.
from models import *  # noqa: F403
from conf.db import DatabaseSettings

# Import the Base from your base.py (where declarative_base is defined)
from models.base import Base
# Import your actual models so they are registered with the Base
from models.plant import Plant 

# Update the metadata target
target_metadata = Base.metadata

settings = DatabaseSettings()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata  # noqa: F405

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    # Use the sync URL from your settings
    url = settings.sync_database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Crucial for SQLite schema changes
        render_as_batch=True,
        # Helps Alembic find your custom types
        user_module_prefix="models.plant.",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Use the sync URL
    url = settings.sync_database_url

    # Create the engine using the dynamic URL
    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Required for modifying existing SQLite tables
            render_as_batch=True,
            user_module_prefix="models.plant.",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
