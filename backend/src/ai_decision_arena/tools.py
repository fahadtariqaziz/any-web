"""Tools the CHAT agent can call by itself (real tool calling: Claude decides which tool, when, with what input).

The onboarding graph never lets Claude pick tools: there, Python calls Tavily at a fixed step, so time and
cost stay predictable (~30 s). In the chat a turn is open-ended, so Claude chooses:

    search_knowledge(query)          the knowledge base: curated docs + research from this and earlier sessions
    web_search(query, perspective)   a fresh Tavily search in one lane (research / doctor / patient)
    remember_fact(fact)              save a lasting fact about the patient (long-term memory)
    load_skill(name)                 load a skill's instructions (skills.py) when the conversation needs it
    ask_researcher(question)         delegate a research question to the research SUB-AGENT (researcher.py)

Guardrails: at most MAX_TOOL_ROUNDS model calls with tools per turn (then one final answer without tools),
at most MAX_WEB_SEARCHES web searches per turn, every tool result is wrapped as <source> data (never
instructions), and a failing tool returns an error text instead of crashing the turn.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool

from ai_decision_arena import knowledge, memory, skills
from ai_decision_arena.research.search import search_one
from ai_decision_arena.schemas import SearchQuery

MAX_TOOL_ROUNDS = 4
MAX_WEB_SEARCHES = 3
WEB_RESULTS = 4


@dataclass
class ToolContext:
    """Who the tools work for. One per chat turn (the web-search counter starts at 0 every turn)."""
    thread_id: str | None = None
    patient_id: str | None = None
    condition: str = ""
    web_searches: int = 0
    used: list[str] = field(default_factory=list)       # tool names in call order, for logs / traces


def _sources(items: list[dict]) -> str:
    if not items:
        return "<results>(nothing found)</results>"
    return "<results>\n" + "\n".join(f"<source>{json.dumps(i, ensure_ascii=False)}</source>" for i in items) + "\n</results>"


# --- tool implementations (plain functions; the factories below bind them to a ToolContext) -------------

def search_knowledge_tool(ctx: ToolContext) -> BaseTool:
    def search_knowledge(query: str) -> str:
        """Search the knowledge base: curated health-safety docs plus the research gathered for this patient and
        for earlier sessions. Fast and free: try this before web_search. Cite results by their id and title."""
        return _sources(knowledge.search(query, thread_id=ctx.thread_id))
    return StructuredTool.from_function(search_knowledge, handle_tool_error=True)


def web_search_tool(ctx: ToolContext) -> BaseTool:
    def web_search(query: str, perspective: Literal["research", "doctor", "patient"]) -> str:
        """Search the web in one lane: "research" (studies, reviews), "doctor" (guidelines, NHS, Mayo Clinic...)
        or "patient" (forums, real experiences). Use short keyword queries. Only when search_knowledge did not
        have the answer; limited to a few searches per message."""
        if ctx.web_searches >= MAX_WEB_SEARCHES:
            return f"Search limit reached ({MAX_WEB_SEARCHES} per message): answer with what you have."
        ctx.web_searches += 1
        hits = search_one(SearchQuery(query=query[:300], perspective=perspective, topic="routine_lifestyle",
                                      preferred_domains=[]))
        return _sources([{"title": h.title, "url": h.url, "lane": perspective, "snippet": h.snippet[:600]}
                         for h in hits[:WEB_RESULTS]])
    return StructuredTool.from_function(web_search, handle_tool_error=True)


def remember_fact_tool(ctx: ToolContext) -> BaseTool:
    def remember_fact(fact: str) -> str:
        """Save ONE lasting fact about the patient for future chats, e.g. "allergic to penicillin", "works night
        shifts", "started walking 20 minutes daily (Oct 2026)". Short and factual, only what the patient said:
        no guesses about causes, no pronouns. Not for passing moods or things already in
        <remembered_from_earlier_chats>. Do not tell the patient each time you save something."""
        if not ctx.patient_id:
            return "Not saved: this browser has no patient id."
        saved = memory.remember(ctx.patient_id, [fact], "chat", ctx.thread_id)
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
        for questions that need several searches or comparing sources (e.g. "Is intermittent fasting safe with
        metformin? What do guidelines and patients say?"). Slower than search_knowledge: say a short sentence
        to the patient first. Returns a short answer with sources."""
        from ai_decision_arena.researcher import research    # imported here: researcher.py imports this module
        return research(question, ctx)
    return StructuredTool.from_function(ask_researcher, handle_tool_error=True)


def chat_tools(ctx: ToolContext) -> list[BaseTool]:
    return [search_knowledge_tool(ctx), web_search_tool(ctx), remember_fact_tool(ctx), load_skill_tool(ctx),
            ask_researcher_tool(ctx)]


# --- the tool loop -----------------------------------------------------------------------------------

def run_tools(message: AIMessage, tools: list[BaseTool], ctx: ToolContext) -> list[ToolMessage]:
    """Run every tool call of one model message, in order. Unknown tools get an error message back."""
    by_name = {t.name: t for t in tools}
    results = []
    for call in message.tool_calls:
        ctx.used.append(call["name"])
        tool = by_name.get(call["name"])
        if tool is None:
            results.append(ToolMessage(content=f"Unknown tool {call['name']!r}.", tool_call_id=call["id"]))
        else:
            results.append(tool.invoke(call))             # a ToolCall in → a ToolMessage out
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
        if not reply.tool_calls:
            return reply.text
        messages = messages + [reply] + run_tools(reply, tools, ctx)
    return ""
