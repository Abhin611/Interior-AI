"""
Seeds products and themes from Dataset1.xlsx into the database.
Run with: uv run python -m app.database.seed
Reads Dataset1.xlsx from the backend root folder (or set SEED_EXCEL_PATH).
"""
import asyncio
import re
import openpyxl
from sqlalchemy import select
from app.database.db import AsyncSessionLocal

# ⚠️ Must import ALL models so SQLAlchemy resolves relationships
from app.models.user import User
from app.models.room import Room
from app.models.design import Design, DesignElement, Theme
from app.models.product import Product
from app.models.bundle import Bundle, BundleItem, Transaction

from loguru import logger

import os
from pathlib import Path

# Defaults to Dataset1.xlsx in the backend root; override with SEED_EXCEL_PATH
EXCEL_PATH = os.getenv(
    "SEED_EXCEL_PATH",
    str(Path(__file__).resolve().parents[2] / "Dataset1.xlsx"),
)

THEMES = [
    {"name": "onam",        "description": "Traditional Kerala festival decoration"},
    {"name": "Christmas",   "description": "Christmas and winter holiday decor"},
    {"name": "Diwali",      "description": "Diwali festival lighting and decor"},
    {"name": "Halloween",   "description": "Halloween spooky decor"},
    {"name": "Birthday",    "description": "Birthday party decoration"},
    {"name": "Pop-Culture", "description": "Pop culture themed decor"},
]


def clean_asin(raw) -> str:
    if not raw:
        return ""
    return re.sub(r'[\t\u200e\u200b\xa0\s]', '', str(raw)).strip()


def parse_rating(raw) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return float(str(raw).split("/")[0])
    except Exception:
        return 0.0


def clean_asset_name(raw) -> str:
    """Clean up the 3D asset name from Excel."""
    if not raw:
        return ""
    return str(raw).strip().replace("\xa0", "").replace("\t", "")


async def seed():
    async with AsyncSessionLocal() as db:

        # ── Seed Themes ───────────────────────────────────────────────
        logger.info("Seeding themes...")
        for t in THEMES:
            result = await db.execute(
                select(Theme).where(Theme.theme_name == t["name"])
            )
            if not result.scalar_one_or_none():
                db.add(Theme(
                    theme_name=t["name"],
                    description=t["description"],
                    rating=0.0,
                ))
                logger.info(f"  + Theme: {t['name']}")
            else:
                logger.info(f"  ~ Exists: {t['name']}")

        await db.commit()

        # ── Seed Products ─────────────────────────────────────────────
        logger.info("Seeding products from Excel...")
        wb = openpyxl.load_workbook(EXCEL_PATH)
        ws = wb["Sheet1"]

        added = 0
        skipped_duplicate = 0
        skipped_invalid = 0

        for row in ws.iter_rows(min_row=2, values_only=True):
            # Columns: Name, ASIN, Photo_name, 3D asset name, Rating, Price, Type, Theme
            name        = row[0]
            asin_raw    = row[1]
            photo_name  = row[2]
            asset_3d    = row[3]
            rating_raw  = row[4]
            price       = row[5]
            ptype       = row[6]
            theme       = row[7]

            # Skip rows missing required fields
            if not name or not asin_raw or not price:
                skipped_invalid += 1
                continue

            asin = clean_asin(asin_raw)
            if not asin:
                skipped_invalid += 1
                continue

            # Skip duplicate ASINs
            result = await db.execute(
                select(Product).where(Product.asin == asin)
            )
            if result.scalar_one_or_none():
                skipped_duplicate += 1
                continue

            db.add(Product(
                asin=asin,
                name=str(name).strip(),
                price=float(price),
                image_url=None,             # add later via ImageKit
                product_url=f"https://www.amazon.in/dp/{asin}",
                category=str(ptype).strip() if ptype and str(ptype).strip() else None,
                theme=str(theme).strip() if theme and str(theme).strip() else None,
                asset_3d_name=clean_asset_name(asset_3d) if asset_3d else None,
                is_active=True,
            ))
            added += 1
            logger.info(f"  + {asin} | {str(name)[:50]} | 3D: {clean_asset_name(asset_3d)}")

        await db.commit()
        logger.info(f"\n✅ Done. Added: {added} | Skipped duplicates: {skipped_duplicate} | Invalid rows: {skipped_invalid}")


if __name__ == "__main__":
    asyncio.run(seed())