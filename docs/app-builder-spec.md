# AI App Builder — original product specification (verbatim)

> This is the brief the user gave on 2026-10-24 when the project pivoted from the health app to the AI application
> builder. It is the **authoritative requirements document**: the milestones in `handoff.md` implement it. Section
> numbers below are what `handoff.md` refers to as "spec §4.3", "spec §5", etc. Do not edit the text; record
> decisions and deviations in `handoff.md` instead.

I want to build a project similar to Lovable, where users can enter any prompt describing an app or website they want to build. The system should understand the user's requirements, research the problem, generate a validated problem statement and solution brief, obtain user approval, create an implementation plan, build the application, and display it in a live preview.

First, analyze the existing codebase and LangGraph workflow. Then create a `handoff.md` file containing short, actionable implementation steps that we will follow incrementally. Do not start implementing the full application yet.

## 1. Clarification Phase

Reuse the existing LangGraph `clarification` and `await_clarification` nodes.

- The clarification node should ask relevant questions to understand the user's actual requirements, intended audience, objectives, expected features, constraints, and desired outcomes.
- It should support 2–3 rounds of clarification when needed.
- Questions should be specific to the user's prompt, and the system should avoid asking questions that have already been answered.
- The `await_clarification` node should pause execution and wait for the user's response before continuing.
- Once sufficient information is available, pass the clarified requirements to the research phase.

## 2. Research Phase

Once the requirements are sufficiently clear, conduct research across three main domains.

**Domain 1: Existing Applications and User Feedback**

- Research similar applications and websites.
- Identify common user complaints, existing limitations, missing features, and must-have functionality.
- Examine reviews, community discussions, product documentation, and relevant user feedback.
- Identify opportunities to solve the problem better than existing alternatives.

**Domain 2: Research Papers and Technical Literature**

- Search for relevant research papers, technical publications, and authoritative documentation.
- Understand the underlying problem, established approaches, technical limitations, and potential solutions.
- Extract useful findings that can inform the proposed solution.
- Distinguish established findings from assumptions and agent-generated recommendations.

**Domain 3: Technical Feasibility and Existing Implementations**

- Examine relevant open-source projects, repositories, libraries, frameworks, APIs, and technical documentation.
- Evaluate whether the proposed application is feasible within the user's constraints.
- Identify suitable technologies, reusable components, integration requirements, and architectural alternatives.
- Highlight technical limitations, dependencies, and implementation risks.

The research process should produce evidence-backed findings with source links or citations wherever possible. The system must not invent research results, sources, user feedback, or technical capabilities.

## 3. Proposal and Evaluation

Reuse the existing `research`, `propose`, `critic`, and `judge` nodes and agents. Adapt their prompts, responsibilities, and internal logic to support the new application-building workflow rather than rebuilding the existing workflow from scratch.

**Research Agent**

- Gather and organize evidence from all three research domains.
- Identify the user's problem, existing alternatives, potential solutions, and technical constraints.
- Preserve source references and distinguish verified facts from assumptions.

**Proposer Agent**

- Develop a proposed solution based on the clarified requirements and research findings.
- Recommend appropriate features, architecture, technologies, and implementation approaches.
- Explain how the proposed solution addresses the user's actual problem.

**Critic Agent**

- Identify mistakes, missing requirements, unsupported claims, weak assumptions, and contradictions.
- Evaluate technical feasibility, security, privacy, reliability, and potential implementation problems.
- Challenge proposals that merely copy existing applications without addressing the underlying problem.

**Judge Agent**

- Evaluate the proposed solutions against defined criteria.
- Compare their relevance, evidence quality, feasibility, completeness, and alignment with the user's requirements.
- Select the strongest proposal and provide the reasoning behind its selection.
- Identify material contradictions or missing information that require another clarification or evaluation cycle.

The existing nodes and agents should be reused wherever possible. Only introduce new nodes when the new workflow requires functionality that the current nodes do not provide.

## 4. Problem Statement and Solution Brief Generation

After the judge selects the best proposal, introduce a new node that generates a concise, approximately one-page problem statement and solution brief.

The document should be grounded in the user's clarified requirements and the research findings. It should distinguish verified facts, research-backed conclusions, user-provided information, agent recommendations, and unresolved assumptions.

The generated document should include the following sections.

### 4.1 Project Overview

- Proposed application or website name, if available.
- A concise description of the project.
- Intended users, stakeholders, and target audience.
- The domain and context in which the problem occurs.

### 4.2 Problem Statement

- Clearly describe the specific problem or unmet need.
- Identify who experiences the problem and in what context.
- Explain the current process, existing alternatives, or how users currently handle the problem.
- Describe the gap between the current situation and the desired outcome.
- Explain the practical consequences of leaving the problem unresolved.
- Include supporting evidence or measurable indicators when available.

The problem statement should be specific, concise, and solution-neutral. It should describe the problem before assuming that a particular feature or technology is the answer.

### 4.3 Research Findings and Evidence

- Summarize the most relevant findings from existing applications and user feedback.
- Highlight important findings from research papers and technical literature.
- Include findings from feasibility analysis, open-source implementations, and relevant technical documentation.
- Identify existing solutions' limitations and the opportunity for improvement.
- Provide links or citations for important claims and clearly flag evidence gaps.

### 4.4 Proposed Solution

- Explain how the recommended application or website will address the identified problem.
- Describe the main capabilities and user-facing features.
- Explain the key user journey or workflow.
- Identify the features that are essential for the initial version (MVP) and distinguish them from future enhancements.
- Explain why the proposed approach is preferable to the alternatives considered.

### 4.5 Functional and Non-Functional Requirements

- List the main functional requirements describing what the system should do.
- Include relevant non-functional requirements, such as performance, security, privacy, reliability, accessibility, and scalability.
- Describe important integrations, data inputs and outputs, and user roles where applicable.
- Include measurable or testable acceptance criteria for critical requirements when sufficient information is available.

### 4.6 Proposed Architecture and Technology

- Describe the recommended high-level architecture and its major components.
- Explain the responsibilities of the frontend, backend, database, external services, and AI or agent components, as applicable.
- Describe how the components communicate and how data flows through the system.
- Recommend technologies based on evidence, feasibility, and the user's constraints.
- Explain important architectural decisions and trade-offs.
- Avoid presenting unverified technology choices as mandatory requirements.

### 4.7 Scope and Deliverables

- Define what is included in the initial implementation.
- Identify important exclusions and features that are out of scope.
- List the expected deliverables, such as the application, backend services, integrations, and documentation.
- Identify dependencies on external services, datasets, APIs, or infrastructure.

### 4.8 Success Criteria

- Define measurable outcomes that indicate whether the application solves the original problem.
- Include relevant metrics such as task completion rate, time saved, error reduction, adoption, reliability, or model performance, depending on the project.
- Specify target values and evaluation methods when they can be justified by evidence or user requirements.
- Do not invent numerical targets when a baseline or sufficient evidence is unavailable.

### 4.9 Constraints, Assumptions, and Risks

- Record technical, financial, regulatory, resource, and timeline constraints that affect the solution.
- Separate confirmed requirements from assumptions.
- Highlight unresolved questions and dependencies.
- Summarize the most important implementation, security, privacy, and operational risks, together with possible mitigations.

### 4.10 References

- Include the most relevant sources used to justify the problem, proposed solution, and architecture.
- Prefer authoritative and primary sources.
- Link claims to their supporting sources where practical.
- Distinguish research findings from the agents' recommendations.

The final document should remain concise enough to fit approximately one page. Prioritize the problem, evidence, proposed solution, essential features, architecture, and success criteria. If detailed requirements or references exceed the available space, include a short appendix or linked research report.

## 5. Validation Before Final Output

After generating the problem statement and solution brief, introduce a validation node to check the document before presenting it to the user.

The validation process should ensure that:

- The problem is clearly stated and consistent with the user's clarified requirements.
- The proposed solution addresses the identified problem rather than merely copying existing applications.
- Major recommendations are supported by research or explicitly labeled as assumptions.
- Features and architecture are technically plausible within the known constraints.
- The scope distinguishes essential functionality from optional enhancements.
- Success criteria are measurable where possible and do not contain fabricated targets.
- Important risks, dependencies, and unresolved questions are disclosed.
- Research claims have supporting sources wherever possible.
- The document is concise, internally consistent, and understandable to both technical and non-technical readers.

If critical information is missing or the judge identifies a material contradiction, return to the relevant existing node for further clarification or evaluation when appropriate.

The final output should be a clear, research-backed problem statement and solution brief that can serve as the starting point for project planning, system design, and implementation.

## 6. User Review and Approval

After validation, display the problem statement and solution brief to the user for review.

- Show the document in a readable format.
- Ask the user to review it and confirm whether it accurately describes the problem and the intended solution.
- Provide an explicit acceptance option and a text field where the user can describe changes or additions.
- If the user requests changes, pass their feedback to the appropriate node and update the document.
- Revalidate the revised document before presenting it again.
- Repeat this review cycle until the user explicitly accepts the final version.

If the user identifies a misunderstanding in the original requirements, return to the clarification node when appropriate. If the issue concerns research or proposal quality, revisit the relevant existing nodes.

Do not start implementation planning or code generation until the user approves the final problem statement and solution brief.

## 7. Planning Phase

After approval, introduce a planning node that creates a detailed implementation plan similar to Claude Code.

- Use Opus 5.5 for planning, assuming the model is available in the configured environment.
- Base the plan on the approved problem statement and solution brief.
- Break the work into implementation phases, milestones, and actionable tasks.
- Define the project structure, dependencies, architecture, APIs, frontend components, backend services, database design, and integrations.
- Identify relevant AI models, agents, tools, and workflows where applicable.
- Define testing strategies, acceptance criteria, and expected outputs for each major task.
- Identify dependencies between tasks and establish an execution order.
- Highlight important risks and technical decisions that need to be addressed before implementation.

The plan should be detailed enough for the implementation agent to execute without repeatedly making major architectural decisions or contradicting the approved requirements.

Present the plan to the user for review and approval before implementation begins. If the user requests changes, revise the plan accordingly.

## 8. Implementation Phase

Once the implementation plan is approved, start implementation using Sonnet 5.5, assuming the model is available in the configured environment.

- Implement the application or website according to the approved plan.
- Use appropriate tools, skills, and subagents when they improve implementation quality.
- Divide work into manageable tasks and track progress.
- Validate code changes through automated tests, error handling, linting, and relevant quality checks.
- Fix implementation issues before marking tasks as complete.
- Keep the implementation aligned with the approved problem statement and plan.
- Allow the user to provide additional instructions through the chat interface during implementation.
- Handle requested changes without unnecessarily overwriting working code or breaking completed functionality.
- Maintain a clear record of implementation progress and unresolved issues.

The system should report genuine progress and test results rather than claiming that tasks are complete without verification.

## 9. Live Preview and Session Isolation

Once the application is ready to run, provide a Lovable-like interface.

**Left side: Chat and instructions**

- Display the conversation between the user and the AI application builder.
- Allow the user to provide initial prompts, answer clarification questions, review documents, approve plans, and request implementation changes.
- Preserve relevant conversation context and project progress throughout the session.

**Right side: Live application preview**

- Run the generated application in an appropriate isolated development environment.
- Display the running website or application in a preview panel.
- Refresh or update the preview when implementation changes are successfully applied.
- Show useful build or runtime errors when the application fails to start.

**Separate project folders**

Save each generated project in its own isolated directory. For example:

- `generated_projects/session1/`
- `generated_projects/session2/`
- `generated_projects/session3/`

Each session should contain the generated source code, relevant configuration, dependencies, and project artifacts.

Implement session isolation so that:

- Each session has a unique identifier and its own project directory.
- Generated code does not overwrite or modify the existing application-builder codebase.
- One session cannot accidentally overwrite another session's files or runtime.
- The correct conversation, approved requirements, implementation plan, and execution state are associated with each session.
- The application builder can resume a session where appropriate.
- File access, terminal commands, package installation, and application execution are restricted to the appropriate project environment.
- Resource usage and processes are managed so that one generated project does not unintentionally disrupt another.

The goal is to let users build multiple independent applications while keeping the core application builder stable and protected.

## 10. How Our Application Builder Will Manage AI Projects

The following requirements apply to **our application-builder platform itself**, not to the individual applications or websites it generates for users.

Our platform must be designed to manage the complete lifecycle of AI-driven software generation reliably, from the initial user prompt to the final running preview. The generated projects may have different architectures and requirements, but our builder needs a consistent internal system for managing prompts, agents, tools, memory, safety, knowledge, and execution.

Analyze the existing codebase first and identify which capabilities already exist, which need improvement, and which must be introduced.

### 10.1 Hallucination Prevention

Design mechanisms to reduce unsupported claims and incorrect implementation decisions throughout the builder's workflow.

- Ground research and problem statements in retrieved evidence and source citations.
- Clearly distinguish verified facts, user-provided information, assumptions, and recommendations.
- Require the critic, judge, and validation nodes to challenge unsupported claims.
- Validate tool outputs, generated plans, code changes, and test results where practical.
- Ensure that agents do not claim a build, test, installation, or preview succeeded unless the relevant operation confirms it.
- Track unresolved questions and communicate uncertainty to the user.

### 10.2 Prompt Rot Prevention and Prompt Maintenance

Design a strategy to prevent agent instructions from becoming outdated or inconsistent as the platform evolves.

- Keep prompts version-controlled and organized by agent, node, and responsibility.
- Define clear ownership and responsibilities for each prompt.
- Maintain prompt evaluation cases and regression tests.
- Test important prompt changes against representative workflows before deploying them.
- Monitor quality regressions, repeated failures, and changes in model behavior.
- Establish a process for reviewing, updating, and retiring outdated instructions.
- Keep prompts aligned with the current tools, schemas, models, and application-builder architecture.

### 10.3 Prompt Management

Create a centralized and maintainable prompt-management approach.

- Separate system instructions, agent-specific instructions, user requirements, retrieved evidence, and task context.
- Avoid duplicating conflicting instructions across agents.
- Support prompt versioning, reusable templates, and controlled configuration.
- Ensure that changes to one agent's prompt do not unintentionally break other agents.
- Record which prompt versions and model configurations were used for each session.
- Evaluate whether prompt caching, structured outputs, or other optimization techniques are useful.

### 10.4 Tool Management

Define how our platform will register, authorize, execute, and monitor tools used by the research and implementation agents.

- Identify which tools are needed for research, file operations, coding, testing, terminal execution, and preview management.
- Define tool input and output schemas and validate them.
- Apply permission boundaries to file access, command execution, external APIs, and network access.
- Require explicit user approval for sensitive or destructive actions where appropriate.
- Handle timeouts, retries, rate limits, failures, and tool-result validation.
- Log tool calls and their outcomes for debugging and auditing.
- Prevent generated projects from accessing the builder's protected files or another session's resources.

### 10.5 Skills and Subagent Management

Define how our application builder will organize reusable skills and specialized subagents.

- Identify the specialized capabilities needed for research, architecture, frontend development, backend development, testing, debugging, and code review.
- Establish clear responsibilities, input/output contracts, and execution boundaries for each subagent.
- Create reusable skills for recurring development tasks and workflows.
- Decide when tasks should be delegated to subagents and when the main agent should handle them directly.
- Avoid unnecessary agent spawning, duplicated work, conflicting edits, and excessive token usage.
- Track task ownership, dependencies, results, and failures.
- Reuse existing agents wherever practical rather than introducing unnecessary complexity.

### 10.6 Short-Term and Long-Term Memory

Design memory management for our platform across both individual tasks and multiple sessions.

**Short-term memory**

- Maintain the active conversation context, clarification answers, current research findings, working plan, task progress, and relevant tool results.
- Use LangGraph state and checkpointing where appropriate.
- Preserve execution state across clarification pauses and recoverable interruptions.
- Manage context size through summarization, selective retrieval, and removal of irrelevant information.

**Long-term memory**

- Store durable project requirements, user-approved decisions, architectural choices, relevant implementation history, and reusable lessons when appropriate.
- Associate memories with the correct user and project session.
- Retrieve relevant information when resuming a project or performing related tasks.
- Update or invalidate outdated decisions when the user approves changes.
- Apply appropriate retention, privacy, access-control, and deletion policies.

Do not mix unrelated project memories or allow information from one user's session to leak into another user's project.

### 10.7 Guardrails and Security

Define guardrails for both AI reasoning and code execution.

- Protect the workflow against prompt injection in user input, retrieved documents, repositories, and external web content.
- Treat external content as untrusted data rather than authoritative instructions.
- Enforce tool permissions and session-specific file-system boundaries.
- Validate generated code and commands before execution where appropriate.
- Protect secrets, credentials, environment variables, and sensitive user data.
- Prevent unauthorized access to other sessions or the core application-builder codebase.
- Apply resource limits, timeouts, and process isolation to generated applications.
- Introduce human approval for high-impact, destructive, or otherwise sensitive actions.
- Record security-relevant events and provide actionable error messages without exposing secrets.

### 10.8 Workflow Triggers and Event Management

Define the conditions under which our platform should execute, pause, resume, or repeat workflow nodes.

Examples include:

- A new user prompt triggers clarification or requirement analysis.
- Missing or ambiguous requirements trigger another clarification round.
- Sufficiently clarified requirements trigger research.
- Completed research triggers proposal generation.
- A completed proposal triggers criticism and evaluation.
- Material contradictions trigger further clarification or re-evaluation.
- A validated problem statement triggers user review.
- Explicit user approval triggers planning.
- An approved implementation plan triggers code generation.
- Completed code changes trigger relevant tests and build checks.
- A successful build triggers or refreshes the live preview.
- A tool failure triggers appropriate retry or recovery logic.
- A user-requested change updates the relevant requirements, plan, or implementation tasks.
- A pause or interruption allows the session to resume without unnecessarily repeating completed work.

Reuse existing LangGraph routing, interrupts, checkpointing, and recovery mechanisms wherever appropriate. Define explicit conditions for transitions so that the workflow does not loop indefinitely or start implementation before approval.

### 10.9 Prompting Strategies

Establish consistent prompting practices across the builder's agents.

- Use clear role definitions, task instructions, and expected outputs.
- Use structured schemas for research results, proposals, critiques, decisions, problem statements, and implementation plans where appropriate.
- Provide only the context relevant to each task.
- Separate user requirements from research evidence and untrusted external content.
- Use evidence-based reasoning, explicit uncertainty, and validation requirements.
- Define stopping conditions and escalation rules for ambiguous or high-risk tasks.
- Use model-specific prompting strategies only where evaluations demonstrate a benefit.
- Maintain regression tests for critical prompts and workflow transitions.

### 10.10 Knowledge Base and External Information

Define how our application builder will collect, organize, retrieve, and maintain its own knowledge sources.

- Identify the research sources needed for application discovery, technical feasibility, architecture, and implementation.
- Use authoritative documentation, research papers, source repositories, and other relevant sources.
- Store useful research results, source metadata, citations, and project-specific technical decisions where appropriate.
- Evaluate whether a searchable knowledge base or retrieval-augmented generation (RAG) is justified for recurring information.
- Keep retrieved content separate from trusted system instructions.
- Track source freshness and handle outdated or contradictory information.
- Associate project-specific knowledge with the correct session.
- Avoid creating a large knowledge base without a clear use case, retrieval strategy, and maintenance plan.

### 10.11 Evaluation, Observability, and Cost Management

Our platform should also provide mechanisms to understand whether the workflow is performing reliably.

- Track node execution, model usage, latency, token consumption, tool calls, and failures.
- Measure research quality, clarification effectiveness, problem-statement accuracy, plan quality, build success, and preview readiness.
- Maintain regression tests for representative end-to-end user requests.
- Record useful traces and errors without unnecessarily logging sensitive information.
- Monitor costs and establish sensible limits for model calls, retries, research, and subagent execution.
- Use evaluation results to improve prompts, routing, tools, and agent responsibilities.

These capabilities should be designed for the application builder itself. They should not automatically be inserted into every generated application. A generated project should receive only the AI infrastructure, memory, tools, or guardrails that its own approved requirements actually need.

## 11. Implementation Handoff

Create a `handoff.md` file containing short, actionable steps that we will follow to implement this project incrementally.

Before writing the plan, inspect the existing repository, graph structure, state definitions, node implementations, prompts, agents, checkpointing, tool integrations, tests, and project configuration.

The handoff document should:

1. Summarize the current architecture and the existing workflow.
2. Identify which nodes and agents can be reused without major changes.
3. Identify which prompts, schemas, state fields, and routing conditions need updating.
4. List the new nodes needed after the judge, including problem statement generation, validation, user review, approval, planning, implementation, and preview.
5. Describe how human approval and clarification interruptions will work.
6. Define the session-based project isolation and execution strategy.
7. Outline the platform-level prompt, tool, skill, subagent, memory, guardrail, trigger, knowledge, evaluation, and observability requirements.
8. Identify the smallest practical milestones and their dependencies.
9. Specify tests and validation checkpoints for every major phase.
10. Explain how existing functionality will be preserved and how changes will be integrated safely.

Keep the steps short, practical, and easy to follow. Organize them in the order in which we should implement and verify the system.

## 12. Important Constraints

- Reuse the existing LangGraph workflow, including `clarification`, `await_clarification`, `research`, `propose`, `critic`, and `judge`.
- Adapt the existing nodes' prompts and logic to the application-builder goal.
- Introduce new nodes after the judge for problem statement generation, validation, user review, approval, planning, implementation, and preview.
- Preserve existing functionality and avoid unnecessary rewrites.
- Treat problem statement approval and implementation-plan approval as separate checkpoints.
- Do not begin implementation before the user approves the problem statement and the implementation plan.
- Keep generated projects isolated from the core application builder and from each other.
- Design platform-level AI management capabilities separately from the requirements of individual generated projects.
- Do not assume Opus 5.5 or Sonnet 5.5 is available without checking the configured model provider.
- Do not invent capabilities, research findings, performance figures, or test results.
- Build incrementally, testing each milestone before moving forward.

## 13. Expected Outcome

The final product should be an AI application builder similar to Lovable that:

1. Accepts an arbitrary app or website idea from a user.
2. Clarifies requirements through an interactive LangGraph workflow.
3. Researches existing solutions, user feedback, research papers, and technical feasibility.
4. Generates, critiques, and evaluates possible solutions.
5. Produces a validated, research-backed problem statement and solution brief.
6. Obtains explicit user approval and incorporates requested changes.
7. Creates an implementation plan and obtains approval.
8. Builds the application using the configured coding model and appropriate tools.
9. Runs tests and validates the generated application.
10. Displays the running application in a live preview beside a chat interface.
11. Saves every generated project in its own isolated session folder.
12. Maintains reliable prompts, tools, skills, subagents, memory, guardrails, workflow triggers, knowledge sources, evaluations, and observability within the application-builder platform itself.

**First task:** Analyze the existing codebase and workflow, then create `handoff.md` with the implementation plan. Do not start implementing the full application until we have reviewed and agreed on that plan.

---

Working agreements added by the user in the same conversation (2026-10-24):
- After each step, create scripts and execute them to verify the changes; ask the user when something needs their input (they are available).
- After each verified step the **user** commits and pushes; the agent never commits. Then move to the next step.
- Use "a simple calculator web app" as the short, standard test idea: if the smallest project builds end to end, bigger projects can follow.
- Record issues met and the way of working in `handoff.md` so a new agent or session can continue without the chat context.
