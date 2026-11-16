from fastapi import APIRouter

from app.services.gpu_service import gpu_status

router = APIRouter(prefix="/ai", tags=["AI"])


@router.get("/status")
async def ai_status():
    """Design pictures are now made by placing real catalog products into the room
    photo on the backend itself, so no GPU server is needed and the service is
    always ready. `gpu` reports the optional Colab image model for reference."""
    return {"online": True, "mode": "catalog", "gpu": await gpu_status()}
