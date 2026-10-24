"""The implementation plan in pure Python (no LLM): the brief-aware schema, markdown rendering, approval hash and the
tasks list the implementer (M8) works through.

Trust boundaries kept here (in addition to ImplementationPlan's own validators: ids, dependency order, files,
allowlisted commands):
- Every MVP feature of the APPROVED brief must be covered by at least one task (`plan_schema_for`): the planner
  cannot silently drop a feature the user approved. The check runs inside call_structured's validation, so a
  missing feature goes back to the planner with the exact list.
- Approval is bound to the exact plan markdown (sha256), like the brief's.
"""

import hashlib

from pydantic import model_validator

from ai_decision_arena.schemas import ImplementationPlan


def _norm(text: str) -> str:
    return " ".join(text.lower().split()).strip(" .")


def plan_schema_for(mvp_features: list[str]) -> type[ImplementationPlan]:
    """ImplementationPlan + a check that feature_coverage names every MVP feature of the approved brief verbatim."""
    required = [f for f in mvp_features if f.strip()]

    class CheckedImplementationPlan(ImplementationPlan):
        @model_validator(mode="after")
        def covers_every_mvp_feature(self) -> "CheckedImplementationPlan":
            covered = {_norm(c.feature) for c in self.feature_coverage if c.task_ids}
            missing = [f for f in required if _norm(f) not in covered]
            if missing:
                raise ValueError("feature_coverage must contain every MVP feature of the approved brief, copied "
                                 "exactly, each with the tasks that implement it. Missing: " + "; ".join(missing))
            return self

    CheckedImplementationPlan.__name__ = "ImplementationPlan"          # the schema name Claude sees
    CheckedImplementationPlan.__qualname__ = "ImplementationPlan"
    return CheckedImplementationPlan


def plan_hash(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def plan_is_approved(state: dict) -> bool:
    """True only if the user approved EXACTLY the plan in the state now, and the brief it was made from is still the
    approved one. The implementer route (M8) checks this, not only the UI."""
    from ai_decision_arena.brief import brief_is_approved

    digest = state.get("plan_approved_hash")
    return bool(state.get("plan_approved_at") and digest and digest == plan_hash(state.get("plan_markdown", ""))
                and brief_is_approved(state))


def tasks_from_plan(plan: ImplementationPlan) -> list[dict]:
    """The implementer's work list (M8 updates status / attempts / result)."""
    return [{"id": t.id, "title": t.title, "phase": t.phase, "depends_on": t.depends_on, "status": "pending",
             "attempts": 0, "result": None} for t in plan.tasks]


def _bullets(items: list[str]) -> list[str]:
    return [f"- {i}" for i in items] if items else ["- none"]


def render_plan_markdown(plan: ImplementationPlan, project_name: str, revision: int, model: str) -> str:
    phase_names = {p.id: p.name for p in plan.phases}
    out = [f"# Implementation plan: {project_name.strip().capitalize() or 'your project'}",
           f"*Plan version {revision + 1} · written by {model} from the approved brief*", "", plan.summary.strip(), "",
           "## Technology", "", *_bullets(plan.tech_stack), "",
           "## Architecture", "", plan.architecture.strip(), "",
           f"**Data model:** {plan.data_model.strip()}", ""]
    for title, items in (("Project structure", plan.project_structure), ("Dependencies", plan.dependencies),
                         ("API endpoints", plan.api_endpoints), ("Frontend components", plan.frontend_components),
                         ("Backend services", plan.backend_services), ("Integrations", plan.integrations)):
        if items:
            out += [f"**{title}**", "", *_bullets(items), ""]
    if plan.ai_components.strip().lower() not in ("", "none"):
        out += [f"**AI components:** {plan.ai_components.strip()}", ""]

    out += ["## Phases and tasks", ""]
    for phase in plan.phases:
        out += [f"### {phase.id}. {phase.name}", f"*{phase.goal.strip()}*", ""]
        for t in [t for t in plan.tasks if t.phase == phase.id]:
            deps = f" · after {', '.join(t.depends_on)}" if t.depends_on else ""
            out += [f"**{t.id}. {t.title}**{deps}", "", t.description.strip(), ""]
            if t.files:
                out += [f"- Files: {', '.join(f'`{f}`' for f in t.files)}"]
            out += [f"- Done when: {'; '.join(t.acceptance_criteria)}",
                    f"- Verified by: {', '.join(f'`{c}`' for c in t.verify_commands)}", ""]
    orphans = [t for t in plan.tasks if t.phase not in phase_names]
    for t in orphans:                                                # (validators prevent this; keep it visible)
        out += [f"**{t.id}. {t.title}** (no phase)", ""]

    out += ["## MVP coverage", "", "| MVP feature (approved brief) | Tasks |", "|---|---|"]
    out += [f"| {c.feature.replace('|', '/')} | {', '.join(c.task_ids)} |" for c in plan.feature_coverage]
    out += ["", "## Testing strategy", "", *_bullets(plan.testing_strategy), "",
            "## Commands", "",
            f"- Install: {', '.join(f'`{c}`' for c in plan.commands.install) or 'none'}",
            f"- Test: {', '.join(f'`{c}`' for c in plan.commands.test)}",
            f"- Build: {', '.join(f'`{c}`' for c in plan.commands.build) or 'none'}",
            f"- Dev server: `{plan.commands.dev}` (listens on `$PORT`)", "",
            "## Risks and decisions", "", *_bullets(plan.risks_and_decisions), ""]
    return "\n".join(out).rstrip() + "\n"
