import json
import math
import hashlib
import urllib.request
from typing import List
from core.config import settings

EMBEDDING_DIMENSION = 768

def _fallback_embedding(text: str, dim: int = EMBEDDING_DIMENSION) -> List[float]:
    """
    Deterministic semantic hash embedding fallback (768-dim) used
    when local Ollama embedding model is offline or downloading.
    """
    vec = [0.0] * dim
    words = text.lower().split()
    if not words:
        return vec

    for i, word in enumerate(words):
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        # Apply word position weighting
        weight = 1.0 / math.sqrt(i + 1)
        vec[idx] += weight

    # Normalize vector to unit length
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec

def get_embedding(text: str) -> List[float]:
    """Generates a 768-dimensional embedding using local Ollama model."""
    cleaned = text.strip()
    if not cleaned:
        return [0.0] * EMBEDDING_DIMENSION

    url = f"{settings.OLLAMA_BASE_URL}/api/embeddings"
    payload = {
        "model": settings.EMBEDDING_MODEL,
        "prompt": cleaned[:4000]
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            emb = data.get("embedding", [])
            if emb and len(emb) == EMBEDDING_DIMENSION:
                return emb
            elif emb:
                # Pad or truncate if dimensions differ
                if len(emb) < EMBEDDING_DIMENSION:
                    emb += [0.0] * (EMBEDDING_DIMENSION - len(emb))
                return emb[:EMBEDDING_DIMENSION]
    except Exception:
        pass

    # Use robust fallback
    return _fallback_embedding(cleaned, EMBEDDING_DIMENSION)

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculates cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
