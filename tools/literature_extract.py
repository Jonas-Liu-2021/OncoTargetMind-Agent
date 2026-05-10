"""
Lightweight literature evidence extraction via LLM.

Takes literature_hits (title + abstract) for a candidate,
calls LLM to produce a structured evidence summary.

No embedding, no vector DB, no full-text RAG.
"""

import json
import re
import logging

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = (
    "You are a cancer genomics literature reviewer. "
    "Given a gene/variant, a cancer type, and a set of paper titles + abstracts, "
    "assess the evidence for that gene/variant as a therapeutic target in that cancer.\n\n"
    "IMPORTANT RULES:\n"
    "- Only use information from the provided abstracts. Do NOT fabricate findings.\n"
    "- If abstracts mention other cancer types, note they are not specific to the query cancer.\n"
    '- If evidence is purely computational, review/preclinical, or mechanistic speculation, mark accordingly.\n'
    "- If there is conflicting evidence (sensitivity vs resistance), note it.\n\n"
    "Output ONLY a JSON object, no markdown, no explanation:\n"
    "{\n"
    '  "support_level": "strong"|"moderate"|"weak"|"none"|"conflicting",\n'
    '  "evidence_types": ["driver","therapeutic_target","drug_sensitivity","drug_resistance","prognostic","functional","preclinical","clinical"],\n'
    '  "supporting_pmids": ["PMID1"],\n'
    '  "opposing_pmids": ["PMID2"],\n'
    '  "summary": "one paragraph summarizing evidence",\n'
    '  "limitations": "evidence gaps, caveats, non-specific cancers",\n'
    '  "confidence": "high"|"medium"|"low"\n'
    "}"
)

EXTRACTION_TIMEOUT = 20


def extract_evidence(candidate: dict) -> dict:
    """
    Call LLM to extract structured evidence from literature_hits.

    Returns literature_evidence dict, or a default empty dict on failure.
    """
    hits = candidate.get("literature_hits", [])
    queries = candidate.get("rag_queries", [])
    if not hits:
        return _empty_evidence("none", "No literature hits available.", queries)

    gene = candidate.get("gene", "")
    variant = candidate.get("variant", "")
    tumor = candidate.get("tumor_type") or candidate.get("cancer_type", "")
    trigger = candidate.get("rag_trigger", "")

    # Pick top 5 for LLM: prefer abstracts, then newest
    from tools.literature_search import _pick_top_for_llm
    top_papers = _pick_top_for_llm(hits)

    # Build paper context for LLM
    paper_sections = []
    for i, p in enumerate(top_papers, 1):
        parts = [f"[Paper {i}]"]
        parts.append(f"Title: {p.get('title', '')}")
        parts.append(f"Year: {p.get('year', '')}")
        parts.append(f"Journal: {p.get('journal', '')}")
        parts.append(f"PMID: {p.get('pmid', '')}")
        if p.get("abstract"):
            parts.append(f"Abstract: {p['abstract'][:800]}")
        else:
            parts.append("Abstract: (not available)")
        paper_sections.append("\n".join(parts))

    papers_text = "\n\n".join(paper_sections)

    user_message = (
        f"Gene: {gene}\n"
        f"Variant: {variant or 'N/A'}\n"
        f"Cancer type: {tumor or 'Not specified'}\n"
        f"Evidence trigger: {trigger}\n\n"
        f"Literature to review:\n{papers_text}"
    )

    try:
        from tools.model_loader import generate_response

        response = generate_response(
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_new_tokens=1536,
        )
        result = _parse_json(response)
        if result and "support_level" in result:
            result.setdefault("evidence_types", [])
            result.setdefault("supporting_pmids", [])
            result.setdefault("opposing_pmids", [])
            result.setdefault("summary", "")
            result.setdefault("limitations", "")
            result.setdefault("confidence", "low")
            result["action"] = _compute_action(
                result.get("support_level", ""),
                result.get("confidence", ""),
            )
            result["provenance"] = {
                "rag_trigger": trigger,
                "queries_used": queries,
                "papers_used": [
                    {"pmid": p.get("pmid", ""), "title": p.get("title", ""), "year": p.get("year", "")}
                    for p in hits[:5] if p.get("title")
                ],
            }
            return result

        logger.warning(f"LLM extraction returned invalid JSON: {response[:200]}")
        return _empty_evidence("none", "LLM response could not be parsed.", queries)

    except Exception as e:
        logger.warning(f"Literature extraction failed: {e}")
        return _empty_evidence("none", f"Extraction error: {e}", candidate.get("rag_queries", []))


def _parse_json(text: str) -> dict | None:
    """Robust JSON parsing, including truncated JSON recovery."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # Truncated JSON recovery: try to close unclosed braces
    m = re.search(r"\{[\s\S]*", text)
    if m:
        truncated = m.group(0)
        # Count open vs close braces
        open_count = truncated.count("{") - truncated.count("}")
        if open_count > 0:
            truncated += "}" * open_count
        open_brackets = truncated.count("[") - truncated.count("]")
        if open_brackets > 0:
            truncated += "]" * open_brackets
        try:
            return json.loads(truncated)
        except json.JSONDecodeError:
            pass
    return None


def _empty_evidence(support_level: str, reason: str, queries: list | None = None) -> dict:
    return {
        "support_level": support_level,
        "evidence_types": [],
        "supporting_pmids": [],
        "opposing_pmids": [],
        "summary": reason,
        "limitations": "",
        "confidence": "low",
        "action": "neutral",
        "provenance": {
            "rag_trigger": "",
            "queries_used": queries or [],
            "papers_used": [],
        },
    }


def _compute_action(support_level: str, confidence: str) -> str:
    if support_level == "conflicting":
        return "penalize"
    if support_level in ("strong", "moderate") and confidence in ("high", "medium"):
        return "boost"
    return "neutral"
