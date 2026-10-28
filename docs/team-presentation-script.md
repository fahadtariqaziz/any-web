# Team video call script: AI App Builder (ai-lab-2)

About 7–8 minutes spoken. Lines in *[brackets]* are cues for you, not words to say.

---

## 1. Opening (30 seconds)

Hi everyone, thanks for joining. Today I want to show you what I've been building: an AI app builder, similar to
Lovable. You describe an app in plain words, for example "I want to build a calculator app", and the system takes it
all the way to a working app you can try live in the browser.

What's different from a simple "prompt in, code out" tool is that it doesn't jump straight into code. First it
understands the idea, researches it, compares a few solutions, writes a brief, and gets your approval. Only then does
it plan and build. You stay in control at every important step.

I'll walk you through it in four phases, then show you a real project.

---

## 2. Phase 1: from idea to solution (about 2 minutes)

**Step one is Intake.** You type your idea. One AI call turns it into a structured summary: the app's name, its
features, any constraints, and what's still missing.

**Step two is Clarification.** The AI asks you at most five questions, in one round, for example "Who will use this
app?", and each question comes with a few answer options you can tap, or you type your own. The run pauses until you
answer; you can skip questions you don't care about. Then it moves on.

**Step three is Research.** The system searches the web in three areas at the same time: existing apps and what
users complain about, research papers, and technical feasibility. One AI call plans the searches, the searches run in
parallel, and then one AI call per area pulls out the useful evidence. The searching itself is done by **Tavily**, a
web search API, not by Claude. Claude decides what to search and reads the results, but every source and link comes
straight from Tavily, so the AI can't invent a reference.

**Step four is the Proposer.** Based on that research, it writes two or three possible solutions.

**Step five is the debate: Critic and Judge.**
- The **Critic** looks at each proposal separately, in parallel, and finds its weaknesses. In the same batch, each
  proposal's claims are checked against the evidence it cited.
- The **Judge** scores all proposals in one AI call. Then plain Python adds up the scores, picks the winner, and
  takes the winner's claim check from the Critic's batch: which claims are verified, which are unsupported. So the
  final decision is calculated, not guessed, and it already knows where the winner's evidence is thin.

What happens when the system isn't confident? By default we use a fast path: anything the Judge is unsure about,
like thin evidence or an unsupported claim of the winner, goes into the brief as an open question, and your review
of the brief is where it gets fixed. We can also switch on automatic loops with one setting. Then the Judge can send
the run back to Research or Clarification on its own. That's more thorough, but each loop adds about a minute.
Either way, nothing uncertain is hidden.

---

## 3. Phase 2: the brief (about 1.5 minutes)

**Final Report.** Python collects the debate results: the winner, the alternatives, the evidence, and the open
questions. No AI call here.

**Brief Writer.** The AI writes a compact brief: the problem, the users, the features, the scope, the technology,
and the risks, with real references, and no appendix: everything is on the page. At the same time, a second AI call
writes a short, readable summary of the report.

**Brief Validator.** First Python checks the brief, for example that every section is there and the references are
real. Then one AI call reviews it. If there's a real problem, the validator asks for a rewrite, once on the fast path.
Smaller problems are listed in the brief as open issues, so you see them.

**Brief Review. This is the first approval point.** You read the brief and either approve it or ask for changes. If you
ask for changes, a router sends them to the right place:
- a wording change goes back to the Brief Writer
- a requirements change goes back to Clarification
- "we need more research" goes back to Research
- "I want a different solution" goes back to the Proposer

---

## 4. Phase 3: planning and building (about 1.5 minutes)

**Planner.** Once the brief is approved, the Planner writes a step-by-step implementation plan: the tasks, the files
each task touches, and the commands that test it. In Claude mode this uses our strongest model, Opus. In local mode
it uses the local model.

**Plan Review. This is the second approval point.** You approve the plan, or ask for changes, which go back to the
Planner, up to three times.

**Implementer.** Now a coding agent builds the app one task at a time. It can only work inside that project's own
folder, so it can't touch the builder itself or any other project. Each task is checked by actually running its test
commands. We don't take the AI's word that it worked. This repeats until every task is done, failed, or blocked.

**Build Check.** Plain Python runs install, test, and build, and then scans the generated code for anything that
looks like an API key or a password. If something fails, it adds a fix task and sends it back to the Implementer, at
most twice; a fix task also gets a short triage procedure: reproduce first, read the first error, never delete a test
to go green. After that, the preview starts anyway and shows you the errors, so nothing is hidden.

---

## 5. Phase 4: preview and completion (about 1 minute)

**Preview.** The system starts the app's dev server, waits until it actually answers, and shows the live app right
next to the chat, so you can click around in it.

**Then you choose one of three options:**
- **Change:** for small things, like "make it dark mode". It becomes one new task, goes through the Implementer and
  the Build Check, and you get a fresh preview.
- **Plan a bigger change:** for new features. This does not go straight to coding. The brief is updated first and
  validated again, you approve the brief and the plan again, and only the new tasks are built.
- **Finish:** goes to Completion.

**Completion.** Everything is saved and the run gets a final status: completed, completed with uncertainty, or
failed. A finished project can be reopened later for more changes.

Three more things. First, if any step fails, the run goes straight to Completion with the status "failed", so it
never hangs halfway. Second, you can press **Stop** at any time: the step in progress finishes and is saved, nothing
later starts, and only you press Continue. Third, next to the flow there's an **Ask** chat where you can ask questions
about the project at any time. It isn't a step in the flow.

---

## 6. Behind the scenes (about 45 seconds)

A few things that make this solid and not just a demo:
- **Cost tracking:** every AI call is measured, so we can see the cost per stage, per project, and per change, and
  there are spending limits.
- **Every tool call is logged**, so when something goes wrong we can see exactly what the agent did.
- **All prompts are versioned and locked**, with evaluation cases, so nobody changes a prompt by accident and quality
  doesn't silently drop.
- **Local mode:** with one setting, everything runs on a local model instead of Claude. It's free but slower and less
  capable, which is useful for development and testing.
- **Tests:** about 320 automated tests run offline in under a minute, plus live check scripts for every
  milestone.
- **A landing page that shows each functionality** with a live-looking mock of its screen, and an animated builder:
  question cards with options, gradient stage chips, a frosted top bar.

---

## 6b. Agent anatomy: is every step an agent? (about 2 minutes, optional)

*[Show the "Anatomy of an Agent" slide. The full mapping is in `docs/builder-agent-anatomy.md`.]*

People often ask whether every step is an agent. It isn't, on purpose. The flow is a fixed workflow in LangGraph,
and inside it there are three real agents: the **coding agent**, which writes the app; the **Ask** chat; and a
**researcher sub-agent** that Ask can hand research questions to. The other steps are single, focused AI calls with
a strict output format, or plain Python. Python makes every decision about what happens next.

In numbers: getting to the brief takes about fifteen to twenty AI calls, most of them in parallel. The planner is one
Opus call. The coding agent runs one session per task, up to three tasks at once.

Tools: the coding agent has six, which are read, write, edit, find files, search, and our own run-command tool. It
has no shell, and it can't leave the project's folder. Ask has five tools, including searching our knowledge base
and calling the researcher. The graph steps have no tools at all. Python does the web searches at a fixed step,
which keeps time and cost predictable.

We have ten skills: three for Ask, loaded only when a question needs them, and seven for the coding agent, picked
by Python from the project's tech stack, or, for a fix task, by the kind of task. The knowledge base holds six curated
docs plus the evidence from every finished project, each with the date it was verified, and Ask and the researcher use
it.

Against hallucination and context rot, the rule is: every call gets only what its job needs, and facts come from
Python, not from the model. Each critic sees one proposal. The coding agent sees only its own task and starts fresh
for every task. Sources, links and scores are handled by Python. Every claim in the brief is labelled and cited.
And a task only counts as done when its tests actually pass.

---

## 6c. What the architecture review changed, and what we kept on purpose (about 2 minutes)

*[Say this when someone asks "did you just add more agents?" The full table is section 7 of
`docs/builder-agent-anatomy.md`.]*

We had the design reviewed against production practice: sub-agents, knowledge base, skills, prompting, guardrails,
memory, triggers, context. The useful part wasn't the list of things to add. It was two rules: keep every step that
gives independent validation, human control or verification, and remove only redundant orchestration; and do
reliability and guardrails before more agents.

So we applied those rules to our own code, and here is what came out.

**We merged one node.** The Evidence Checker made no AI call of its own; it reused the Critic's claim check and then
made a second routing decision about the same question: "is the winner defensible?" That decision now lives in one
place, the Judge, with all its inputs. Nothing it verified was dropped; the graph just has one decision point instead
of two.

**We kept three things the review suggested cutting**, because its own conditions say so once you look at the code.
The Final Report is saved, shown and served by the API, so it stays a step. The Brief Writer can't be one call: the
whole brief exceeds the API's structured-output limit, and the three parts already run in parallel, so it costs one
call's time anyway. And the preview is the product.

**We added guardrails before agents.** Every build check now scans the generated code for secrets, so "keys never go
in code" is checked, not trusted. And there's a safe Stop: the current step finishes and is saved, and only you
continue.

**Instead of a QA agent, we wrote a procedure.** A fix task now gets a failure-triage skill: reproduce first, read
the first error, name the cause, never weaken a test. Pass or fail still comes from the exit codes, so an agent's
opinion can never be mistaken for a result. We also added a secure-coding skill for every project.

**Prompts got examples where judgement matters.** The claim check and the Critic now carry a few decision-boundary
examples: a capability in a source never proves an outcome; individual reports are anecdotal; "it might not scale"
for a personal tool is not a finding. Each change has eval cases and a new locked version.

**Knowledge got a date and memory got a source.** Every knowledge result says when it was verified, and results for
the project's own stack rank first. Every remembered fact says whether you said it or the assistant noted it, and
when, so the model never mistakes an old note for your current words.

What we did not do, on purpose: no independent reviewer agent yet, because the critic, the claim check and the judge
already give three independent reads and the evals haven't shown a miss; no vector search, because we've measured no
retrieval miss; no skills for the single-call steps, because without a tool loop a skill is just more prompt text.
Each of those has a trigger written down for when it would become worth it.

---

## 7. Demo (optional, 1–2 minutes)

*[Open the reference calculator project: http://localhost:3001/c/e39ceeb5-cf6b-4950-b518-b656ec65515b.
If the preview has stopped, press Start.]*

Here's a real project. On the left is the conversation, where you can see every pause: the clarification questions,
the brief approval, and the plan approval. On the right are the tabs: Preview, Brief, Plan, Build, and Activity.

*[Click Preview.]* This is the calculator it built. We then extended it live: first dark mode and a percent key as
small changes, and then a scientific mode as a "bigger change", which went through the brief and the plan again.

*[Click Build and show the Cost card.]* And here you can see what each stage cost.

---

## 8. Closing (30 seconds)

So in one sentence: you describe an idea, the system clarifies it, researches it, debates the options, writes a brief
you approve, plans the build you approve, codes it task by task with real tests, and shows you a live preview you can
keep changing.

Next, I want to run a brand-new idea end to end in the new interface, which will also give us a cost baseline per
stage. After that, the optional next step is running each project inside its own Docker container for stronger
isolation.

Happy to take questions.

---

## Quick cheat sheet (if you lose your place)

Idea → Clarification (one round, up to 5 questions with options) → Research (3 areas) → Proposals → Critique + Claim Checks → Judge (scores,
winner, winner's claims; doubts become open questions; with automatic loops on, it can go back to Research or
Clarification) → Report → Brief → Validation → **Brief Approval** → Plan → **Plan Approval** → Coding (task by task) →
Build Check + secret scan (+ fix tasks with triage) → Preview → Change / Bigger Change / Finish → Completion. **Stop**
works at any point and keeps everything done so far.
