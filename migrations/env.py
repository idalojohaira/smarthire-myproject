from logging.config import fileConfig

# --- START: Flask Integration Imports (Required for loading Flask config) ---
import sys
from os.path import abspath, dirname
# Add the project root to the path so 'app' can be imported
sys.path.insert(0, dirname(dirname(abspath(__file__)))) 
from app import app, db # Import your Flask app and SQLAlchemy db instance

# Push the application context to make config and db.metadata available
app.app_context().push()
# --- END: Flask Integration Imports ---


from sqlalchemy import engine_from_config
from sqlalchemy import create_engine # <--- NEW: Import create_engine
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target_metadata to use your actual models' metadata
target_metadata = db.metadata # <--- CHANGED: Links Alembic to your models


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    
    This function has been modified to use the Flask app's configured
    SQLALCHEMY_DATABASE_URI to create a live connection for autogenerate.
    """
    
    # 1. Get the URI from Flask config
    database_url = app.config.get('SQLALCHEMY_DATABASE_URI')

    if database_url is None:
        raise Exception("SQLALCHEMY_DATABASE_URI not found in app.config.")

    # 2. Create the engine using the Flask URI
    connectable = create_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    # 3. Use the engine connection to configure the Alembic context
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()