import json
import asyncio
import uuid
import httpx
from typing import Optional
from loguru import logger
from pathlib import Path
from app.core.settings import settings
from app.services.gpu_service import get_gpu_url, GpuOfflineError, is_transport_problem
from app.services import progress
from app.services.theme_hints import theme_scene, short_name, clip_words

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

    base = await get_gpu_url()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{base}/upload/image",
            files={"image": (filename, image_bytes, "image/jpeg")},
            data={"type": "input", "overwrite": "true"},
        )
        resp.raise_for_status()
        return resp.json().get("name", filename)


# =========================
# PROMPT BUILDER
# =========================

def _build_prompt(
    theme: Optional[str],
    planned_products: list,
    user_prompt: Optional[str] = None,
) -> tuple[str, str]:
    # Stable Diffusion only reads the first ~75 tokens, so keep it short and put
    # the important words first. Three modes:
    #   theme only    -> a rich description of that theme's decorated room
    #   prompt only   -> the user's own words lead
    #   theme + prompt-> the user's words lead, the theme fills in the rest
    scene = theme_scene(theme)
    user = clip_words(user_prompt, 24)

    # The model only reads ~75 tokens, so the words that matter most go FIRST.
    # Furniture comes right after the user's own words, otherwise it gets cut off.
    asked_for_furniture = any(
        w in (user_prompt or "").lower()
        for w in ("sofa", "couch", "chair", "table", "bed", "desk", "shelf", "furniture")
    )
    furniture = "" if asked_for_furniture else (
        "a cozy furnished living room with a large sofa, armchair, rug, coffee table and plants"
    )
    # Product names only help when a theme is chosen; with a free-text prompt the
    # user's words must lead, so unrelated product names are left out of the picture.
    items = ", ".join(
        clip_words(short_name(p["product_name"]), 3) for p in planned_products[:3]
    ) if scene else ""
    tail = "photorealistic interior photo, detailed, warm lighting"

    if user and scene:
        parts = [user, furniture, clip_words(scene, 14), items]
    elif user:
        parts = [user, furniture]
    else:
        parts = [furniture, clip_words(scene, 18) or "festive home decor", items]
    positive = ", ".join([p for p in parts if p] + [tail])

    negative = (
        "empty room, bare walls, empty floor, blurry, low quality, deformed, text, "
        "watermark, people, floating objects, bad perspective"
    )

    return positive, negative


# =========================
# WORKFLOW BUILDER
# =========================

def _build_workflow(
    input_image_name: str,
    theme: Optional[str],
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
    # Strong enough to actually add furniture and decor to a plain room; the GPU
    # server keeps the room's walls, windows and floor in place with ControlNet.
    workflow["6"]["inputs"]["denoise"] = 0.85
    workflow["6"]["inputs"]["steps"] = 30
    workflow["6"]["inputs"]["cfg"] = 8
    workflow["6"]["inputs"]["controlnet_scale"] = 0.55

    return workflow


# =========================
# COMFYUI EXECUTION
# =========================

async def _queue_workflow(workflow: dict) -> str:
    base = await get_gpu_url()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{base}/prompt",
            json={"prompt": workflow, "client_id": str(uuid.uuid4())},
        )
        resp.raise_for_status()
        return resp.json()["prompt_id"]


async def _wait_for_image(prompt_id: str) -> Optional[bytes]:
    elapsed = 0
    failures = 0
    base = await get_gpu_url()

    async with httpx.AsyncClient(timeout=30) as client:
        while elapsed < POLL_TIMEOUT:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

            try:
                resp = await client.get(f"{base}/history/{prompt_id}")
                resp.raise_for_status()
                failures = 0
                history = resp.json()

                if prompt_id not in history:
                    continue

                outputs = history[prompt_id].get("outputs", {})
                for node in outputs.values():
                    images = node.get("images", [])
                    if images:
                        img = images[0]

                        img_resp = await client.get(
                            f"{base}/view",
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
                if is_transport_problem(e):
                    failures += 1
                    if failures >= 3:
                        raise GpuOfflineError("GPU server stopped answering") from e

    return None


# =========================
# GENERATION PIPELINE
# =========================

async def _generate_with_comfyui(
    image_url: str,
    theme: str,
    planned_products: list,
    user_prompt: Optional[str] = None,
    user_id=None,
    progress_id: Optional[str] = None,
) -> Optional[str]:

    try:
        progress.set_stage(user_id, progress_id, "preparing")
        image_bytes = await _download_image(image_url)
        progress.set_stage(user_id, progress_id, "sending")
        input_name = await _upload_to_comfyui(image_bytes)

        workflow = _build_workflow(
            input_name,
            theme,
            planned_products,
            user_prompt
        )

        prompt_id = await _queue_workflow(workflow)
        progress.set_stage(user_id, progress_id, "generating")
        result = await _wait_for_image(prompt_id)

        if not result:
            return None

        progress.set_stage(user_id, progress_id, "saving")

        from app.services.storage_service import upload_image

        return await upload_image(
            content=result,
            filename=f"design_{uuid.uuid4().hex[:6]}.jpg",
            user_id="ai"
        )

    except GpuOfflineError:
        raise
    except Exception as e:
        if is_transport_problem(e):
            logger.error(f"GPU server unreachable: {e}")
            raise GpuOfflineError(str(e)) from e
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
            "product_id": p.get("product_id"),
            "asset_3d_name": p.get("asset_3d_name"),
            "product_theme": p.get("theme"),
            "category": "Wall",
            "pos_x": -0.6 + i * (1.2 / max(1, len(wall))),
            "pos_y": 1.5,
            "pos_z": 0.3,
        })

    # HANGING
    for i, p in enumerate(hanging[:4]):
        planned.append({
            "product_name": p["name"],
            "product_id": p.get("product_id"),
            "asset_3d_name": p.get("asset_3d_name"),
            "product_theme": p.get("theme"),
            "category": "Hanging",
            "pos_x": -0.5 + i * (1.0 / max(1, len(hanging))),
            "pos_y": 2.2,
            "pos_z": 0.0,
        })

    # FLOOR
    for i, p in enumerate(floor[:6]):
        planned.append({
            "product_name": p["name"],
            "product_id": p.get("product_id"),
            "asset_3d_name": p.get("asset_3d_name"),
            "product_theme": p.get("theme"),
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
    user_id=None,
    progress_id: Optional[str] = None,
) -> dict:

    theme = theme or None
    products = products or []

    # PLAN
    planned = _plan_layout(products)

    # GENERATE
    design_url = await _generate_with_comfyui(
        image_url=image_url,
        theme=theme,
        planned_products=planned,
        user_prompt=user_prompt,
        user_id=user_id,
        progress_id=progress_id,
    )

    # ✅ FIX: elements were missing
    elements = [
        {
            "name": p["product_name"],
            "product_id": p.get("product_id"),
            "asset_3d_name": p.get("asset_3d_name"),
            "product_theme": p.get("product_theme"),
            "category": p["category"],
            "pos_x": p["pos_x"],
            "pos_y": p["pos_y"],
            "pos_z": p["pos_z"],
        }
        for p in planned
    ]

    return {
        "design_image_url": design_url,
        "style": theme or "custom",
        "elements": elements,
    }