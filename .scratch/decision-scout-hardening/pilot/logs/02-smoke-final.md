Shell output:
```json
{"denials": [{"path": "/live/source.py", "denied": true, "errno": 30}, {"path": "/live/test_behavior.py", "denied": true, "errno": 30}, {"path": "/live/fixtures/input.txt", "denied": true, "errno": 30}, {"path": "/live/config/settings.conf", "denied": true, "errno": 30}, {"path": "/live/.git/index", "denied": true, "errno": 30}, {"path": "/protected-meta/receipt.json", "denied": true, "errno": 30}], "cwd": "/snapshot", "hidden": {"/mnt": true, "/home": true, "/run": true, "/meta": true, "/init": true}}
```

Exact file-tool refusal:
```text
patch rejected: writing is blocked by read-only sandbox; rejected by user approval settings
```

Unexecuted actions: none. No retries, workarounds, browsing, MCP, delegation, or other file changes were attempted.