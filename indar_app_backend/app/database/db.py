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

# Settings the Colab notebook writes to (its public URL changes every session).
# Idempotent; run on every startup. Matches the Supabase migration "app_config_gpu_url".
APP_CONFIG_SQL = [
    """create table if not exists public.app_config (
         key text primary key,
         value text not null,
         updated_at timestamptz not null default now())""",
    "alter table public.app_config enable row level security",
    """insert into public.app_config (key, value)
       values ('gpu_token', encode(gen_random_bytes(18), 'hex'))
       on conflict (key) do nothing""",
    """create or replace function public.set_gpu_url(p_token text, p_url text)
       returns boolean language plpgsql security definer set search_path = public
       as $fn$
       begin
         if p_token is null or p_token <> (select value from app_config where key = 'gpu_token') then
           raise exception 'invalid token';
         end if;
         if p_url !~ '^https://[a-z0-9-]+\\.trycloudflare\\.com$' then
           raise exception 'invalid url';
         end if;
         insert into app_config (key, value, updated_at) values ('gpu_url', p_url, now())
         on conflict (key) do update set value = excluded.value, updated_at = now();
         return true;
       end;
       $fn$""",
    "revoke all on function public.set_gpu_url(text, text) from public",
    "grant execute on function public.set_gpu_url(text, text) to anon, authenticated",
]


async def init_app_config():
    async with engine.begin() as conn:
        for stmt in APP_CONFIG_SQL:
            await conn.exec_driver_sql(stmt)
