---
description: "5-phase planning command: PRD analysis, design review, technical decisions, dynamic research team, metrics. Produces a complete implementation plan + ADRs before any code is written. Use when starting a new feature or significant change."
argument-hint: "Feature description or path to PRD file"
agent: "agent"
tools: [read, search, execute, edit, agent, context7/*, logfire/*]
model: "Claude Sonnet 4.6 (copilot)"
---

<!-- Source: https://github.com/FlorianBruniaux/claude-code-ultimate-guide/blob/968bba91b877c90dd17230e91aa1e3d9d224a344/examples/commands/plan-start.md -->
<!-- Adaptation: Task tool → runSubagent (sequential, reports returned directly) -->
<!-- Adaptation: CLAUDE.md → AGENTS.md | Read/Grep/Glob → read/search aliases -->
<!-- Adaptation: .claude/tasks/<id>/output.log → results returned directly from subagent -->

# Plan Start — 5-Phase Planning

Analyze the request and produce a complete implementation plan through structured
phases. **No code is written.** Every significant decision is recorded.
Start a new conversation after this prompt before running `/plan-validate`.

---

## Phase 1: PRD & Design Analysis

### Step 1.1 — PRD Analysis

*Skip if no PRD exists (refactor, infra change, bug fix).*

Read all PRD files and `docs/INFORMATION_ARCHITECTURE.md` if present. Search the
codebase to understand current implementation status.

Surface findings in 3 buckets:

**Missing requirements** — acceptance criteria that are absent or incomplete
**Ambiguous requirements** — items with multiple valid interpretations
**Compliance concerns** — security, data privacy, API contract implications

For each finding: present options with concrete pros/cons. Discuss with user. Record
every decision in the plan file under a `## Decisions` section before moving on. Do
not proceed past unresolved ambiguities.

### Step 1.2 — Design Analysis

*Skip if no UI changes are in scope.*

Read: `DESIGN_SYSTEM.md`, existing UX ADRs, `AGENTS.md` UX rules.

Produce specs for:
- **Screen inventory**: new/modified screens, route placement, component reuse audit
- **State catalog**: empty, loading, populated, error, and partial states for every interactive element
- **Interaction specs**: user flows (happy path + alternates), focus/keyboard behavior
- **Animation specs**: map each interaction to existing keyframes or specify new ones, include `prefers-reduced-motion` fallbacks
- **Responsive behavior**: breakpoints, web/mobile divergence decisions
- **Accessibility**: WAI-ARIA pattern selection, live regions, error visibility

Create Design ADRs for significant UX decisions. Record minor layout choices directly
in the plan file.

---

## Phase 2: Technical Analysis

Invoke 1-2 subagents (using `runSubagent`) for targeted codebase research. Run them
sequentially. The `planner` agent (`.github/agents/planner.agent.md`) can be reused
for scoped sub-investigations. Collect each report before spawning the next.

While reviewing reports, check:
- Existing ADRs in `docs/adr/` — if 3+ ADRs confirm a decision → auto-resolve without asking
- `docs/adr/PATTERNS.md` — apply confirmed patterns directly

When agents return: present architecture decisions with 2-3 options each, concrete
pros/cons, and a recommendation. Ask for user input on each unresolved decision.

For each significant decision:
1. Create `docs/adr/ADR-XXXX.md` using standard Nygard format (Context / Decision / Status / Consequences)
2. Update `docs/adr/PATTERNS.md` with the new observation

---

## Phase 3: Scope Assessment

Apply trigger rules to determine which research agents are needed. Present the proposed
team with justification for each inclusion.

**Research agent pool:**

| Agent | Trigger | Model |
|-------|---------|-------|
| `code-explorer` | Always | Sonnet |
| `arch-researcher` | Changes touch 2+ architectural layers | Sonnet |
| `database-analyst` | Any DB schema change | Sonnet |
| `security-analyst` | Auth, payments, PII, RBAC, rate limiting | Opus |
| `test-analyzer` | Non-trivial feature (not just a bug fix) | Sonnet |
| `cross-platform-specialist` | Web + mobile parity required | Sonnet |
| `design-system-researcher` | UI changes in scope | Sonnet |
| `dependency-researcher` | New packages being added | Sonnet |
| `devops-specialist` | Docker, env vars, CI/CD changes | Sonnet |
| `integration-researcher` | New services, libraries, OTEL config | Opus |
| `planning-coordinator` | Always, when 2+ agents selected | Opus |

**Tier labels** (descriptive, not prescriptive):
- Tier 0 (0 agents): Solo — inline research, no spawning
- Tier 1 (1-3 agents): Focused
- Tier 2 (4-6 agents): Standard
- Tier 3 (7-9 agents): Comprehensive
- Tier 4 (10+ agents): Full Spectrum

Tell the user: "I recommend a **[Tier N - Label]** team: [agent list with one-line
justification each]. Want to add or remove any agents?"

Wait for approval before Phase 4.

---

## Phase 4: Research & Plan Creation

**Tier 0**: Conduct inline research. Write plan directly without spawning subagents.

**Tier 1+**: Invoke approved agents sequentially using `runSubagent`. For each agent
provide:
- Its specific research scope
- The relevant files/areas to investigate
- The questions it needs to answer

Collect each agent's complete report before moving to the next. Report progress to the
user: "3/6 agents complete..."

When all agents return:
- If `planning-coordinator` was selected → invoke `.github/agents/planning-coordinator.agent.md`
  as a subagent, passing all collected reports as context. Its output becomes the final plan.
- Otherwise → synthesize directly from reports.

**Plan file structure** (`docs/plans/plan-{name}.md`):

```markdown
# Plan: {feature-name}
Created: {date} | Branch: {branch-name} | Tier: {N}

## Summary
One paragraph: what this implements and why.

## Decisions
Decisions recorded during Phase 1 (PRD analysis).

## Architecture
ADRs created, patterns applied, architectural choices made.

## Tasks
Ordered task list with layers (1 = foundation, 2 = depends on 1, etc.)

### Layer 1
- [ ] Task A — description, files affected, acceptance criteria
- [ ] Task B — description, files affected, acceptance criteria

### Layer 2
- [ ] Task C — depends on A — description, files affected, acceptance criteria

## Test Plan
How each task will be verified. TDD tasks marked explicitly.

## Integration Verification
Smoke test commands to run post-execution (if backend/services in scope).

## Out of Scope
What this plan explicitly does not address.
```

Commit: plan file + ADR files.

---

## Phase 5: Finalize Metrics

Record timestamps, phase durations, agent counts in `docs/plans/metrics/{name}.json`.
Commit.

---

## Auto-Transition

If Phase 1 produced no unresolved ambiguities and Phase 2 produced no unresolved
decisions: tell the user "Plan complete — start a new chat and run `/plan-validate`
to validate it."

If any human discussion occurred: ask "Ready to validate this plan?" before
suggesting next steps.

---

## Project Context

- Project rules and conventions: [AGENTS.md](../../AGENTS.md)
- ADRs: `docs/adr/`
- Plans: `docs/plans/`
- Planning Coordinator: [.github/agents/planning-coordinator.agent.md](../agents/planning-coordinator.agent.md)
- ADR Writer: [.github/agents/adr-writer.agent.md](../agents/adr-writer.agent.md)

## See Also

- `/plan-validate` — validate the plan produced here
- `/plan-execute` — execute the validated plan
