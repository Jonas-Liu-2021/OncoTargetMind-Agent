"""
Literature search via Europe PMC REST API.

Searches rag_queries against Europe PMC, returns top-N papers.
No embedding, no vector DB, no LLM summarization — just metadata + abstracts.
"""

import requests

BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
TIMEOUT = 15
MAX_RESULTS = 5


MAX_RESULTS_PER_QUERY = 5  # per-query
MAX_TOTAL_RETRIEVED = 10
MAX_FOR_LLM = 5


def search_single(query: str, max_results: int = MAX_RESULTS_PER_QUERY) -> list[dict]:
    """Search Europe PMC with a single query. Returns list of paper dicts."""
    try:
        resp = requests.get(
            BASE_URL,
            params={
                "query": query,
                "resultType": "core",
                "pageSize": max_results,
                "format": "json",
            },
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        results = data.get("resultList", {}).get("result", [])
        papers = []
        for r in results:
            papers.append({
                "title": r.get("title", ""),
                "pmid": r.get("pmid", ""),
                "pmcid": r.get("pmcid", ""),
                "doi": r.get("doi", ""),
                "journal": r.get("journalTitle", ""),
                "year": r.get("pubYear", ""),
                "authors": r.get("authorString", ""),
                "abstract": r.get("abstractText", ""),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}" if r.get("pmid") else r.get("doi", ""),
                "query_used": query,
            })
        return papers

    except Exception:
        return []


def _has_abstract(p: dict) -> bool:
    return bool(p.get("abstract", "").strip())


def _pick_top_for_llm(papers: list[dict], n: int = MAX_FOR_LLM) -> list[dict]:
    """Pick top-N papers for LLM: prefer papers with abstracts, then by year desc."""
    with_abs = [p for p in papers if _has_abstract(p)]
    without_abs = [p for p in papers if not _has_abstract(p)]
    with_abs.sort(key=lambda p: p.get("year", "0"), reverse=True)
    without_abs.sort(key=lambda p: p.get("year", "0"), reverse=True)
    selected = (with_abs + without_abs)[:n]
    return selected


def search_candidate(candidate: dict, max_per_query: int = MAX_RESULTS_PER_QUERY,
                     max_total: int = MAX_TOTAL_RETRIEVED) -> list[dict]:
    """
    Search for literature relevant to a candidate target.
    Retrieves up to max_total papers, then picks top 5 by abstract+years for LLM.
    """
    queries = candidate.get("rag_queries", [])
    if not queries:
        return []

    seen_pmids = set()
    all_papers = []

    for query in queries[:3]:
        papers = search_single(query, max_per_query)
        for p in papers:
            if p["pmid"] not in seen_pmids:
                seen_pmids.add(p["pmid"])
                all_papers.append(p)
            if len(all_papers) >= max_total:
                break
        if len(all_papers) >= max_total:
            break

    return all_papers[:max_total]
