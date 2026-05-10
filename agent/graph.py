"""
LangGraph workflow assembly for OncoTargetMind Agent.

Workflow:
    intent_router
      ├─ input_parser (target_analysis)
      │   → candidate_generation → target_scoring → report_generation
      ├─ clinical_sensitive → END
      ├─ insufficient_info → END
      └─ rejected → END
"""

from langgraph.graph import StateGraph, END

from agent.state import AgentState, RouterOutput
from agent.nodes import (
    intent_router_node,
    input_parser_node,
    candidate_generation_node,
    target_scoring_node,
    report_generation_node,
)


def _route_after_router(state: AgentState) -> str:
    """Read router_output.route to decide next step."""
    router = state.get("router_output", {})
    route = router.get("route", "rejected")
    if route == "input_parser":
        return "input_parser"
    # ask_for_more_info, rejected → END
    return "end"


def _route_after_parser(state: AgentState) -> str:
    """Check if parsing succeeded."""
    if state.get("error"):
        return "end"
    return "continue"


def build_graph() -> StateGraph:
    """Build and compile the OncoTargetMind agent workflow graph."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("intent_router", intent_router_node)
    workflow.add_node("input_parser", input_parser_node)
    workflow.add_node("candidate_generation", candidate_generation_node)
    workflow.add_node("target_scoring", target_scoring_node)
    workflow.add_node("report_generation", report_generation_node)

    # Entry → router
    workflow.set_entry_point("intent_router")

    # Router → input_parser or END (for clinical_sensitive / insufficient_info / rejected)
    workflow.add_conditional_edges(
        "intent_router",
        _route_after_router,
        {"input_parser": "input_parser", "end": END},
    )

    # Main pipeline
    workflow.add_conditional_edges(
        "input_parser",
        _route_after_parser,
        {"continue": "candidate_generation", "end": END},
    )
    workflow.add_edge("candidate_generation", "target_scoring")
    workflow.add_edge("target_scoring", "report_generation")
    workflow.add_edge("report_generation", END)

    return workflow.compile()


# Singleton graph instance
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_analysis(raw_input: str) -> dict:
    """
    Run the full analysis pipeline synchronously.

    Args:
        raw_input: Free-text clinical description.

    Returns:
        dict with keys: router_output, parsed, candidate_targets, scored_targets, report, error
    """
    graph = get_graph()
    initial_state: AgentState = {
        "raw_input": raw_input,
        "router_output": RouterOutput(
            intent="",
            route="",
            source="",
            confidence=0.0,
            reason="",
        ),
        "parsed": {},
        "candidate_targets": [],
        "scored_targets": [],
        "report": "",
        "error": "",
        "messages": [],
    }
    result = graph.invoke(initial_state)
    return result
