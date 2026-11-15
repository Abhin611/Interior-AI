import uuid
from typing import Optional, List
from pydantic import BaseModel


class ProductOut(BaseModel):
    product_id: uuid.UUID
    asin: str
    name: str
    price: float
    category: Optional[str] = None
    theme: Optional[str] = None
    asset_3d_name: Optional[str] = None
    product_url: Optional[str] = None
    image_url: Optional[str] = None        # computed — not from DB
    asset_3d_url: Optional[str] = None     # computed — not from DB

    model_config = {"from_attributes": True}


class BundleOut(BaseModel):
    bundle_id: uuid.UUID
    design_id: uuid.UUID
    user_id: Optional[str] = None
    total_price: float
    amazon_cart_url: Optional[str] = None

    model_config = {"from_attributes": True}


class BundleItemOut(BaseModel):
    product: ProductOut
    quantity: int

    model_config = {"from_attributes": True}


class BundleDetailOut(BaseModel):
    bundle_id: uuid.UUID
    design_id: uuid.UUID
    user_id: Optional[str] = None
    total_price: float
    amazon_cart_url: Optional[str] = None
    items: List[BundleItemOut] = []

    model_config = {"from_attributes": True}