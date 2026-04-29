---
name: Create MR
description: "Create a GitHub Pull Request with a canonical body from a structured context. Use when: opening a PR after feature execution, creating a PR from a hotfix branch, or any time a consistent PR description is required."
argument-hint: "Pass: plan name, one-line summary, task list with files, ADRs list, test plan, and CI results (all optional if not applicable)"
tools: [read, execute]
model: "Claude Sonnet 4.6 (copilot)"
---

# Create MR — Canonical Pull Request Creation

Produce a consistent, well-structured GitHub PR using the canonical body template,
then push the branch and open the PR.

---

## Inputs

The caller must provide:

| Field | Required | Description |
|---|---|---|
| `branch` | yes | Source branch name (e.g. `feature/user-auth`) |
| `target` | yes | Target branch (e.g. `main`) |
| `title` | yes | One-line imperative summary (≤ 72 chars) |
| `summary` | yes | One paragraph describing what changed and why |
| `tasks` | yes | List of completed tasks with affected files |
| `adrs` | no | ADRs created or consulted during this plan |
| `test_plan` | no | Test strategy from the plan's Test Plan section |
| `ci_results` | no | Output from `make test` / `make test-integration` |
| `breaking_changes` | no | Any breaking API or schema changes |
| `notes` | no | Anything reviewers should pay special attention to |

Omit any section whose input was not provided — do **not** invent content.

---

## Step 1: Gather Git Context

If any input above is missing, infer it from git before asking the user:

```bash
# Confirm current branch
git rev-parse --abbrev-ref HEAD

# Commits on this branch not yet on target
git log origin/{target}..HEAD --oneline

# Files changed
git diff origin/{target}..HEAD --name-only
```

---

## Step 2: Write `.mr-body.md`

Produce the file in the repository root (or worktree root). Use exactly this
structure — include only sections for which input was provided:

```markdown
## Summary

{summary paragraph}

## Changes

{one bullet per completed task}
- `{file or module}` — {what changed}

## Breaking Changes

> ⚠️ {description of breaking change and migration path}

## ADRs

{list of ADRs referenced or created}
- [ADR-XXXX]({path}) — {title}

## Test Plan

{test strategy}

## CI Results

```
{make test / make test-integration output snippet — last 30 lines max}
```

## Notes for Reviewers

{anything that needs extra attention}
```

**Rules:**
- Omit `## Breaking Changes` if there are none.
- Omit `## ADRs` if no ADRs are provided.
- Omit `## CI Results` if no CI output is available.
- Omit `## Notes for Reviewers` if nothing special applies.
- Never fabricate content for missing sections.
- Keep bullet points concise: one line each.
- Use relative paths for file references.

---

## Step 3: Push and Create PR

```bash
git push origin feature/{plan-name}
gh pr create \
  --title "{title}" \
  --body "$(cat .mr-body.md)" \
  --base {target} \
  --head {branch}
```

---

## Step 4: Confirm and Report

After the PR is created, return to the caller:

- PR URL (as a markdown link)
- Branch pushed: `{branch}` → `{target}`
- Path to `.mr-body.md` in the worktree (for audit)

Do **not** merge the PR — that is the caller's responsibility after CI passes.
