# Handoff — <ticket-id>

## What was done

<summary>

## What remains

<remaining work>

## Important discoveries

<findings the next agent must know>

## Artifact identity

- Evidence: <path> sha256 <hash> observed_commit <sha> round <n>
- Evidence audit: <path> sha256 <hash> gate <sufficient|insufficient>
- Decision: <path>
- Plan: <path> sha256 <hash> (registered)
- Review: <path> sha256 <hash> verdict <pass|changes_requested|none>

## Verification limits

<what was verified and how: static reading / execution / test; what was NOT
verified and the residual uncertainty. Static reading is not runtime evidence.>

## Known relevant drift

- Repository HEAD: <commit>
- Evidence observed commit: <commit> — if it differs from HEAD, the affected
  anchors need a relevance assessment; old evidence is not automatically discarded
- Review reviewed commit / verdict: <commit> / <verdict>
- Changed paths that matter: <list or none>

## Current failure (if any)

<none | description>

## Do not repeat

<mistakes to avoid; facts and areas already established that need no rediscovery>

## Next recommended action

<exact next role / action / task per state.yaml; blockers to resolve first>

## Repository State

- Branch: <branch>
- HEAD: <commit hash>
- Uncommitted files: <list or none>
- Test status: <passing / failing / not run>