# 🛋️ Indar — Backend

> The AI brain behind Indar: turns a photo of your room into a redesigned, shoppable, AR-ready space.

Indar's backend is a **FastAPI orchestration engine** that chains together image generation, vision-language product matching, and AR asset delivery into one seamless pipeline — no manual tagging, no generic stock suggestions, just *your room*, reimagined.

---

## ✨ What it does

1. 📸 **Ingests** your room photo and session context (Supabase)
2. 🎨 **Generates** a redecorated version of *your actual room* using ComfyUI + Dreamshaper 8 (img2img — grounded in your real layout and lighting, not a random inspiration pic)
3. 🧩 **Matches** products from the theme catalog (only items that have a GLB model) and plans where each one goes in the room
4. 🛒 **Bundles** matched products into a purchasable Amazon cart
5. 🕶️ **Serves** GLB assets so those exact products can be previewed in AR before you buy

---

## 🧠 Why it's interesting

The hard part isn't calling one AI model — it's making **independent stages that were never built to talk to each other** work as one pipeline:

- ComfyUI outputs *pixels*, not products
- Product matching has to turn a theme into catalog items that fit the room
- The AR step needs a GLB model to exist for whatever gets picked

So the backend enforces strict data contracts between each stage — normalizing model output, validating it against what the next stage actually needs, and folding AR-asset availability *into* the product-matching logic itself (a great visual match with no 3D model is a dead end).

---

## 🏗️ Tech Stack

| Layer | Tech |
|---|---|
| API | FastAPI |
| Image Generation | ComfyUI + Dreamshaper 8 (img2img) |
| Product Matching | Theme catalog + placement planning (no vision model needed) |
| AR Assets | GLB models |
| Storage | Supabase |
| Commerce | Amazon bundle generation |

---

## 🔮 Pipeline at a glance

```
📷 Room Photo
    ↓
🎨 ComfyUI (Dreamshaper 8) → Redecorated Visual
    ↓
🧩 Catalog matching → Real Products
    ↓
🕶️ GLB Resolution (AR-ready check)
    ↓
🛒 Purchasable Bundle + AR Preview
```

---

## 🚀 Status

Actively developed as a full end-to-end AI product pipeline — generation, understanding, commerce, and AR, all in one flow.
