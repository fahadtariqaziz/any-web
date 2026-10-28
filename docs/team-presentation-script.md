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

**Step two is Clarification.** If something important is missing, the AI asks you questions, for example "Do you also
need scientific functions?", and the run pauses until you answer. This can happen up to three rounds, and you can
skip questions you don't care about. Once there's enough information, it moves on.

**Step three is Research.** The system searches the web in three areas at the same time: existing apps and what
users complain about, research papers, and technical feasibility. One AI call plans the searches, the searches run in
parallel, and then one AI call per area pulls out the useful evidence. The searching itself is done by **Tavily**, a
web search API, not by Claude. Claude decides what to search and reads the results, but every source and link comes
straight from Tavily, so the AI can't invent a reference.

**Step four is the Proposer.** Based on that research, it writes two or three possible solutions.

**Step five is the debate: Critic, Judge, and Evidence Checker.**
- The **Critic** looks at each proposal separately, in parallel, and finds its weaknesses. In the same batch, each
  proposal's claims are checked against the evidence it cited.
- The **Judge** scores all proposals in one AI call. Then plain Python adds up the scores and picks the winner, so
  the final decision is calculated, not guessed.
- The **Evidence Checker** makes no new AI call. It reuses the winner's claim check.

What happens when the system isn't confident? By default we use a fast path: anything the Judge or the Evidence
Checker is unsure about, like thin evidence or an unsupported claim, goes into the brief as an open question, and
your review of the brief is where it gets fixed. We can also switch on automatic loops with one setting. Then the
Judge can send the run back to Research or Clarification on its own, and so can the Evidence Checker. That's more
thorough, but each loop adds about a minute. Either way, nothing uncertain is hidden.

---

## 3. Phase 2: the brief (about 1.5 minutes)

**Final Report.** Python collects the debate results: the winner, the alternatives, the evidence, and the open
questions. No AI call here.

**Brief Writer.** The AI writes a one-page brief: the problem, the users, the features, the scope, the technology,
and the risks, with real references. At the same time, a second AI call writes a short, readable summary of the
report.

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

**Build Check.** Plain Python runs install, test, and build. If something fails, it adds a fix task and sends it back
to the Implementer, at most twice. After that, the preview starts anyway and shows you the errors, so nothing is
hidden.

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

Two more things. First, if any step fails, the run goes straight to Completion with the status "failed", so it never
hangs halfway. Second, next to the flow there's an **Ask** chat where you can ask questions about the project at any
time. It isn't a step in the flow.

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
- **Tests:** about 270 automated tests run offline in around 40 seconds, plus live check scripts for every
  milestone.

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

We have seven skills: three for Ask, loaded only when a question needs them, and four for the coding agent, picked
by Python from the project's tech stack. The knowledge base holds six curated docs plus the evidence from every
finished project, and Ask and the researcher use it.

Against hallucination and context rot, the rule is: every call gets only what its job needs, and facts come from
Python, not from the model. Each critic sees one proposal. The coding agent sees only its own task and starts fresh
for every task. Sources, links and scores are handled by Python. Every claim in the brief is labelled and cited.
And a task only counts as done when its tests actually pass.

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

Idea → Clarification (up to 3 rounds) → Research (3 areas) → Proposals → Critique + Claim Checks → Judge → Evidence
Check (doubts become open questions; with automatic loops on, it can go back to Research or Clarification) → Report → Brief → Validation → **Brief Approval** → Plan →
**Plan Approval** → Coding (task by task) → Build Check (+ fix tasks) → Preview → Change / Bigger Change / Finish →
Completion
