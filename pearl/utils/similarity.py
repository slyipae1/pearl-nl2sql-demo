from __future__ import annotations

import logging
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Optional

from config import SETTINGS

logger = logging.getLogger(__name__)


@lru_cache(maxsize=512)
def _get_embedding_client():
    """Lazy-load embedding client on first call."""
    try:
        from openai import OpenAI
        
        return OpenAI(
            base_url=SETTINGS.embed_base_url,
            api_key=SETTINGS.embed_api_key,
        )
    except Exception as exc:
        logger.warning("Failed to create embedding client: %s. Falling back to sequence matcher.", exc)
        return None


@lru_cache(maxsize=512)
def _get_cached_embedding(text: str) -> Optional[list[float]]:
    """Get embedding for text with in-memory cache."""
    if not text or not SETTINGS.embed_api_key:
        return None
    
    try:
        client = _get_embedding_client()
        if not client:
            return None
        
        response = client.embeddings.create(
            model=SETTINGS.embed_model_name,
            input=text,
            encoding_format="float"
        )
        
        if response.data:
            return list(response.data[0].embedding)
    except Exception as exc:
        logger.warning("Failed to get embedding for text: %s", exc)
        return None
    
    return None


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec_a or not vec_b:
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)


def _similar(a: str, b: str) -> float:
    """
    Measure similarity between two strings.
    
    Routes to embedding-based cosine similarity if SIMILARITY_MEASURE is 'embedding_cosine',
    otherwise uses SequenceMatcher ratio (default).
    
    Returns a float in [0, 1].
    """
    a_text = str(a or "").strip()
    b_text = str(b or "").strip()
    
    if not a_text or not b_text:
        return 1.0 if a_text == b_text else 0.0
    
    # Use embedding-based similarity if configured
    if SETTINGS.similarity_measure == "SequenceMatcher":
        # Default: use SequenceMatcher
        return SequenceMatcher(None, a_text, b_text).ratio()
    else:
        embed_a = _get_cached_embedding(a_text)
        embed_b = _get_cached_embedding(b_text)
        
        if embed_a and embed_b:
            sim = _cosine_similarity(embed_a, embed_b)
            # Normalize to 0-1 range; cosine similarity can be negative but we clamp it
            return max(0.0, min(1.0, (sim + 1.0) / 2.0))
        
        # Fallback to SequenceMatcher on embedding failure
        logger.debug("Embedding retrieval failed; falling back to SequenceMatcher for similarity")
        return SequenceMatcher(None, a_text, b_text).ratio()
