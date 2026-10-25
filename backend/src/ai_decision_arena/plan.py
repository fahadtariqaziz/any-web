"""The implementation plan in pure Python (no LLM): the brief-aware schema, markdown rendering, approval hash and the
tasks list the implementer (M8) works through.

Trust boundaries kept here (in addition to ImplementationPlan's own validators: ids, dependency order, files,
allowlisted commands):
- Every MVP feature of the APPROVED brief must be covered by at least one task (`plan_schema_for`): the planner
  cannot silently drop a feature the user approved. The check runs inside call_structured's validation, so a
  missing feature goes back to the planner with the exact list.
- Approval is bound to the exact plan markdown (sha256), like the brief's.
- A plan for an app that is ALREADY BUILT (M10: a bigger change after the brief was updated) is written as a
  PlanExtension with only the new work; Python merges it with the built part (`built_part`, `merge_extension`) and the
  MERGED plan must pass every check above. Built tasks keep their status; only the new ones are pending.
"""

import hashlib

from pydantic import model_validator

from ai_decision_arena.schemas import ImplementationPlan, PlanExtension


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


def built_part(plan: ImplementationPlan, tasks: list[dict]) -> ImplementationPlan | None:
    """The part of the stored plan that was already worked on (its tasks are no longer pending), or None when
    nothing is built yet. A pending extension under review is dropped, so a revision starts again from the build."""
    worked = {t["id"] for t in tasks if t.get("status") != "pending"}
    kept = [t for t in plan.tasks if t.id in worked]
    if not kept:
        return None
    used_phases = {t.phase for t in kept}
    kept_ids = {t.id for t in kept}
    coverage = [c.model_copy(update={"task_ids": [i for i in c.task_ids if i in kept_ids]}) for c in plan.feature_coverage]
    return plan.model_copy(update={"tasks": kept, "phases": [p for p in plan.phases if p.id in used_phases],
                                   "feature_coverage": [c for c in coverage if c.task_ids]})


def merge_extension(built: ImplementationPlan, ext: PlanExtension) -> dict:
    """The built plan + the extension, as plain data for ImplementationPlan validation: built phases / tasks first, the
    new ones after; everything descriptive (summary, stack, structure, commands...) comes from the extension, which
    describes the whole project after the change."""
    data = ext.model_dump(mode="json")
    built_phase_ids = {p.id for p in built.phases}
    data["phases"] = [p.model_dump(mode="json") for p in built.phases] + [p for p in data["phases"]
                                                                          if p["id"] not in built_phase_ids]
    data["tasks"] = [t.model_dump(mode="json") for t in built.tasks] + data["tasks"]
    return data


def extension_schema_for(mvp_features: list[str], built: ImplementationPlan) -> type[PlanExtension]:
    """PlanExtension + a check that the MERGED plan passes every ImplementationPlan check and covers the MVP (so a
    problem goes back to the planner with the exact message, inside call_structured)."""
    full = plan_schema_for(mvp_features)
    built_ids = [t.id for t in built.tasks]

    class CheckedPlanExtension(PlanExtension):
        @model_validator(mode="after")
        def merged_plan_is_valid(self) -> "CheckedPlanExtension":
            reused = [t.id for t in self.tasks if t.id in built_ids]
            if reused:
                raise ValueError(f"new task ids must not reuse built task ids {reused}; continue after {built_ids[-1]}")
            if not self.tasks:
                raise ValueError("an extension needs at least one new task")
            try:
                full.model_validate(merge_extension(built, self))
            except ValueError as exc:
                raise ValueError(f"merged with the built tasks ({', '.join(built_ids)}), the plan is invalid: {exc}") from exc
            return self

    CheckedPlanExtension.__name__ = "PlanExtension"
    CheckedPlanExtension.__qualname__ = "PlanExtension"
    return CheckedPlanExtension


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


def render_plan_markdown(plan: ImplementationPlan, project_name: str, revision: int, model: str,
                         built_ids: frozenset[str] = frozenset()) -> str:
    """built_ids: tasks that are already built (a plan extension): marked, so the reader sees what is new."""
    phase_names = {p.id: p.name for p in plan.phases}
    new = [t.id for t in plan.tasks if t.id not in built_ids]
    out = [f"# Implementation plan: {project_name.strip().capitalize() or 'your project'}",
           f"*Plan version {revision + 1} · written by {model} from the approved brief*", ""]
    if built_ids:
        out += [f"> **{len(new)} new task{'s' if len(new) != 1 else ''} ({', '.join(new)})** on top of the "
                f"{len(built_ids)} already built (marked *built*). Only the new tasks run.", ""]
    out += [plan.summary.strip(), "",
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
            if t.id in built_ids:
                out += [f"**{t.id}. {t.title}** · *built*", ""]
                continue
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
