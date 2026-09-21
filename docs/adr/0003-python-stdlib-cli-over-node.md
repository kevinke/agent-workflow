# Python 3 stdlib CLI over Node/npm

The `ai-workflow` CLI is written in Python 3 using only the standard library, not Node/TypeScript (the stack the broader skills/MCP ecosystem mostly distributes through npm).

The community's Node preference is real but rooted in a different deployment context: MCP servers are child processes of the IDE host (Claude Code, Cursor, VS Code — all Electron/Node applications), so Node is already present at the moment they run, and `npx @foo/bar` gives zero-friction distribution. That reasoning does not transfer to this kit. Our CLI runs **in the target repository**, not in an IDE; the target may be any language's project. Requiring Node would force `npm install` + `node_modules` into every adopted repo, breaking the zero-dependency promise of ADR-0002 ("any agent in any repo can run `ai-workflow` immediately") and adding a supply-chain surface. Python 3 stdlib is the most widely pre-installed cross-platform runtime, and the restricted YAML parser (ADR-0002) already keeps the CLI dependency-free by design.

The CLI is deliberately thin — the workflow's real computation is LLMs reading markdown protocol docs — so the language choice barely affects quality. The skills layer is language-agnostic markdown regardless.

We will revisit this only under one condition: if the kit ships a genuine MCP server component (exposing `ai-workflow status/validate` as MCP tools to an IDE host). That would be a separate thin adapter on top of the core, using the official Python MCP SDK — never a rewrite of the core CLI. The cost of staying Python is hand-maintaining the parser and accepting that npx-style one-shot distribution is unavailable.
