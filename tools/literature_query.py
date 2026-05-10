"""
Literature query builder for OncoTargetMind Agent.

Standardizes rag_trigger constants and generates PubMed/Europe PMC query strings.
Does NOT implement real RAG, embedding, vector DB, or document download.
"""

# ============================================================
# RAG trigger constants
# ============================================================

class RagTrigger:
    LOW_CIVIC_EVIDENCE = "LOW_CIVIC_EVIDENCE"
    NON_PREDICTIVE_CIVIC_EVIDENCE = "NON_PREDICTIVE_CIVIC_EVIDENCE"
    NO_CIVIC_RESULT = "NO_CIVIC_RESULT"
    DGIDB_ONLY_CONTEXT_MISSING = "DGIDB_ONLY_CONTEXT_MISSING"
    EXPRESSION_GENE_CONTEXT_NEEDED = "EXPRESSION_GENE_CONTEXT_NEEDED"
    NO_STRUCTURED_EVIDENCE = "NO_STRUCTURED_EVIDENCE"

    ALL = frozenset({
        LOW_CIVIC_EVIDENCE,
        NON_PREDICTIVE_CIVIC_EVIDENCE,
        NO_CIVIC_RESULT,
        DGIDB_ONLY_CONTEXT_MISSING,
        EXPRESSION_GENE_CONTEXT_NEEDED,
        NO_STRUCTURED_EVIDENCE,
    })


TRIGGER_DESCRIPTIONS = {
    RagTrigger.LOW_CIVIC_EVIDENCE: "CIViC C/D/E level evidence — lower quality",
    RagTrigger.NON_PREDICTIVE_CIVIC_EVIDENCE: "CIViC evidence present but non-predictive",
    RagTrigger.NO_CIVIC_RESULT: "No CIViC evidence found for this variant",
    RagTrigger.DGIDB_ONLY_CONTEXT_MISSING: "DGIdb found drugs but cancer-type context unverified",
    RagTrigger.EXPRESSION_GENE_CONTEXT_NEEDED: "Expression change detected — need tumor-specific target evidence",
    RagTrigger.NO_STRUCTURED_EVIDENCE: "No evidence in CIViC or DGIdb",
}

# ============================================================
# Query builder
# ============================================================


# Map Chinese cancer names → English (for PubMed queries)
_CANCER_ZH_TO_EN = {
    "肺腺癌": "lung adenocarcinoma",
    "肺鳞癌": "lung squamous cell carcinoma",
    "非小细胞肺癌": "NSCLC",
    "小细胞肺癌": "SCLC",
    "肺癌": "lung cancer",
    "乳腺癌": "breast cancer",
    "结直肠癌": "colorectal cancer",
    "结肠癌": "colon cancer",
    "直肠癌": "rectal cancer",
    "胃癌": "gastric cancer",
    "食道癌": "esophageal cancer",
    "食管癌": "esophageal cancer",
    "肝癌": "liver cancer",
    "肝细胞癌": "hepatocellular carcinoma",
    "胰腺癌": "pancreatic cancer",
    "前列腺癌": "prostate cancer",
    "卵巢癌": "ovarian cancer",
    "甲状腺癌": "thyroid cancer",
    "黑色素瘤": "melanoma",
    "胶质瘤": "glioma",
    "胶质母细胞瘤": "glioblastoma",
    "淋巴瘤": "lymphoma",
    "白血病": "leukemia",
    "骨髓瘤": "myeloma",
    "肾细胞癌": "renal cell carcinoma",
    "鼻咽癌": "nasopharyngeal carcinoma",
    "宫颈癌": "cervical cancer",
    "膀胱癌": "bladder cancer",
    "胆管癌": "cholangiocarcinoma",
    "胃肠道间质瘤": "GIST",
}


def _translate_tumor(tumor: str) -> str:
    """Translate Chinese cancer type to English for PubMed query compatibility.
    Uses hardcoded mapping first, then falls back to LLM translation."""
    if not tumor:
        return tumor
    # Already English
    if all(ord(c) < 128 for c in tumor):
        return tumor
    # Exact match
    if tumor.strip() in _CANCER_ZH_TO_EN:
        return _CANCER_ZH_TO_EN[tumor.strip()]
    # Substring match (e.g. "晚期肺腺癌" → "肺腺癌")
    for zh, en in _CANCER_ZH_TO_EN.items():
        if zh in tumor:
            return en
    # LLM translation fallback
    return _llm_translate_tumor(tumor)


def _llm_translate_tumor(tumor: str) -> str:
    """Use LLM to translate an unknown Chinese cancer type to English."""
    try:
        from tools.model_loader import generate_response
        result = generate_response(
            messages=[
                {"role": "system", "content": "You translate Chinese cancer names to English. Reply ONLY the English name."},
                {"role": "user", "content": tumor},
            ],
            max_new_tokens=64,
        )
        translation = result.strip().strip('"').strip("'").rstrip(".").strip()
        has_cjk = any("一" <= c <= "鿿" for c in translation)
        if translation and not has_cjk and len(translation) < 80:
            return translation
    except Exception:
        pass
    return tumor


def build_literature_queries(candidate: dict) -> list[str]:
    """
    Generate 2-3 PubMed/Europe PMC query strings based on rag_trigger.

    Expected candidate fields:
      gene, variant, tumor_type / cancer_type, direction,
      matched_drugs / therapies, rag_trigger
    """
    gene = candidate.get("gene", "")
    variant = candidate.get("variant", "")
    tumor_raw = candidate.get("tumor_type") or candidate.get("cancer_type", "")
    tumor = _translate_tumor(tumor_raw)
    direction = candidate.get("direction", "")
    drugs = candidate.get("matched_drugs") or candidate.get("therapies", [])
    trigger = candidate.get("rag_trigger", "")

    if not trigger or trigger not in RagTrigger.ALL:
        return []

    queries = _QUERY_RULES.get(trigger, _default_queries)(gene, variant, tumor, direction, drugs)
    return [q for q in queries if q]  # filter empty


def _default_queries(gene, variant, tumor, direction, drugs):
    return [
        f'"{gene}" AND "{tumor}"' if gene and tumor else "",
        f'"{gene} {variant}"' if gene and variant else f'"{gene}"',
    ]


def _low_civic(gene, variant, tumor, direction, drugs):
    qs = []
    term = f'"{gene} {variant}"' if variant else f'"{gene}"'
    if tumor:
        qs.append(f'{term} AND "{tumor}" AND (clinical OR cohort OR trial)')
        qs.append(f'{term} AND "{tumor}" AND (sensitivity OR resistance OR biomarker)')
    else:
        qs.append(f'{term} AND (clinical OR cohort OR trial)')
    return _append_drug_query(qs, gene, tumor, drugs)


def _non_predictive(gene, variant, tumor, direction, drugs):
    qs = []
    term = f'"{gene} {variant}"' if variant else f'"{gene}"'
    if tumor:
        qs.append(f'{term} AND "{tumor}" AND (therapy OR sensitivity OR resistance)')
        qs.append(f'{term} AND "{tumor}" AND (targeted therapy OR inhibitor)')
    else:
        qs.append(f'{term} AND (therapy OR sensitivity OR resistance)')
    return _append_drug_query(qs, gene, tumor, drugs)


def _dgidb_only(gene, variant, tumor, direction, drugs):
    qs = []
    term = f'"{gene} {variant}"' if variant and variant.lower() not in ("mut", "") else f'"{gene} mutation"'
    if tumor:
        qs.append(f'{term} AND "{tumor}" AND (inhibitor OR targeted therapy OR sensitivity OR resistance)')
        qs.append(f'"{gene}" AND "{tumor}" AND (biomarker OR therapeutic target)')
    else:
        qs.append(f'{term} AND (inhibitor OR targeted therapy OR sensitivity)')
    return _append_drug_query(qs, gene, tumor, drugs)


def _expression_gene(gene, variant, tumor, direction, drugs):
    qs = []
    dir_kw = direction if direction else "overexpression OR downregulated"
    if tumor:
        qs.append(f'"{gene}" AND "{tumor}" AND ({dir_kw})')
        qs.append(f'"{gene}" AND "{tumor}" AND (knockdown OR CRISPR OR dependency OR inhibitor)')
        qs.append(f'"{gene}" AND "{tumor}" AND (prognosis OR resistance OR sensitivity)')
    else:
        qs.append(f'"{gene}" AND ({dir_kw})')
        qs.append(f'"{gene}" AND (knockdown OR CRISPR OR dependency)')
    return qs[:3]


def _no_evidence(gene, variant, tumor, direction, drugs):
    qs = []
    term = f'"{gene} {variant}"' if variant and variant.lower() not in ("mut", "") else f'"{gene}"'
    if tumor:
        qs.append(f'{term} AND "{tumor}" AND (driver OR oncogene OR tumor suppressor)')
        qs.append(f'"{gene}" AND "{tumor}" AND (therapeutic target OR biomarker)')
    else:
        qs.append(f'{term} AND (driver OR oncogene OR tumor suppressor)')
    return _append_drug_query(qs, gene, tumor, drugs)


def _append_drug_query(queries, gene, tumor, drugs):
    if drugs and tumor:
        d = drugs[0] if isinstance(drugs, list) else drugs
        queries.append(f'"{gene}" AND "{tumor}" AND "{d}" AND (sensitivity OR resistance OR trial)')
    elif drugs:
        d = drugs[0] if isinstance(drugs, list) else drugs
        queries.append(f'"{gene}" AND "{d}" AND (sensitivity OR resistance OR trial)')
    return queries[:3]


_QUERY_RULES = {
    RagTrigger.LOW_CIVIC_EVIDENCE: _low_civic,
    RagTrigger.NON_PREDICTIVE_CIVIC_EVIDENCE: _non_predictive,
    RagTrigger.DGIDB_ONLY_CONTEXT_MISSING: _dgidb_only,
    RagTrigger.EXPRESSION_GENE_CONTEXT_NEEDED: _expression_gene,
    RagTrigger.NO_STRUCTURED_EVIDENCE: _no_evidence,
}
