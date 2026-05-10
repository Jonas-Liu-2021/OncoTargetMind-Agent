<div align="right">
  <a href="#english">English</a> | <a href="#chinese">中文</a>
</div>

---

<a id="english"></a>

# 🧬 OncoTargetMind Agent

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

**Input:**

> NSCLC patient with EGFR L858R mutation and MET amplification.
> up: MYC, CCND1
> down: TP53, CDKN2A

**Output:**

| Target | Score | Matched Drugs |
|--------|-------|---------------|
| EGFR | 32/30 | Osimertinib, Gefitinib, Erlotinib |
| BRAF | 31/30 | Vemurafenib, Dabrafenib, Encorafenib |
| CDKN2A | 23/30 | Palbociclib, Ribociclib, Abemaciclib |

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

