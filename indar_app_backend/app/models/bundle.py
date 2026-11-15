from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, ForeignKey, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database.base import Base
import uuid


class Bundle(Base):
    __tablename__ = "bundles"

    bundle_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    design_id = Column(UUID(as_uuid=True), ForeignKey("designs.design_id"), nullable=False)
    user_id = Column(String, nullable=False, index=True)  # Supabase auth UUID, plain string no FK
    total_price = Column(Float, nullable=False)
    amazon_cart_url = Column(String, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    design = relationship("Design", back_populates="bundles")
    items = relationship("BundleItem", back_populates="bundle", cascade="all, delete-orphan")


class BundleItem(Base):
    __tablename__ = "bundle_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bundle_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bundles.bundle_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.product_id"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)

    # Relationships
    bundle = relationship("Bundle", back_populates="items")
    product = relationship("Product")


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, index=True)  # Supabase auth UUID, plain string no FK
    bundle_id = Column(UUID(as_uuid=True), ForeignKey("bundles.bundle_id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, default="redirected")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    bundle = relationship("Bundle")