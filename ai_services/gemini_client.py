import os
import json
import logging
import hashlib
import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)

# Try importing google-genai
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


def get_genai_client():
    api_key = getattr(settings, "GEMINI_API_KEY", "") or getattr(settings, "GEN_SECRET", "")
    if not api_key or not GENAI_AVAILABLE:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.warning(f"Failed to initialize GenAI client: {e}")
        return None


def generate_content(prompt, system_instruction=None):
    """
    Call Gemini model to generate text or structured JSON.
    Falls back gracefully if unavailable.
    """
    client = get_genai_client()
    model_name = getattr(settings, "GEMINI_MODEL_ID", "gemini-3.1-flash-lite")

    if client:
        try:
            config = {}
            if system_instruction:
                config["system_instruction"] = system_instruction
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(**config) if config else None,
            )
            if response and response.text:
                return response.text
        except Exception as e:
            logger.warning(f"Gemini API call failed: {e}. Falling back.")

    return None


def generate_embedding(text):
    """
    Generate normalized float embedding vector.
    Uses Gemini embedding models (e.g. gemini-embedding-001) if available, or a deterministic fallback.
    """
    client = get_genai_client()
    if client:
        for model_id in ["gemini-embedding-001", "text-embedding-004"]:
            try:
                response = client.models.embed_content(
                    model=model_id,
                    contents=text,
                )
                if hasattr(response, "embeddings") and response.embeddings:
                    first_emb = response.embeddings[0]
                    if hasattr(first_emb, "values") and first_emb.values:
                        return list(first_emb.values)
                if hasattr(response, "embedding") and hasattr(response.embedding, "values"):
                    return list(response.embedding.values)
            except Exception as e:
                logger.debug(f"Gemini embed_content with {model_id} failed: {e}")

    # High quality deterministic pseudo-embedding fallback for dev / tests
    # Hashes tokens into a 64-dimensional dense float vector with L2 normalization
    dim = 64
    vec = np.zeros(dim, dtype=np.float32)
    words = text.lower().split()
    if not words:
        words = ["empty"]
    for i, word in enumerate(words):
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        weight = 1.0 / (1.0 + (i * 0.05))
        vec[idx] += weight * (1.0 if (h >> 4) % 2 == 0 else -1.0)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()
