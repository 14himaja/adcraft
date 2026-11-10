"""Embedding generation and vector similarity services for Hybrid RAG."""

import hashlib
import math
import httpx
import structlog
from app.config import Settings

log = structlog.get_logger()
EMBEDDING_DIM = 64  # Standardized dimension for fast deterministic vectors


class EmbeddingGenerationError(RuntimeError):
    """Raised when embedding generation fails from the configured provider."""
    pass


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculates cosine similarity between two float vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


def _deterministic_vector(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Generates a normalized deterministic dense embedding vector from text.
    
    Tokens in the text are hashed onto coordinate buckets so that texts sharing
    words or n-grams have high cosine similarity, while unrelated texts have low similarity.
    """
    clean = text.lower().strip()
    if not clean:
        return [0.0] * dim

    vec = [0.0] * dim
    words = clean.split()
    for w in words:
        # Hash each token into 3 distinct dimensions with alternating signs
        for salt in ("1", "2", "3"):
            h = int(hashlib.sha256(f"{w}_{salt}".encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
            vec[idx] += sign

    # Add bigrams for local sequence awareness
    for i in range(len(words) - 1):
        bigram = f"{words[i]}_{words[i+1]}"
        h = int(hashlib.sha256(bigram.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
        vec[idx] += sign * 1.5

    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0.0:
        return [round(x / norm, 6) for x in vec]
    return [0.0] * dim


async def _direct_gemini_embed(text: str, model_name: str, api_key: str) -> list[float]:
    """Calls Gemini embedContent REST API directly as a robust pathway."""
    clean_model = model_name.removeprefix("gemini/").removeprefix("models/")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:embedContent?key={api_key}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json={"content": {"parts": [{"text": text[:2000]}]}})
        resp.raise_for_status()
        raw_emb = resp.json().get("embedding", {}).get("values", [])
        if not raw_emb:
            raise ValueError("No embedding values in Gemini API response")
        norm = math.sqrt(sum(x * x for x in raw_emb))
        if norm > 0.0:
            return [round(x / norm, 6) for x in raw_emb]
        return raw_emb


async def generate_embedding(text: str, settings: Settings) -> list[float]:
    """Generates an embedding vector for the given text.
    
    Uses currently supported Gemini embedding model (gemini-embedding-001) or OpenAI/OpenRouter
    when configured. In scripted/test mode, generates deterministic vector.
    """
    if not text.strip():
        return [0.0] * EMBEDDING_DIM

    # In scripted/test mode, use deterministic vector
    if settings.llm_provider in ("scripted", "fake"):
        return _deterministic_vector(text)

    # Gemini provider
    if settings.llm_provider == "gemini" and settings.gemini_api_key:
        emb_model = getattr(settings, "gemini_embedding_model", "gemini-embedding-001")
        litellm_model = emb_model if emb_model.startswith("gemini/") else f"gemini/{emb_model}"
        api_key = settings.gemini_api_key

        # 1. Try LiteLLM with gemini/gemini-embedding-001
        try:
            import litellm
            res = await litellm.aembedding(
                model=litellm_model,
                input=[text[:2000]],
                api_key=api_key,
            )
            data = res.get("data")
            if data and len(data) > 0 and "embedding" in data[0]:
                raw_emb = data[0]["embedding"]
                norm = math.sqrt(sum(x * x for x in raw_emb))
                if norm > 0.0:
                    return [round(x / norm, 6) for x in raw_emb]
                return raw_emb
        except Exception as lite_exc:
            log.warning("litellm_gemini_embed_failed_trying_direct", model=litellm_model, error=str(lite_exc))

        # 2. Try direct Generative Language API call
        try:
            return await _direct_gemini_embed(text, emb_model, api_key)
        except Exception as direct_exc:
            log.warning("gemini_embedding_failed_fallback_deterministic", model=emb_model, error=str(direct_exc))
            return _deterministic_vector(text)

    # OpenAI / OpenRouter providers
    if settings.openai_api_key or settings.openrouter_api_key:
        model_name = getattr(settings, "embedding_model", "text-embedding-3-small")
        api_key = settings.openai_api_key or settings.openrouter_api_key
        try:
            import litellm
            res = await litellm.aembedding(
                model=model_name,
                input=[text[:2000]],
                api_key=api_key,
            )
            data = res.get("data")
            if data and len(data) > 0 and "embedding" in data[0]:
                raw_emb = data[0]["embedding"]
                norm = math.sqrt(sum(x * x for x in raw_emb))
                if norm > 0.0:
                    return [round(x / norm, 6) for x in raw_emb]
                return raw_emb
        except Exception as exc:
            log.warning("openai_embedding_failed_fallback_deterministic", model=model_name, error=str(exc))
            return _deterministic_vector(text)

    return _deterministic_vector(text)


