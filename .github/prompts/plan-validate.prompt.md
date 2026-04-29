---
description: "2-layer plan validation: instant structural checks + trigger-based specialist subagents. Auto-fixes issues using ADRs and first principles. Every issue must be resolved before execution. Use after /plan-start, before /plan-execute."
argument-hint: "Plan name (e.g. user-authentication) — omit to pick up the most recent plan"
agent: "agent"
tools: [read, search, agent, edit]
model: "Claude Sonnet 4.6 (copilot)"
---

<!-- Source: https://github.com/FlorianBruniaux/claude-code-ultimate-guide/blob/968bba91b877c90dd17230e91aa1e3d9d224a344/examples/commands/plan-validate.md -->
<!-- Adaptation: Task tool → runSubagent (sequential, reports returned directly) -->
<!-- Adaptation: CLAUDE.md → AGENTS.md | Read/Grep/Glob → read/search aliases -->

# Plan Validate — 2-Layer Validation

Independently validate the plan produced by `/plan-start`. **No code is written.**
Start a new conversation after this prompt before running `/plan-execute`.

Validation is separate from planning by design: validators that didn't write the plan
are not anchored to its assumptions.

---

## Prerequisite

A committed plan file must exist at `docs/plans/plan-{name}.md`. If multiple plans
exist, list them and ask the user which to validate.

---

## Layer 1: Structural Validation

Run immediately, no subagents required. Check the plan document for:

**Format & Completeness**
- [ ] All required sections present (Summary, Decisions, Architecture, Tasks, Test Plan, Out of Scope)
- [ ] Each task has: description, files affected, acceptance criteria, layer assignment

**Dependency Chain**
- [ ] No circular dependencies between tasks
- [ ] Tasks in higher layers only depend on tasks in lower layers
- [ ] All stated dependencies exist in the plan

**File Existence**
- [ ] Every file listed for modification actually exists in the codebase (use `file_search`)
- [ ] New files are in appropriate directories per project conventions (check `AGENTS.md`)

**ADR Consistency**
- [ ] Plan decisions align with ADRs created during `/plan-start`
- [ ] No contradiction with existing ADRs in `docs/adr/`

**AGENTS.md Compliance**
- [ ] Plan respects all hard rules in `AGENTS.md`
- [ ] No first-principles violations (no workarounds, no backward-compat shims)

**Test Coverage**
- [ ] Every new function/component has a corresponding test task
- [ ] TDD-marked tasks have failing test written before implementation task

Record all Layer 1 issues with severity (BLOCKER / WARNING / INFO) before proceeding
to Layer 2.

---

## Layer 2: Specialist Review

Select subagents by applying trigger rules to the plan content. No user input needed
— triggers are objective.

**Validation agent pool:**

| Agent | Trigger | Model |
|-------|---------|-------|
| `security-reviewer` | Auth, payments, PII, RBAC, new public APIs | Opus |
| `db-migration-reviewer` | New tables, columns, indexes, or migration files | Opus |
| `performance-reviewer` | New queries, resolvers, routes, or added dependencies | Sonnet |
| `design-system-reviewer` | New UI components or visual styling changes | Sonnet |
| `ux-reviewer` | New pages, forms, modals, or interaction patterns | Sonnet |
| `cross-platform-reviewer` | Changes touching both web and mobile, or shared packages | Sonnet |
| `native-app-reviewer` | Mobile screens, native UI package changes | Sonnet |
| `integration-reviewer` | New external services, libraries, or OTEL config | Opus |
| `plan-challenger` | Any plan with architectural decisions or security surface | Opus |

Invoke triggered subagents sequentially using `runSubagent`. Each subagent receives:
the plan file path, relevant ADRs, and targeted questions based on its domain.

Report progress to user: "Invoking security-reviewer (auth changes detected)..."

Each subagent must return structured findings:

```
FINDING: [BLOCKER|WARNING|INFO]
Location: [plan section or file reference]
Issue: [concrete description]
Risk: [what breaks if this isn't addressed]
Suggestion: [specific fix or alternative]
```

The `plan-challenger` agent (`.github/agents/plan-challenger.agent.md`) performs
adversarial review across 5 dimensions — invoke it for any non-trivial plan.

---

## Auto-Fix Phase

Merge Layer 1 structural issues + Layer 2 specialist findings into a single issue
list. Every issue must be resolved. No skipping.

**Triage each issue:**

**Bucket A — Auto-resolve:**
- Issue matches an existing ADR decision → cite ADR, mark resolved
- Issue matches a confirmed pattern in `docs/adr/PATTERNS.md` → cite pattern, mark resolved
- Issue resolvable from first principles in `AGENTS.md` → apply rule, mark resolved

**Bucket B — Needs human input:**
- Novel architectural question not covered by existing decisions
- Conflicting ADRs with no clear precedent
- Blocker with no obvious resolution

For Bucket B items: present the issue, explain why it can't be auto-resolved, propose
options, wait for decision. Record the decision in the plan's `## Decisions` section
and create a new ADR if it's architecturally significant.

**Apply all fixes in one batch** once all issues are triaged. Update the plan file.
Commit the updated plan.

---

## Issue Persistence

Record every issue in `docs/plans/metrics/{name}.json` under `validation.issues`:

```json
{
  "id": "S-001",
  "layer": 1,
  "severity": "WARNING",
  "category": "test-coverage",
  "description": "No test task for the new webhook handler",
  "reporting_agent": "structural",
  "triage": "A",
  "resolution_source": "first-principles",
  "resolution": "Added test task in Layer 2 of the plan"
}
```

---

## Auto-Transition

If all issues are auto-resolved (Bucket A only): tell the user "All issues resolved.
Start a new chat and run `/plan-execute` to execute."

If any human input was required (Bucket B): ask "All issues resolved. Ready to
execute?" before suggesting next steps.

---

## Usage

Invoked by typing `/plan-validate` in Copilot Chat. Picks up the most recent
uncommitted plan automatically. Or specify: `/plan-validate plan-user-authentication`.

## Project Context

- Project rules: [AGENTS.md](../../AGENTS.md)
- Plan Challenger: [.github/agents/plan-challenger.agent.md](../agents/plan-challenger.agent.md)
- ADRs: `docs/adr/`
- Plans: `docs/plans/`

## See Also

- `/plan-start` — produces the plan validated here
- `/plan-execute` — executes the validated plan
