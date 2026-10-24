"""Step 1.2 — first AI node: a graph where one node calls Claude.

Run from the backend/ folder:
    uv run python scripts/claude_graph.py
    uv run python scripts/claude_graph.py "Should I use FastAPI or Django for a small REST API?"
"""

import os
import sys
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class ClaudeState(TypedDict, total=False):
    question: str
    cleaned_question: str
    answer: str
    tokens_used: int


# Create the model once and reuse it in every call.
llm = ChatAnthropic(
    model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
    max_tokens=400,   # caps the reply length, and so the cost
    timeout=60,
)


def prepare(state: ClaudeState) -> dict:
    """Normal Python node (no AI): validate and clean the input."""
    question = state.get("question", "").strip()
    if not question:
        raise ValueError("question must not be empty")
    return {"cleaned_question": question}


def ask_claude(state: ClaudeState) -> dict:
    """AI node: send a system prompt + the question to Claude."""
    messages = [
        # The system prompt sets Claude's role and rules.
        SystemMessage(content=(
            "You are a senior software architect. Answer in at most 5 short bullet points. "
            "If important details are missing, say which ones would change your answer."
        )),
        # The human message is the actual user input.
        HumanMessage(content=state["cleaned_question"]),
    ]
    reply = llm.invoke(messages)
    usage = reply.usage_metadata or {}
    # reply.content can be a LIST of blocks (e.g. a "thinking" block + a "text" block).
    # reply.text joins only the text blocks, so the state stores just the answer.
    return {"answer": reply.text, "tokens_used": usage.get("total_tokens", 0)}


def build_graph():
    builder = StateGraph(ClaudeState)
    builder.add_node("prepare", prepare)
    builder.add_node("ask_claude", ask_claude)
    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "ask_claude")
    builder.add_edge("ask_claude", END)
    return builder.compile()


def main() -> None:
    question = " ".join(sys.argv[1:]) or "I have 10,000 users. PostgreSQL or MongoDB?"
    graph = build_graph()
    print(graph.get_graph().draw_ascii())

    # run_name + metadata make this run easy to find and filter in LangSmith.
    result = graph.invoke(
        {"question": question},
        config={"run_name": "claude_graph_demo", "metadata": {"step": "1.2"}},
    )
    print(f"Question: {result['question']}\n")
    print(f"Claude's answer:\n{result['answer']}\n")
    print(f"Tokens used: {result['tokens_used']}")


if __name__ == "__main__":
    main()
