---
name: Plan Execute
description: "Execute a validated plan: worktree isolation, TDD scaffolding, level-based sequential subagents, quality gate with smoke test, PR creation and merge. Handles everything through to merged PR. Use after Plan Validate confirms all issues resolved."
argument-hint: "Plan name (e.g. user-authentication) — omit to pick up the most recent validated plan"
tools: [read, search, execute, edit, agent, logfire/*, playwright/*]
agents: ["Quality Fixer", "Quality Fixer Smoke", "Create MR"]
model: "Claude Sonnet 4.6 (copilot)"
---

<!-- Source: https://github.com/FlorianBruniaux/claude-code-ultimate-guide/blob/968bba91b877c90dd17230e91aa1e3d9d224a344/examples/commands/plan-execute.md -->
<!-- Adaptation: Task tool → runSubagent (sequential per layer, reports returned directly) -->
<!-- Adaptation: CLAUDE.md → AGENTS.md | Read/Grep/Glob/Bash → read/search/execute aliases -->

# Plan Execute — Execution to Merged PR

Execute the validated plan in an isolated worktree. Invoke per-task subagents
sequentially per layer, verify quality, create and merge the PR.

Start a new chat before switching to this agent.

---

## Prerequisite

A validated plan must exist at `docs/plans/plan-{name}.md` with all issues
resolved (output of Plan Validate).

---

## Step 1: Worktree Setup

Create an isolated git worktree:

```bash
git worktree add .worktrees/{plan-name} -b feature/{plan-name}
```

All execution happens inside the worktree. Main branch remains clean throughout.

---

## Step 2: TDD Scaffolding

*Only for tasks marked as TDD in the plan.*

For each TDD task, before any implementation:
1. Write the failing test(s) that define the acceptance criteria
2. Run tests to confirm they fail (red)
3. Commit the failing tests: `git commit -m "test: failing tests for {task} (TDD)"`
4. Note the test file path in the task context for the implementation subagent

Do not write implementation code in this step.

---

## Step 3: Level-Based Sequential Execution

Parse the task list from the plan. Group tasks by layer (Layer 1 = foundation,
Layer 2 = depends on Layer 1, etc.).

**For each layer:**
1. Identify all tasks in the layer
2. For each task, invoke a subagent via `runSubagent` with the following context:
   - Task description, files to modify, acceptance criteria, relevant ADRs
   - First-principles from `AGENTS.md`
3. Wait for the subagent's report confirming the task is complete
4. Verify the commit was made: `git log --oneline -1` in the worktree
5. Complete all tasks in the layer before starting the next layer

> **Note**: Tasks within a layer are invoked sequentially. Future versions may
> parallelize independent tasks — the layer structure in the plan already marks
> which tasks share no file dependencies.

**Agent instructions template for each task:**

```
You are implementing one task from a validated plan.

Task: {description}
Files to modify: {file list}
Acceptance criteria: {criteria}
Relevant ADRs: {adr list}

First principles (from AGENTS.md):
- Build state-of-the-art. No workarounds, no legacy patterns.
- Fix at the correct architectural level, never with component-level hacks.
- If you discover that the plan is wrong or missing context, STOP and report —
  do not improvise architecture.

Commit your changes when complete:
  git commit -m "feat: {task-description}"
```

**Drift detection**: after each layer, diff actual changes against the plan spec.
If implementation deviates significantly (new files not in plan, plan files not
touched), flag and ask how to proceed. Do not silently continue on drift.

---

## Step 4: Quality Gate

Run in sequence:
1. Linter (check `AGENTS.md` for the exact command, e.g. `make verify`)
2. Type checker (e.g. `tsc -b` or `pyright`)
3. Full test suite (e.g. `make test`)

If all pass: proceed to smoke test.

If any fail: invoke a `quality-fixer` subagent with the failure output. It gets up
to **3 auto-fix attempts**. After each attempt, re-run the quality gate.
If still failing after 3 attempts: stop, report the failure with the full error
output, and wait for human intervention.

**Local integration tests** *(skip for pure frontend or docs-only plans)*:

```bash
make integration-env-up   # idempotent: starts any stopped DBs (from develop worktree),
                          # skips fixed-name containers already running, reuses any
                          # healthy API at localhost:8001 from another worktree
make test-integration
make integration-env-down # optional: stop local stack after tests
```

`scripts/integration-env-up.sh` handles the two-worktree architecture automatically:
- finds `[develop]` via `git worktree list` and starts any stopped DB containers there
- skips `conversa-redis` / `conversa-pg-proxy` if already running (avoids name conflicts)
- reuses any healthy `localhost:8001` rather than fighting over the port
- from the `develop` worktree itself, skips the local stack entirely (ports already bound)

Run the smoke commands defined in the plan's `## Integration Verification` section.
Additionally:
- If new API routes: verify each returns expected status codes
- If Docker services: scan container logs for ERROR-level entries

Integration failures are debugged by a `quality-fixer-smoke` subagent with the same
3-attempt limit.

---

## Step 5: Pre-MR Documentation

*In the worktree, before creating the MR.*

**PRD Reconciliation**: compare implemented behavior against the original PRD. Note
any deviations or additions discovered during implementation. Update the PRD with
actuals. These updates ship in the same MR as the feature.

**Plan Archival**: move `docs/plans/plan-{name}.md` to
`docs/plans/completed/plan-{name}.md`. Update the status header.

Commit: `docs: reconcile PRD and archive plan for {feature-name}`.

---

## Step 6: Push and MR

Delegate to the `Create MR` agent. Pass it the following inputs collected during
this execution:

| Input | Source |
|---|---|
| `branch` | `feature/{plan-name}` |
| `target` | `main` (or as specified in the plan) |
| `title` | `{feature-name}: {one-line summary from plan}` |
| `summary` | Plan summary paragraph |
| `tasks` | Completed task list with files affected |
| `adrs` | ADRs created during this plan |
| `test_plan` | Plan's `## Test Plan` section |
| `ci_results` | Output from `make test` and `make test-integration` |

The `Create MR` agent will write `.mr-body.md`, push the branch, and open the MR.

**After PR creation, the GitHub Actions CI pipeline fires automatically** (no manual
action needed). Wait for all status checks to go green before merging.

Once CI is green, merge using squash via the GitHub UI or:

```bash
gh pr merge --squash --delete-branch
```

---

## Step 7: Post-Merge Metrics

Switch back to main. Update `docs/plans/metrics/{name}.json` with:
- Task count and per-layer breakdown
- TDD task count
- Diff stats (files changed, lines added/removed)
- Quality gate results (pass/fail, fix attempts)
- Smoke test results
- Drift score (0–1, how closely implementation matched plan)
- MR data (IID, merge commit, CI pipeline URL, timestamp)

Commit metrics update.

---

## Step 8: Worktree Cleanup

```bash
git worktree remove .worktrees/{plan-name}
```

---

## Project Context

- Project rules: [AGENTS.md](../../AGENTS.md)
- Quality Fixer: [.github/agents/quality-fixer.agent.md](../agents/quality-fixer.agent.md)
- Quality Fixer (Smoke): [.github/agents/quality-fixer-smoke.agent.md](../agents/quality-fixer-smoke.agent.md)

## See Also

- Plan Start (`@plan-start`) — produces the initial plan
- Plan Validate (`@plan-validate`) — validates the plan before execution
