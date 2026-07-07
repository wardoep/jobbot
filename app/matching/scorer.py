"""
LAYER TWO — the soft score (ranking only).

A `Scorer` takes the resume text plus a list of job texts and returns one
similarity number per job, 0.0–1.0 (engine.py multiplies by 100 for display).

`TfidfScorer` is the no-dependency TF-IDF cosine method seeded from
jobbot_demo.py. Because every scorer implements the same `score()` method, we
can later drop in an `EmbeddingScorer` (Claude / sentence-transformers) WITHOUT
touching the gate, the engine, or the web app.
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections import Counter


class Scorer(ABC):
    #: short id, handy for logging/showing which engine produced a score
    name: str = "base"

    @abstractmethod
    def score(self, resume_text: str, job_texts: list[str]) -> list[float]:
        """Return one 0.0–1.0 similarity per job, aligned to job_texts order."""
        raise NotImplementedError


class TfidfScorer(Scorer):
    """TF-IDF + cosine similarity (ported from jobbot_demo.py)."""

    name = "tfidf"

    def score(self, resume_text: str, job_texts: list[str]) -> list[float]:
        if not job_texts:
            return []

        # IDF is computed over the jobs being ranked: rare words count more.
        docs = [self._tokenize(t) for t in job_texts]
        n_docs = len(docs)
        vocab = {w for doc in docs for w in doc}
        idf = {}
        for w in vocab:
            df = sum(1 for doc in docs if w in doc)
            idf[w] = math.log((n_docs + 1) / (df + 1)) + 1

        resume_vec = self._vectorize(resume_text, idf)
        resume_norm = math.sqrt(sum(v * v for v in resume_vec.values()))

        results = []
        for text in job_texts:
            job_vec = self._vectorize(text, idf)
            results.append(self._cosine(resume_vec, resume_norm, job_vec))
        return results

    # -- internals ---------------------------------------------------------
    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[a-z]+", (text or "").lower())

    def _vectorize(self, text: str, idf: dict[str, float]) -> dict[str, float]:
        tokens = self._tokenize(text)
        if not tokens:
            return {}
        counts = Counter(tokens)
        total = len(tokens)
        return {w: (counts[w] / total) * idf.get(w, 1.0) for w in counts}

    @staticmethod
    def _cosine(vec_a: dict, norm_a: float, vec_b: dict) -> float:
        if norm_a == 0:
            return 0.0
        norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
        if norm_b == 0:
            return 0.0
        shared = set(vec_a) & set(vec_b)
        dot = sum(vec_a[w] * vec_b[w] for w in shared)
        return dot / (norm_a * norm_b)


def get_default_scorer() -> Scorer:
    """The active scorer. Swap this one line to upgrade to embeddings later."""
    return TfidfScorer()
