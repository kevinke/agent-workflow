"""`ai-workflow init` — install the protocol + templates into a target repo.

Idempotent and non-destructive: creates `.ai/workflow/` and `.agents/skills/`
when absent, copies bundled protocol docs and templates without overwriting
existing files, and maintains the AGENTS.md managed block (`<!-- BEGIN/END
AI-WORKFLOW -->`) in place without touching any user content outside the block.

The bundled protocol lives alongside the kit repo that ships this CLI.
"""

import os
import shutil

__all__ = ["init", "ManagedBlockError"]


# Marker lines delimiting the adapter block we own. Everything between (and
# including) them is ours; everything outside is preserved verbatim.
BEGIN_MARKER = "<!-- BEGIN AI-WORKFLOW -->"
END_MARKER = "<!-- END AI-WORKFLOW -->"

# Managed adapter block for Codex/ZCode (spec §12, TICKET-004). Final wording:
# a thin pointer only — read state.yaml, follow phase/role in the protocol,
# read only what you need, never redo completed phases, update state + handoff
# before stopping. Adapters never copy the protocol body (ADR-0001).
MANAGED_BLOCK = BEGIN_MARKER + """

On entering this repo, read `.ai/work/<ticket>/state.yaml` first: it is the
authoritative workflow state. Follow the current phase and role in
`.ai/workflow/PROTOCOL.md` and `.ai/workflow/ROLES.md`. Read only the artifacts
you need. Never redo completed phases. Update state.yaml and handoff.md before
stopping.

""" + END_MARKER


class ManagedBlockError(Exception):
    pass


def _kit_root():
    # this file: scripts/ai-workflow/init.py
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _protocol_source():
    return os.path.join(_kit_root(), ".ai", "workflow")


def _copy_tree(src, dst, seen):
    """Copy src into dst, never overwriting existing files (skip silently)."""
    if not os.path.exists(src):
        return
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        dest_dir = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(dest_dir, exist_ok=True)
        for fname in files:
            src_path = os.path.join(root, fname)
            dest_path = os.path.join(dest_dir, fname)
            if os.path.exists(dest_path):
                continue  # idempotent: never overwrite existing user/protocol file
            shutil.copy2(src_path, dest_path)
            seen.append(dest_path)


def _read_or_create_agents(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    return ""


def _apply_managed_block(text):
    """Return (new_text, changed) replacing/augmenting the managed block."""
    begin = text.find(BEGIN_MARKER)
    end = text.find(END_MARKER)
    if begin == -1 and end == -1:
        # Append the block after a blank-line separator so it never merges with
        # the last line of user content (dogfood finding).
        if text == "":
            sep = ""
        elif text.endswith("\n\n"):
            sep = ""
        elif text.endswith("\n"):
            sep = "\n"
        else:
            sep = "\n\n"
        return text + sep + MANAGED_BLOCK + "\n", True
    if begin == -1 or end == -1 or end < begin:
        raise ManagedBlockError(
            "AGENTS.md has an unbalanced AI-WORKFLOW marker; refusing to touch it. Fix manually."
        )
    # Replace only the region between markers inclusive (idempotent update).
    before = text[:begin]
    after = text[end + len(END_MARKER):]
    return before + MANAGED_BLOCK + after, True


def init(target, agents_name="AGENTS.md"):
    """Install protocol + templates + managed block into target repo.

    Returns a list of created/updated file paths (for reporting).
    """
    created = []
    os.makedirs(target, exist_ok=True)

    # 1. Protocol docs + templates under .ai/workflow/ (never overwrite).
    dst_workflow = os.path.join(target, ".ai", "workflow")
    os.makedirs(dst_workflow, exist_ok=True)
    _copy_tree(_protocol_source(), dst_workflow, created)

    # 2. Skills directory scaffold.
    skills_dir = os.path.join(target, ".agents", "skills")
    os.makedirs(skills_dir, exist_ok=True)

    # 3. AGENTS.md managed block.
    agents_path = os.path.join(target, agents_name)
    text = _read_or_create_agents(agents_path)
    new_text, _changed = _apply_managed_block(text)
    if new_text != text:
        with open(agents_path, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        created.append(agents_path)

    return created