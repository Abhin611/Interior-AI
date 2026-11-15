import uuid
from sqlalchemy import String, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database.base import Base


class Theme(Base):
    __tablename__ = "themes"

    theme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    theme_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(500), nullable=True)
    rating: Mapped[float] = mapped_column(Float, default=0.0)

    designs: Mapped[list["Design"]] = relationship("Design", back_populates="theme")


class Design(Base):
    __tablename__ = "designs"

    design_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rooms.room_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    theme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("themes.theme_id"),
        nullable=True,
        index=True,
    )
    style: Mapped[str] = mapped_column(String(255), nullable=True)
    design_image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    room: Mapped["Room"] = relationship("Room", back_populates="designs")
    theme: Mapped["Theme"] = relationship("Theme", back_populates="designs")
    elements: Mapped[list["DesignElement"]] = relationship(
        "DesignElement", back_populates="design", cascade="all, delete-orphan"
    )
    bundles: Mapped[list["Bundle"]] = relationship(
        "Bundle", back_populates="design", cascade="all, delete-orphan"
    )


class DesignElement(Base):
    __tablename__ = "design_elements"

    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    design_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("designs.design_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.product_id"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    pos_x: Mapped[float] = mapped_column(Float, nullable=True)
    pos_y: Mapped[float] = mapped_column(Float, nullable=True)
    pos_z: Mapped[float] = mapped_column(Float, nullable=True)
    # Stores the matched product's 3D asset filename so the Flutter AR view
    # can load the correct model per element without any fuzzy matching.
    asset_3d_name: Mapped[str] = mapped_column(String(255), nullable=True)

    # Relationships
    design: Mapped["Design"] = relationship("Design", back_populates="elements")
    product: Mapped["Product"] = relationship("Product", back_populates="elements")