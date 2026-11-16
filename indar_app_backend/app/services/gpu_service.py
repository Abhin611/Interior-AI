"""
Where is the GPU server, and is it up?

The free Colab GPU gets a new public URL every session. The notebook registers
that URL in the `app_config` table (key `gpu_url`) through the `set_gpu_url`
database function, and the backend reads it from there. If nothing is
registered, the COMFYUI_URL from .env is used instead.
"""
import time
from typing import Optional

import httpx
from loguru import logger
from sqlalchemy import text

from app.core.settings import settings
from app.database.db import async_session

_CACHE_SECONDS = 10
_cached: tuple[float, str] | None = None


class GpuOfflineError(Exception):
    """The GPU server could not be reached (Colab stopped or disconnected)."""


async def get_gpu_url() -> str:
    """Current GPU server URL (no trailing slash). Empty string if none is known."""
    global _cached
    now = time.monotonic()
    if _cached and now - _cached[0] < _CACHE_SECONDS:
        return _cached[1]

    url = ""
    try:
        async with async_session() as db:
            row = await db.execute(text("select value from app_config where key = 'gpu_url'"))
            found = row.scalar_one_or_none()
            if found:
                url = found
    except Exception as e:  # table missing or database hiccup: fall back to .env
        logger.warning(f"Could not read gpu_url from app_config: {e}")

    url = (url or settings.COMFYUI_URL or "").rstrip("/")
    _cached = (now, url)
    return url


def forget_cached_url() -> None:
    global _cached
    _cached = None


async def gpu_status() -> dict:
    """Ping the GPU server. Returns {"online": bool, "model": str|None}."""
    url = await get_gpu_url()
    if not url:
        return {"online": False, "model": None, "reason": "not_configured"}
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            resp = await client.get(f"{url}/system_stats")
        if resp.status_code == 200:
            return {"online": True, "model": resp.json().get("model")}
        return {"online": False, "model": None, "reason": f"http_{resp.status_code}"}
    except Exception as e:
        logger.info(f"GPU ping failed: {type(e).__name__}")
        return {"online": False, "model": None, "reason": "unreachable"}


def is_transport_problem(exc: Exception) -> bool:
    """True when the failure means 'server not reachable' rather than a bug."""
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        # 502/503/504 and Cloudflare's 52x/530 mean the tunnel has no server behind it
        return exc.response.status_code in (502, 503, 504) or 520 <= exc.response.status_code <= 530
    return False


def gpu_offline_message() -> Optional[str]:
    return (
        "The AI server is offline. Open the Indar Colab notebook, press "
        "Runtime > Run all, wait for it to say it is ready, then try again."
    )
