# Restricted YAML subset parser over PyYAML

The `ai-workflow` CLI parses `state.yaml` with a small hand-written parser that supports only the constructs the fixed state schema uses (nested maps, lists, scalars, null) — not a full YAML implementation, and no PyYAML dependency.

We chose this to keep the CLI zero-dependency: PyYAML is not in the Python standard library, so relying on it would break the "any agent in any repo can run `ai-workflow` immediately" promise exactly at the moment it matters most (validating a freshly migrated repo). The parser is feasible because the state schema is ours and fixed; `STATE_SCHEMA.md` constrains `state.yaml` to the subset, and `validate` enforces it. The cost is hand-maintaining a parser and forbidding exotic YAML in state files.
