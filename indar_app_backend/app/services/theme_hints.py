"""
Words that turn a theme / a user's prompt into a picture description the image
model understands.

Stable Diffusion reads only the first ~75 tokens of a prompt, so everything here
is short and the important words come first.
"""
import re
from typing import Optional

# What a fully decorated room for each theme looks like.
THEME_SCENES = {
    "diwali": "Diwali festival, glowing brass diyas, marigold flower garlands, colorful rangoli on the floor, "
              "string lights, golden lanterns, silk cushions",
    "christmas": "Christmas, big decorated Christmas tree with ornaments and lights, red stockings, green wreath, "
                 "wrapped gift boxes, red and gold cushions, candles",
    "halloween": "Halloween, carved glowing pumpkins, spiderwebs, black bats on the wall, candles, "
                 "purple and orange lights, skeleton decor",
    "birthday": "birthday party, many colorful balloons, streamers, happy birthday banner, "
                "cake table with presents, confetti, party lights",
    "onam": "Onam festival, large flower pookalam on the floor, banana leaves, brass nilavilakku lamp, "
            "jasmine garlands, white and gold kasavu cloth, mango leaf toran",
    "pop-culture": "pop culture fan room, movie and band posters on the wall, neon sign, vinyl records, "
                   "bean bags, LED strip lights, action figures on shelves",
}

# Words people type that mean one of our themes.
_THEME_WORDS = {
    "diwali": ["diwali", "deepavali", "deepawali", "rangoli", "diya"],
    "christmas": ["christmas", "xmas", "santa", "x-mas"],
    "halloween": ["halloween", "spooky", "pumpkin"],
    "birthday": ["birthday", "balloon", "bday"],
    "onam": ["onam", "pookalam", "kerala"],
    "pop-culture": ["pop culture", "pop-culture", "poster", "neon", "anime", "fan room"],
}

_STOP = {
    "with", "that", "this", "from", "into", "have", "make", "room", "some", "your", "like",
    "want", "need", "more", "less", "very", "also", "put", "add", "decor", "decorate",
    "decorated", "decoration", "decorations", "style", "theme", "style", "please", "should",
}


def theme_scene(theme: Optional[str]) -> str:
    return THEME_SCENES.get((theme or "").lower(), "")


def infer_theme(prompt: Optional[str]) -> Optional[str]:
    """Which of our themes does the prompt talk about? None if it names none."""
    text = (prompt or "").lower()
    for theme, words in _THEME_WORDS.items():
        if any(w in text for w in words):
            return theme
    return None


def keywords(prompt: Optional[str]) -> list[str]:
    """Meaningful words (4+ letters) from the prompt, for matching product names."""
    words = re.findall(r"[a-zA-Z][a-zA-Z-]{3,}", (prompt or "").lower())
    out: list[str] = []
    for w in words:
        if w not in _STOP and w not in out:
            out.append(w)
    return out[:12]


def short_name(product_name: str, max_words: int = 5) -> str:
    """'Gesto 80 Diya Curtain Lights - Warm White ... (10 x 3 Ft)' -> 'Gesto 80 Diya Curtain Lights'."""
    name = re.sub(r"\([^)]*\)", " ", product_name or "")
    name = re.split(r"\s[|\-–—]\s|,|\|", name)[0]
    return " ".join(name.split()[:max_words]).strip()


def clip_words(text: Optional[str], n: int) -> str:
    return " ".join((text or "").split()[:n])
