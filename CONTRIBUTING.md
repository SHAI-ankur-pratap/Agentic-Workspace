# Contributing to Agentic-Workspace

## AI-Driven PR Flow

All contributions go through an automated AI review process.
Engineers do not push directly to .

### How to contribute

1. **Fork this repo** to your personal GitHub account
2. **Create a feature branch** on your fork: 
3. **Make your changes** and commit them
4. **Open a Pull Request**: your fork → 

### What happens automatically

Once you open the PR:

| Step | Actor | Time |
|------|-------|------|
| Code review | Claude Code bot | ~5 seconds |
| Security scan | Claude Code bot | ~5 seconds |
| Review comment posted | Bot | automatic |
| Stakeholder notified | GitHub | automatic |
| **You click Approve or Deny** | **Authorized stakeholder** | your call |
| Merge to main | Claude Code bot | automatic |

### What you cannot do

- Push directly to  — branch protection blocks it
- Merge your own PR — only the bot token can execute merges
- Skip the review — the status check must pass before merge is allowed

### Authorized approvers

- @SHAI-ankur-pratap

### Secrets required (repo-level)

| Secret | Purpose |
|--------|---------|
|  | Bot account token — executes merges |
|  | Shorthills LiteLLM proxy key |
|  |  |
|  | Comma-separated GitHub usernames |

---

*AI PR flow set up by Ankur Pratap — June 2026*
