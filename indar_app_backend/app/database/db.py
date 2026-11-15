from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.settings import settings
from app.database.base import Base

# app/database/db.py

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
    pool_pre_ping=True,  # add this
    pool_recycle=300,
    # SQL logs in terminal during dev only
    pool_size=10,
    max_overflow=20,  # drops stale Supabase connections automatically
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# app/database/db.py
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    """Dependency — yields one DB session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """
    Dev only — creates tables directly from models.
    In production, use Alembic migrations instead.
    NOTE: Supabase already has its own auth.users table —
    this only creates YOUR app tables (rooms, designs, etc.)
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)