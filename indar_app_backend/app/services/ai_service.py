import json
import asyncio
import uuid
import httpx
from typing import Optional
from loguru import logger
from pathlib import Path
from app.core.settings import settings

# Resolve relative to the backend root so it works from any working directory
WORKFLOW_PATH = Path(__file__).resolve().parents[2] / "img2img_workflow.json"

POLL_INTERVAL = 5
POLL_TIMEOUT = 300


# =========================
# IMAGE HELPERS
# =========================

async def _download_image(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def _upload_to_comfyui(image_bytes: bytes) -> str:
    filename = f"room_{uuid.uuid4().hex[:8]}.jpg"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.COMFYUI_URL}/upload/image",
            files={"image": (filename, image_bytes, "image/jpeg")},
            data={"type": "input", "overwrite": "true"},
        )
        resp.raise_for_status()
        return resp.json().get("name", filename)


# =========================
# PROMPT BUILDER
# =========================

def _build_prompt(
    theme: str,
    planned_products: list,
    user_prompt: Optional[str] = None,
) -> tuple[str, str]:

    context_names = [p["product_name"] for p in planned_products]

    placement_text = [
        f"{p['product_name']} at x={p['pos_x']}, y={p['pos_y']}, z={p['pos_z']}"
        for p in planned_products
    ]

    positive = (
        f"same exact room, no structural changes, "
        f"decorate for {theme}, "
        f"use ONLY: {', '.join(context_names)}, "
        f"place EXACTLY: {', '.join(placement_text)}, "
        f"correct scale, realistic, no floating objects, "
        f"perfect perspective, photorealistic"
        + (f", {user_prompt}" if user_prompt else "")
    )

    negative = (
        "extra objects, wrong placement, floating decor, "
        "bad perspective, blurry, low quality"
    )

    return positive, negative


# =========================
# WORKFLOW BUILDER
# =========================

def _build_workflow(
    input_image_name: str,
    theme: str,
    planned_products: list,
    user_prompt: Optional[str] = None,
) -> dict:

    with open(WORKFLOW_PATH, "r") as f:
        workflow = json.load(f)

    positive, negative = _build_prompt(
        theme,
        planned_products,
        user_prompt
    )

    workflow["1"]["inputs"]["image"] = input_image_name
    workflow["3"]["inputs"]["text"] = positive
    workflow["5"]["inputs"]["text"] = negative
    workflow["6"]["inputs"]["seed"] = uuid.uuid4().int % (2**32)

    return workflow


# =========================
# COMFYUI EXECUTION
# =========================

async def _queue_workflow(workflow: dict) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.COMFYUI_URL}/prompt",
            json={"prompt": workflow, "client_id": str(uuid.uuid4())},
        )
        resp.raise_for_status()
        return resp.json()["prompt_id"]


async def _wait_for_image(prompt_id: str) -> Optional[bytes]:
    elapsed = 0

    async with httpx.AsyncClient(timeout=30) as client:
        while elapsed < POLL_TIMEOUT:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

            try:
                resp = await client.get(f"{settings.COMFYUI_URL}/history/{prompt_id}")
                resp.raise_for_status()
                history = resp.json()

                if prompt_id not in history:
                    continue

                outputs = history[prompt_id].get("outputs", {})
                for node in outputs.values():
                    images = node.get("images", [])
                    if images:
                        img = images[0]

                        img_resp = await client.get(
                            f"{settings.COMFYUI_URL}/view",
                            params={
                                "filename": img["filename"],
                                "subfolder": img.get("subfolder", ""),
                                "type": img.get("type", "output"),
                            }
                        )
                        img_resp.raise_for_status()
                        return img_resp.content

            except Exception as e:
                logger.warning(f"Polling error: {e}")

    return None


# =========================
# GENERATION PIPELINE
# =========================

async def _generate_with_comfyui(
    image_url: str,
    theme: str,
    planned_products: list,
    user_prompt: Optional[str] = None,
) -> Optional[str]:

    try:
        image_bytes = await _download_image(image_url)
        input_name = await _upload_to_comfyui(image_bytes)

        workflow = _build_workflow(
            input_name,
            theme,
            planned_products,
            user_prompt
        )

        prompt_id = await _queue_workflow(workflow)
        result = await _wait_for_image(prompt_id)

        if not result:
            return None

        from app.services.storage_service import upload_image

        return await upload_image(
            content=result,
            filename=f"design_{uuid.uuid4().hex[:6]}.jpg",
            user_id="ai"
        )

    except Exception as e:
        logger.error(f"Generation failed: {e}")
        return None


# =========================
# LAYOUT PLANNER (FIXED)
# =========================

def _plan_layout(products: list) -> list:
    planned = []

    wall = [p for p in products if p["category"] == "Wall"]
    hanging = [p for p in products if p["category"] == "Hanging"]
    floor = [p for p in products if p["category"] == "Floor"]

    # WALL
    for i, p in enumerate(wall[:5]):
        planned.append({
            "product_name": p["name"],
            "category": "Wall",
            "pos_x": -0.6 + i * (1.2 / max(1, len(wall))),
            "pos_y": 1.5,
            "pos_z": 0.3,
        })

    # HANGING
    for i, p in enumerate(hanging[:4]):
        planned.append({
            "product_name": p["name"],
            "category": "Hanging",
            "pos_x": -0.5 + i * (1.0 / max(1, len(hanging))),
            "pos_y": 2.2,
            "pos_z": 0.0,
        })

    # FLOOR
    for i, p in enumerate(floor[:6]):
        planned.append({
            "product_name": p["name"],
            "category": "Floor",
            "pos_x": -0.7 + i * (1.4 / max(1, len(floor))),
            "pos_y": 0.0,
            "pos_z": 0.6,
        })

    return planned


# =========================
# MAIN ENTRY (FIXED)
# =========================

async def analyze_room(
    image_url: str,
    theme: Optional[str] = None,
    products: Optional[list] = None,
    user_prompt: Optional[str] = None,
) -> dict:

    theme = theme or "festive"
    products = products or []

    # PLAN
    planned = _plan_layout(products)

    # GENERATE
    design_url = await _generate_with_comfyui(
        image_url=image_url,
        theme=theme,
        planned_products=planned,
        user_prompt=user_prompt,
    )

    # ✅ FIX: elements were missing
    elements = [
        {
            "name": p["product_name"],
            "category": p["category"],
            "pos_x": p["pos_x"],
            "pos_y": p["pos_y"],
            "pos_z": p["pos_z"],
        }
        for p in planned
    ]

    return {
        "design_image_url": design_url,
        "style": theme,
        "elements": elements,
    }