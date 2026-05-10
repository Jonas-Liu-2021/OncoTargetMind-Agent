"""
LangGraph node implementations for OncoTargetMind Agent.
"""

import json
import re
import logging

from agent.state import AgentState, CandidateTarget
from agent.parser import parse_input
from agent.knowledge import (
    VARIANT_DRUG_MAP,
    GENE_DRUGGABILITY,
    DOWN_GENE_STRATEGIES,
)
from agent.scoring import score_target, rank_targets

logger = logging.getLogger(__name__)

# --- Reports for non-analysis routes ---

INSUFFICIENT_INFO_REPORT = """# OncoTargetMind Agent — Insufficient Information

**Reason**: The input mentions cancer but lacks specific molecular findings.

**What is needed**:
- **Variants**: Gene mutations or alterations (e.g. BRAF V600E, EGFR amplification, ALK fusion)
- **Expression changes**: Up- or down-regulated genes (e.g. up: MYC, CCND1 / down: TP53, PTEN)
- **Cancer type** (optional but improves scoring accuracy)

**Example inputs**:
- "NSCLC with EGFR L858R and MET amplification. up: MYC. down: TP53."
- "Melanoma patient with BRAF V600E. PDL1 overexpressed."

Please provide specific genomic findings and try again.
"""

# --- Intent Router Node ---

def intent_router_node(state: AgentState) -> dict:
    """
    Route user input through the two-layer router (rule blocklist + LLM).
    Sets router_output in state; downstream routing reads this field.
    """
    from agent.router import (
        route_intent, CLINICAL_REJECTION, NON_RESEARCH_REJECTION, TECHNICAL_ERROR,
    )

    text = state.get("raw_input", "")
    router_output = route_intent(text)

    report = ""
    error = ""
    route = router_output["route"]
    intent = router_output["intent"]
    source = router_output["source"]

    if route == "input_parser":
        error = ""  # proceed to analysis
    elif route == "ask_for_more_info":
        report = INSUFFICIENT_INFO_REPORT
        error = "insufficient_info"
    elif intent == "clinical_sensitive":
        report = CLINICAL_REJECTION
        error = "rejected"
    elif source == "llm_unavailable":
        report = TECHNICAL_ERROR
        error = "rejected"
    else:
        # off_topic, general non-research
        report = NON_RESEARCH_REJECTION
        error = "rejected"

    return {
        "router_output": router_output,
        "report": report,
        "error": error,
    }

from agent.knowledge import (
    VARIANT_DRUG_MAP,
    GENE_DRUGGABILITY,
    DOWN_GENE_STRATEGIES,
)
from agent.scoring import score_target, rank_targets

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a structured data extractor. Output ONLY a JSON object, nothing else.\n\n"
    "Schema:\n"
    "{\n"
    '  "variants": [{"gene": "GENE", "variant": "MUTATION"}],\n'
    '  "up_genes": ["GENE"],\n'
    '  "down_genes": ["GENE"],\n'
    '  "cancer_type": "TYPE"\n'
    "}\n\n"
    "Rules:\n"
    "1. variants: gene-level genomic alterations including specific mutations (EGFR L858R), "
    "amplifications (MET amplification), fusions (ALK fusion), deletions (CDKN2A deletion). "
    "Gene is ONLY the gene symbol (EGFR, MET, ALK, CDKN2A). Variant is the change type "
    "(L858R, amplification, fusion, deletion). Do NOT combine gene+variant into one string.\n"
    "2. up_genes: genes described as upregulated/overexpressed/activated at expression level. "
    "Gene symbol ONLY. Do NOT put gene deletions/amplifications here — those are variants.\n"
    "3. down_genes: genes described as downregulated/lost at expression level. "
    "Gene symbol ONLY. Do NOT put gene deletions here — genomic deletions are variants.\n"
    "4. cancer_type: cancer name like NSCLC, melanoma. Empty string if not mentioned.\n"
    "5. All lists empty [] if nothing found.\n\n"
    "Examples:\n"
    "Input: NSCLC with EGFR L858R. up: MYC. down: TP53.\n"
    'Output: {"variants":[{"gene":"EGFR","variant":"L858R"}],"up_genes":["MYC"],"down_genes":["TP53"],"cancer_type":"NSCLC"}\n\n'
    "Input: Melanoma patient, BRAF V600E and KIT amplification.\n"
    'Output: {"variants":[{"gene":"BRAF","variant":"V600E"},{"gene":"KIT","variant":"amplification"}],"up_genes":[],"down_genes":[],"cancer_type":"melanoma"}\n\n'
    "Input: Colorectal cancer. KRAS G12D. up: VEGFA, EGFR. down: SMAD4.\n"
    'Output: {"variants":[{"gene":"KRAS","variant":"G12D"}],"up_genes":["VEGFA","EGFR"],"down_genes":["SMAD4"],"cancer_type":"colorectal cancer"}\n\n'
    "Input: 肺腺癌患者，检测到EGFR L858R突变和MET扩增。上调：MYC。下调：TP53。\n"
    'Output: {"variants":[{"gene":"EGFR","variant":"L858R"},{"gene":"MET","variant":"扩增"}],"up_genes":["MYC"],"down_genes":["TP53"],"cancer_type":"肺腺癌"}\n\n'
    "Input: 黑色素瘤 BRAF V600E 突变\n"
    'Output: {"variants":[{"gene":"BRAF","variant":"V600E"}],"up_genes":[],"down_genes":[],"cancer_type":"黑色素瘤"}'
)


def input_parser_node(state: AgentState) -> dict:
    """
    Parse user input via model_loader (DeepSeek API > GGUF > safetensors).
    Falls back to rule-based parser if LLM fails or produces invalid JSON.
    """
    text = state.get("raw_input", "")
    if not text.strip():
        return {"parsed": {}, "error": "Empty input. Please provide clinical details."}

    try:
        parsed = _llm_parse(text)
        # Validate required keys
        for key in ("variants", "up_genes", "down_genes", "cancer_type"):
            if key not in parsed:
                parsed[key] = [] if key != "cancer_type" else ""
        # Clean and normalize variant entries
        cleaned_variants = []
        for v in parsed.get("variants", []):
            if not isinstance(v, dict):
                continue
            gene = str(v.get("gene", "")).strip().upper()
            variant = str(v.get("variant", "")).strip()
            if not gene or not _is_valid_gene(gene):
                continue
            cleaned_variants.append({
                "gene": gene,
                "variant": variant,
                "normalized": _normalize_variant_str(variant),
            })
        parsed["variants"] = cleaned_variants
        parsed["up_genes"] = [g.upper() for g in parsed.get("up_genes", []) if isinstance(g, str) and _is_valid_gene(g)]
        parsed["down_genes"] = [g.upper() for g in parsed.get("down_genes", []) if isinstance(g, str) and _is_valid_gene(g)]

        # Amplification → also route to up_genes / Deletion → also route to down_genes
        for v in cleaned_variants:
            g = v["gene"]
            if v["normalized"] == "amp" and g not in parsed["up_genes"]:
                parsed["up_genes"].append(g)
            if v["normalized"] == "del" and g not in parsed["down_genes"]:
                parsed["down_genes"].append(g)

        return {"parsed": parsed, "error": ""}
    except Exception as e:
        logger.warning(f"LLM parsing failed: {e}. Falling back to rule-based parser.")
        parsed = parse_input(text)
        return {"parsed": parsed, "error": ""}


# Valid gene symbols: uppercase letters+digits, at least 2 chars, not just digits
_GENE_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")


def _is_valid_gene(symbol: str) -> bool:
    """Check if a string looks like a genuine gene symbol, not a variant codon like V600E."""
    s = symbol.strip().upper()
    if not _GENE_RE.match(s):
        return False
    # Exclude strings that look like variant codons: letter+digits+letter (e.g. V600E, G12C)
    if re.match(r"^[A-Z]\d+[A-Z]$", s):
        return False
    return True


def _normalize_variant_str(variant: str) -> str:
    """Normalize a variant string for knowledge base lookup (EN + ZH)."""
    v = variant.strip().lower()
    if v in ("amp", "amplification", "扩增"):
        return "amp"
    if v in ("mut", "mutation", "突变", "变异"):
        return "mut"
    if v.startswith("exon") or "外显子" in v:
        v = re.sub(r"\s+", "", v)
    if v in ("fusion", "融合", "重排"):
        return "fusion"
    if v in ("del", "deletion", "deleted", "deletions", "缺失"):
        return "del"
    if v in ("ins", "insertion", "inserted", "insertions", "插入"):
        return "ins"
    return variant.strip()


def _llm_parse(text: str) -> dict:
    """Call LLM via model_loader to extract structured data from clinical free text."""
    from tools.model_loader import generate_response

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Parse this clinical input:\n\n{text}"},
    ]

    response = generate_response(messages, max_new_tokens=512)
    return _extract_json(response)


def _extract_json(text: str) -> dict:
    """Robust JSON extraction from model output."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from ```json ... ``` code block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding the first { ... } block
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Failed to extract valid JSON from model output: {text[:200]}")


def candidate_generation_node(state: AgentState) -> dict:
    """
    Generate candidate targets with layered evidence:
      Variants: CIViC → DGIdb → knowledge.py (fallback)
      Up/down genes: DGIdb → knowledge.py (fallback)
    """
    from tools.evidence import (
        gather_variant_evidence, gather_gene_evidence, evidence_to_scores,
    )

    parsed = state.get("parsed", {})
    tumor_type = parsed.get("cancer_type", "")
    candidates: list[CandidateTarget] = []
    seen_genes: set[str] = set()

    variants = parsed.get("variants", [])
    up_genes = parsed.get("up_genes", [])
    down_genes = parsed.get("down_genes", [])

    # 1. Variant-driven candidates (CIViC → DGIdb → KB)
    for v in variants:
        gene = v["gene"]
        if gene in seen_genes:
            continue
        seen_genes.add(gene)

        # Use normalized variant for CIViC/DGIdb lookup (English, e.g. "mut" not "突变")
        evidence = gather_variant_evidence(gene, v.get("normalized", v["variant"]), tumor_type)
        scores = evidence_to_scores(evidence)
        drugs = evidence.get("drugs", [])

        # Amp/del variants: also query DGIdb for broader drug coverage
        if v.get("normalized") in ("amp", "del"):
            from tools.evidence import _query_dgidb
            dgidb_data = _query_dgidb([gene])
            dgidb_drugs = [d["drug"] for d in dgidb_data.get(gene, [])[:20]]
            drugs = list(set(drugs + dgidb_drugs))
            if dgidb_drugs and evidence["confidence"] == "high":
                evidence["description"] += f" | DGIdb: {len(dgidb_drugs)} additional drugs"

        # Build rationale from evidence
        rationale = evidence["description"]
        if evidence["need_rag"]:
            rationale += f" | [RAG needed: {evidence['rag_trigger']}]"

        # Fallback: knowledge.py for rationale enrichment only
        lookup_key = f"{gene} {v['normalized']}"
        kb_entry = VARIANT_DRUG_MAP.get(lookup_key) or VARIANT_DRUG_MAP.get(f"{gene} mut")
        if kb_entry and evidence["confidence"] in ("weak", "none"):
            scores = {
                "druggability": kb_entry["druggability"],
                "specificity": kb_entry["specificity"],
                "evidence_level": kb_entry["evidence"],
            }
            drugs = kb_entry["drugs"]
            rationale = kb_entry["rationale"] + " (source: knowledge.py fallback)"
        elif kb_entry:
            drugs = list(set(drugs + kb_entry["drugs"]))
            if evidence["confidence"] in ("weak",):
                scores = {
                    "druggability": min(kb_entry["druggability"], scores["druggability"] + 2),
                    "specificity": min(kb_entry["specificity"], scores["specificity"] + 2),
                    "evidence_level": min(kb_entry["evidence"], scores["evidence_level"] + 2),
                    }

        category = "direct_inhibitor"
        candidates.append(CandidateTarget(
            gene=gene,
            variant=v["variant"],
            rationale=rationale,
            category=category,
            druggability=scores["druggability"],
            specificity=scores["specificity"],
            evidence_level=scores["evidence_level"],

            matched_drugs=drugs,
            need_rag=evidence["need_rag"],
            rag_trigger=evidence.get("rag_trigger", ""),
            rag_queries=[],
            evidence_detail={
                "source": evidence["source"],
                "level": evidence.get("level"),
                "confidence": evidence["confidence"],
                "drug_count": len(drugs),
                "diseases": evidence.get("diseases", []),
                "tumor_matched": evidence.get("tumor_matched", False),
                "match_detail": evidence.get("match_detail", {}),
                "description": evidence.get("description", ""),
            },
        ))

    # 2. Up-regulated gene candidates (DGIdb → KB fallback)
    for gene in up_genes:
        if gene in seen_genes:
            continue
        seen_genes.add(gene)

        evidence = gather_gene_evidence(gene, "up", tumor_type)
        scores = evidence_to_scores(evidence)
        drugs = evidence.get("drugs", [])

        rationale = evidence["description"]
        if evidence["need_rag"]:
            rationale += f" | [RAG needed: {evidence['rag_trigger']}]"

        # KB fallback
        kb_entry = GENE_DRUGGABILITY.get(gene)
        if kb_entry and evidence["confidence"] == "none":
            scores = {
                "druggability": kb_entry["druggability"],
                "specificity": kb_entry["specificity"],
                "evidence_level": kb_entry["evidence"],
            }
            drugs = kb_entry["drugs"]
            rationale = kb_entry["rationale"] + " (source: knowledge.py fallback)"
        elif kb_entry:
            drugs = list(set(drugs + kb_entry["drugs"]))
            rationale += f" | KB: {kb_entry['rationale'][:100]}"

        candidates.append(CandidateTarget(
            gene=gene,
            variant="overexpression",
            rationale=rationale,
            category="direct_inhibitor",
            druggability=scores["druggability"],
            specificity=scores["specificity"],
            evidence_level=scores["evidence_level"],

            matched_drugs=drugs,
            need_rag=evidence["need_rag"],
            rag_trigger=evidence.get("rag_trigger", ""),
            rag_queries=[],
            evidence_detail={
                "source": evidence["source"],
                "level": evidence.get("level"),
                "confidence": evidence["confidence"],
                "drug_count": len(drugs),
                "diseases": evidence.get("diseases", []),
                "tumor_matched": evidence.get("tumor_matched", False),
                "match_detail": evidence.get("match_detail", {}),
                "description": evidence.get("description", ""),
            },
        ))

    # 3. Down-regulated gene candidates (DGIdb → KB fallback, synthetic lethality)
    for gene in down_genes:
        if gene in seen_genes:
            continue
        seen_genes.add(gene)

        evidence = gather_gene_evidence(gene, "down", tumor_type)
        scores = evidence_to_scores(evidence)
        drugs = evidence.get("drugs", [])

        rationale = evidence["description"]
        if evidence["need_rag"]:
            rationale += f" | [RAG needed: {evidence['rag_trigger']}]"

        # KB fallback
        kb_entry = DOWN_GENE_STRATEGIES.get(gene)
        if kb_entry and evidence["confidence"] == "none":
            scores = {
                "druggability": kb_entry["druggability"],
                "specificity": kb_entry["specificity"],
                "evidence_level": kb_entry["evidence"],
            }
            drugs = kb_entry.get("drugs", [])
            rationale = kb_entry["rationale"] + " (source: knowledge.py fallback)"
        elif kb_entry:
            drugs = list(set(drugs + kb_entry.get("drugs", [])))
            rationale += f" | KB: {kb_entry['rationale'][:100]}"

        candidates.append(CandidateTarget(
            gene=gene,
            variant="loss/down-regulation",
            rationale=rationale,
            category="synthetic_lethality",
            druggability=scores["druggability"],
            specificity=scores["specificity"],
            evidence_level=scores["evidence_level"],

            matched_drugs=drugs,
            need_rag=evidence["need_rag"],
            rag_trigger=evidence.get("rag_trigger", ""),
            rag_queries=[],
            evidence_detail={
                "source": evidence["source"],
                "level": evidence.get("level"),
                "confidence": evidence["confidence"],
                "drug_count": len(drugs),
                "diseases": evidence.get("diseases", []),
                "tumor_matched": evidence.get("tumor_matched", False),
                "match_detail": evidence.get("match_detail", {}),
                "description": evidence.get("description", ""),
            },
        ))

    # Attach literature queries + search for candidates needing RAG
    from tools.literature_query import build_literature_queries
    from tools.literature_search import search_candidate

    for c in candidates:
        c["literature_hits"] = []
        if c.get("need_rag") and c.get("rag_trigger"):
            c["rag_queries"] = build_literature_queries({
                "gene": c["gene"],
                "variant": c.get("variant", ""),
                "tumor_type": tumor_type,
                "direction": "up" if "overexpression" in c.get("variant", "") else (
                    "down" if "loss" in c.get("variant", "") else ""
                ),
                "matched_drugs": c.get("matched_drugs", []),
                "rag_trigger": c["rag_trigger"],
            })
            if c["rag_queries"]:
                c["literature_hits"] = search_candidate(c, max_per_query=3, max_total=5)
                if c["literature_hits"]:
                    from tools.literature_extract import extract_evidence

                    c["literature_evidence"] = extract_evidence({
                        "gene": c["gene"],
                        "variant": c.get("variant", ""),
                        "tumor_type": tumor_type,
                        "rag_trigger": c["rag_trigger"],
                        "rag_queries": c["rag_queries"],
                        "literature_hits": c["literature_hits"],
                    })
                else:
                    c["literature_evidence"] = {"support_level": "none", "evidence_types": [],
                        "supporting_pmids": [], "opposing_pmids": [], "summary": "No literature found.",
                        "limitations": "", "confidence": "low"}
            else:
                c["literature_evidence"] = {"support_level": "none", "evidence_types": [],
                    "supporting_pmids": [], "opposing_pmids": [], "summary": "No queries to search.",
                    "limitations": "", "confidence": "low"}
        else:
            c["rag_queries"] = []
            c["literature_evidence"] = {"support_level": "none", "evidence_types": [],
                "supporting_pmids": [], "opposing_pmids": [], "summary": "Candidate does not require literature search.",
                "limitations": "", "confidence": "low"}

    return {"candidate_targets": candidates}


def target_scoring_node(state: AgentState) -> dict:
    """Score and rank candidate targets."""
    candidates = state.get("candidate_targets", [])
    if not candidates:
        return {"scored_targets": []}

    scored = [score_target(c) for c in candidates]
    ranked = rank_targets(scored)
    return {"scored_targets": ranked}


def report_generation_node(state: AgentState) -> dict:
    """
    Generate a Markdown report from scored targets.
    No LLM — uses string templating.
    """
    parsed = state.get("parsed", {})
    scored = state.get("scored_targets", [])
    raw_input = state.get("raw_input", "")

    lines: list[str] = []
    lines.append("# OncoTargetMind Agent — Analysis Report")
    lines.append("")
    lines.append("## 1. Input Summary")
    lines.append("")
    lines.append(f"```\n{raw_input}\n```")
    lines.append("")

    # Parsed summary
    variants = parsed.get("variants", [])
    up_genes = parsed.get("up_genes", [])
    down_genes = parsed.get("down_genes", [])
    cancer_type = parsed.get("cancer_type", "")

    lines.append("| Category | Detected |")
    lines.append("|----------|----------|")
    lines.append(f"| Cancer Type | {cancer_type or 'Not specified'} |")
    variant_str = ", ".join(f"{v['gene']} {v['variant']}" for v in variants) or "None"
    lines.append(f"| Variants | {variant_str} |")
    lines.append(f"| Up-regulated Genes | {', '.join(up_genes) or 'None'} |")
    lines.append(f"| Down-regulated Genes | {', '.join(down_genes) or 'None'} |")
    lines.append("")

    # Scored targets
    lines.append("## 2. Candidate Targets (ranked by score)")
    lines.append("")

    if not scored:
        lines.append("> No targetable alterations identified from the input.")
    else:
        for i, t in enumerate(scored, 1):
            score_bar = _score_bar(t["total_score"], max_score=30)
            lines.append(f"### {i}. {t['gene']} — Score: {t['total_score']}/30 {score_bar}")
            lines.append("")
            lines.append(f"- **Variant**: {t.get('variant', 'N/A')}")
            lines.append(f"- **Category**: {t.get('category', 'N/A')}")
            lines.append(f"- **Rationale**: {t['rationale']}")
            lines.append("")
            lines.append("| Dimension | Score (0-10) |")
            lines.append("|-----------|-------------|")
            lines.append(f"| Druggability | {t['druggability']} |")
            lines.append(f"| Specificity | {t['specificity']} |")
            lines.append(f"| Evidence Level | {t['evidence_level']} |")
            lines.append("")
            drugs = t.get("matched_drugs", [])
            if drugs:
                lines.append(f"**Matched Drugs**: {', '.join(drugs)}")
            else:
                lines.append("**Matched Drugs**: None in curated knowledge base")

            if t.get("need_rag"):
                lines.append("")
                lines.append(f"**Literature Search Needed**: {t.get('rag_trigger', '')}")

                ev = t.get("literature_evidence", {})
                if ev:
                    action = ev.get("action", "neutral")
                    action_label = {"boost": "⬆ BOOST", "neutral": "— NEUTRAL", "penalize": "⬇ PENALIZE"}.get(action, action)
                    lines.append(f"**Evidence Assessment**: {ev.get('support_level', 'N/A')} "
                                 f"(confidence: {ev.get('confidence', 'N/A')}) "
                                 f"**Action**: {action_label}")
                    if ev.get("evidence_types"):
                        lines.append(f"**Evidence Types**: {', '.join(ev['evidence_types'])}")
                    if ev.get("summary"):
                        lines.append(f"> {ev['summary']}")
                    if ev.get("limitations"):
                        lines.append(f"**Limitations**: {ev['limitations']}")
                    prov = ev.get("provenance", {})
                    if prov:
                        queries = prov.get("queries_used", [])
                        papers = prov.get("papers_used", [])
                        if queries or papers:
                            lines.append(f"**Source**: {prov.get('rag_trigger', '')} "
                                         f"({len(papers)} papers via {len(queries)} queries)")

                hits = t.get("literature_hits", [])
                if hits:
                    n_abs = sum(1 for h in hits if h.get("abstract", "").strip())
                    lines.append("")
                    lines.append(f"**Top Literature Results** ({len(hits)} retrieved, {n_abs} with abstracts):")
                    for j, paper in enumerate(hits[:5], 1):
                        title = paper.get("title", "")
                        pmid = paper.get("pmid", "")
                        year = paper.get("year", "")
                        has_abs = "📄" if paper.get("abstract", "").strip() else " "
                        lines.append(f"{j}. {has_abs} {title} ({year})")
                        if pmid:
                            lines.append(f"   PMID: [{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid})")
            lines.append("")

    # Scoring methodology
    lines.append("## 3. Methodology")
    lines.append("")
    lines.append("Scoring dimensions (each 0-10, total max 30):")
    lines.append("")
    lines.append("| Dimension | Description |")
    lines.append("|-----------|-------------|")
    lines.append("| **Druggability** | Is there an approved drug or investigational agent targeting this gene? |")
    lines.append("| **Specificity** | How cancer-specific is the target vs. normal tissue? |")
    lines.append("| **Evidence Level** | Consensus evidence strength: CIViC/DGIdb base + tumor match + literature RAG modifier. |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Report generated by OncoTargetMind Agent v0.1 — For research use only.*")

    report = "\n".join(lines)
    return {"report": report}


def _score_bar(score: int, max_score: int = 40, width: int = 20) -> str:
    """Generate a visual score bar string."""
    filled = int(score / max_score * width)
    empty = width - filled
    return f"`[{'#' * filled}{'-' * empty}]`"
