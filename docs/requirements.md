# Project: AI Decision Arena
Complete Project Requirements, Architecture, and Implementation Instructions

I want to build a project called AI Decision Arena, a general-purpose technical problem-solving and decision-support system powered by multiple AI agents. I want to use LangGraph for orchestration, Claude as the only LLM provider, Tavily for web research, LangSmith for tracing and observability, FastAPI for the backend, PostgreSQL for local persistence, and Next.js with TypeScript and Tailwind CSS for the frontend.

Please act as a senior AI engineer and software architect. Help me design and implement this project with clean architecture, maintainable code, proper error handling, and a working end-to-end flow.

Do not just give me a conceptual explanation. I eventually want a functional application that I can run locally, test, and extend.

## 1. Project Vision
AI Decision Arena should help users solve technical problems and make informed technical decisions.

Users should be able to submit any technical problem, including:

- Choosing between technologies, databases, frameworks, or AI models.
- Comparing different software architectures.
- Investigating production bugs and technical issues.
- Evaluating AI/ML tools, libraries, and infrastructure.
- Comparing deployment options, cloud services, and development approaches.
- Researching technical questions using official documentation and real-world developer experiences.

The system should not behave like a normal chatbot that generates an answer from a single LLM call.

Instead, it should:

- Understand the user's problem and requirements.
- Identify missing information and ask clarification questions when necessary.
- Research the problem using relevant public sources.
- Collect structured evidence rather than simply passing raw web pages to an LLM.
- Generate two or three possible solutions.
- Have another agent critically evaluate the proposed solutions.
- Have a judge agent compare and score the solutions.
- Verify important factual claims and their sources.
- Ask the user for additional information whenever the available evidence or requirements are insufficient.
- Allow the user to review, accept, reject, or request revisions to the proposed solution.
- Generate a final recommendation with supporting evidence, trade-offs, assumptions, and unresolved questions.

The system should prioritize evidence-based reasoning, transparency, and useful recommendations over confidently generating an answer when the available information is insufficient.

## 2. Required Technology Stack
Use the following technologies. Do not replace them with alternative technologies unless there is a genuine technical limitation that you explain first.

### Backend and AI orchestration
- Python
- FastAPI
- LangGraph for graph construction, conditional routing, state management, and human-in-the-loop execution.
- Anthropic Claude API as the ONLY LLM provider.
- Pydantic for structured output validation.
- Tavily API for web search and research.
- LangSmith for LangGraph tracing, debugging, and observability.

Do not use OpenAI, Gemini, Groq, Ollama, or another LLM provider as a fallback. All LLM reasoning, proposal generation, criticism, judging, and evidence assessment must use Claude through the Anthropic API.

Use the official Anthropic Python SDK or a compatible LangChain integration, and use the current supported versions of the required packages.

### Persistence
- Local PostgreSQL database.
- LangGraph PostgreSQL checkpointer for persistent graph execution and resumability.
- SQLAlchemy with an appropriate PostgreSQL driver, or another well-supported approach for application-owned relational data.
- Database migrations using Alembic if SQLAlchemy is used.

Use PostgreSQL locally during development. Do not require Redis, a vector database, or another database for the initial MVP unless a concrete requirement justifies it.

### Frontend
- Next.js
- TypeScript
- Tailwind CSS

Build a functional, responsive interface that lets users interact with the graph, answer clarification questions, inspect research evidence, review agent outputs, and view the final decision report.

### Configuration
Use environment variables for all credentials and sensitive configuration.

Example .env.example:

```
ANTHROPIC_API_KEY=
TAVILY_API_KEY=

LANGSMITH_API_KEY=
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=ai-decision-arena

DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/ai_decision_arena

FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000
```

These are example settings, not real credentials. Choose the correct database driver and current supported LangSmith environment variables for the installed versions.

Never commit .env files or expose API keys to the browser. Claude, Tavily, and LangSmith credentials must remain on the backend.

## 3. Multi-Agent Architecture
Implement the system as a LangGraph StateGraph with clearly defined nodes and conditional edges.

Use the following 11 logical node types as the initial architecture. Some nodes may execute multiple times because of clarification or research loops.

1. Intake Node
2. Clarification Node
3. Research Node
4. Proposer Agent
5. Critic Agent
6. Judge Agent
7. Evidence Checker Node
8. Human Review Node
9. Final Report Node
10. Error Recovery Node
11. Completion Node

Use a separate conditional routing function wherever routing decisions are required. Routing functions do not need to be counted as graph nodes.

You may recommend merging nodes only if it materially improves reliability or simplicity, but explain the trade-off before changing the architecture.

### Node 1: Intake Node
Purpose: Understand and normalize the user's initial problem.

Responsibilities:

- Receive the user's original question.
- Validate the request and reject empty or malformed inputs.
- Identify the likely problem domain, such as backend engineering, databases, AI/ML, infrastructure, security, or general software architecture.
- Extract known requirements, constraints, goals, budget, scale, technology preferences, and other relevant details.
- Store the original question without losing the user's meaning.
- Initialize counters and workflow status for a new decision session.
- Avoid inventing requirements that the user did not provide.

Expected state updates:

- question
- problem_domain
- requirements
- constraints
- missing_information
- status

Route the request to the Clarification Node.

### Node 2: Clarification Node
Purpose: Determine whether additional user input is required before reliable research and solution generation can begin.

Responsibilities:

- Analyze the original question and the current requirements.
- Identify missing details that could materially change the recommendation.
- Ask concise, targeted questions rather than overwhelming the user with unnecessary questions.
- Prefer asking multiple closely related questions in a single interaction when appropriate.
- Use the information already available in the state to avoid asking duplicate questions.
- If the information is sufficient, allow the graph to continue without interrupting the user.

The node must produce a validated structured result similar to:

```python
{
    "need_clarification": True,
    "questions": [
        "What is your expected workload?",
        "Do you have a preferred cloud provider?"
    ],
    "reason": "These constraints could change the recommendation."
}
```

The field must be named exactly need_clarification, with a boolean value.

Routing behavior:

- If need_clarification is True, invoke LangGraph's interrupt() to pause execution and present the questions to the user.
- If need_clarification is False, route directly to the Research Node.
- When the user responds, validate the answers, update the requirements in the graph state, and resume the same graph execution using the existing thread identifier.
- Re-evaluate the updated requirements after resumption, rather than blindly continuing with stale assumptions.

Do not call interrupt() merely to display a question. The node should pause only when actual user input is required.

Use a bounded clarification policy so the system does not ask endless follow-up questions. If important information remains unavailable, explicitly record assumptions and unresolved questions instead of looping indefinitely.

Use LangGraph's supported persistence and interrupt/resume patterns, ensuring that state is saved before the graph pauses.

### Node 3: Research Node
Purpose: Collect relevant public evidence before solutions are proposed or evaluated.

Use Tavily as the web search provider.

Research should be driven by the user's problem domain and the requirements gathered during clarification.

#### Research source priority
Search and assess sources in approximately this order:

1. Official documentation and primary sources.
2. Official benchmark reports, technical specifications, and release notes.
3. GitHub repositories, issues, pull requests, and public discussions.
4. Public developer experiences from Reddit and other relevant community discussions.
5. Credible technical articles, engineering blogs, and independent comparisons.

This is a relevance-based priority, not an absolute rule. For example, community discussions may be more useful for identifying recurring real-world problems than official documentation.

Use Tavily to search for relevant pages and retrieve useful content through supported APIs. Do not assume that every search result includes a complete page or that every public page is accessible.

#### Research behavior
- Generate search queries based on the problem, requirements, and relevant competing solutions.
- Search for official documentation first when it exists.
- Research competing approaches rather than searching only for evidence supporting one solution.
- Look for limitations, known issues, operational costs, migration problems, scaling concerns, and practical implementation experiences.
- Prefer recent evidence when the subject changes rapidly.
- Preserve publication dates when available and record the retrieval date.
- Deduplicate repeated results.
- Keep research bounded by configurable search and content limits.

#### Important: Store structured evidence, not raw pages alone
Do not simply concatenate raw web pages and send the entire content to Claude.

Convert relevant research into structured evidence records.

Each evidence record should contain fields similar to:

```python
{
    "evidence_id": "ev_001",
    "source_title": "Official documentation title",
    "source_url": "https://example.com/documentation",
    "source_type": "official_documentation",
    "published_at": None,
    "retrieved_at": "ISO-8601 timestamp",
    "relevant_excerpt": "Short relevant excerpt or faithful summary",
    "claims_supported": [
        "The technology supports the required feature."
    ],
    "limitations": [
        "The feature has a documented constraint."
    ],
    "sentiment": None,
    "relevance_score": 0.92,
    "reliability_notes": "Primary source for the documented feature.",
    "verification_status": "pending"
}
```

Treat these fields as an illustrative schema. Define proper Pydantic models and validate all retrieved records.

Do not fabricate missing metadata, dates, quotations, source contents, or evidence identifiers. Distinguish direct quotations from paraphrases and preserve the original source URL.

For community reviews, also capture:

- The specific issue or experience being discussed.
- Whether the evidence is an individual anecdote or a recurring observation.
- The context in which the experience occurred.
- Any reported limitations or workarounds.
- Whether the discussion is sufficiently relevant to the user's situation.

Do not claim that a complaint is widespread based on a single comment. Do not invent review counts or consensus.

The Research Node should return a structured evidence collection, a summary of the findings, identified evidence gaps, and any conflicting claims.

If Tavily fails, return a recoverable error or mark the evidence gap. Never silently replace missing research with fabricated facts.

### Node 4: Proposer Agent
Purpose: Generate two or three viable solutions for the user's technical problem.

The Proposer Agent must use:

- The original question.
- The clarified requirements and constraints.
- The structured evidence from the Research Node.
- Relevant limitations and conflicting evidence.

For each proposed solution, provide:

- Solution name.
- Description and how it addresses the problem.
- Benefits and advantages.
- Drawbacks and disadvantages.
- Estimated cost, including the basis for the estimate.
- Assumptions.
- Implementation complexity.
- Scalability considerations.
- Security and reliability considerations, where relevant.
- Supporting evidence IDs.
- Evidence gaps and uncertainty.

Cost estimates should be clearly labeled as estimates, not verified prices, unless current pricing evidence has been retrieved. State the assumptions, usage levels, and pricing sources when possible.

Generate two or three meaningfully different alternatives rather than minor variations of the same approach.

If only one viable solution exists, explain why and identify the missing information that would be needed to compare alternatives.

The Proposer must not invent citations or claim that a source supports a statement when the source has not been retrieved and assessed.

Use a Pydantic schema for proposals so the Critic and Judge receive consistent data.

### Node 5: Critic Agent
Purpose: Critically evaluate every proposed solution.

The Critic must independently assess the proposals rather than simply agreeing with the Proposer.

For each solution, identify:

- Hidden technical risks.
- Weak or unsupported assumptions.
- Scalability bottlenecks.
- Performance limitations.
- Security concerns.
- Operational complexity.
- Maintenance and migration costs.
- Vendor lock-in or dependency risks.
- Potential failure modes.
- Missing requirements.
- Contradictions between proposed claims and collected evidence.
- Situations where another solution may be more appropriate.

The Critic should distinguish verified problems from possible risks.

Every factual criticism should reference supporting evidence IDs when available. If a criticism is based on engineering reasoning rather than a retrieved source, label it accordingly.

The Critic should provide actionable counterarguments and suggest improvements to the proposed solutions.

Do not instruct the Critic to disagree with everything. Its goal is to find meaningful weaknesses, not to manufacture objections.

### Node 6: Judge Agent
Purpose: Compare the proposals and decide which option best fits the user's actual requirements.

The Judge must consider:

- Original problem and clarified requirements.
- The proposals and their trade-offs.
- The Critic's objections.
- The structured evidence collected through research.
- Evidence verification results, when available.
- Missing or contradictory evidence.
- Cost, implementation complexity, scalability, reliability, and security.

Use a configurable weighted scoring rubric. For example:

- Requirements fit: 30%.
- Technical feasibility: 25%.
- Reliability and risks: 20%.
- Cost efficiency: 15%.
- Evidence quality: 10%.

These weights should be configurable rather than permanently hardcoded. Different technical problems may require different priorities.

For each solution, return:

- Individual criterion scores.
- Weighted total score.
- Score explanations.
- Key benefits and drawbacks.
- Confidence level with a justification.
- Supporting evidence IDs.
- Remaining risks and assumptions.

The Judge must not treat the numeric score as objective truth. Explain the reasoning behind the scores.

#### Conditional routing
The Judge must identify when the current information is insufficient to make a defensible recommendation.

If evidence is missing or claims materially contradict one another, return a structured decision such as:

```python
{
    "decision": "request_more_research",
    "reason": "The performance comparison uses incompatible benchmarks.",
    "required_evidence": [
        "A comparable benchmark under the expected workload"
    ],
    "clarification_questions": [],
    "winning_solution_id": None
}
```

Possible decisions should include:

- proceed
- request_more_research
- request_clarification
- insufficient_evidence

Routing behavior:

- If more research is required, route to the Research Node.
- If additional user information is required, route to the Clarification Node, which should pause through interrupt() when user input is needed.
- If evidence remains insufficient after the allowed retries, produce an appropriately qualified result.
- If evidence is sufficient, route to the Evidence Checker Node.

Do not allow the Judge to create an unlimited research loop.

### Node 7: Evidence Checker Node
Purpose: Verify the important factual claims that support the proposed solutions and the Judge's recommendation.

The Evidence Checker must:

- Inspect the source records associated with factual claims.
- Confirm that each cited source is relevant to the specific claim.
- Confirm that the source actually supports the claim rather than merely mentioning the same topic.
- Identify outdated evidence, irrelevant sources, unsupported assertions, and contradictory findings.
- Check that cited URLs and excerpts correspond to the stored evidence records.
- Flag claims that are speculative, inferred, or based only on anecdotal reports.
- Reject irrelevant or demonstrably unsupported evidence for the claim it is supposed to support.
- Preserve a record of rejected evidence and the reason for rejection.
- Identify when additional research is needed.

Use explicit verification statuses, such as:

- verified
- partially_supported
- unsupported
- contradicted
- irrelevant
- unavailable

The Evidence Checker must not automatically declare a source reliable merely because it is an official or popular website. It must assess whether the evidence actually supports the relevant claim.

If verification identifies a material evidence gap, route back to the Research Node if retry capacity remains. Otherwise, mark the issue unresolved and continue with the appropriate uncertainty disclosure.

The checker must not claim that a URL is currently reachable unless it has actually been checked.

The final report should only present evidence as verified when the verification process supports that status.

### Node 8: Human Review Node
Purpose: Let the user inspect the recommendation and influence the decision when needed.

Human interaction is not limited to the initial clarification stage.

Support user actions such as:

- Approve the recommendation.
- Reject the recommendation.
- Request another debate round.
- Ask for more research.
- Correct a requirement or assumption.
- Provide a missing constraint.
- Select a different proposed solution.
- Ask the system to compare two particular options.

Use LangGraph's interrupt() to pause the graph when user input is required.

The application should save the graph state through the configured checkpointer before pausing.

When the user submits a response, resume the same execution using LangGraph's supported resume mechanism and the same thread_id.

Do not start a new graph execution for every human response if the intention is to continue the existing interrupted workflow.

If the user changes requirements, update the state and invalidate or re-evaluate affected research, proposals, scores, and conclusions. Do not reuse stale results without checking whether they are still relevant.

For human approval, define clear allowed actions and validate the submitted action before routing.

Do not allow the LLM to approve actions on behalf of the user when explicit human approval is required.

### Node 9: Final Report Node
Purpose: Generate the final decision report using the validated proposals, research evidence, Critic's analysis, Judge's scoring, and Evidence Checker results.

The report should contain:

- Original problem.
- Confirmed requirements and constraints.
- Clarifications received from the user.
- Summary of the research methodology.
- Recommended solution.
- Two or three alternatives, when available.
- Benefits and drawbacks of each solution.
- Weighted scores and their explanations.
- Estimated costs and their assumptions.
- Key supporting evidence with source links.
- Critic's most important objections.
- Security, scalability, performance, and maintenance considerations where relevant.
- Remaining uncertainties and unsupported claims.
- Unresolved questions.
- Recommended next steps and an implementation outline.

Clearly distinguish verified facts, engineering judgments, estimates, and assumptions.

If the Judge cannot establish a reliable winner, the report must say so. It may provide a conditional recommendation, but must not fabricate certainty or suppress important contradictions.

Do not invent sources, quotes, statistics, prices, or review counts.

### Node 10: Error Recovery Node
Purpose: Handle recoverable failures without corrupting the graph state.

Handle cases such as:

- Tavily API failures or rate limits.
- Claude API timeouts or rate limits.
- Invalid LLM structured output.
- PostgreSQL connection errors.
- Missing or malformed user responses.
- Interrupted execution or application restarts.
- Invalid source content.
- Failed evidence retrieval.

Use bounded retries with appropriate backoff for transient errors. Do not repeatedly retry permanent failures.

Maintain an error record containing the affected operation, error category, retry count, and safe diagnostic information.

Never log API keys, passwords, sensitive user information, or full secret-bearing request payloads.

If a failure cannot be recovered, return a useful error status and preserve any checkpointed state needed for resumption.

The Error Recovery Node should not be used as an unlimited catch-all loop. Define explicit edges for recoverable and terminal errors.

### Node 11: Completion Node
Purpose: Mark the workflow as completed and make the final result available to the frontend.

Responsibilities:

- Set the final workflow status.
- Persist the final report and relevant metadata.
- Preserve the thread association.
- Record total debate rounds and research retries.
- Record execution duration and usage metrics where available.
- Make the final response accessible through the appropriate API endpoint.
- Ensure that retries or repeated requests do not create duplicate completed results unintentionally.

Use explicit statuses such as:

- awaiting_clarification
- researching
- debating
- awaiting_human_review
- verifying
- completed
- completed_with_uncertainty
- failed

Do not mark a workflow as successfully completed if the required final report was never generated or persisted.

## 4. Shared State Design
Use a Python TypedDict as the LangGraph shared state definition.

Keep the state structured, typed where practical, and limited to the information needed by subsequent nodes. Do not put unlimited raw webpage content into the graph state.

The state should include fields similar to:

```python
class ArenaState(TypedDict, total=False):
    thread_id: str

    question: str
    problem_domain: str
    requirements: dict
    constraints: dict
    missing_information: list[str]

    need_clarification: bool
    clarification_questions: list[str]
    clarification_answers: dict

    research_queries: list[str]
    evidence: list[dict]
    evidence_gaps: list[str]
    conflicting_claims: list[dict]

    proposals: list[dict]
    criticisms: list[dict]
    scores: list[dict]
    verdict: dict
    verification_results: list[dict]

    debate_round: int
    research_retry_count: int
    clarification_round_count: int

    human_action: str
    user_feedback: str

    final_report: dict
    status: str
    error: dict
```

This is a starting schema, not a requirement to copy it without reviewing the design.

Define Pydantic models for the more complex nested structures, including evidence, proposals, scores, verdicts, and final reports.

Use clear state ownership. For example, the Proposer should update proposals, the Critic should update criticisms, and the Evidence Checker should update verification results.

Do not let unrelated nodes overwrite the entire state accidentally.

Where LangGraph parallel execution is introduced later, define appropriate reducers for shared fields that may receive concurrent updates. For the initial MVP, prefer a straightforward sequential graph.

Avoid storing unnecessary duplicate copies of large documents or entire LLM prompts in the shared state.

## 5. Human-in-the-Loop and Persistence Requirements
Human-in-the-loop execution is a core requirement.

Use LangGraph's interrupt() and a persistent PostgreSQL checkpointer.

Each user decision session must have a stable, unique thread_id.

For example:

```python
config = {
    "configurable": {
        "thread_id": thread_id
    }
}
```

The frontend must retain the session identifier and use it when requesting the session's status, submitting clarification answers, or resuming a paused graph.

The implementation must support this sequence:

1. The user submits a problem.
2. The graph begins execution.
3. The Clarification Node determines that more information is needed.
4. The graph calls interrupt() and pauses.
5. The checkpointer persists the execution state.
6. The backend returns the pending questions and the session identifier.
7. The user answers through the frontend.
8. The backend validates the answer.
9. The graph resumes with the user's response.
10. The state is updated and execution continues.
11. If another clarification or approval is required, the graph can pause again.
12. Otherwise, the graph finishes and returns the final report.

The system must also support resumption after a backend process restart, provided the PostgreSQL database and checkpoint data remain available.

Use the current documented LangGraph PostgreSQL checkpointer setup and lifecycle. Initialize database connections correctly, handle schema setup through the supported mechanism, and close resources safely.

Do not assume that an in-memory checkpointer is sufficient for the final implementation.

The thread_id is an execution identifier, not an authentication mechanism. In production, associate sessions with authenticated users or enforce ownership checks to prevent unauthorized access to another user's thread.

Also handle duplicate submissions and repeated resume requests safely. Where possible, use an idempotency strategy and validate that a thread is actually waiting for the requested input.

## 6. Loop Limits and Routing Rules
Prevent infinite loops and uncontrolled API usage.

Use these initial limits:

- Maximum debate rounds: 2.
- Maximum research retries: 2.
- Clarification questions: bounded by a configurable maximum, for example two clarification interactions initially.
- API retries: bounded separately from research retries.

Define exactly what each counter means.

For example:

- The initial research pass is not a retry.
- research_retry_count increments only when the graph deliberately returns to Research after an initial research pass.
- debate_round increments whenever a new substantive proposal/criticism round begins.
- A clarification interaction counts as one user-input round, not one question.

The initial flow should be:

Intake → Clarification → Research → Proposer → Critic → Judge → Evidence Checker → Human Review → Final Report → Completion

This is a conceptual sequence. The actual graph must include conditional edges and loops.

Required conditional behavior:

### Clarification routing
- If need_clarification == True, pause with interrupt().
- Validate and incorporate the user's answer.
- Resume the same thread.
- Re-evaluate whether more clarification is necessary.
- If no clarification is needed, route to Research.

### Research routing
- If the Judge identifies a material evidence gap or contradictory claims, route back to Research if retries remain.
- Increment the research retry counter on that deliberate return.
- Re-run the relevant searches, preferably targeting the specific unresolved claims.
- If the retry limit is reached, preserve the uncertainty and continue to a qualified outcome rather than repeatedly searching.

### Debate routing
- Allow up to two substantive debate rounds.
- The Critic should challenge the proposals in each round.
- If the second round still leaves significant uncertainty, do not automatically invent a winner.
- Allow the Judge to produce an insufficient_evidence decision.

### Human-review routing
- If the user requests revision, route back to the relevant node.
- If requirements change, re-evaluate affected proposals and evidence.
- If the user approves, continue to final reporting.
- If the user rejects the recommendation, ask for useful feedback or constraints, then follow a bounded revision path.

### Uncertainty behavior
If uncertainty remains after the maximum research retries and debate rounds:

- Explicitly state what remains unknown.
- List unresolved questions.
- Explain why the available evidence is insufficient.
- Provide a conditional recommendation only if justified.
- Never fabricate evidence or certainty to force completion.

Use explicit routing functions and graph state rather than hidden, ad hoc control flow inside agent prompts.

## 7. LangSmith Tracing and Observability
Integrate LangSmith to trace graph executions.

I want to inspect the execution of individual nodes, including:

- Intake.
- Clarification.
- Research.
- Proposer.
- Critic.
- Judge.
- Evidence Checker.
- Human Review.
- Final Report.
- Error Recovery.
- Completion.

For each execution, I should be able to inspect:

- Node start and end times.
- Input and output state, subject to privacy controls.
- LLM calls and token usage when available.
- Errors and retries.
- Research queries and returned source references.
- Debate rounds.
- Conditional routing decisions.
- Interruptions and resumptions.
- Final workflow status.

Use LangSmith tracing with the configured project name ai-decision-arena.

Ensure that tracing works across the LangGraph execution and that useful run metadata is attached, such as the thread identifier, node name, and problem domain.

Do not expose secrets or unnecessary personal data in traces. Avoid logging API keys and sensitive payloads. Provide a way to disable tracing locally if needed.

Use LangSmith for debugging and evaluation, but do not confuse tracing with application persistence. PostgreSQL and the LangGraph checkpointer remain responsible for the application's durable state and execution resumption.

## 8. Backend API Requirements
Build a FastAPI backend with clearly defined request and response schemas.

At minimum, consider these endpoints:

### Create a decision session
`POST /api/decisions`

Accepts the initial problem and optional user-provided context.

Returns a thread_id, current status, and either pending clarification questions or an execution status/result.

### Read session status
`GET /api/decisions/{thread_id}`

Returns the session status and relevant information needed to render the current frontend state.

### Submit clarification or resume an interrupted graph
`POST /api/decisions/{thread_id}/resume`

Accepts a validated response to the current interrupt, such as clarification answers, a review decision, or revision instructions.

The backend must verify the expected pending action before resuming the graph.

### Read final report
`GET /api/decisions/{thread_id}/report`

Returns the final report when available, or an appropriate status if the workflow has not finished.

### Read evidence
`GET /api/decisions/{thread_id}/evidence`

Returns structured evidence records and source references for the session.

### Provide feedback
`POST /api/decisions/{thread_id}/feedback`

Stores the user's rating, decision, or written feedback.

These are suggested routes. You may adjust them to fit the implementation, but document the final API contract.

Use Pydantic request and response models, consistent error responses, appropriate HTTP status codes, and request validation.

If the graph runs for a long time, avoid blocking a normal HTTP request indefinitely. Choose an appropriate background execution or streaming approach while ensuring that graph state and interrupt/resume behavior remain correct.

For the MVP, polling session status is acceptable. Server-Sent Events can be added later for live agent activity.

## 9. PostgreSQL Data Model
Use PostgreSQL for both graph checkpoint persistence and application-owned data.

Keep LangGraph's checkpoint tables separate from the application's own tables, using the supported checkpoint setup.

Application-owned tables may include:

decision_sessions
- id
- thread_id
- user_id if authentication is added
- question
- problem_domain
- status
- created_at
- updated_at

evidence_records
- id
- thread_id
- evidence_id
- source_url
- source_title
- source_type
- excerpt_or_summary
- verification_status
- retrieved_at
- metadata

decision_reports
- id
- thread_id
- report_json
- created_at

user_feedback
- id
- thread_id
- rating
- action
- comments
- created_at

These tables are illustrative. Design proper primary keys, foreign keys, indexes, constraints, and JSONB fields where appropriate.

Avoid duplicating every field that already exists in the checkpoint state unless there is a clear query, reporting, or audit requirement.

Provide migrations and instructions to initialize the local PostgreSQL database.

Do not store API secrets in database records.

## 10. Frontend Requirements
Build the frontend using Next.js, TypeScript, and Tailwind CSS.

The UI should make the multi-agent process understandable rather than hiding everything behind a single chat response.

Required screens and components:

### A. Problem input
- Text area for the technical problem.
- Optional context and constraints.
- Submit button.
- Session creation and loading states.

### B. Clarification interface
- Display the questions generated by the Clarification Node.
- Provide suitable input controls for the questions.
- Allow the user to answer multiple questions in one submission.
- Preserve the session identifier.
- Submit answers and resume the graph.

### C. Research evidence panel
- Show source titles and clickable source URLs.
- Display source types, retrieval dates, excerpts, and verification statuses.
- Separate official documentation from community experiences.
- Indicate evidence gaps and contradictory claims.

### D. Agent activity view
- Show the current node and workflow status.
- Display meaningful progress updates.
- Show proposals, criticisms, and judge scores when available.
- Display retry and debate-round counts.

Do not claim that a node is running when it has not started. Use actual backend status information.

### E. Decision comparison
Show the proposed solutions side by side, including:

- Benefits.
- Drawbacks.
- Estimated costs.
- Assumptions.
- Risks.
- Scores.
- Evidence supporting the solution.

### F. Human review interface
Provide actions for:

- Approve.
- Reject.
- Request another debate round.
- Request more research.
- Modify requirements.
- Provide additional context.

Only show actions that are valid for the current workflow state.

### G. Final report
Display the recommendation, alternatives, evidence, uncertainties, and implementation steps.

### H. Feedback
Allow users to rate the usefulness of the recommendation and optionally explain what was wrong or missing.

Use accessible components, responsive layouts, loading indicators, error states, and clear status messages.

Keep the frontend API client separate from UI components. Never put Claude, Tavily, or LangSmith API keys in client-side environment variables.

## 11. Example End-to-End Experience
Use the following example as a reference for expected system behavior.

### Step 1: User submits a problem
User:

"I am building an AI application that may have 10,000 users. Should I use PostgreSQL or MongoDB for the backend?"

The Intake Node identifies a database architecture decision.

### Step 2: Clarification Node asks questions
The system determines that the initial question lacks important details.

It pauses through interrupt() and asks:

- Is the application data primarily relational or document-oriented?
- What is the expected read/write workload?
- Are transactions and complex joins important?
- Do you have a preferred cloud provider or budget?

The frontend shows the questions and waits for the user.

### Step 3: User answers
User:

"The data is mostly relational. Reads will be more frequent than writes. We need transactions and complex joins, and we plan to deploy on AWS."

The backend validates the answers, updates the graph state, and resumes the existing thread.

The Clarification Node checks whether more information is necessary. If not, it routes to Research.

### Step 4: Research Node investigates the problem
The Research Node searches official PostgreSQL and MongoDB documentation first.

It then searches for relevant benchmark reports, GitHub issues, and public developer experiences.

It collects evidence about:

- Relational data and complex joins.
- Transaction support and operational requirements.
- Read-heavy workloads.
- Indexing and query optimization.
- Scaling and connection management.
- AWS deployment options and associated costs.

It stores structured evidence records with source links, excerpts, relevance assessments, and verification statuses.

It does not assume that 10,000 users automatically require a particular database or that a single benchmark represents the user's workload.

### Step 5: Proposer Agent creates alternatives
The Proposer produces two or three options where appropriate.

For example:

Option A: PostgreSQL

- Benefits: relational data modeling, joins, and transactional capabilities.
- Drawbacks: requires appropriate schema and query design; performance depends on workload and operations.
- Estimated cost: based on the selected deployment and explicit assumptions.
- Assumptions: relational queries and transactional consistency are important.

Option B: MongoDB

- Benefits: flexible document-oriented data modeling and suitable document-query workloads.
- Drawbacks: may be less natural for a workload centered on complex relational joins.
- Estimated cost: based on the chosen hosting model and explicit assumptions.
- Assumptions: document-oriented access patterns justify its use.

Option C: Managed PostgreSQL on AWS

- Benefits: relational capabilities combined with a managed operational model.
- Drawbacks: managed-service pricing and configuration need to be evaluated.
- Estimated cost: depends on instance sizing, storage, traffic, and deployment configuration.
- Assumptions: a managed database is preferred over self-hosting.

These are example proposal shapes, not predetermined conclusions. The actual options and their claims must follow the user's requirements and the retrieved evidence.

### Step 6: Critic Agent challenges the options
The Critic examines each proposal.

It points out that:

- The number of users alone is not sufficient to estimate database capacity.
- The actual query patterns and expected request rate matter.
- Connection pooling, indexing, caching, and read replicas may affect performance.
- Managed database pricing depends on configuration and workload.
- A benchmark from a different workload may not predict the application's performance.

It references evidence IDs where available and labels engineering judgments separately from sourced facts.

### Step 7: Judge Agent compares the options
The Judge evaluates the options against the confirmed requirements.

It produces criterion scores, weighted totals, explanations, and confidence assessments.

If a critical performance claim relies on incomparable benchmarks, the Judge requests additional research instead of automatically declaring a winner.

### Step 8: Research loop, if necessary
The graph checks the research retry counter.

If retry capacity remains, it routes to Research with targeted questions about the conflicting claims.

The Research Node collects additional evidence and updates the evidence gaps.

The Proposer, Critic, and Judge can then run another substantive debate round, subject to the maximum of two debate rounds.

If the research retry limit has been reached, the graph records the unresolved uncertainty rather than looping indefinitely.

### Step 9: Evidence Checker verifies claims
The Evidence Checker checks that the important database feature, performance, cost, and scaling claims are supported by the recorded sources.

It flags unsupported or contradictory claims and rejects irrelevant evidence for the claims it is supposed to support.

If further verification is impossible within the retry budget, the final result explicitly states that limitation.

### Step 10: Human Review
The system presents the recommendation, alternatives, evidence links, trade-offs, and unresolved concerns.

The user can:

- Approve the recommendation.
- Reject it.
- Request additional research.
- Ask for another debate round, if available.
- Change a requirement.
- Provide a missing constraint.

If the user changes the requirements, the graph re-evaluates the affected evidence and conclusions.

The graph pauses with interrupt() whenever actual user input is required and resumes through the same thread_id.

### Step 11: Final report
The Final Report Node produces a report containing:

- The recommended option and justification.
- Alternative options and their scores.
- Benefits, drawbacks, assumptions, and estimated costs.
- Supporting source links.
- Critic's objections.
- Unverified or contradictory claims.
- Remaining uncertainties.
- Recommended next steps.

If the available evidence does not justify a confident winner, the system says so instead of inventing certainty.

### Step 12: Completion and tracing
The Completion Node persists the report, marks the workflow status, and records the relevant execution metadata.

LangSmith provides traces of node execution, LLM calls, errors, routing, and retries.

PostgreSQL retains the application data and graph checkpoints so the session can be inspected or resumed later where appropriate.

The user can provide feedback, which is stored for future evaluation and improvement of the system's prompts, decision rubric, and test cases. Feedback must not automatically be treated as verified truth or as model training.

## 12. Testing and Quality Requirements
Implement tests for both individual nodes and the full graph.

At minimum, test:

- A problem that needs no clarification.
- A problem that requires one clarification interaction.
- A problem that requires more than one clarification interaction, within the configured limit.
- A Tavily search failure.
- An invalid or incomplete Claude structured response.
- Conflicting research evidence.
- An irrelevant source that should be rejected.
- A Judge decision that requests more research.
- The maximum research retry limit.
- The maximum debate-round limit.
- A human rejection and revision.
- A user changing requirements after research.
- A graph interruption followed by successful resumption.
- A backend restart followed by resumption from a PostgreSQL checkpoint.
- Unauthorized access to another user's session if authentication is implemented.
- Final report generation when uncertainty remains.

Use mocked external APIs for deterministic unit tests. Add a small number of optional integration tests against real APIs, but do not require paid API access for every automated test.

Create a small evaluation dataset of representative technical problems and define measurable evaluation criteria for evidence relevance, recommendation quality, citation support, clarification efficiency, and cost.

> **Note (2026-10-18):** The user decided to test manually instead of writing automated tests. Use the scenarios above as a **manual test checklist**.

## 13. Reliability, Security, and Cost Controls
Implement the following:

- API timeouts and bounded retries.
- Input validation and sensible request-size limits.
- Explicit workflow and error statuses.
- Protection against infinite loops.
- Safe handling of untrusted retrieved webpage content.
- Prompt-injection defenses for retrieved content.
- Secret management through environment variables.
- Rate limiting where appropriate.
- Database transaction and connection management.
- Thread ownership checks if authentication is implemented.
- Usage and latency tracking where provider metadata is available.
- Configurable model selection within the Anthropic provider, without adding another LLM provider.
- Configurable maximum research queries, retrieved pages, and content size.
- A maximum execution budget for each decision session.
- Privacy-aware logging and tracing.

Treat retrieved webpages as untrusted data, not instructions. Agents must not execute arbitrary instructions found in source content or perform destructive external actions without appropriate safeguards and explicit user authorization.

For the MVP, the agents should be read-only: research, analyze, compare, and recommend. Do not implement automatic infrastructure changes, deployments, database mutations in external systems, or other high-impact actions.

## 14. Implementation Deliverables
I want you to help build the project in a practical order.

Provide the following deliverables:

- A concise architecture explanation.
- The complete LangGraph graph design with nodes, conditional edges, and loop limits.
- The shared TypedDict state and Pydantic models.
- The project directory structure.
- Dependency and package setup.
- PostgreSQL setup and migrations.
- The persistent LangGraph PostgreSQL checkpointer configuration.
- Claude API integration and structured-output handling.
- Tavily research integration and evidence extraction.
- The prompts and implementation for each agent.
- The Clarification Node with interrupt() and correct resume behavior.
- The Judge and Evidence Checker routing logic.
- FastAPI endpoints and API schemas.
- LangSmith tracing configuration.
- A Next.js frontend with the required screens and human-review interactions.
- Unit tests, graph integration tests, and evaluation cases.
- A complete .env.example.
- A README with installation, configuration, migrations, startup, testing, and troubleshooting instructions.

## 15. How I Want You to Work
Follow these implementation principles:

- Use current, compatible versions of the libraries and consult their official documentation when API behavior is version-sensitive.
- Do not invent package functions, LangGraph APIs, or configuration settings.
- Keep the code modular and easy to understand.
- Prefer clear function names, type hints, docstrings, and Pydantic validation.
- Do not put the entire application in a single Python file.
- Do not hardcode credentials, costs, fake citations, or fabricated review statistics.
- Do not build unnecessary infrastructure before the MVP works.
- Use the same Claude provider for every LLM-based agent.
- Use Tavily for web search and structured evidence collection.
- Use LangSmith for tracing and evaluation.
- Use LangGraph's persistent checkpointing and interrupt/resume features correctly.
- Explain important design choices briefly.
- Make sure the code for each stage is consistent with the previously defined state, graph, schemas, and API contracts.
- Do not leave essential functions as pseudocode, TODO comments, or empty placeholders in a deliverable described as working.
- If the response is too large for one message, split implementation into clearly numbered stages and keep all interfaces consistent.
- Clearly distinguish implemented features from optional future enhancements.
- When a requirement is ambiguous, state the assumption or ask a focused question rather than silently inventing behavior.

Start by presenting the architecture, the 11-node graph design, the shared state, and the conditional routing strategy. Then propose the implementation sequence and begin with the backend foundation.

The end goal is a locally runnable, testable AI Decision Arena that can gather evidence, debate multiple technical solutions, ask the user for clarification whenever necessary, pause and resume safely, and produce transparent, evidence-backed technical recommendations.
