"""
In-memory progress of running design generations, so the app can show real
steps instead of a blind spinner. One backend process only (fine for this app).
"""
import time

_TTL = 15 * 60
_jobs: dict[str, dict] = {}

# stage -> (percent, message)
STAGES = {
    "preparing": (5, "Reading your room photo..."),
    "sending": (15, "Sending the photo to the AI server..."),
    "generating": (30, "AI is redecorating your room..."),
    "composing": (45, "Placing real products in your room..."),
    "saving": (88, "Saving your new design..."),
    "matching": (94, "Picking matching products..."),
    "done": (100, "Done!"),
    "failed": (100, "Something went wrong."),
}


def _key(user_id, progress_id: str) -> str:
    return f"{user_id}:{progress_id}"


def _sweep() -> None:
    cutoff = time.time() - _TTL
    for k in [k for k, v in _jobs.items() if v["t"] < cutoff]:
        _jobs.pop(k, None)


def set_stage(user_id, progress_id: str | None, stage: str) -> None:
    if not progress_id:
        return
    _sweep()
    pct, msg = STAGES[stage]
    _jobs[_key(user_id, progress_id)] = {
        "stage": stage, "percent": pct, "message": msg, "t": time.time(),
        "started": _jobs.get(_key(user_id, progress_id), {}).get("started", time.time()),
    }


def get_stage(user_id, progress_id: str) -> dict:
    job = _jobs.get(_key(user_id, progress_id))
    if not job:
        return {"stage": "unknown", "percent": 0, "message": "Starting...", "elapsed": 0}
    out = {k: job[k] for k in ("stage", "percent", "message")}
    out["elapsed"] = int(time.time() - job["started"])
    return out
