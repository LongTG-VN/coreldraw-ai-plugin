# Post-Merge Branch Audit

## Scope

Audit date: 2026-09-01. The source of truth is `main` at
`8a50d10e3e8a83cfe2cfd5fbf30d5ea521b8a601`, the two-parent consolidation
commit whose parents are `9f94db0` and `bf87914`.

## Result

All 18 remote development/stabilization branches are ancestors of `main`.
For every branch below, `git rev-list --count main..<branch>` returned `0`:

- `agent/antigravity-design-tools`
- `agent/codex-training-bootstrap`
- `agent/complete-coreldraw-mvp`
- `agent/template-production-mvp`
- `codex/company-gold-data-bootstrap`
- `codex/corel-ai-agent-overnight`
- `codex/corel-balanced-reliability-gate`
- `codex/corel-codex-mcp-live`
- `codex/corel-codex-ui`
- `codex/corel-final-reliability-gate`
- `codex/corel-operator-24h`
- `codex/corel-operator-production-reliability`
- `codex/corel-operator-v1-medium-risk-approval`
- `codex/corel-operator-v1-product`
- `codex/corel-real-llm-supervised`
- `codex/corel-working-copy-diagnostic`
- `codex/real-company-gold-pilot`
- `stabilize/pre-codex-return-20260812`

`git branch -r --no-merged main` returned no branches. Therefore no merge,
cherry-pick, or conflict resolution is required. Historical branches remain
available for archaeology; they must not be treated as newer product state.

## Decision

`main` is complete with respect to the listed remote branches. The canonical
stabilization work continues on `codex/post-merge-stabilization`; it must be
reviewed before any later merge to `main`.
