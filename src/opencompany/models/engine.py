import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    _host = os.environ.get("DB_HOST", "localhost")
    _port = os.environ.get("DB_PORT", "5432")
    _user = os.environ.get("DB_USER", "opencompany")
    _pass = os.environ.get("DB_PASSWORD", "opencompany")
    _name = os.environ.get("DB_NAME", "opencompany")
    DATABASE_URL = f"postgresql+asyncpg://{_user}:{_pass}@{_host}:{_port}/{_name}"

engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=20)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with async_session() as session:
        yield session
