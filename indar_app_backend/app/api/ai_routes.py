from fastapi import APIRouter

from app.services.gpu_service import gpu_status, gpu_offline_message

router = APIRouter(prefix="/ai", tags=["AI"])


@router.get("/status")
async def ai_status():
    """Is the GPU server (Colab) reachable right now? No login needed."""
    status = await gpu_status()
    if not status["online"]:
        status["message"] = gpu_offline_message()
    return status
