"""Check that the API keys in backend/.env work.

Run from the backend/ folder:
    uv run python scripts/check_env.py

Makes one tiny call each to Claude, Tavily and LangSmith. Never prints key values.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env into os.environ. LangChain and LangSmith read their settings from there.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_FILE)

REQUIRED_KEYS = ["ANTHROPIC_API_KEY", "TAVILY_API_KEY", "LANGSMITH_API_KEY"]


def check_keys_present() -> bool:
    """Make sure every required key has a value (without showing it)."""
    ok = True
    for name in REQUIRED_KEYS:
        value = os.getenv(name, "")
        if value:
            print(f"  ✅ {name} is set ({len(value)} chars)")
        else:
            print(f"  ❌ {name} is missing in {ENV_FILE}")
            ok = False
    return ok


def check_claude() -> None:
    """Ask Claude for a one-word reply. This call is also traced to LangSmith."""
    from langchain_anthropic import ChatAnthropic

    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    llm = ChatAnthropic(model=model, max_tokens=20, timeout=30)
    reply = llm.invoke("Reply with exactly one word: OK")
    usage = reply.usage_metadata or {}
    print(f"  ✅ Claude ({model}) replied: {reply.text!r}  tokens={usage.get('total_tokens')}")


def check_tavily() -> None:
    """Run one small web search."""
    from tavily import TavilyClient

    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    result = client.search("type 2 diabetes management guidelines", max_results=1)
    top = result["results"][0]
    print(f"  ✅ Tavily found: {top['title']}  ({top['url']})")


def check_langsmith() -> None:
    """List one project to prove the API key is accepted."""
    from langsmith import Client

    projects = list(Client().list_projects(limit=1))
    print(f"  ✅ LangSmith connected (tracing={os.getenv('LANGSMITH_TRACING')}, "
          f"project={os.getenv('LANGSMITH_PROJECT')}, found {len(projects)} project(s))")


def main() -> None:
    print("1) Keys in .env")
    if not check_keys_present():
        return

    # Run each check separately so one failure doesn't hide the others.
    for label, check in [("2) Claude", check_claude), ("3) Tavily", check_tavily),
                         ("4) LangSmith", check_langsmith)]:
        print(label)
        try:
            check()
        except Exception as exc:  # show the error type + message, never the key
            print(f"  ❌ {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
