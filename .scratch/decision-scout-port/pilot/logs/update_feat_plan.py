"""Append Task 2 (handoff rework) to the registered PILOT-FEAT-01 plan.

Byte-level edit with guards:
  - Task 1 canonical hash must equal the registered value before AND after.
  - 'task_count: 1' must occur exactly once and is replaced in place.
  - '## Task 2' must not exist yet.
Prints: eol style, new whole-file sha256, Task 1/Task 2 canonical hashes.
"""
import hashlib
import re

TARGET = r"C:\Users\Kevin\AppData\Local\Temp\scout008-target\.scratch\PILOT-FEAT-01\plan.md"
TASK1_EXPECTED = "9063ea957a720252ac54b734e96fdec5f91025750f9766dac58902676c173294"

TASK2 = """## Task 2

### Objective
Complete the persisted handoff for the reload change: replace every placeholder
in .ai/work/PILOT-FEAT-01/handoff.md with concrete, verified contents so the
cross-harness handoff obligation is satisfied. No production-code change.

### Inputs
- review.md finding (verdict changes_requested): the only gap is the unfilled
  handoff template; the reload implementation and both acceptance commands
  already pass.
- Current repository identity (branch, HEAD, uncommitted state) and the artifact
  hashes as re-verified during this task.
- Task 1's acceptance commands, re-run to produce fresh execution evidence.

### Allowed changes
- .ai/work/PILOT-FEAT-01/handoff.md
- .ai/work/PILOT-FEAT-01/progress.md
- .ai/work/PILOT-FEAT-01/state.yaml (written only through the workflow CLI)

### Protected scope
- Do not modify service.py, demo.py, or any other production file.
- Do not modify review.md (its verdict and hash are bound in state.yaml),
  plan.md (registered), evidence.md, or evidence-audit.md.
- Do not alter Task 1's registered section; its canonical hash must survive.

### Invariants
- Task 1 canonical hash remains 9063ea957a720252ac54b734e96fdec5f91025750f9766dac58902676c173294.
- review.md raw-byte sha256 remains 8bc6e0e6fddee140b0a8812a979e0672ddd12cff02f12870ccf9f6433ff80d1c.
- state.yaml is only ever written by the ai-workflow CLI.

### Acceptance criteria
- handoff.md has every required section filled with verified values; the
  placeholder probe `Select-String -Path .ai\work\PILOT-FEAT-01\handoff.md -Pattern '<[a-z ]+>'`
  returns no matches.
- Both Task 1 acceptance commands re-run green: prints 5, then prints 7.
- `validate PILOT-FEAT-01` reports OK with no ERROR findings.

### Verification
Command 1 (placeholder probe; expect no matches):
`Select-String -Path .ai\work\PILOT-FEAT-01\handoff.md -Pattern '<[a-z ]+>'`
Command 2 (expect prints 5, exit 0):
`$env:PYTHONDONTWRITEBYTECODE=1; python -c "from service import CachedValue; c = CachedValue({'value': 1}); c.reload({'value': 5}); print(c.read())"`
Command 3 (expect prints 7, exit 0):
`$env:PYTHONDONTWRITEBYTECODE=1; python -c "from service import CachedValue; src = {'value': 7}; c = CachedValue({'value': 1}); c.reload(src); src['value'] = 9; print(c.read())"`
Command 4 (expect validate OK):
`python d:\Code\agent-workflow\scripts\ai-workflow\main.py validate PILOT-FEAT-01`

### Dependencies
Task 1 (the reload implementation whose handoff this task completes).

### Escalation conditions
- Completing the handoff would require touching a protected file (review.md,
  plan.md, evidence.md, evidence-audit.md, service.py, demo.py).
- The re-review demands further production-code changes or a different design.
"""


def canonical(section):
    normalised = section.replace("\r\n", "\n")
    lines = [line.rstrip() for line in normalised.split("\n")]
    return hashlib.sha256("\n".join(lines).rstrip().encode("utf-8")).hexdigest()


def task_section(text, n):
    lines = text.replace("\r\n", "\n").split("\n")
    marker = "## Task %d" % n
    start = next((i for i, ln in enumerate(lines) if ln.strip() == marker), None)
    if start is None:
        raise SystemExit("FAIL: %r heading not found" % marker)
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^## (?!#)", lines[j]):
            end = j
            break
    return "\n".join(lines[start:end])


with open(TARGET, "rb") as fh:
    data = fh.read()
text = data.decode("utf-8")
eol = "\r\n" if "\r\n" in text else "\n"
print("eol style:", repr(eol))
print("ends with newline:", data.endswith(b"\n"))

before = canonical(task_section(text, 1))
print("Task 1 canonical before:", before)
if before != TASK1_EXPECTED:
    raise SystemExit("FAIL: Task 1 hash mismatch before edit")
if text.count("task_count: 1") != 1:
    raise SystemExit("FAIL: 'task_count: 1' count != 1")
if "## Task 2" in text:
    raise SystemExit("FAIL: Task 2 already present")

new_text = text.replace("task_count: 1", "task_count: 2")
if not new_text.endswith("\n"):
    new_text += eol
task2 = TASK2.replace("\r\n", "\n").replace("\n", eol)
new_text = new_text + eol + task2
if not new_text.endswith(eol):
    new_text += eol

new_bytes = new_text.encode("utf-8")
with open(TARGET, "wb") as fh:
    fh.write(new_bytes)

with open(TARGET, "rb") as fh:
    written = fh.read()
wt = written.decode("utf-8")
after1 = canonical(task_section(wt, 1))
after2 = canonical(task_section(wt, 2))
print("Task 1 canonical after: ", after1)
if after1 != TASK1_EXPECTED:
    raise SystemExit("FAIL: Task 1 hash drifted after edit")
print("Task 2 canonical hash:  ", after2)
print("new whole-file sha256:  ", hashlib.sha256(written).hexdigest())
print("bytes:", len(written))