from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import re
from typing import Any

import httpx

from .config import resolve_hf_api_token, settings

logger = logging.getLogger("sas.greeting_image")


def _slugify(text: str, max_len: int = 40) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned[:max_len] or "secret"


def _prompt_from_secret(secret_text: str) -> str:
    # Deterministic transformation that keeps intent while making image generation robust.
    return (
        f"Create a unique personal security greeting illustration that represents: '{secret_text}'. "
        f"Style: {settings.image_style_preset}. "
        "No text, no letters, no numbers, no watermark. "
        "Centered composition, high contrast, memorable iconography."
    )


def _seed_for_secret(secret_text: str) -> int:
    digest = hashlib.sha256(secret_text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _parse_image_size(image_size: str) -> tuple[int, int]:
    match = re.match(r"^\s*(\d+)\s*x\s*(\d+)\s*$", image_size)
    if not match:
        return 1024, 1024
    return int(match.group(1)), int(match.group(2))


def _extract_image_bytes(payload: dict[str, Any]) -> bytes | None:
    # Some providers return JSON with base64/image URLs.
    if isinstance(payload.get("image"), str) and payload["image"].startswith("data:image"):
        _, b64_payload = payload["image"].split(",", 1)
        return base64.b64decode(b64_payload)

    candidates = []
    for key in ("images", "output", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            candidates.extend(value)

    for item in candidates:
        if not isinstance(item, dict):
            continue
        b64_value = item.get("b64_json") or item.get("base64")
        if isinstance(b64_value, str):
            return base64.b64decode(b64_value)
        url_value = item.get("url")
        if isinstance(url_value, str) and url_value.startswith("http"):
            with httpx.Client(timeout=60.0) as client:
                res = client.get(url_value)
                if res.status_code == 200 and res.content:
                    return res.content
    return None


def _pil_to_png_bytes(image_obj: Any) -> bytes:
    """Convert a PIL.Image returned by InferenceClient.text_to_image into PNG bytes."""
    buffer = io.BytesIO()
    image_obj.save(buffer, format="PNG")
    return buffer.getvalue()


def _generate_image_hf(prompt: str, seed: int) -> bytes:
    """Generate an image via Hugging Face Inference Providers.

    Uses `huggingface_hub.InferenceClient.text_to_image` so the request is routed through HF
    to whichever provider currently serves the configured model (e.g. fal-ai, replicate).
    The legacy `api-inference.huggingface.co/models/<id>` URL is no longer used because most
    image-generation models (incl. FLUX) are not exposed there.
    """
    token = resolve_hf_api_token()
    if not token:
        logger.error(
            "_generate_image_hf: no token (checked settings.hf_api_token and env "
            "HF_API_TOKEN, HF_TOKEN, HUGGING_FACE_HUB_TOKEN)"
        )
        raise RuntimeError("HF_API_TOKEN is not configured.")

    try:
        from huggingface_hub import InferenceClient
        from huggingface_hub.errors import HfHubHTTPError
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is not installed. Run: pip install --upgrade huggingface_hub"
        ) from exc

    provider = (getattr(settings, "image_inference_provider", "auto") or "auto").strip() or "auto"
    width, height = _parse_image_size(settings.image_size)

    logger.info(
        "_generate_image_hf: model=%s provider=%s size=%dx%d seed=%d",
        settings.image_model,
        provider,
        width,
        height,
        seed,
    )

    client = InferenceClient(provider=provider, api_key=token, timeout=120)

    # text_to_image accepts seed/width/height; some providers ignore unknown kwargs.
    try:
        image_obj = client.text_to_image(
            prompt,
            model=settings.image_model,
            width=width,
            height=height,
            seed=seed,
        )
    except HfHubHTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        body = ""
        try:
            body = exc.response.text  # type: ignore[union-attr]
        except Exception:
            body = str(exc)
        body_short = (body or "")[:1500]
        if status in (401, 403):
            raise RuntimeError(
                "Hugging Face authentication failed (HTTP "
                f"{status}). Check your HF_API_TOKEN scope (needs Inference) and that the "
                "model is accepted on your Hub account. Provider response: " + body_short
            ) from exc
        if status == 402 or "credit" in body.lower() or "quota" in body.lower():
            raise RuntimeError(
                "Hugging Face Inference Providers reported insufficient credits/quota for "
                f"model {settings.image_model!r}. Free users get ~$0.10/month; PRO gets ~$2/month. "
                "Add credits at https://huggingface.co/settings/billing or pick a cheaper model. "
                "Provider response: " + body_short
            ) from exc
        if status == 404:
            raise RuntimeError(
                f"Model {settings.image_model!r} is not available via Inference Providers "
                f"(provider={provider}). Pick a supported model from "
                "https://huggingface.co/models?inference_provider=fal-ai&pipeline_tag=text-to-image "
                "or set IMAGE_INFERENCE_PROVIDER to a different provider. Response: "
                + body_short
            ) from exc
        raise RuntimeError(
            f"Hugging Face Inference Providers call failed (HTTP {status}): {body_short}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Hugging Face image generation error: {exc}") from exc

    if image_obj is None:
        raise RuntimeError("Hugging Face image generation returned no image.")

    if isinstance(image_obj, (bytes, bytearray)):
        return bytes(image_obj)
    if hasattr(image_obj, "save"):  # PIL.Image
        return _pil_to_png_bytes(image_obj)
    raise RuntimeError(
        f"Unexpected image return type from InferenceClient: {type(image_obj).__name__}"
    )


def get_image_generation_health() -> dict[str, Any]:
    """Return configuration and lightweight connectivity checks for image generation."""
    provider = settings.image_provider.lower().strip()
    health: dict[str, Any] = {
        "provider": provider,
        "model": settings.image_model,
        "configured": False,
        "connectivity_ok": False,
        "details": "",
    }
    if provider not in {"hf", "huggingface"}:
        health["details"] = "Unsupported image provider. Expected 'hf'."
        return health
    if not resolve_hf_api_token():
        health["details"] = (
            "HF_API_TOKEN is missing (checked settings and env HF_API_TOKEN, HF_TOKEN, HUGGING_FACE_HUB_TOKEN)."
        )
        return health
    if not settings.image_model:
        health["details"] = "IMAGE_MODEL is missing."
        return health

    health["configured"] = True
    health["inference_provider"] = (
        getattr(settings, "image_inference_provider", "auto") or "auto"
    )
    model_url = f"https://huggingface.co/api/models/{settings.image_model}"
    headers = {"Authorization": f"Bearer {resolve_hf_api_token()}"}
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(model_url, headers=headers)
        if response.status_code == 200:
            health["connectivity_ok"] = True
            health["details"] = (
                "Model exists on the Hub. Actual generation is routed through Inference Providers; "
                "use POST /auth/register to verify quota and provider routing."
            )
        else:
            health["details"] = f"Model lookup failed ({response.status_code})."
    except Exception as exc:
        health["details"] = f"Connectivity check failed: {exc}"
    return health


def generate_decoy_greeting_image(seed_key: str, decoy_index: int, decoy_text: str) -> tuple[bytes, str]:
    """HF-generated decoy unrelated to any user secret (deterministic per seed key + index)."""
    prompt = (
        f"Create a decoy security illustration representing: '{decoy_text}'. "
        "Must be unrelated to any specific user's secret image. "
        "No text, no letters, no numbers, no watermark, no logos. "
        f"Style: {settings.image_style_preset}."
    )
    seed = int(
        hashlib.sha256(f"decoy:{seed_key}:{decoy_index}".encode("utf-8")).hexdigest()[:8],
        16,
    )
    image_bytes = _generate_image_hf(prompt, seed)
    return image_bytes, "image/png"


def generate_greeting_image(secret_text: str) -> tuple[bytes, str, int, str]:
    """Generate deterministic greeting image bytes and reproducibility metadata."""
    provider = settings.image_provider.lower().strip()
    if provider not in {"hf", "huggingface"}:
        raise RuntimeError("Only image_provider=hf is supported in this build.")

    prompt = _prompt_from_secret(secret_text)
    seed = _seed_for_secret(secret_text)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    image_bytes = _generate_image_hf(prompt, seed)
    # PNG is the canonical storage format currently generated by provider calls.
    return image_bytes, "image/png", seed, prompt_hash

