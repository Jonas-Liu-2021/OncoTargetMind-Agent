"""
Rule-based target scoring.
3 dimensions: druggability, specificity, evidence_level (0-10 each, max 30).

Evidence Level = base (CIViC/DGIdb) + tumor_bonus + rag_modifier (literature).
"""

from agent.state import CandidateTarget, ScoredTarget

_RAG_MODIFIER = {
    "strong":    {"high": +2, "medium": +1, "low": +1},
    "moderate":  {"high": +1, "medium":  0, "low":  0},
    "weak":      {"high":  0, "medium":  0, "low":  0},
    "conflicting":{"high":-2, "medium": -2, "low": -2},
    "none":      {"high": -1, "medium": -1, "low": -1},
}


def _compute_rag_modifier(candidate: dict) -> int:
    """Compute RAG modifier for Evidence Level. 0 if no RAG needed."""
    if not candidate.get("need_rag"):
        return 0
    ev = candidate.get("literature_evidence", {})
    if not ev:
        return 0
    support = ev.get("support_level", "none")
    confidence = ev.get("confidence", "low")
    return _RAG_MODIFIER.get(support, {}).get(confidence, 0)


def score_target(candidate: CandidateTarget) -> ScoredTarget:
    druggability = candidate.get("druggability", 1)
    specificity = candidate.get("specificity", 1)
    evidence_level = candidate.get("evidence_level", 1)
    tumor_matched = candidate.get("evidence_detail", {}).get("tumor_matched", False)
    rag_mod = _compute_rag_modifier(candidate)

    evidence_level = max(0, min(10, evidence_level + (1 if tumor_matched else 0) + rag_mod))
    total_score = druggability + specificity + evidence_level

    return ScoredTarget(
        gene=candidate["gene"],
        variant=candidate.get("variant", ""),
        rationale=candidate.get("rationale", ""),
        category=candidate.get("category", ""),
        druggability=druggability,
        specificity=specificity,
        evidence_level=evidence_level,
        total_score=total_score,
        matched_drugs=candidate.get("matched_drugs", []),
        need_rag=candidate.get("need_rag", False),
        rag_trigger=candidate.get("rag_trigger", ""),
        rag_queries=candidate.get("rag_queries", []),
        literature_hits=candidate.get("literature_hits", []),
        literature_evidence=candidate.get("literature_evidence", {}),
        evidence_detail=candidate.get("evidence_detail", {}),
    )


def rank_targets(scored: list[ScoredTarget]) -> list[ScoredTarget]:
    """Sort scored targets by total_score descending."""
    return sorted(scored, key=lambda t: t["total_score"], reverse=True)
