"""
Streamlit UI for OncoTargetMind Agent.
"""

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from agent.graph import run_analysis

st.set_page_config(
    page_title="OncoTargetMind Agent",
    page_icon="🧬",
    layout="wide",
)

st.title("🧬 OncoTargetMind Agent")
st.caption("Biomedical Target Discovery — Minimal Runnable Version v0.1")

st.markdown("---")

# Input section
st.subheader("Clinical Input")

example_input = ("Endometrial cancer sample with PTEN downregulation, PIK3CA mutation, CCND1 upregulation. Evaluate potential therapeutic targets.")

user_input = st.text_area(
    "Enter clinical or genomic findings:",
    value=example_input,
    height=200,
    placeholder=(
        "Describe variants, up/down-regulated genes, and cancer type.\n"
        "Examples:\n"
        "  BRAF V600E, EGFR L858R\n"
        "  up: MYC, CCND1\n"
        "  down: TP53, RB1\n"
        "  NSCLC / melanoma / breast cancer"
    ),
)

col1, col2 = st.columns([1, 5])
with col1:
    analyze_btn = st.button("Analyze", type="primary", use_container_width=True)

# Analysis logic
if analyze_btn:
    if not user_input.strip():
        st.error("Please enter clinical or genomic findings.")
    else:
        with st.spinner("Analyzing..."):
            result = run_analysis(user_input)

        st.markdown("---")

        if result.get("report"):
            st.markdown(result["report"])

        # Debug: always show router output
        with st.expander("Router Debug", expanded=False):
            router = result.get("router_output", {})
            if router:
                st.json(router)

        if not result.get("error"):
            # Targets tab only for successful analysis
            scored = result.get("scored_targets", [])
            if not scored:
                st.info("No candidate targets identified.")
            else:
                with st.expander("Targets", expanded=True):
                    for i, t in enumerate(scored, 1):
                        st.markdown(f"### #{i} {t['gene']} — Score: {t['total_score']}/30 "
                                    f"({'⭐' * min(5, t['total_score'] // 8)})")
                        st.markdown(f"**Category**: {t.get('category', 'N/A')} | "
                                    f"**Variant**: {t.get('variant', 'N/A')}")
                        st.markdown(t["rationale"])
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.metric("Druggability", f"{t['druggability']}/10")
                        with c2:
                            st.metric("Specificity", f"{t['specificity']}/10")
                        with c3:
                            st.metric("Evidence Level", f"{t['evidence_level']}/10")
                        drugs = t.get("matched_drugs", [])
                        if drugs:
                            with st.expander(f"Matched Drugs ({len(drugs)})", expanded=False):
                                st.markdown(", ".join(drugs))
                        st.divider()

            with st.expander("Parsed Data", expanded=False):
                st.json(result.get("parsed", {}))
                st.json(result.get("scored_targets", []))

            with st.expander("Evidence Debug (CIViC / DGIdb)", expanded=False):
                for t in result.get("scored_targets", []):
                    ev = t.get("evidence_detail", {})
                    if ev:
                        st.markdown(f"**{t['gene']}** — source: `{ev.get('source','?')}` "
                                    f"level: `{ev.get('level','?')}` "
                                    f"confidence: `{ev.get('confidence','?')}` "
                                    f"drugs: {ev.get('drug_count',0)}")
                        if ev.get("diseases"):
                            st.markdown(f"  Diseases: {ev['diseases']}")
                        md = ev.get("match_detail", {})
                        if md:
                            st.markdown(f"  Tumor match: `{ev.get('tumor_matched', False)}` "
                                        f"method=`{md.get('method','?')}` "
                                        f"matched={md.get('matched_diseases',[])} "
                                        f"unmatched={md.get('unmatched_diseases',[])}")
                        if ev.get("description"):
                            st.caption(ev["description"][:300])
                st.divider()
                st.caption("Literature evidence (raw):")
                for t in result.get("scored_targets", []):
                    lev = t.get("literature_evidence", {})
                    if lev and lev.get("support_level"):
                        st.markdown(f"**{t['gene']}** — {lev.get('support_level')} "
                                    f"({lev.get('confidence','?')}) action=`{lev.get('action','?')}` "
                                    f"types={lev.get('evidence_types',[])}")
                        if lev.get("summary"):
                            st.caption(lev["summary"][:200])
                st.divider()
                st.caption("Literature hits:")
                for t in result.get("scored_targets", []):
                    hits = t.get("literature_hits", [])
                    if hits:
                        n_abs = sum(1 for h in hits if h.get("abstract", "").strip())
                        st.markdown(f"**{t['gene']}** — {len(hits)} papers ({n_abs} with abstracts)")
                        for h in hits[:5]:
                            st.caption(f"  [{h.get('year','')}] {h.get('title','')[:100]} (PMID:{h.get('pmid','')})")
                st.divider()
                st.json(result.get("scored_targets", []))

st.markdown("---")
st.caption("OncoTargetMind Agent v0.1 — For research use only. Not for clinical decision-making.")
