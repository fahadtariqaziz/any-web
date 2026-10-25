"""Tools the CHAT agent can call by itself (real tool calling: Claude decides which tool, when, with what input).

The onboarding graph never lets Claude pick tools: there, Python calls Tavily at a fixed step, so time and
cost stay predictable (~30 s). In the chat a turn is open-ended, so Claude chooses:

    search_knowledge(query)          the knowledge base: curated docs + research from this and earlier sessions
    web_search(query, domain)        a fresh Tavily search in one domain (apps / papers / tech)
    remember_fact(fact)              save a lasting fact about the user or their project (long-term memory)
    ask_researcher(question)         delegate a research question to the research SUB-AGENT (researcher.py)
    load_skill(name)                 the full text of one builder skill from <available_skills> (skills.py)

Guardrails: at most MAX_TOOL_ROUNDS model calls with tools per turn (then one final answer without tools),
at most MAX_WEB_SEARCHES web searches per turn, every tool result is wrapped as <source> data (never
instructions), and a failing tool returns an error text instead of crashing the turn.
Every model round (the sub-agent's too) is metered into the turn's ToolContext.meter (usage.py).
"""

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

from ai_decision_arena import knowledge, memory, skills, tool_log
from ai_decision_arena.pricing import tokens_from_langchain
from ai_decision_arena.research.search import search_one
from ai_decision_arena.schemas import SearchQuery
from ai_decision_arena.usage import UsageMeter, record

MAX_TOOL_ROUNDS = 4
MAX_WEB_SEARCHES = 3
WEB_RESULTS = 4


@dataclass
class ToolContext:
    """Who the tools work for. One per chat turn (the web-search counter starts at 0 every turn)."""
    thread_id: str | None = None
    user_id: str | None = None
    project: str = ""
    web_searches: int = 0
    used: list[str] = field(default_factory=list)       # tool names in call order, for logs / traces
    meter: UsageMeter = field(default_factory=UsageMeter)   # tokens + USD of this turn's model calls


def _meter(llm, message, ctx: ToolContext) -> None:
    if message is not None:
        record(getattr(llm, "model", "") or "unknown", tokens_from_langchain(message.usage_metadata), meter=ctx.meter)


def _sources(items: list[dict]) -> str:
    if not items:
        return "<results>(nothing found)</results>"
    return "<results>\n" + "\n".join(f"<source>{json.dumps(i, ensure_ascii=False)}</source>" for i in items) + "\n</results>"


# --- tool implementations (plain functions; the factories below bind them to a ToolContext) -------------

def search_knowledge_tool(ctx: ToolContext) -> BaseTool:
    def search_knowledge(query: str) -> str:
        """Search the knowledge base: the research gathered for this project and for earlier sessions. Fast and
        free: try this before web_search. Cite results by their id and title."""
        return _sources(knowledge.search(query, thread_id=ctx.thread_id))
    return StructuredTool.from_function(search_knowledge, handle_tool_error=True)


def web_search_tool(ctx: ToolContext) -> BaseTool:
    def web_search(query: str, domain: Literal["apps", "papers", "tech"]) -> str:
        """Search the web in one domain: "apps" (existing products, reviews, what their users say), "papers"
        (research and technical literature) or "tech" (libraries, frameworks, APIs, docs, repositories). Use short
        keyword queries. Only when search_knowledge did not have the answer; limited to a few searches per message."""
        if ctx.web_searches >= MAX_WEB_SEARCHES:
            return f"Search limit reached ({MAX_WEB_SEARCHES} per message): answer with what you have."
        ctx.web_searches += 1
        hits = search_one(SearchQuery(query=query[:300], domain=domain, topic={"apps": "existing_solutions", "papers": "established_approaches", "tech": "libraries_and_frameworks"}[domain],
                                      preferred_domains=[]))
        return _sources([{"title": h.title, "url": h.url, "lane": domain, "snippet": h.snippet[:600]}
                         for h in hits[:WEB_RESULTS]])
    return StructuredTool.from_function(web_search, handle_tool_error=True)


def remember_fact_tool(ctx: ToolContext) -> BaseTool:
    def remember_fact(fact: str) -> str:
        """Save ONE lasting fact about the user or their projects for future sessions, e.g. "prefers TypeScript and
        React", "deploys on Vercel", "team of two, no designer". Short and factual, only what the user said: no
        guesses, no pronouns. Not for one-off requests or things already in <remembered_from_earlier_sessions>.
        Do not tell the user each time you save something."""
        if not ctx.user_id:
            return "Not saved: this browser has no user id."
        saved = memory.remember(ctx.user_id, [fact], "chat", ctx.thread_id)
        return "Saved." if saved else "Not saved (database unavailable)."
    return StructuredTool.from_function(remember_fact, handle_tool_error=True)


def load_skill_tool(ctx: ToolContext) -> BaseTool:
    def load_skill(name: str) -> str:
        """Load the full instructions of one skill from <available_skills> and follow them in your answer."""
        return skills.load_skill(name)
    return StructuredTool.from_function(load_skill, handle_tool_error=True)


def ask_researcher_tool(ctx: ToolContext) -> BaseTool:
    def ask_researcher(question: str) -> str:
        """Delegate a research question to the research assistant (a separate agent with its own tools). Use it
        for questions that need several searches or comparing sources (e.g. "Which offline-storage libraries do
        PWA calculators use, and what do their users complain about?"). Slower than search_knowledge: say a short
        sentence to the user first. Returns a short answer with sources."""
        from ai_decision_arena.researcher import research    # imported here: researcher.py imports this module
        return research(question, ctx)
    return StructuredTool.from_function(ask_researcher, handle_tool_error=True)


def chat_tools(ctx: ToolContext) -> list[BaseTool]:
    """The Ask-mode tools."""
    return [search_knowledge_tool(ctx), web_search_tool(ctx), remember_fact_tool(ctx), load_skill_tool(ctx),
            ask_researcher_tool(ctx)]


# --- the tool loop -----------------------------------------------------------------------------------

def _call_target(args: dict) -> str:
    """What a chat tool call was about, for the log: the query / question / fact (no tool output)."""
    return " · ".join(f"{k}={v}" for k, v in args.items() if isinstance(v, str))


def run_tools(message: AIMessage, tools: list[BaseTool], ctx: ToolContext) -> list[ToolMessage]:
    """Run every tool call of one model message, in order. Unknown tools get an error message back."""
    by_name = {t.name: t for t in tools}
    results = []
    for call in message.tool_calls:
        ctx.used.append(call["name"])
        tool = by_name.get(call["name"])
        started = time.monotonic()
        if tool is None:
            result = ToolMessage(content=f"Unknown tool {call['name']!r}.", tool_call_id=call["id"], status="error")
        else:
            try:
                result = tool.invoke(call)                # a ToolCall in → a ToolMessage out
            except Exception as exc:                      # not a ToolException: logged, then raised as before
                tool_log.record(ctx.thread_id or "", "chat", call["name"], target=_call_target(call.get("args") or {}),
                                ok=False, reason=f"{type(exc).__name__}: {exc}"[:300],
                                duration_seconds=round(time.monotonic() - started, 3))
                raise
        results.append(result)
        failed = getattr(result, "status", "success") == "error"
        tool_log.record(ctx.thread_id or "", "chat", call["name"], target=_call_target(call.get("args") or {}),
                        ok=not failed, reason=str(result.content)[:300] if failed else None,
                        duration_seconds=round(time.monotonic() - started, 3))
    return results


def stream_with_tools(llm, messages: list[BaseMessage], tools: list[BaseTool], ctx: ToolContext,
                      config: dict, max_rounds: int = MAX_TOOL_ROUNDS) -> Iterator[str]:
    """Stream the answer text while letting Claude call tools in between.

    Each round streams one model call. If the finished message asks for tools, they run, their results are
    added to the conversation and the next round starts. The last round has no tools, so the turn always ends
    with an answer. Text written before a tool call ("Let me look that up.") is streamed too."""
    with_tools = llm.bind_tools(tools)
    wrote_text = False
    for round_no in range(1, max_rounds + 2):
        model = with_tools if round_no <= max_rounds else llm
        full: AIMessageChunk | None = None
        separated = False
        for chunk in model.stream(messages, config=config | {"run_name": f"{config.get('run_name', 'agent')}_round_{round_no}"}):
            full = chunk if full is None else full + chunk
            if chunk.text:
                if wrote_text and not separated:           # a new round's text starts on a new paragraph
                    yield "\n\n"
                separated = True
                wrote_text = True
                yield chunk.text
        _meter(llm, full, ctx)
        if full is None or not full.tool_calls:
            return
        messages = messages + [full] + run_tools(full, tools, ctx)


def invoke_with_tools(llm, messages: list[BaseMessage], tools: list[BaseTool], ctx: ToolContext,
                      config: dict, max_rounds: int = MAX_TOOL_ROUNDS) -> str:
    """Same loop without streaming (for the sub-agent): returns the final answer text."""
    with_tools = llm.bind_tools(tools)
    for round_no in range(1, max_rounds + 2):
        model = with_tools if round_no <= max_rounds else llm
        reply: AIMessage = model.invoke(messages, config=config | {"run_name": f"{config.get('run_name', 'agent')}_round_{round_no}"})
        _meter(llm, reply, ctx)
        if not reply.tool_calls:
            return reply.text
        messages = messages + [reply] + run_tools(reply, tools, ctx)
    return ""
