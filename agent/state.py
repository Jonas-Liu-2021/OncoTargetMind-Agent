from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class CandidateTarget(TypedDict):
    gene: str
    variant: str
    rationale: str
    category: str  # "direct_inhibitor", "synthetic_lethality", "pathway_target"
    need_rag: bool
    rag_trigger: str  # RagTrigger enum value or ""
    rag_queries: list[str]
    literature_hits: list[dict]
    literature_evidence: dict
    evidence_detail: dict  # debug: CIViC/DGIdb raw summary


class ScoredTarget(TypedDict):
    gene: str
    variant: str
    rationale: str
    category: str
    druggability: int
    specificity: int
    evidence_level: int
    total_score: int
    matched_drugs: list[str]
    need_rag: bool
    rag_trigger: str
    rag_queries: list[str]
    literature_hits: list[dict]
    literature_evidence: dict
    evidence_detail: dict


class RouterOutput(TypedDict):
    intent: str
    route: str
    source: str
    confidence: float
    reason: str


class AgentState(TypedDict):
    raw_input: str
    router_output: RouterOutput
    parsed: dict
    candidate_targets: list[CandidateTarget]
    scored_targets: list[ScoredTarget]
    report: str
    error: str
    messages: Annotated[list, add_messages]
