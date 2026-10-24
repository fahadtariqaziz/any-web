"""Step 1.1 — the smallest useful LangGraph: State + 2 nodes + edges. No AI yet.

Run from the backend/ folder:
    uv run python scripts/hello_graph.py
"""

from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

# Load .env so this run is also traced in LangSmith.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


# 1) STATE — the shared dict that flows through the graph.
class HelloState(TypedDict, total=False):
    question: str
    greeting: str
    answer: str


# 2) NODES — plain functions: read the state, return ONLY the fields to update.
def greet(state: HelloState) -> dict:
    print("  → running node: greet")
    return {"greeting": "Hello from the Decision Arena!"}


def respond(state: HelloState) -> dict:
    print("  → running node: respond")
    return {"answer": f"{state['greeting']} You asked: {state['question']!r}"}


# 3) GRAPH — register nodes, then connect them with edges.
def build_graph():
    builder = StateGraph(HelloState)
    builder.add_node("greet", greet)
    builder.add_node("respond", respond)

    builder.add_edge(START, "greet")      # where execution begins
    builder.add_edge("greet", "respond")  # greet runs, then respond
    builder.add_edge("respond", END)      # finish

    return builder.compile()              # compile() checks the wiring and makes it runnable


def main() -> None:
    graph = build_graph()

    print("=== Graph as ASCII ===")
    print(graph.get_graph().draw_ascii())

    print("=== Graph as Mermaid text (paste into https://mermaid.live) ===")
    print(graph.get_graph().draw_mermaid())

    png_path = Path(__file__).resolve().parent.parent / "hello_graph.png"
    try:
        # Renders through the mermaid.ink web service, so it needs internet.
        graph.get_graph().draw_mermaid_png(output_file_path=str(png_path))
        print(f"=== PNG saved to {png_path} ===\n")
    except Exception as exc:
        print(f"(PNG skipped: {type(exc).__name__}: {exc})\n")

    print("=== Running the graph ===")
    result = graph.invoke({"question": "PostgreSQL or MongoDB?"})
    print("\n=== Final state ===")
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
