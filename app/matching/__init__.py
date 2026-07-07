"""
The matching engine — JobBot's "brain".

Two layers, kept strictly separate (the spec's core design rule):
  1. gate.py   — HARD FILTERS: yes/no. A job must pass every filter the user set
                 (blank = "any"). Pure gate, no scoring.
  2. scorer.py — SOFT SCORE: of the survivors, how well does each job match the
                 resume? A 0-100 number used only to RANK. Swappable (TF-IDF now,
                 AI embeddings later) behind one interface.

engine.py runs layer 1 then layer 2 and (optionally) stores the results.
"""

from app.matching.engine import (
    ScoredJob,
    compute_and_store_matches,
    evaluate_jobs,
)
from app.matching.gate import FilterPrefs, passes_filters
from app.matching.scorer import Scorer, TfidfScorer, get_default_scorer

__all__ = [
    "FilterPrefs",
    "passes_filters",
    "Scorer",
    "TfidfScorer",
    "get_default_scorer",
    "ScoredJob",
    "evaluate_jobs",
    "compute_and_store_matches",
]
