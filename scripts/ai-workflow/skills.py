"""`ai-workflow install-skills` — install the kit's role skills into a target repo.

Improvement 2 (TICKET-012), option C: by default the role skills live in the
harness's global skill library (single source, zero drift); this command is the
optional "self-contained repo" path. It copies the kit's canonical SKILL.md
bundle (exactly the seven kit-owned skills under `.agents/skills/`) into the
target's `.agents/skills/`, **updating in place**: already-current files are
skipped (idempotent), changed files are overwritten, and nothing outside the
seven known skill names is ever touched.
"""

import os

__all__ = ["install_skills", "KIT_SKILLS"]

# The seven role skills the kit owns and ships.
KIT_SKILLS = (
    "repo-scout", "evidence-auditor", "technical-decision", "executor-plan",
    "ticket-executor", "checkpoint-handoff", "workflow-bootstrap",
)


def _kit_skills_dir():
    # this file: scripts/ai-workflow/skills.py
    kit = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(kit, ".agents", "skills")


def install_skills(target):
    """Install the kit's seven role skills into target (idempotent, in place).

    Returns the list of paths written (created or updated); [] when all seven
    are already current. Never touches files outside the kit-owned names.
    """
    written = []
    src_root = _kit_skills_dir()
    if not os.path.isdir(src_root):
        return written
    for name in KIT_SKILLS:
        src = os.path.join(src_root, name, "SKILL.md")
        if not os.path.isfile(src):
            continue  # a kit-owned skill missing locally: skip, do not invent
        with open(src, encoding="utf-8") as fh:
            content = fh.read()
        dst = os.path.join(target, ".agents", "skills", name, "SKILL.md")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        existing = None
        if os.path.exists(dst):
            with open(dst, encoding="utf-8") as fh:
                existing = fh.read()
        if existing == content:
            continue  # already current; idempotent no-op for this skill
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write(content)
        written.append(dst)
    return written
