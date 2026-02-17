import asyncio
import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://opencompany:opencompany@localhost:5432/opencompany",
)

engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=20)
async_session = async_sessionmaker(engine, expire_on_commit=False)

_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop):
    global _main_loop
    _main_loop = loop


def get_main_loop() -> asyncio.AbstractEventLoop | None:
    return _main_loop


async def get_session():
    async with async_session() as session:
        yield session
