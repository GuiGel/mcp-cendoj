---
name: mr
description: "Analyze changes, detect scope issues, and create a well-structured GitLab MR"
argument-hint: "[--base <branch>] [--draft]"
---

# Create Merge Request (GitLab)

Analyze changes, detect scope issues, and create a well-structured MR following project conventions using `glab`.

## Process

1. **Analyze Changes**: Calculate complexity score from files, commits, and directories.
2. **Detect Scope Issues**: Warn if MR is too large or mixes unrelated changes.
3. **Suggest Split**: If needed, group commits by scope and propose separate MRs.
4. **Collect Info**: Ask for type, target branch, draft status, labels.
5. **Generate Content**: Create TLDR + description + checklist.
6. **Create MR**: Execute `glab mr create` with proper formatting.
7. **Remind Follow-up**: Display post-MR checklist (CI/CD Pipelines, SonarQube).

## Complexity Score

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Code files | x2 | `*.ts, *.tsx` (excluding tests) |
| Test files | x0.5 | `*.test.ts, *.spec.ts` |
| Config files | x1 | `*.json, *.yml, *.md` |
| Directories | x3 | Distinct `src/*` directories |
| Commits | x1 | Number of commits |

**Thresholds**: 0-15 ✅ Normal | 16-25 ⚠️ Large | 26+ 🔴 Split recommended

## Scope Coherence

| Pattern | Verdict |
|---------|---------|
| Single scope | ✅ OK |
| Related scopes (sessions + calendar) | ✅ OK |
| Unrelated scopes (payments + auth) | 🔴 Split |
| feat + fix same scope | ✅ OK |
| feat + fix different scopes | 🔴 Split |

## Split Suggestion Format

When split is recommended, display:

```markdown
🔴 Scope trop large (score: 32)

Commits par scope :
├── payments (5 commits, 8 fichiers)
│   ├── feat(payments): add Stripe checkout
│   └── fix(payments): handle currency
│
└── notifications (3 commits, 6 fichiers)
└── feat(notifications): add email templates

💡 Suggestion :

1.  MR \#1 : feature/payments-stripe → Commits payments
2.  MR \#2 : feature/notifications → Commits notifications

Options :
[A] Continuer avec une seule MR (non recommandé)
[B] Découper (semi-auto - commandes git fournies)
[C] Voir détail fichiers

```

## Questions to Ask

1. **Type**: feature | fix | tech | docs | security
2. **Target Branch**: Show recent branches (develop, main, others)
3. **Draft**: Yes (WIP) | No (ready for review)
4. **Labels**: Based on type + optional (breaking-change, security)

## MR Title Format

```

\<type\>(\<scope\>): \<description\>

````
*Note: GitLab Drafts will automatically be prefixed with "Draft: " by the CLI.*

## MR Body Template

```markdown
## TLDR
---

## Type
{Feature | Fix | Tech | Docs | Security}

## Description
{Context and changes}

## Technical Changes
{List of main modifications}

## Tests
- [ ] Unit tests added/passing
- [ ] Manual testing completed

## Checklist
- [ ] Code follows conventions
- [ ] No console.log left
- [ ] Types OK (`pnpm typecheck`)

---

🤖 Generated with [Github Copilot](https://docs.github.com/)
````

## Commands to Execute

```bash
# 1. Get base branch
BASE_BRANCH="develop"

# 2. Calculate complexity score
CODE=$(git diff --name-only $BASE_BRANCH..HEAD | grep -E '\.(ts|tsx)$' | grep -v test | wc -l)
TESTS=$(git diff --name-only $BASE_BRANCH..HEAD | grep -E '\.test\.|\.spec\.' | wc -l)
DIRS=$(git diff --name-only $BASE_BRANCH..HEAD | cut -d'/' -f1-2 | sort -u | wc -l)
COMMITS=$(git rev-list --count $BASE_BRANCH..HEAD)
SCORE=$((CODE * 2 + TESTS / 2 + DIRS * 3 + COMMITS))

# 3. Get scopes from commits
git log --oneline $BASE_BRANCH..HEAD --format="%s" | sed -n 's/^\w*(\([^)]*\)).*/\1/p' | sort | uniq -c

# 4. Create MR using glab
glab mr create \
  --title "<type>(<scope>): <description>" \
  --description "$BODY" \
  --target-branch $BASE_BRANCH \
  --label "<label>" \
  --remove-source-branch \
  --draft  # if WIP
```

## Post-MR Output

```
✅ MR créée : [https://gitlab.com/org/repo/-/merge_requests/XXX](https://gitlab.com/org/repo/-/merge_requests/XXX)

📋 Prochaines étapes automatiques :
   • Le pipeline GitLab CI vérifiera le build et les tests
   • SonarQube analysera la qualité (si configuré)
   • Claude Code Review fournira un feedback IA

⏳ Pensez à surveiller le statut du pipeline avant de demander une review.
```

## Usage

```
/mr
/mr --base main
/mr --draft
```

Target: $ARGUMENTS (optional: --base, --draft)
