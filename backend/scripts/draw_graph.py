"""Draw the arena graph as a READABLE picture: arena_graph.png (+ arena_graph.mmd, the Mermaid text).

LangGraph's own drawing (graph.get_graph().draw_mermaid_png()) is correct but hard to read: every node has a
"failed → completion" edge (~12 extra lines), and conditional edges carry no reason. This script:
- reads the REAL edges from build_graph(), so the picture can never drift from the code,
- hides the "failed → completion" edges and explains them in one note instead,
- labels every edge with the condition that sends the graph there (LABELS below),
- draws loops (edges that go BACK to an earlier step) dashed, so the main top-to-bottom path stands out,
- colours nodes by kind (AI agent / waits for the user / plain Python) and groups them into phases.

Run from the backend/ folder (needs internet: the PNG is rendered by the mermaid.ink web service):
    uv run python scripts/draw_graph.py
"""

from pathlib import Path

from langchain_core.runnables.graph_mermaid import draw_mermaid_png
from langgraph.checkpoint.memory import InMemorySaver

from ai_decision_arena.graph import build_graph

OUT_DIR = Path(__file__).resolve().parent.parent

# Why the graph takes each edge (source, target) → label. An edge missing here is drawn without a label.
LABELS = {
    ("clarification", "await_clarification"): "needs answers (max 2 rounds)",
    ("await_clarification", "clarification"): "user answered",
    ("clarification", "research"): "enough info",
    ("proposer", "critic"): "full mode",
    ("proposer", "judge"): "quick mode: no critic",
    ("judge", "research"): "more research (bounded)",
    ("judge", "clarification"): "ask the user",
    ("judge", "evidence_checker"): "proceed",
    ("judge", "final_report"): "proceed, quick mode",
    ("evidence_checker", "research"): "material evidence gap",
    ("evidence_checker", "final_report"): "claims checked",
}

# Phases, top to bottom. Every node of the graph must be in one of them.
PHASES = {
    "1 · Understand the case": ["intake", "clarification", "await_clarification"],
    "2 · Research (3 lanes)": ["research"],
    "3 · Debate": ["proposer", "critic", "judge"],
    "4 · Verify": ["evidence_checker"],
    "5 · Report": ["final_report", "completion"],
}

# Edges that go back to an earlier step (drawn dashed).
LOOPS = {
    ("await_clarification", "clarification"),
    ("judge", "research"),
    ("judge", "clarification"),
    ("evidence_checker", "research"),
}

PAUSES = {"await_clarification"}   # interrupt(): the graph stops until the user replies
PYTHON = {"completion"}                            # no LLM call


def node_class(name: str) -> str:
    return "pause" if name in PAUSES else "python" if name in PYTHON else "agent"


def build_mermaid() -> str:
    graph = build_graph(InMemorySaver()).get_graph()
    # X → completion is the "failed" edge for every X except final_report (its normal next step).
    edges = [e for e in graph.edges if e.target != "completion" or e.source == "final_report"]
    names = {e.source for e in edges} | {e.target for e in edges}
    placed = {n for nodes in PHASES.values() for n in nodes}
    missing = names - placed - {"__start__", "__end__"}
    if missing:
        raise SystemExit(f"Add these nodes to PHASES in draw_graph.py: {sorted(missing)}")

    lines = ["flowchart TD", '    __start__(["START"])', '    __end__(["END"])']
    for i, (title, nodes) in enumerate(PHASES.items()):
        lines.append(f'    subgraph phase{i}["{title}"]')
        for n in nodes:
            shape = f'{n}{{{{"⏸ {n}"}}}}' if n in PAUSES else f'{n}["{n}"]'   # pauses are hexagons
            lines.append(f"        {shape}:::{node_class(n)}")
        lines.append("    end")
    for e in edges:
        label = LABELS.get((e.source, e.target))
        line = "-.->" if (e.source, e.target) in LOOPS else "-->"
        arrow = f'{line}|"{label}"|' if label else line
        lines.append(f"    {e.source} {arrow} {e.target}")

    lines += [
        '    note["<b>Not drawn:</b> any node fails → completion<br/>(status failed, the API error is shown)<br/>'
        'Each LLM call first retries, then tries the fallback model"]:::note',
        '    legend["<b>Legend</b><br/>blue = AI agent (LLM call)<br/>orange hexagon = waits for the user<br/>'
        'grey = plain Python<br/>dashed arrow = loop back to an earlier step"]:::note',
        "    classDef agent fill:#dbeafe,stroke:#2563eb,color:#1e3a8a",
        "    classDef pause fill:#ffedd5,stroke:#ea580c,color:#7c2d12",
        "    classDef python fill:#f1f5f9,stroke:#64748b,color:#334155",
        "    classDef note fill:#fefce8,stroke:#a16207,color:#713f12,stroke-dasharray:4 3",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    mermaid = build_mermaid()
    (OUT_DIR / "arena_graph.mmd").write_text(mermaid)
    draw_mermaid_png(mermaid, output_file_path=str(OUT_DIR / "arena_graph.png"), background_color="white")
    print(f"Wrote {OUT_DIR / 'arena_graph.png'} and arena_graph.mmd (paste the .mmd into https://mermaid.live to edit)")


if __name__ == "__main__":
    main()
