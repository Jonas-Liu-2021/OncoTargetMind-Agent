# 🧬 OncoTargetMind Agent



<p align="center">
  <a href="#english">English</a> | <a href="#chinese">中文</a>
</p>



<a id="english"></a>

AI-powered **cancer therapeutic target discovery** agent for precision oncology research.

> Input genomic variants & expression changes → **find matched drugs** → **rank by evidence** → **literature-verified report**.

## 🧠 How It Works

```
User Input (free-text, EN/ZH)
  → Intent Router (rule + LLM guard)
  → Structured Parser (DeepSeek)
  → Evidence Pipeline:
       CIViC → DGIdb → PubMed (Europe PMC) → LLM extraction
  → 3D Scoring (druggability / specificity / evidence level)
  → Markdown Report
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

**Input** (free-text, English or Chinese):

> 子宫内膜癌样本中 PTEN 下调，PIK3CA 突变，CCND1 上调，请评估潜在靶点。

**Output** (Markdown report):

| # | Target | Score | Source | Matched Drugs |
|---|--------|-------|--------|---------------|
| 1 | PIK3CA | 26/30 | CIViC (A-level) | Alpelisib, Inavolisib, Taselisib |
| 2 | CCND1 | 18/30 | DGIdb | Palbociclib, Ribociclib, Abemaciclib |
| 3 | PTEN | 18/30 | DGIdb | Everolimus, Ipatasertib |

**Literature evidence** (PIK3CA):

- **Assessment**: moderate (confidence: medium) · **Action**: ⬆ BOOST
- **Evidence types**: drug_sensitivity, clinical, functional
- **Summary**: CIViC A-level evidence for PIK3CA in breast cancer; RAG confirms PIK3CA mutation as
  therapeutic target in endometrial cancer via PI3Kα inhibitor studies (PMID 41976288, PMID 40360883).
- **Limitations**: Evidence from wildtype context or non-mutation-specific studies; clinical trials ongoing.

| Dimension | Score |
|-----------|-------|
| Druggability | 10 |
| Specificity | 8 |
| Evidence Level | 8 |

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

