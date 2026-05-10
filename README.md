# 🧬 OncoTargetMind Agent

<p align="center">
  <a href="#english">English</a> | <a href="#chinese">中文</a>
</p>

---

<a id="english"></a>

AI-powered **cancer therapeutic target discovery** agent for precision oncology research.

> Input genomic variants & expression changes → **find matched drugs** → **rank by evidence** → **literature-verified report**.

## 🧠 How It Works

```mermaid
flowchart TD
    A[User Input] --> B{Intent Router}
    B -->|clinical| C[Safety Rejection]
    B -->|off-topic| C
    B -->|target_analysis| D[Structured Parser]

    D --> E{Variant?}
    E -->|yes| F[CIViC Search]
    E -->|no| G[Expression Gene]

    F --> H{CIViC result?}
    H -->|A/B predictive| I[High Confidence]
    H -->|C/D/E| J[Moderate + RAG]
    H -->|no result| K[DGIdb Search]
    K --> L[DGIdb + RAG]

    G --> M[DGIdb Search]
    M --> N[DGIdb + RAG]

    I --> O[3D Scoring]
    J --> O
    L --> O
    N --> O

    O --> P[Markdown Report]

    subgraph RAG["RAG Pipeline"]
        Q[PubMed Query Builder] --> R[Europe PMC Search]
        R --> S[LLM Evidence Extraction]
        S --> T{Boost / Neutral / Penalize}
    end

    J -.-> RAG
    L -.-> RAG
    N -.-> RAG
    T --> O
```

## 🚀 Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/OncoTargetMind-Agent.git
cd OncoTargetMind-Agent
pip install -r requirements.txt
```

Create `.env` file with your DeepSeek API key:

```
DEEPSEEK_API_KEY=sk-your-key-here
```

Run:

```bash
# Streamlit UI (recommended for testing)
python run_ui.py

# Or FastAPI server
python run_api.py
```

## 📊 Data Sources

| Source | Type | Coverage |
|--------|------|----------|
| [CIViC](https://civicdb.org) | Expert-curated variant evidence (A–E levels) | Specific variants |
| [DGIdb](https://dgidb.org) | Drug-gene interaction database | Genome-wide |
| [Europe PMC](https://europepmc.org) | Biomedical literature (abstracts) | 40M+ papers |
| DeepSeek API | LLM for parsing, routing, evidence extraction | — |

## 🏗️ Architecture

```
agent/
├── state.py           # Data models (AgentState, CandidateTarget, etc.)
├── router.py          # Intent router (rule blocklist + LLM classifier)
├── parser.py          # Rule-based fallback parser
├── nodes.py           # 5 LangGraph nodes (router → parser → candidate → scoring → report)
├── graph.py           # LangGraph workflow + conditional edges
├── knowledge.py       # Local fallback knowledge base
└── scoring.py         # 3-dimension scoring (30 pts max)

tools/
├── model_loader.py    # DeepSeek API client
├── civic.py           # CIViC v2 GraphQL client
├── evidence.py        # Layered evidence engine (CIViC → DGIdb → KB)
├── literature_query.py # RAG trigger + PubMed query builder
├── literature_search.py # Europe PMC REST API
└── literature_extract.py # LLM evidence summarization

app/
├── api.py             # FastAPI (POST /analyze)
└── streamlit_app.py   # Streamlit UI
```

## 🔬 Example

**Input** (free-text, Chinese — English also supported):

> 子宫内膜癌样本中 PTEN 下调，PIK3CA 突变，CCND1 上调，请评估潜在靶点。

**Result:**

| # | Target | Score | Source | Matched Drugs |
|---|--------|-------|--------|---------------|
| 1 | PIK3CA | 27/30 | CIViC (B-level, matched) | Taselisib, Capivasertib, Palbociclib |
| 2 | CCND1 | 13/30 | DGIdb + RAG ↑ | Palbociclib, Ribociclib, Abemaciclib |
| 3 | PTEN | 13/30 | DGIdb + RAG ↑ | Ipatasertib, Capivasertib, Everolimus |

<details>
<summary>🔍 PIK3CA — CIViC matched (click to expand)</summary>

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Druggability | 10 | CIViC B-level, predictive evidence |
| Specificity | 8 | Tumor matched: Endometrial Cancer |
| Evidence Level | 9 | CIViC base + tumor match (+1) |

**Matched Drugs** (14): Taselisib, Capivasertib, Pictilisib, Palbociclib, Temsirolimus, Trametinib, Everolimus, Ridaforolimus, Cabozantinib, plus 5 more.

> 🔬 *CIViC: 10 items, best level B, predictive, tumors matched by string matching. No RAG triggered — CIViC quality sufficient.*
</details>

<details>
<summary>📚 CCND1 — RAG-triggered with literature evidence (click to expand)</summary>

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Druggability | 5 | DGIdb drugs found, cancer context unverified |
| Specificity | 5 | Has drug interactions |
| Evidence Level | 3 | DGIdb-only base |

**Matched Drugs** (23): Palbociclib, Ribociclib, Abemaciclib, Briciclib, Tagitinin A, plus 18 more.

---

**Literature Assessment** — `moderate` (confidence: medium) · Action: ⬆ BOOST

**Evidence Types**: driver, therapeutic_target, drug_sensitivity, functional, preclinical

> CCND1 overexpression is implicated in endometrial cancer. Paper 2 (PMID 39940659) shows CCND1 overexpression is common in early-stage endometrioid carcinoma. Paper 4 (PMID 41560755) directly links CCND1/CDK4/6 axis to CDK4/6 inhibitor sensitivity in endometrial cancer, demonstrated via CRISPR screens and functional assays.

**Limitations**: Preclinical only; no clinical trial data yet.

**Source**: EXPRESSION_GENE_CONTEXT_NEEDED · 5 papers via 3 queries

| 📄 PMID | Title | Year |
|---------|-------|------|
| 41744888 | Endocrine Therapy for Endometrial Carcinoma | 2026 |
| 39940659 | Cyclin D1 Expression: Prognostic Value in Endometrial Cancer | 2025 |
| 41560755 | NEK6 as determinant of CDK4/6 inhibitor sensitivity in EC | 2025 |

</details>

<details>
<summary>📚 PTEN — RAG-triggered with literature evidence (click to expand)</summary>

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Druggability | 5 | DGIdb drugs found |
| Specificity | 5 | Has drug interactions |
| Evidence Level | 3 | DGIdb-only base |

**Matched Drugs** (22): Ipatasertib, Capivasertib, Everolimus, AZD8186, AKT Inhibitor MK2206, plus 17 more.

---

**Literature Assessment** — `moderate` (confidence: medium) · Action: ⬆ BOOST

**Evidence Types**: therapeutic_target, preclinical

> PTEN-deficient mouse model of endometrioid endometrial cancer suggests HDAC1 inhibition as therapeutic target (PMID 41563767). Review discusses PTEN mutations in endometrial cancer and synthetic lethality concept (PMID 41383404).

**Limitations**: Preclinical only (mouse models); no clinical data.

**Source**: EXPRESSION_GENE_CONTEXT_NEEDED · 5 papers via 3 queries

</details>

## ⚠️ Disclaimer

This tool is for **research use only**. It does not provide diagnosis, treatment recommendations, drug selection, dosage advice, or prognosis. Always consult a licensed oncologist for clinical decisions.

## 📄 License

MIT

---

<a id="chinese"></a>

## 🧬 OncoTargetMind Agent（中文简介）

面向精准肿瘤学研究的 AI 靶点发现智能体。

输入基因组变异与表达变化 → 匹配药物 → 证据排序 → 输出文献验证报告。

> 📝 *Full Chinese README coming soon.*

