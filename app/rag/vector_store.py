"""In-Memory Vector Store and Cosine Similarity Retrieval Engine for LifeLink RAG.

Provides deterministic, evidence-traceable document search with TF-IDF weighting,
clinical abbreviation expansion, and idempotent chunk management.
"""
import re
import math
from typing import List, Dict, Tuple, Optional, Any
from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    issuing_organization: str
    source_url: str
    domain: str
    text: str
    vector: Dict[str, float] = Field(default_factory=dict)


# Real clinical acronyms and abbreviations expanded for lexical bridging
CLINICAL_ABBREVIATIONS: Dict[str, List[str]] = {
    "prbc": ["packed", "red", "blood", "cells"],
    "ffp": ["fresh", "frozen", "plasma"],
    "sdp": ["single", "donor", "platelets"],
    "rdp": ["random", "donor", "platelets"],
    "cit": ["cold", "ischemic", "time"],
}


def tokenize(text: str) -> List[str]:
    """
    Tokenizes text into lowercase tokens, stripping common stopwords.
    Expands clinical acronyms while preserving blood groups and clinical metrics.
    """
    stopwords = {
        "the", "and", "is", "in", "to", "of", "a", "an", "for", "with",
        "on", "at", "by", "from", "up", "about", "into", "over", "after",
        "it", "this", "that", "are", "was", "were", "be", "been", "being",
        "must", "should", "all", "each", "every", "what", "how",
    }
    raw_tokens = re.findall(r"\b[a-zA-Z0-9_\-\+]{2,}\b|\b[abABoO][\+\-]\b", text.lower())
    tokens: List[str] = []
    for w in raw_tokens:
        clean_w = w.strip()
        if not clean_w or clean_w in stopwords:
            continue
        tokens.append(clean_w)
        # Expand verified clinical abbreviations
        if clean_w in CLINICAL_ABBREVIATIONS:
            tokens.extend(CLINICAL_ABBREVIATIONS[clean_w])
    return tokens


def cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
    """Computes cosine similarity between two normalized sparse vectors."""
    if not vec1 or not vec2:
        return 0.0

    # Dot product of L2-normalized sparse vectors equals cosine similarity
    dot = 0.0
    for term, val in vec1.items():
        if term in vec2:
            dot += val * vec2[term]
    return max(0.0, min(1.0, dot))


class InMemoryVectorStore:
    """
    Lightweight, deterministic vector store for grounded clinical document retrieval.
    Applies TF-IDF weighting and enforces idempotent chunk ingestion and document replacement.
    """

    def __init__(self):
        self._chunks: List[DocumentChunk] = []
        self._doc_registry: Dict[str, Dict[str, Any]] = {}
        self._df: Dict[str, int] = {}

    def _recompute_df(self) -> None:
        """Recomputes document frequency table across all indexed chunks."""
        self._df.clear()
        for c in self._chunks:
            for t in set(tokenize(c.text)):
                self._df[t] = self._df.get(t, 0) + 1

    def compute_tfidf_vector(self, text: str) -> Dict[str, float]:
        """Computes an L2-normalized Term Frequency - Inverse Document Frequency (TF-IDF) sparse vector."""
        tokens = tokenize(text)
        if not tokens:
            return {}

        tf: Dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0.0) + 1.0

        num_docs = max(1, len(self._chunks))
        vec: Dict[str, float] = {}
        for t, cnt in tf.items():
            doc_freq = self._df.get(t, 0)
            idf = math.log((num_docs + 1.0) / (doc_freq + 1.0)) + 1.0
            vec[t] = cnt * idf

        # L2 Normalization
        norm = math.sqrt(sum(v * v for v in vec.values()))
        if norm > 0:
            for k in vec:
                vec[k] /= norm
        return vec

    def add_chunk(self, chunk: DocumentChunk) -> None:
        """Adds or updates a document chunk idempotently."""
        for idx, existing in enumerate(self._chunks):
            if existing.chunk_id == chunk.chunk_id:
                self._chunks[idx] = chunk
                self._recompute_df()
                return
        self._chunks.append(chunk)
        self._recompute_df()

    def remove_document(self, doc_id: str) -> int:
        """Removes all chunks associated with a specific document ID. Returns removed count."""
        initial_len = len(self._chunks)
        self._chunks = [c for c in self._chunks if c.doc_id != doc_id]
        if doc_id in self._doc_registry:
            del self._doc_registry[doc_id]
        self._recompute_df()
        return initial_len - len(self._chunks)

    def register_document_metadata(self, doc_id: str, metadata: Dict[str, Any]) -> None:
        """Records provenance and version metadata for an indexed document."""
        self._doc_registry[doc_id] = metadata

    def clear(self) -> None:
        """Clears all stored chunks, document frequency tables, and document metadata."""
        self._chunks.clear()
        self._doc_registry.clear()
        self._df.clear()

    def count(self) -> int:
        """Returns total number of indexed chunks."""
        return len(self._chunks)

    def document_count(self) -> int:
        """Returns total number of unique documents indexed."""
        return len(self._doc_registry)

    def get_indexed_documents(self) -> List[Dict[str, Any]]:
        """Returns metadata list of all indexed documents."""
        return list(self._doc_registry.values())

    def search(
        self,
        query: str,
        domain: Optional[str] = None,
        top_k: int = 3,
    ) -> List[Tuple[DocumentChunk, float]]:
        """Performs TF-IDF cosine similarity search with optional clinical domain filtering."""
        query_vec = self.compute_tfidf_vector(query)
        if not query_vec:
            return []

        scored_chunks: List[Tuple[DocumentChunk, float]] = []
        for chunk in self._chunks:
            if domain and chunk.domain.lower() != domain.lower():
                continue

            chunk_vec = self.compute_tfidf_vector(chunk.text)
            sim = cosine_similarity(query_vec, chunk_vec)
            if sim > 0.0:
                scored_chunks.append((chunk, sim))

        # Sort descending by similarity score
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        return scored_chunks[:top_k]
