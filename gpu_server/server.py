"""
Indar GPU server - a small stand-in for ComfyUI.

It answers the same four ComfyUI API calls the backend makes
(/upload/image, /prompt, /history/{id}, /view), and runs the img2img
redesign with Dreamshaper 8 through Hugging Face `diffusers`.
So the backend's COMFYUI_URL can point at either this server or a real ComfyUI.

Run on a GPU machine (e.g. Google Colab, see colab/Indar_GPU_Server.ipynb):
    pip install -r requirements.txt
    uvicorn server:app --host 0.0.0.0 --port 8188

Test mode with no GPU and no model download (returns a tinted copy of the photo):
    INDAR_FAKE_GPU=1 uvicorn server:app --port 8188
"""
import io
import os
import queue
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw, ImageEnhance

MODEL_ID = os.getenv("INDAR_MODEL", "Lykon/dreamshaper-8")
# ControlNet keeps the room's walls, windows and floor in place while the model
# adds furniture and decor. Set INDAR_CONTROLNET=off to use plain img2img.
CONTROLNET_ID = os.getenv("INDAR_CONTROLNET", "lllyasviel/control_v11p_sd15_canny")
FAKE = os.getenv("INDAR_FAKE_GPU") == "1"
MAX_SIDE = int(os.getenv("INDAR_MAX_SIDE", "768"))

BASE = Path(os.getenv("INDAR_WORKDIR", Path(__file__).parent / "work"))
INPUT, OUTPUT = BASE / "input", BASE / "output"
INPUT.mkdir(parents=True, exist_ok=True)
OUTPUT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Indar GPU server")
jobs: dict[str, dict] = {}          # prompt_id -> {"status": ..., "file": ..., "error": ...}
work: "queue.Queue[tuple[str, dict]]" = queue.Queue()
_pipe = None
_cn_ok = False   # True when the ControlNet pipeline loaded


# ── Model ─────────────────────────────────────────────────────────────────

def get_pipe():
    global _pipe, _cn_ok
    if _pipe is None:
        import torch
        from diffusers import DPMSolverMultistepScheduler

        pipe = None
        if CONTROLNET_ID.lower() != "off":
            try:
                from diffusers import ControlNetModel, StableDiffusionControlNetImg2ImgPipeline
                controlnet = ControlNetModel.from_pretrained(CONTROLNET_ID, torch_dtype=torch.float16)
                pipe = StableDiffusionControlNetImg2ImgPipeline.from_pretrained(
                    MODEL_ID, controlnet=controlnet, torch_dtype=torch.float16,
                    variant="fp16", safety_checker=None,
                )
                _cn_ok = True
            except Exception as e:  # fall back to plain img2img instead of failing
                print(f"[gpu] ControlNet unavailable ({e}); using plain img2img")
                pipe = None
        if pipe is None:
            from diffusers import StableDiffusionImg2ImgPipeline
            pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
                MODEL_ID, torch_dtype=torch.float16, variant="fp16", safety_checker=None
            )
        # Same sampler as the ComfyUI workflow: dpmpp_2m + karras
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(
            pipe.scheduler.config, use_karras_sigmas=True,
            algorithm_type="dpmsolver++", solver_order=2, final_sigmas_type="sigma_min",
        )
        _pipe = pipe.to("cuda")
    return _pipe


def edge_map(img: Image.Image) -> Image.Image:
    """White edges on black (what the canny ControlNet expects)."""
    try:
        import cv2
        import numpy as np
        edges = cv2.Canny(np.array(img.convert("RGB")), 60, 140)
        return Image.fromarray(np.stack([edges] * 3, axis=-1))
    except Exception:
        from PIL import ImageFilter
        g = img.convert("L").filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 25 else 0)
        return g.convert("RGB")


def fit(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    scale = min(1.0, MAX_SIDE / max(img.size))
    w, h = int(img.width * scale) // 8 * 8, int(img.height * scale) // 8 * 8
    return img.resize((max(w, 64), max(h, 64)), Image.LANCZOS)


def generate(params: dict) -> Image.Image:
    src = fit(Image.open(INPUT / params["image"]))
    if FAKE:
        out = ImageEnhance.Color(src).enhance(1.6)
        out = Image.blend(out, Image.new("RGB", out.size, (255, 170, 60)), 0.18)
        ImageDraw.Draw(out).text((12, 12), "FAKE GPU - test image", fill=(255, 255, 255))
        return out

    import torch
    pipe = get_pipe()
    gen = torch.Generator("cuda").manual_seed(int(params["seed"]) % (2**32))
    common = dict(
        prompt=params["positive"],
        negative_prompt=params["negative"],
        image=src,
        guidance_scale=float(params["cfg"]),
        num_inference_steps=int(params["steps"]),
        generator=gen,
    )
    if _cn_ok:
        return pipe(
            strength=float(params["denoise"]),
            control_image=edge_map(src),
            controlnet_conditioning_scale=float(params.get("controlnet_scale", 0.6)),
            **common,
        ).images[0]
    # Plain img2img: a high strength would scramble the room, so cap it.
    return pipe(strength=min(float(params["denoise"]), 0.62), **common).images[0]


def worker():
    while True:
        prompt_id, params = work.get()
        jobs[prompt_id]["status"] = "running"
        try:
            name = f"indar_{prompt_id[:8]}.png"
            generate(params).save(OUTPUT / name)
            jobs[prompt_id].update(status="done", file=name)
        except Exception as e:  # report instead of killing the worker
            jobs[prompt_id].update(status="error", error=str(e))
            print(f"[job {prompt_id}] failed: {e}")


threading.Thread(target=worker, daemon=True).start()


# ── Workflow parsing (ComfyUI API format) ────────────────────────────────

def parse_workflow(wf: dict) -> dict:
    by_type = {}
    for node_id, node in wf.items():
        by_type.setdefault(node.get("class_type"), []).append((node_id, node))
    try:
        load = by_type["LoadImage"][0][1]["inputs"]
        sampler = by_type["KSampler"][0][1]["inputs"]
        pos_id, neg_id = sampler["positive"][0], sampler["negative"][0]
        return {
            "image": load["image"],
            "positive": wf[pos_id]["inputs"]["text"],
            "negative": wf[neg_id]["inputs"]["text"],
            "seed": sampler.get("seed", 42),
            "steps": sampler.get("steps", 25),
            "cfg": sampler.get("cfg", 7),
            "denoise": sampler.get("denoise", 0.55),
            "controlnet_scale": sampler.get("controlnet_scale", 0.6),
        }
    except (KeyError, IndexError, TypeError) as e:
        raise HTTPException(400, f"Unsupported workflow: missing {e}")


# ── ComfyUI-compatible API ───────────────────────────────────────────────

@app.get("/system_stats")
def system_stats():
    return {"server": "indar-gpu", "fake": FAKE, "model": MODEL_ID, "controlnet": _cn_ok, "queue": work.qsize()}


@app.post("/upload/image")
async def upload_image(image: UploadFile = File(...), type: str = Form("input"), overwrite: str = Form("true")):
    name = Path(image.filename or f"{uuid.uuid4().hex}.jpg").name
    (INPUT / name).write_bytes(await image.read())
    return {"name": name, "subfolder": "", "type": "input"}


@app.post("/prompt")
def queue_prompt(body: dict):
    params = parse_workflow(body.get("prompt") or {})
    if not (INPUT / params["image"]).exists():
        raise HTTPException(400, f"Input image '{params['image']}' was not uploaded")
    prompt_id = str(uuid.uuid4())
    jobs[prompt_id] = {"status": "queued"}
    work.put((prompt_id, params))
    return {"prompt_id": prompt_id, "number": work.qsize(), "node_errors": {}}


@app.get("/history/{prompt_id}")
def history(prompt_id: str):
    job = jobs.get(prompt_id)
    if not job or job["status"] in ("queued", "running"):
        return {}
    if job["status"] == "error":
        return {prompt_id: {"outputs": {}, "status": {"status_str": "error", "messages": [job["error"]]}}}
    return {prompt_id: {"outputs": {"9": {"images": [
        {"filename": job["file"], "subfolder": "", "type": "output"}
    ]}}, "status": {"status_str": "success", "completed": True}}}


@app.get("/view")
def view(filename: str, subfolder: str = "", type: str = "output"):
    folder = OUTPUT if type == "output" else INPUT
    path = (folder / Path(filename).name)
    if not path.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8188)
