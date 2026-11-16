from fastapi import APIRouter
from app.api.auth_routes import router as auth_router
from app.api.user_routes import router as user_router
from app.api.room_routes import router as room_router
from app.api.design_routes import router as design_router
from app.api.product_routes import router as product_router
from app.api.ai_routes import router as ai_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(room_router)
api_router.include_router(design_router)
api_router.include_router(product_router)
api_router.include_router(ai_router)
