"""CIViC v2 GraphQL client — Clinical Interpretation of Variants in Cancer."""

import requests

CIVIC_URL = "https://civicdb.org/api/graphql"
TIMEOUT = 15


def search_variant(gene: str, variant: str) -> list[dict]:
    """Search CIViC for a variant and return evidence items with therapies."""
    query = """
    query SearchVariant($q: String!) {
      search(query: $q) {
        resultType
        name
        id
      }
    }
    """
    variables = {"q": f"{gene} {variant}"}
    try:
        resp = requests.post(
            CIVIC_URL,
            json={"query": query, "variables": variables},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        results = data.get("data", {}).get("search", [])
        # Get molecular profile IDs from search results
        mp_ids = [
            r["id"] for r in results
            if r.get("resultType") == "MOLECULAR_PROFILE"
        ][:3]
        if not mp_ids:
            # Fallback: use VARIANT type results
            mp_ids = [
                r["id"] for r in results
                if r.get("resultType") == "VARIANT"
            ][:3]

        # Fetch evidence for each molecular profile
        evidence_items = []
        for mp_id in mp_ids:
            evidence_items.extend(_get_evidence(mp_id))

        return evidence_items[:10]  # Cap at 10 evidence items

    except Exception:
        return []


def _get_evidence(molecular_profile_id: int) -> list[dict]:
    """Fetch evidence items for a molecular profile."""
    query = """
    query Evidence($id: Int!) {
      molecularProfile(id: $id) {
        name
        evidenceItems(first: 10) {
          nodes {
            name
            evidenceLevel
            evidenceDirection
            significance
            description
            therapies { name }
            disease { name }
            source { name }
          }
        }
      }
    }
    """
    try:
        resp = requests.post(
            CIVIC_URL,
            json={"query": query, "variables": {"id": molecular_profile_id}},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        mp = data.get("data", {}).get("molecularProfile", {})
        evidence_nodes = mp.get("evidenceItems", {}).get("nodes", [])

        result = []
        for node in evidence_nodes:
            therapies = [t["name"] for t in node.get("therapies", [])]
            result.append({
                "evidence_id": node.get("name", ""),
                "level": node.get("evidenceLevel", ""),
                "direction": node.get("evidenceDirection", ""),
                "significance": node.get("significance", ""),
                "description": node.get("description", ""),
                "therapies": therapies,
                "disease": node.get("disease", {}).get("name", ""),
                "source": node.get("source", {}).get("name", ""),
            })
        return result

    except Exception:
        return []


def search_gene_therapies(gene: str) -> list[str]:
    """Quick search for therapies associated with a gene."""
    evidence = search_variant(gene, "")
    therapies = set()
    for item in evidence:
        for t in item.get("therapies", []):
            therapies.add(t)
    return sorted(therapies)
