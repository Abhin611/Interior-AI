import uuid
from sqlalchemy import String, Float, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database.base import Base


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    asin: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    product_url: Mapped[str] = mapped_column(String(500), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=True, index=True)  # Hanging|Wall|Floor
    theme: Mapped[str] = mapped_column(String(100), nullable=True, index=True)     # onam|Christmas etc

    # Links to your .glb/.obj file
    # Flutter AR layer uses this to load the 3D model
    asset_3d_name: Mapped[str] = mapped_column(String(500), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    elements: Mapped[list["DesignElement"]] = relationship(
        "DesignElement", back_populates="product"
    )
    bundle_items: Mapped[list["BundleItem"]] = relationship(
        "BundleItem", back_populates="product"
    )