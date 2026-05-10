"""
Two-layer intent router for OncoTargetMind Agent (research-use only).

Pipeline:
  1. Rule blocklist — catch clear clinical decision-making requests
  2. LLM router — classify intent semantically
  3. Both must pass → proceed; either blocks → rejection
"""

import re
import json
import logging
from agent.state import RouterOutput

logger = logging.getLogger(__name__)

# ============================================================
# 1. Rule blocklist — only catch clear clinical requests
#    Goal: minimize false positives. Research queries should pass.
# ============================================================

# Only patterns that clearly indicate clinical decision-making or personal crisis.
# "我" alone, "我们", "你", "能" are NOT matched — they'd cause too many false positives.
_CLINICAL_BLOCKLIST = [
    # Clear drug/treatment selection for a specific case
    re.compile(r"(?:应该|推荐|建议|可以)\s*(?:吃|用|选|换)\s*(?:什么|哪种|哪个|什么|哪)\s*(?:药|方案|治疗|靶向)"),
    re.compile(r"哪种\s*(?:药|方案|治疗|靶向药)\s*(?:最|更|比较)\s*(?:好|合适|有效)"),
    re.compile(r"用什么\s*(?:药|方案|靶向药|办法)"),
    # Dosage / prescribing
    re.compile(r"(?:剂量|用量|吃多少|用多少|开药|给药|处方)"),
    # Prognosis / survival
    re.compile(r"(?:还能活|生存期|生存率|能活多久|还能不能活|还能治吗|是不是晚期|有没有救)"),
    # Emergency
    re.compile(r"(?:紧急|急救|快不行了|疼得受不了|马上不行|病危)"),
    # English equivalents
    re.compile(r"(?:should|could|can)\s+(?:I|we)\s+(?:take|use|get|try|start)\s+", re.IGNORECASE),
    re.compile(r"what\s+(?:drug|medication|treatment|therapy|dose|dosage)\s+(?:should|can|could)\s+I", re.IGNORECASE),
    re.compile(r"how long\s+(?:do|will)\s+I\s+(?:have|live|survive)", re.IGNORECASE),
]


def _rule_blocklist_check(text: str) -> tuple[bool, str]:
    """
    Returns (blocked, reason).
    blocked=True means input matches a clinical decision pattern → reject.
    """
    for pattern in _CLINICAL_BLOCKLIST:
        m = pattern.search(text)
        if m:
            return True, f"Matched clinical pattern: {m.group(0)[:60]}"
    return False, ""


# ============================================================
# 2. LLM Router
# ============================================================

ROUTER_SYSTEM_PROMPT = (
    "You are an intent classifier for a cancer genomics research agent. "
    "Classify the user's input into exactly one intent. "
    "Output ONLY a JSON object, no markdown, no explanation.\n\n"
    "Intents:\n"
    '- "target_analysis": User provides or asks about genomic findings (variants, expression changes) '
    "in a research context. Includes case descriptions, gene lists, or requests for target identification.\n"
    '- "clinical_sensitive": User is asking for personal medical advice, treatment recommendations, '
    "drug selection, dosage, prognosis, or describing a real patient case with personal stakes.\n"
    '- "insufficient_info": Cancer-related research query but lacks specific molecular data.\n'
    '- "off_topic": Not related to cancer genomics research.\n\n'
    "JSON schema:\n"
    '{"intent": "<intent>", "reason": "<one sentence>"}\n\n'
    "Examples:\n"
    'Input: "NSCLC patient with EGFR L858R and MET amplification, analyze targets"\n'
    'Output: {"intent":"target_analysis","reason":"Clear variant findings in NSCLC for target analysis"}\n\n'
    'Input: "肺腺癌 EGFR L858R 突变，帮我分析靶点"\n'
    'Output: {"intent":"target_analysis","reason":"肺腺癌靶点分析请求"}\n\n'
    'Input: "我应该吃什么药治疗肺癌？"\n'
    'Output: {"intent":"clinical_sensitive","reason":"Personal treatment inquiry"}\n\n'
    'Input: "Tell me about lung cancer"\n'
    'Output: {"intent":"insufficient_info","reason":"Cancer-related but no molecular data"}\n\n'
    'Input: "What is the weather today?"\n'
    'Output: {"intent":"off_topic","reason":"Not related to cancer genomics"}\n\n'
    'Input: "什么是EGFR基因？"\n'
    'Output: {"intent":"off_topic","reason":"General biology question"}\n\n'
    'Input: "从科研角度分析KRAS G12C在结直肠癌中的靶向策略"\n'
    'Output: {"intent":"target_analysis","reason":"Research-oriented analysis of KRAS G12C in CRC"}\n\n'
    'Input: "肺腺癌患者，检测到EGFR L858R突变，请评估潜在治疗靶点"\n'
    'Output: {"intent":"target_analysis","reason":"肺腺癌靶点评估请求"}\n\n'
    'Input: "我妈确诊了肺癌，我该怎么办"\n'
    'Output: {"intent":"clinical_sensitive","reason":"Personal family medical situation"}'
)

LLM_ROUTER_TIMEOUT = 10


def _call_llm_router(text: str) -> dict | None:
    """Call DeepSeek API to classify intent. Returns parsed dict or None on failure."""
    try:
        from tools.model_loader import _get_deepseek_key, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
        import requests

        key = _get_deepseek_key()
        if not key:
            logger.info("No API key for LLM router")
            return None

        messages = [
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Classify this input:\n\n{text}"},
        ]

        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": messages,
                "max_tokens": 128,
                "temperature": 0.0,
                "stream": False,
            },
            timeout=LLM_ROUTER_TIMEOUT,
        )

        if resp.status_code != 200:
            logger.warning(f"LLM router HTTP {resp.status_code}")
            return None

        raw = resp.json()["choices"][0]["message"]["content"].strip()
        return _parse_router_json(raw)

    except Exception as e:
        logger.warning(f"LLM router failed: {e}")
        return None


def _parse_router_json(text: str) -> dict | None:
    """Robust JSON parsing for LLM router output."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


# ============================================================
# 3. Rejection messages
# ============================================================

CLINICAL_REJECTION = """# OncoTargetMind Agent

我非常理解你现在可能会感到担心或不安。癌症相关问题往往涉及具体病情、检查结果、分期、既往治疗、身体状况等多方面信息，需要由肿瘤科医生或多学科诊疗团队结合完整资料进行判断。

需要说明的是，我是一个面向企业研发和科研场景的肿瘤靶点发现智能体，主要用于公共数据分析、机制假设生成、候选靶点评估和文献证据整合。**我不能提供诊断、治疗方案选择、用药建议、预后判断或个体化临床决策建议。**

如果你正在为自己或家人的病情寻求帮助，建议尽快咨询正规医院的肿瘤科医生，并携带病理报告、影像检查、基因检测报告和既往治疗记录等资料。

如果你希望从科研角度了解某种癌症、基因突变、表达变化或潜在靶点，可以把问题改写为科研问题，例如：

> "从科研角度分析 EGFR 突变在肺腺癌中的相关通路和潜在靶点。"

在这种非个体化、研究用途的前提下，我可以继续帮助你分析。
"""

NON_RESEARCH_REJECTION = """# OncoTargetMind Agent

你输入的内容似乎不是肿瘤靶点研究相关的科研问题。

**我是什么：**
我是一个面向肿瘤靶点发现的科研智能体，帮助研究者解析基因组变异、筛选候选靶点、评估证据等级。

**我能做什么：**
- 输入基因变异信息（如 BRAF V600E、EGFR L858R），分析潜在靶点和匹配药物
- 输入上下调基因（如 up: MYC / 下调: TP53），评估通路靶向策略
- 输入癌种 + 分子信息，生成靶点排序报告

**示例输入：**
- "非小细胞肺癌，检测到 EGFR L858R 突变和 MET 扩增"
- "NSCLC with BRAF V600E, up: MYC, CCND1, down: TP53, CDKN2A"
- "从科研角度分析 KRAS G12C 在结直肠癌中的靶向策略"

请将问题改写为研究用途的基因组分析请求后重试。
"""

TECHNICAL_ERROR = """# OncoTargetMind Agent

抱歉，LLM 路由服务暂不可用，无法判断你的输入意图。请稍后重试。
"""

# ============================================================
# 4. Main entry point
# ============================================================

def route_intent(text: str) -> RouterOutput:
    """
    Two-layer router:
      1. Rule blocklist → block clinical decision requests
      2. LLM router → classify intent
      Both pass → proceed; either blocks/errors → rejection
    """
    if not text or not text.strip():
        return RouterOutput(
            intent="off_topic",
            route="rejected",
            source="rule_blocklist",
            confidence=1.0,
            reason="Empty input.",
        )

    # ---- Layer 1: Rule blocklist ----
    blocked, block_reason = _rule_blocklist_check(text)
    if blocked:
        return RouterOutput(
            intent="clinical_sensitive",
            route="rejected",
            source="rule_blocklist",
            confidence=1.0,
            reason=block_reason,
        )

    # ---- Layer 2: LLM router ----
    llm_result = _call_llm_router(text)

    if not llm_result or not llm_result.get("intent"):
        # LLM unavailable → reject (MVP: no fallback)
        return RouterOutput(
            intent="off_topic",
            route="rejected",
            source="llm_unavailable",
            confidence=1.0,
            reason="LLM router unavailable. Please try again.",
        )

    intent = llm_result["intent"]
    reason = llm_result.get("reason", "")

    # ---- Resolve route ----
    if intent == "target_analysis":
        route = "input_parser"
    elif intent == "insufficient_info":
        route = "ask_for_more_info"
    else:
        route = "rejected"  # clinical_sensitive, off_topic

    return RouterOutput(
        intent=intent,
        route=route,
        source="llm",
        confidence=1.0 if route == "rejected" else 0.8,
        reason=reason,
    )
