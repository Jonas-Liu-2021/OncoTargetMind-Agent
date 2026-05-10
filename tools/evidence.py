"""
Layered evidence gathering for OncoTargetMind Agent.

Priority for variants:  CIViC → DGIdb → knowledge.py (fallback)
Priority for up/down genes: DGIdb → knowledge.py (fallback)

Returns EvidenceBundle dict with:
  source, level, drugs, diseases, need_rag, rag_trigger, confidence, description
"""

from tools.civic import search_variant as civic_search
from tools.literature_query import RagTrigger


# Evidence level → numeric weight (used by scoring)
LEVEL_WEIGHTS = {"A": 10, "B": 8, "C": 6, "D": 4, "E": 2}

# Evidence level → confidence label
LEVEL_CONFIDENCE = {"A": "high", "B": "high", "C": "moderate", "D": "weak", "E": "weak"}


def _query_dgidb(genes: list[str]) -> dict[str, list[dict]]:
    """Query DGIdb GraphQL for drug-gene interactions. Returns {gene: [drug_info]}."""
    if not genes:
        return {}
    try:
        import requests
        query = """
        query DrugGene($names: [String!]!) {
          genes(names: $names) {
            nodes {
              name
              interactions {
                drug { name }
                interactionScore
              }
            }
          }
        }
        """
        resp = requests.post(
            "https://dgidb.org/api/graphql",
            json={"query": query, "variables": {"names": genes}},
            timeout=15,
        )
        if resp.status_code != 200:
            return {}
        data = resp.json()
        result = {}
        for node in data.get("data", {}).get("genes", {}).get("nodes", []):
            interactions = sorted(
                node.get("interactions", []),
                key=lambda x: -x.get("interactionScore", 0),
            )
            result[node["name"]] = [
                {"drug": i["drug"]["name"], "score": i["interactionScore"]}
                for i in interactions
            ]
        return result
    except Exception:
        return {}


def _classify_civic_evidence(evidence_list: list[dict], tumor_type: str = "") -> dict:
    """
    Classify CIViC evidence quality.
    Returns the best evidence level found, predictive status, and tumor-type match.
    """
    if not evidence_list:
        return {"best_level": None, "is_predictive": False, "is_high_quality": False,
                "drugs": [], "diseases": [], "tumor_matched": False, "match_detail": {},
                "summary": ""}

    levels = [e.get("level", "") for e in evidence_list if e.get("level")]
    best_level = "A"
    for l in ["A", "B", "C", "D", "E"]:
        if l in levels:
            best_level = l
            break

    # Predictive = SENSITIVITYRESPONSE or RESISTANCE
    predictive_items = [
        e for e in evidence_list
        if e.get("significance") in ("SENSITIVITYRESPONSE", "RESISTANCE")
    ]
    is_predictive = len(predictive_items) > 0
    is_high_quality = best_level in ("A", "B")

    # Collect drugs and diseases
    drugs = list(set(t for e in evidence_list for t in e.get("therapies", [])))
    diseases = list(set(e.get("disease", "") for e in evidence_list if e.get("disease")))

    # Three-layer tumor-type matching
    match_detail = match_tumor_to_diseases(tumor_type, diseases)
    tumor_matched = match_detail["tumor_matched"]

    summary = (
        f"CIViC: {len(evidence_list)} items, best level {best_level}, "
        f"{'predictive' if is_predictive else 'non-predictive'}, "
        f"tumor match: {match_detail['method']}"
    )

    return {
        "best_level": best_level,
        "is_predictive": is_predictive,
        "is_high_quality": is_high_quality,
        "drugs": drugs,
        "diseases": diseases,
        "tumor_matched": tumor_matched,
        "match_detail": match_detail,
        "summary": summary,
    }


def gather_variant_evidence(gene: str, variant: str, tumor_type: str = "") -> dict:
    """
    Evidence pipeline for a gene + variant.

    Returns EvidenceBundle dict:
      source, level, drugs, diseases, need_rag, rag_trigger, confidence, description
    """
    # ---- Step 1: CIViC ----
    # Map generic/Chinese variant terms to CIViC-compatible English keywords
    _GENERIC_MAP = {
        "mut": "mutation", "mutation": "mutation", "突变": "mutation",
        "amp": "amplification", "amplification": "amplification", "扩增": "amplification",
        "fusion": "fusion", "融合": "fusion", "重排": "fusion",
        "del": "deletion", "deletion": "deletion", "缺失": "deletion",
        "ins": "insertion", "insertion": "insertion", "插入": "insertion",
    }
    civic_query_variant = _GENERIC_MAP.get(variant.lower(), variant)
    civic_evidence = civic_search(gene, civic_query_variant)
    civic = _classify_civic_evidence(civic_evidence, tumor_type)

    if civic["best_level"] and civic["is_high_quality"] and civic["is_predictive"]:
        # CIViC A/B predictive → primary evidence, no RAG needed
        return {
            "source": "civic",
            "level": civic["best_level"],
            "drugs": civic["drugs"],
            "diseases": civic["diseases"],
            "tumor_matched": civic["tumor_matched"],
            "match_detail": civic.get("match_detail", {}),
            "need_rag": False,
            "rag_trigger": "",
            "confidence": "high",
            "description": civic["summary"],
        }

    # ---- Step 2: CIViC C/D/E or non-predictive → query DGIdb + mark for RAG ----
    if civic["best_level"] and (not civic["is_high_quality"] or not civic["is_predictive"]):
        dgidb_data = _query_dgidb([gene])
        dgidb_drugs = [d["drug"] for d in dgidb_data.get(gene, [])[:20]]
        all_drugs = list(set(civic["drugs"] + dgidb_drugs))

        if not civic["is_predictive"]:
            rag_trigger = RagTrigger.NON_PREDICTIVE_CIVIC_EVIDENCE
        else:
            rag_trigger = RagTrigger.LOW_CIVIC_EVIDENCE

        return {
            "source": "civic_dgidb",
            "level": civic["best_level"],
            "drugs": all_drugs,
            "diseases": civic["diseases"],
            "tumor_matched": civic["tumor_matched"],
            "match_detail": civic.get("match_detail", {}),
            "need_rag": True,
            "rag_trigger": rag_trigger,
            "confidence": LEVEL_CONFIDENCE.get(civic["best_level"], "weak"),
            "description": civic["summary"] + f" | DGIdb: {len(dgidb_drugs)} drugs",
        }

    # ---- Step 3: CIViC no results → DGIdb + RAG ----
    dgidb_data = _query_dgidb([gene])
    dgidb_drugs = [d["drug"] for d in dgidb_data.get(gene, [])[:20]]

    if dgidb_drugs:
        return {
            "source": "dgidb",
            "level": None,
            "drugs": dgidb_drugs,
            "diseases": [],
            "tumor_matched": False,
            "match_detail": {},
            "need_rag": True,
            "rag_trigger": RagTrigger.DGIDB_ONLY_CONTEXT_MISSING,
            "confidence": "weak",
            "description": f"DGIdb: {len(dgidb_drugs)} drug interactions found. Cancer relevance not confirmed.",
        }

    # ---- Step 4: Nothing in CIViC or DGIdb ----
    return {
        "source": "none",
        "level": None,
        "drugs": [],
        "diseases": [],
        "tumor_matched": False,
        "match_detail": {},
        "need_rag": True,
        "rag_trigger": RagTrigger.NO_STRUCTURED_EVIDENCE,
        "confidence": "none",
        "description": "No evidence found in CIViC or DGIdb.",
    }


def gather_gene_evidence(gene: str, direction: str, tumor_type: str = "") -> dict:
    """
    Evidence pipeline for up/down-regulated genes.
    Uses DGIdb + triggers RAG for tumor-specific context.
    """
    dgidb_data = _query_dgidb([gene])
    dgidb_drugs = [d["drug"] for d in dgidb_data.get(gene, [])[:20]]

    direction_label = "overexpression" if direction in ("up", "overexpression") else "loss"

    if dgidb_drugs:
        return {
            "source": "dgidb",
            "level": None,
            "drugs": dgidb_drugs,
            "diseases": [],
            "tumor_matched": False,
            "match_detail": {},
            "need_rag": True,
            "rag_trigger": RagTrigger.EXPRESSION_GENE_CONTEXT_NEEDED,
            "confidence": "weak",
            "description": (
                f"DGIdb: {len(dgidb_drugs)} drugs for {gene}. "
                f"Tumor-specific relevance unverified — RAG needed."
            ),
        }

    return {
        "source": "none",
        "level": None,
        "drugs": [],
        "diseases": [],
        "tumor_matched": False,
        "match_detail": {},
        "need_rag": True,
        "rag_trigger": RagTrigger.NO_STRUCTURED_EVIDENCE,
        "confidence": "none",
        "description": f"No DGIdb interactions for {gene}.",
    }


def evidence_to_scores(evidence: dict) -> dict[str, int]:
    """
    Convert evidence bundle to scoring dimensions.
    Weights: CIViC A/B predictive = high; C/D/E = mid; DGIdb-only = low.
    """
    source = evidence.get("source", "none")
    level = evidence.get("level")
    confidence = evidence.get("confidence", "none")
    has_drugs = len(evidence.get("drugs", [])) > 0

    # Druggability: depends on having drugs + source quality
    if source == "civic" and level in ("A", "B"):
        druggability = 10
    elif source in ("civic", "civic_dgidb") and level:
        druggability = 8 if has_drugs else 6
    elif has_drugs:
        druggability = 5  # DGIdb only → druggable but context unknown
    else:
        druggability = 2

    # Evidence level: strict mapping from CIViC level
    evidence_level = LEVEL_WEIGHTS.get(level, 0) if level else (3 if has_drugs else 1)

    # Specificity: higher if tumor-type evidence matches
    tumor_matched = evidence.get("tumor_matched", False)
    specificity = 8 if (source == "civic" and tumor_matched) else (5 if has_drugs else 3)

    return {
        "druggability": druggability,
        "specificity": specificity,
        "evidence_level": evidence_level,
    }


# ============================================================
# Three-layer cancer type matching
# ============================================================

import re

# Cancer acronyms for string matching
_ACRONYM_MAP = {
    "nsclc": ["non-small cell lung cancer", "non small cell lung carcinoma", "lung adenocarcinoma", "lung squamous cell carcinoma"],
    "sclc": ["small cell lung cancer", "small cell lung carcinoma"],
    "hcc": ["hepatocellular carcinoma", "liver cancer", "liver cell carcinoma"],
    "rcc": ["renal cell carcinoma", "kidney cancer"],
    "crc": ["colorectal cancer", "colorectal carcinoma", "colon cancer", "rectal cancer"],
    "gist": ["gastrointestinal stromal tumor"],
    "aml": ["acute myeloid leukemia", "acute myelogenous leukemia"],
    "cmll": ["chronic myelomonocytic leukemia"],
    "gbm": ["glioblastoma", "glioblastoma multiforme"],
    "all": ["acute lymphoblastic leukemia", "acute lymphocytic leukemia"],
    "cll": ["chronic lymphocytic leukemia"],
}

# Chinese → English from literature_query
_CANCER_ZH_TO_EN = {
    "肺腺癌": "lung adenocarcinoma", "肺鳞癌": "lung squamous cell carcinoma",
    "非小细胞肺癌": "nsclc", "小细胞肺癌": "sclc", "肺癌": "lung cancer",
    "乳腺癌": "breast cancer", "结直肠癌": "colorectal cancer",
    "胃癌": "gastric cancer", "食道癌": "esophageal cancer", "食管癌": "esophageal cancer",
    "肝细胞癌": "hepatocellular carcinoma", "肝癌": "liver cancer",
    "胰腺癌": "pancreatic cancer", "前列腺癌": "prostate cancer",
    "卵巢癌": "ovarian cancer", "甲状腺癌": "thyroid cancer",
    "黑色素瘤": "melanoma", "胶质瘤": "glioma",
    "胶质母细胞瘤": "glioblastoma", "淋巴瘤": "lymphoma",
    "白血病": "leukemia", "骨髓瘤": "myeloma",
    "肾细胞癌": "renal cell carcinoma", "鼻咽癌": "nasopharyngeal carcinoma",
    "宫颈癌": "cervical cancer", "膀胱癌": "bladder cancer",
    "胆管癌": "cholangiocarcinoma", "胃肠道间质瘤": "gist",
}


def _translate_tumor(tumor: str) -> str:
    """Translate Chinese cancer name to English."""
    if not tumor:
        return tumor
    # Already ASCII
    if all(ord(c) < 128 for c in tumor):
        return tumor.strip().lower()
    # Exact match in table
    t = tumor.strip()
    if t in _CANCER_ZH_TO_EN:
        return _CANCER_ZH_TO_EN[t]
    # Substring match
    for zh, en in _CANCER_ZH_TO_EN.items():
        if zh in t:
            return en
    # LLM fallback
    return _llm_translate_tumor(t)


def _llm_translate_tumor(tumor: str) -> str:
    """LLM fallback for unknown Chinese cancer names."""
    try:
        from tools.model_loader import generate_response
        result = generate_response(
            messages=[
                {"role": "system", "content": "You translate Chinese cancer names to English. Reply ONLY the English name."},
                {"role": "user", "content": tumor},
            ],
            max_new_tokens=64,
        )
        translation = result.strip().strip('"').strip("'").rstrip(".").strip().lower()
        has_cjk = any("一" <= c <= "鿿" for c in translation)
        if translation and not has_cjk:
            return translation
    except Exception:
        pass
    return tumor.strip().lower()


def _normalize_disease(name: str) -> str:
    """Normalize a CIViC disease name for comparison."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _expand_acronyms(name: str) -> set[str]:
    """Expand known acronyms to their full forms."""
    variants = {name}
    for acronym, expansions in _ACRONYM_MAP.items():
        if acronym in name.split():
            for exp in expansions:
                variants.add(name.replace(acronym, exp))
        # Also check: is `name` a full form of an acronym?
        norm = _normalize_disease(name)
        for exp in expansions:
            if _normalize_disease(exp) in norm:
                variants.add(acronym)
                for e2 in expansions:
                    variants.add(e2)
    return variants


def _llm_batch_match(tumor_en: str, diseases: list[str]) -> set[str]:
    """Use LLM to match which CIViC diseases correspond to the user's tumor type."""
    if not diseases:
        return set()
    try:
        from tools.model_loader import generate_response
        disease_list = "\n".join(f"- {d}" for d in diseases)
        prompt = (
            f"User's cancer type: {tumor_en}\n\n"
            f"CIViC disease names:\n{disease_list}\n\n"
            "Which of these CIViC diseases are the SAME cancer type or a SUBTYPE "
            "of the user's cancer? Return ONLY a JSON array of matching disease names, e.g. "
            '["Lung Adenocarcinoma", "NSCLC"]. If none match, return [].'
        )
        resp = generate_response(
            messages=[
                {"role": "system", "content": "You match cancer type names. Return ONLY a JSON array of matching disease names."},
                {"role": "user", "content": prompt},
            ],
            max_new_tokens=128,
        )
        import json as _json
        m = re.search(r"\[.*\]", resp, re.DOTALL)
        if m:
            return set(_json.loads(m.group(0)))
        return set()
    except Exception:
        return set()


def match_tumor_to_diseases(tumor_type: str, civic_diseases: list[str]) -> dict:
    """
    Three-layer cancer type matching between user tumor_type and CIViC diseases.

    Returns:
      tumor_matched: bool
      matched_diseases: list[str]
      unmatched_diseases: list[str]
      method: "translation" | "string" | "llm" | "none"
    """
    if not tumor_type or not civic_diseases:
        return {"tumor_matched": False, "matched_diseases": [],
                "unmatched_diseases": civic_diseases or [], "method": "none"}

    # Layer 1: Translate user tumor to English
    tumor_en = _translate_tumor(tumor_type)

    # Layer 2: String matching with acronym expansion
    tumor_norm = _normalize_disease(tumor_en)
    tumor_variants = _expand_acronyms(tumor_en)

    matched = []
    unmatched = []
    for d in civic_diseases:
        d_norm = _normalize_disease(d)
        d_variants = _expand_acronyms(d.lower())

        # Check if any variant of tumor matches any variant of disease
        matched_by_string = False
        for tv in tumor_variants:
            tv_norm = _normalize_disease(tv)
            for dv in d_variants:
                dv_norm = _normalize_disease(dv)
                if tv_norm in dv_norm or dv_norm in tv_norm:
                    matched_by_string = True
                    break
            if matched_by_string:
                break

        if matched_by_string:
            matched.append(d)
        else:
            unmatched.append(d)

    if matched and not unmatched:
        return {"tumor_matched": True, "matched_diseases": matched,
                "unmatched_diseases": [], "method": "string"}

    # Layer 3: LLM batch matching for unmatched diseases
    if unmatched and tumor_en:
        llm_matches = _llm_batch_match(tumor_en, unmatched)
        still_unmatched = [d for d in unmatched if d not in llm_matches]
        matched += list(llm_matches)

        if llm_matches:
            return {"tumor_matched": True, "matched_diseases": matched,
                    "unmatched_diseases": still_unmatched, "method": "llm"}

    return {"tumor_matched": len(matched) > 0, "matched_diseases": matched,
            "unmatched_diseases": unmatched, "method": "string" if matched else "none"}
