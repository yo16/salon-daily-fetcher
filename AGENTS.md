# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd prime` to get started (the rules in this file and CLAUDE.md take precedence over its output).

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
```

`.beads/issues.jsonl` is written and `git add`-ed automatically after every bd write (`export.auto`), so there is no separate sync step.

**Do not** run `bd sync`, `bd dolt push`, or `bd dolt remote add`: this project intentionally has no Dolt remote. Ignore the warning `beads: auto-export warning: no Dolt remote configured.` and the "repair" command it prints.

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

