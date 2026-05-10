"""
Rule-based input parser. Extracts variants, up/down-regulated genes,
and cancer type from free-text clinical descriptions.
"""

import re


# Regex that detects if a token looks like a codon variant (e.g., V600E, G12C)
_CODON_PATTERN = re.compile(r"^[A-Z]\d+[A-Z]$", re.IGNORECASE)


def _is_codon_variant(s: str) -> bool:
    """Check if a string looks like a variant codon (e.g. V600E, G12C) rather than a gene name."""
    return bool(_CODON_PATTERN.match(s))


VARIANT_PATTERNS = [
    # Standard notation: GENE MUTATION (e.g., BRAF V600E, EGFR L858R)
    re.compile(
        r"(?P<gene>[A-Z][A-Z0-9]+)\s+(?P<variant>[A-Z]\d+[A-Z])", re.IGNORECASE
    ),
    # Exon notation: GENE exonNdel/ins (e.g., EGFR exon19del, MET exon14skip)
    re.compile(
        r"(?P<gene>[A-Z][A-Z0-9]+)\s+(?P<variant>exon\d+\s?(?:del|ins|skip))",
        re.IGNORECASE,
    ),
    # Fusion notation: GENE fusion (e.g., ALK fusion, ROS1 fusion)
    re.compile(
        r"(?P<gene>[A-Z][A-Z0-9]+)\s+(?P<variant>fusion)", re.IGNORECASE
    ),
    # Amplification: GENE amp/amplification
    re.compile(
        r"(?P<gene>[A-Z][A-Z0-9]+)\s+(?P<variant>amp(?:lification)?)", re.IGNORECASE
    ),
    # Deletion: GENE deletion/deleted
    re.compile(
        r"(?P<gene>[A-Z][A-Z0-9]+)\s+(?P<variant>del(?:etion|eted)?)", re.IGNORECASE
    ),
    # Mutation shorthand: GENE mut/mutation (skip if gene looks like a codon)
    re.compile(
        r"(?P<gene>[A-Z][A-Z0-9]+)\s+(?P<variant>mut(?:ation)?)", re.IGNORECASE
    ),
]


def _normalize_variant(gene: str, variant: str) -> str:
    """Normalize variant string for consistent lookup."""
    v = variant.strip().lower()
    if v in ("amp", "amplification"):
        return "amp"
    if v in ("mut", "mutation"):
        return "mut"
    if v in ("del", "deletion", "deleted"):
        return "del"
    if v.startswith("exon"):
        # Normalize "exon 19 del" → "exon19del"
        v = re.sub(r"\s+", "", v)
    if v == "fusion":
        return "fusion"
    return variant.strip()


def parse_input(text: str) -> dict:
    """
    Parse free-text clinical input into structured data.

    Returns dict with keys:
        variants: list of {gene, variant, normalized}
        up_genes: list[str]
        down_genes: list[str]
        cancer_type: str
        raw_entities: list of recognized entity strings
    """
    variants = []
    up_genes = []
    down_genes = []
    cancer_type = ""
    seen = set()

    # --- Extract variants using regex patterns ---
    for pattern in VARIANT_PATTERNS:
        for match in pattern.finditer(text):
            gene = match.group("gene").upper()
            # Skip if gene looks like a variant codon (e.g., V600E matched as gene)
            if _is_codon_variant(gene):
                continue
            raw_variant = match.group("variant")
            normalized = _normalize_variant(gene, raw_variant)
            key = f"{gene} {normalized}"
            if key not in seen:
                seen.add(key)
                variants.append({
                    "gene": gene,
                    "variant": raw_variant,
                    "normalized": normalized,
                })

    # --- Extract up/down-regulated genes ---
    # Pattern: up: GENE1, GENE2 or up-regulated: GENE1
    up_pattern = re.compile(
        r"(?:up[-\s]*(?:regulated)?(?:\s*genes?)?\s*[:：])\s*([A-Za-z0-9,\s]+?)(?:\n|;|$|down|\.)",
        re.IGNORECASE,
    )
    up_match = up_pattern.search(text)
    if up_match:
        genes_str = up_match.group(1)
        for g in re.split(r"[,，;\s]+", genes_str.strip()):
            g = g.strip().upper()
            if g and re.match(r"^[A-Z][A-Z0-9]+$", g) and g not in up_genes:
                up_genes.append(g)

    # Pattern: down: GENE1, GENE2 or down-regulated: GENE1
    down_pattern = re.compile(
        r"(?:down[-\s]*(?:regulated)?(?:\s*genes?)?\s*[:：])\s*([A-Za-z0-9,\s]+?)(?:\n|;|$|up|\.)",
        re.IGNORECASE,
    )
    down_match = down_pattern.search(text)
    if down_match:
        genes_str = down_match.group(1)
        for g in re.split(r"[,，;\s]+", genes_str.strip()):
            g = g.strip().upper()
            if g and re.match(r"^[A-Z][A-Z0-9]+$", g) and g not in down_genes:
                down_genes.append(g)

    # --- Extract cancer type ---
    cancer_keywords = [
        "melanoma",
        "nsclc",
        "non-small cell lung cancer",
        "small cell lung cancer",
        "lung cancer",
        "breast cancer",
        "colorectal cancer",
        "colon cancer",
        "glioma",
        "glioblastoma",
        "ovarian cancer",
        "pancreatic cancer",
        "gist",
        "gastrointestinal stromal",
        "thyroid cancer",
        "leukemia",
        "aml",
        "lymphoma",
        "prostate cancer",
        "gastric cancer",
        "liver cancer",
        "hepatocellular",
    ]
    text_lower = text.lower()
    for kw in cancer_keywords:
        if kw in text_lower:
            cancer_type = kw
            break

    return {
        "variants": variants,
        "up_genes": up_genes,
        "down_genes": down_genes,
        "cancer_type": cancer_type,
        "raw_entities": [v["gene"] for v in variants] + up_genes + down_genes,
    }
