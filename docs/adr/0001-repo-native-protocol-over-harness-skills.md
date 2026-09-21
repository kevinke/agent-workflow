# Repo-native protocol over Harness-native skills

The workflow's source of truth lives in plain Git files (`.ai/workflow/` protocol, `.ai/work/<ticket>/` state and artifacts), not in any Harness's skill format. Skills, `AGENTS.md` managed blocks, and TRAE project rules are only thin adapters that point each Harness at the protocol.

We chose this because Codex, TRAE, and ZCode each have their own skill discovery, loading, and config formats; the only thing they all share is the ability to read and write ordinary repository files. Making the protocol a repo-native layer means no single Harness can lock the workflow in, and a weak model can be told exactly what to do by reading `state.yaml` instead of re-deriving progress from prose. The cost is that each Harness needs a small adapter, and protocol upgrades are explicit operations on target repos.
