# Worktree Shared Directories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Document that Git worktrees share the primary checkout's large cache,
data, and frontend dependency directories through symlinks.

**Architecture:** Amend the existing isolated-worktree paragraph in `AGENTS.md`.
Keep the virtual environment worktree-local, and add one sentence naming the
three directories that must instead be symlinked from the primary checkout.

**Tech Stack:** Markdown documentation and Git.

## Global Constraints

- A worktree's `.venv` must remain separate and must not be symlinked.
- `cache/`, `data/`, and `frontend/node_modules/` must be symlinked to the
  primary checkout.
- No runtime code or tests change.

---

### Task 1: Document shared worktree directories

**Files:**
- Modify: `AGENTS.md:36-39`

**Interfaces:**
- Consumes: The existing worktree setup guidance.
- Produces: A complete instruction for agents setting up a worktree.

- [x] **Step 1: Inspect the existing setup paragraph**

Run: `sed -n '29,43p' AGENTS.md`

Expected: The paragraph requires a separate `.venv` and explains why it cannot
be symlinked.

- [x] **Step 2: Amend the paragraph with the shared-directory rule**

Add this sentence after the `.venv` guidance:

```markdown
Symlink `cache/`, `data/`, and `frontend/node_modules/` from the primary
checkout into the worktree so the large shared assets and Node dependencies are
not duplicated.
```

- [x] **Step 3: Verify the documentation change**

Run: `sed -n '29,46p' AGENTS.md && git diff --check`

Expected: The paragraph preserves the local-`.venv` rule, names all three
symlink targets, and `git diff --check` produces no output.

- [x] **Step 4: Commit the documentation change**

```bash
git add AGENTS.md
git commit -m "docs: clarify worktree shared directories"
```
