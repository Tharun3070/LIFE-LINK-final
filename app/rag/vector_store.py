"""In-Memory Vector Store and Cosine Similarity Retrieval Engine for LifeLink RAG."""
import re
import math
from typing import List, Dict, Tuple, Optional
from pydantic import BaseModel


class DocumentChunk(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    issuing_organization: str
    source_url: str
    domain: str
    text: str
    vector: Dict[str, float] = {}


def tokenize(text: str) -> List[str]:
    """Tokenizes text into lowercase alphanumeric words, stripping punctuation and common noise words."""
    stopwords = {
        "the", "and", "is", "in", "to", "of", "a", "an", "for", "with",
        "on", "at", "by", "from", "up", "about", "into", "over", "after",
        "it", "this", "that", "are", "was", "were", "be", "been", "being",
    }
    words = re.findall(r"\b[a-zA-Z0-9_\-\+]{2,}\b", text.lower())
    return [w for w in words if w not in stopwords]


def compute_tf_vector(text: str) -> Dict[str, float]:
    """Computes an L2-normalized Term Frequency (TF) sparse vector."""
    tokens = tokenize(text)
    if not tokens:
        return {}

    tf: Dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0.0) + 1.0

    # L2 Normalization
    norm = math.sqrt(sum(v * v for v in tf.values()))
    if norm > 0:
        for k in tf:
            tf[k] /= norm

    return tf


def cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
    """Computes cosine similarity between two normalized sparse vectors."""
    if not vec1 or not vec2:
        return 0.0

    # Vectors are already L2 normalized, so cosine similarity is the dot product
    dot = 0.0
    for term, val in vec1.items():
        if term in vec2:
            dot += val * vec2[term]
    return max(0.0, min(1.0, dot))


class InMemoryVectorStore:
    """Lightweight, deterministic vector store for grounded clinical document retrieval."""

    def __init__(self):
        self._chunks: List[DocumentChunk] = []

    def add_chunk(self, chunk: DocumentChunk) -> None:
        if not chunk.vector:
            chunk.vector = compute_tf_vector(chunk.text)
        self._chunks.append(chunk)

    def clear(self) -> None:
        self._chunks.clear()

    def count(self) -> int:
        return len(self._chunks)

    def search(
        self,
        query: str,
        domain: Optional[str] = None,
        top_k: int = 3,
    ) -> List[Tuple[DocumentChunk, float]]:
        """Performs semantic similarity search with optional clinical domain filtering."""
        query_vec = compute_tf_vector(query)
        if not query_vec:
            return []

        scored_chunks: List[Tuple[DocumentChunk, float]] = []
        for chunk in self._chunks:
            if domain and chunk.domain.lower() != domain.lower():
                continue

            sim = cosine_similarity(query_vec, chunk.vector)
            if sim > 0.0:
                scored_chunks.append((chunk, sim))

        # Sort descending by similarity score
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        return scored_chunks[:top_k]
