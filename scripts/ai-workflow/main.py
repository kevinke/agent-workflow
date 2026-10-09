"""`ai-workflow` CLI entry point (Python 3 stdlib, zero dependencies).

Usage:
    ai-workflow init [target] [--with-skills]
    ai-workflow status [ticket-id]
    ai-workflow validate [ticket-id]
    ai-workflow start <ticket-id> [opts]
    ai-workflow adopt <ticket-id> [opts]
    ai-workflow advance <ticket-id> --to <phase>
    ai-workflow claim <ticket-id> [opts]
    ai-workflow release <ticket-id>
    ai-workflow complete-task <ticket-id> [--total N]
    ai-workflow register-plan <ticket-id> --path <plan> --total N
    ai-workflow set-gate <ticket-id> --gate <g> [--round N]
    ai-workflow prepare-review <ticket-id> --commit <oid> --output <dir>
    ai-workflow run-review <ticket-id> --review-context <dir> --kind <k> -- <argv...>
    ai-workflow escalate <ticket-id> [opts]
    ai-workflow set-status <ticket-id> --status <s>
    ai-workflow resume <ticket-id>
    ai-workflow archive-artifacts <ticket-id> --output <new.zip>
    ai-workflow install-skills [target]
    ai-workflow upgrade
    ai-workflow upgrade-ticket <ticket-id>

Subcommands implement the workflow state machine (spec §9); the semantic
mutators (advance/claim/release/complete-task/set-gate/escalate/set-status)
are TICKET-010/012.
"""

import os
import re
import sys

import adopt
import artifact_archive
import contracts
import init
import mutate
import resume
import review_boundary
import review_snapshot
import skills
import start
import status
import upgrade
import validate

COMMANDS = {"init", "status", "validate", "start", "adopt", "advance", "claim",
            "release", "complete-task", "register-plan", "set-gate", "escalate",
            "set-status", "set-review", "prepare-review", "run-review",
            "resume", "archive-artifacts",
            "install-skills", "upgrade", "upgrade-ticket"}

USAGE = """ai-workflow — repo-native agent workflow protocol (subset)

commands:
  init [target] [--with-skills]  install protocol + templates + AGENTS.md managed block
      --with-skills             also install the eight role skills (optional, in place)
  status [ticket-id]  one-screen summary of a ticket (or the active ticket)
  validate [ticket-id] validate workflow state; ERROR -> non-zero exit
  start <ticket-id> [opts]  scaffold a new (greenfield) ticket from template
      --title <title>       ticket title
      --phase <phase>       start phase (default: requirement)
      --spec <path> --ticket <path> --plan <path>   source-artifact references
  adopt <ticket-id> [opts]  legacy repo adoption: migration report + state scaffold
      --phase <phase>       adopted phase (default: requirement)
      --title <title>       ticket title
      --spec <path> --ticket <path> --plan <path>   source-artifact references
  advance <ticket-id> --to <phase>  move along the state machine (enforces gates)
  claim <ticket-id> [--harness H] [--model M]   set the soft claim + provenance
  release <ticket-id>     clear the soft claim (provenance kept)
  complete-task <ticket-id> [--total N]  mark one implementation task done
  register-plan <ticket-id> --path P --total N  register a referenced Plan (v2)
  set-gate <ticket-id> --gate G [--round N]  record evidence verdict (G: sufficient|insufficient)
  set-review <ticket-id> --verdict V  record a Review verdict (V: pass|changes_requested)
  prepare-review <ticket-id> --commit <literal-oid> --output <new-directory>
                      prepare an identified independent review snapshot
                      (independent clone + raw-byte Plan/input copies +
                      supervisor manifest) for isolated reviewer verification
  run-review <ticket-id> --review-context <dir> --kind baseline|probe -- <argv...>
                      run one verifier command under the enforced
                      linux-bwrap-v1 host boundary inside a prepared review
                      snapshot and record a supervisor receipt (stdout/stderr
                      captured, real exit status, residual snapshot changes).
                      Exits with the command's own status; a boundary blocker
                      exits 1 and never falls back to an unconstrained run.
                      Requires an available host boundary (bwrap via WSL on
                      Windows); unsupported hosts report a named blocker.
  escalate <ticket-id> --scope S --reason "..." | --clear [--resolution TEXT]  set/clear escalation
  set-status <ticket-id> --status S  set lateral status (active|blocked|paused|escalation_required|abandoned)
  resume <ticket-id>  print a read-only continuation brief (exit 1 on ERROR blockers)
  archive-artifacts <ticket-id> --output <new.zip>
                      export the Ticket's verified raw artifacts (manifest.json
                      + member bytes) once its Review bindings are current; v1
                      or pending/unbound Tickets are refused — not a backup API.
                      Resume the archive elsewhere WITH the matching code
                      repository/history: the bindings are byte hashes plus a
                      reviewed commit.
  install-skills [target]  install the eight role skills into the target repo (idempotent)
  upgrade             explicit protocol upgrade using workflow_version
  upgrade-ticket <ticket-id>  explicitly convert one active v1 Ticket to
                      workflow_version 2 (records the senior reconstruction)
"""


def _resolve_root(args):
    return os.path.abspath(os.getcwd())


def _print_findings(findings):
    for f in sorted(findings, key=lambda x: (x.severity != "ERROR", x.message)):
        print("%-5s %s" % (f.severity, f.message))


def _parse_options(rest, known):
    """Parse `--key value` pairs from rest. Returns (opts, error_or_None)."""
    opts = {}
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg in known and i + 1 < len(rest):
            opts[arg[2:]] = rest[i + 1]
            i += 2
        else:
            return opts, "unknown or missing-value option %r" % arg
    return opts, None


def cmd_init(args, root):
    rest = args[1:]
    with_skills = "--with-skills" in rest
    rest = [r for r in rest if r != "--with-skills"]
    target = rest[0] if rest else root
    created = init.init(target)
    if with_skills:
        created += skills.install_skills(target)
    if created:
        print("installed into %s:" % target)
        for p in created:
            print("  %s" % os.path.relpath(p, target))
    else:
        print("nothing to do: protocol already installed (idempotent).")


def cmd_install_skills(args, root):
    target = args[1] if len(args) > 1 else root
    written = skills.install_skills(target)
    if not written:
        print("nothing to do: the eight role skills are already current (idempotent).")
        return 0
    print("installed skills into %s:" % target)
    for p in written:
        print("  %s" % os.path.relpath(p, target))
    return 0


def cmd_status(args, root):
    tickets = status.list_tickets(root)
    if not tickets:
        print("no tickets under .ai/work/.")
        return 0
    ticket = args[1] if len(args) > 1 else tickets[0]
    if ticket not in tickets:
        sys.stderr.write("unknown ticket %r (have: %s)\n" % (ticket, ", ".join(tickets)))
        return 1
    print(status.status_for_ticket(root, ticket))
    return 0


def cmd_resume(args, root):
    """Read-only continuation brief: 0 valid, 1 ERROR blockers/unreadable, 2 usage."""
    rest = args[1:]
    if not rest or rest[0].startswith("--") or len(rest) > 1:
        sys.stderr.write("usage: ai-workflow resume <ticket-id>\n")
        return 2
    ticket_id = rest[0]
    tickets = status.list_tickets(root)
    if ticket_id not in tickets:
        sys.stderr.write("unknown ticket %r (have: %s)\n"
                         % (ticket_id, ", ".join(tickets)))
        return 1
    try:
        text = resume.resume_for_ticket(root, ticket_id)
    except resume.ResumeError as exc:
        sys.stderr.write("resume: %s\n" % exc)
        return 1
    print(text)
    return 1 if resume.continuation_blocked(root, ticket_id) else 0


def cmd_validate(args, root):
    findings = validate.validate_repo(root)
    if args and len(args) > 1 and args[1]:
        # Restrict to a single ticket for reporting clarity.
        findings = [f for f in findings if "[%s]" % args[1] in f.message or "repo" in f.message]
    _print_findings(findings)
    has_error = validate.has_errors(findings)
    print(("ERRORS PRESENT — fix before handoff." if has_error else "validate: OK (no ERROR findings)."))
    return 1 if has_error else 0


def cmd_adopt(args, root):
    opts = {}
    rest = args[1:]
    if not rest:
        sys.stderr.write("usage: ai-workflow adopt <ticket-id> [opts]\n")
        return 2
    ticket_id = rest[0]
    rest = rest[1:]
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg in ("--phase", "--title", "--spec", "--ticket", "--plan") and i + 1 < len(rest):
            opts[arg[2:]] = rest[i + 1]
            i += 2
        else:
            sys.stderr.write("unknown adopt option %r\n" % arg)
            return 2
    created = adopt.adopt(
        root, ticket_id,
        phase=opts.get("phase"),
        title=opts.get("title"),
        spec_path=opts.get("spec"),
        ticket_path=opts.get("ticket"),
        plan_path=opts.get("plan"),
    )
    if not created:
        print("nothing to do: %s already adopted (idempotent)." % ticket_id)
        return 0
    print("adopted %s into the workflow:" % ticket_id)
    for p in created:
        print("  %s" % os.path.relpath(p, root))
    print("next: a senior completes adoption per MIGRATION.md "
          "(continuation_safe starts false).")
    return 0


def cmd_start(args, root):
    opts = {}
    rest = args[1:]
    if not rest or rest[0].startswith("--"):
        sys.stderr.write("usage: ai-workflow start <ticket-id> [--title <title>] "
                         "[--phase <phase>] [--spec <path>] [--ticket <path>] "
                         "[--plan <path>]\n")
        return 2
    ticket_id = rest[0]
    i = 1
    while i < len(rest):
        arg = rest[i]
        if arg in ("--title", "--phase", "--spec", "--ticket", "--plan") and i + 1 < len(rest):
            opts[arg[2:]] = rest[i + 1]
            i += 2
        else:
            sys.stderr.write("unknown start option %r\n" % arg)
            return 2
    created = start.start(
        root, ticket_id,
        title=opts.get("title"),
        phase=opts.get("phase"),
        spec_path=opts.get("spec"),
        ticket_path=opts.get("ticket"),
        plan_path=opts.get("plan"),
    )
    if not created:
        print("nothing to do: %s already started (idempotent)." % ticket_id)
        return 0
    print("started %s:" % ticket_id)
    for p in created:
        print("  %s" % os.path.relpath(p, root))
    return 0


def cmd_upgrade(args, root):
    try:
        updated, _ = upgrade.upgrade(root)
    except upgrade.UpgradeError as exc:
        sys.stderr.write("upgrade: %s\n" % exc)
        return 2
    installed = upgrade.installed_workflow_version(root)
    if not updated:
        print("nothing to do: protocol already at workflow_version %s (idempotent)."
              % installed)
        return 0
    print("upgraded protocol to workflow_version %s:" % upgrade.kit_workflow_version())
    for p in updated:
        print("  %s" % os.path.relpath(p, root))
    return 0


def cmd_upgrade_ticket(args, root):
    """Explicitly convert one v1 Ticket to v2: usage -> 2, protocol reject -> 1."""
    rest = args[1:]
    if not rest or rest[0].startswith("--") or len(rest) > 1:
        sys.stderr.write("usage: ai-workflow upgrade-ticket <ticket-id>\n")
        return 2
    ticket_id = rest[0]
    try:
        print(upgrade.upgrade_ticket(root, ticket_id))
    except upgrade.UpgradeError as exc:
        sys.stderr.write("upgrade-ticket: %s\n" % exc)
        return 1
    return 0


class _UsageError(Exception):
    """A malformed argument (bad option value), reported as a usage error (exit 2)."""


def _parse_nonneg_int(raw, opt):
    """Parse a plain decimal (ASCII 0-9) integer; malformed -> _UsageError.

    Matches `[0-9]+` before calling int(), so Unicode digit-likes (e.g. '²',
    where str.isdigit() is True but int() raises ValueError) are rejected
    cleanly instead of leaking an uncaught traceback. Callers apply their own
    positivity constraint on the returned non-negative value.
    """
    if not re.fullmatch(r"[0-9]+", raw):
        raise _UsageError("%s must be a non-negative integer (got %r)" % (opt, raw))
    return int(raw)


def _cmd_mutate(name, usage, args, root, known_opts, apply):
    """Shared driver for the semantic mutators: usage errors -> 2, rejected -> 1."""
    rest = args[1:]
    if not rest or rest[0].startswith("--"):
        sys.stderr.write("usage: ai-workflow %s\n" % usage)
        return 2
    ticket_id = rest[0]
    opts, err = _parse_options(rest[1:], known_opts)
    if err:
        sys.stderr.write("%s: %s\n" % (name, err))
        return 2
    try:
        print(apply(ticket_id, opts))
    except _UsageError as exc:
        sys.stderr.write("%s: %s\n" % (name, exc))
        return 2
    except mutate.MutateError as exc:
        sys.stderr.write("%s: %s\n" % (name, exc))
        return 1
    return 0


def cmd_archive_artifacts(args, root):
    """Verified export: usage -> 2, contract/IO refusal -> 1, success -> 0."""
    rest = args[1:]
    if not rest or rest[0].startswith("--"):
        sys.stderr.write("usage: ai-workflow archive-artifacts <ticket-id> "
                         "--output <new.zip>\n")
        return 2
    ticket_id = rest[0]
    opts, err = _parse_options(rest[1:], {"--output"})
    if err:
        sys.stderr.write("archive-artifacts: %s\n" % err)
        return 2
    if not opts.get("output"):
        sys.stderr.write("usage: ai-workflow archive-artifacts <ticket-id> "
                         "--output <new.zip>\n")
        return 2
    try:
        dest = artifact_archive.archive_ticket(root, ticket_id, opts["output"])
    except artifact_archive.ArchiveError as exc:
        sys.stderr.write("archive-artifacts: %s\n" % exc)
        return 1
    print("archived %s to %s" % (ticket_id, dest))
    return 0


def cmd_advance(args, root):
    def apply(ticket_id, opts):
        to = opts.get("to")
        if not to:
            raise mutate.MutateError("--to <phase> is required")
        return mutate.advance(root, ticket_id, to)
    return _cmd_mutate(
        "advance", "advance <ticket-id> --to <phase>",
        args, root, {"--to"}, apply)


def cmd_claim(args, root):
    def apply(ticket_id, opts):
        return mutate.claim(root, ticket_id,
                            harness=opts.get("harness"), model=opts.get("model"))
    return _cmd_mutate(
        "claim", "claim <ticket-id> [--harness H] [--model M]",
        args, root, {"--harness", "--model"}, apply)


def cmd_complete_task(args, root):
    def apply(ticket_id, opts):
        raw = opts.get("total")
        total = _parse_nonneg_int(raw, "--total") if raw is not None else None
        return mutate.complete_task(root, ticket_id, total=total)
    return _cmd_mutate(
        "complete-task", "complete-task <ticket-id> [--total N]",
        args, root, {"--total"}, apply)


def cmd_register_plan(args, root):
    def apply(ticket_id, opts):
        path = opts.get("path")
        if not path:
            raise mutate.MutateError("--path <plan> is required")
        raw = opts.get("total")
        if raw is None:
            raise mutate.MutateError("--total N is required")
        total = _parse_nonneg_int(raw, "--total")
        if total <= 0:
            raise _UsageError("--total must be a positive integer (got %r)" % raw)
        return mutate.register_plan(root, ticket_id, path, total)
    return _cmd_mutate(
        "register-plan", "register-plan <ticket-id> --path <plan> --total N",
        args, root, {"--path", "--total"}, apply)


def cmd_set_gate(args, root):
    def apply(ticket_id, opts):
        gate = opts.get("gate")
        if not gate:
            raise mutate.MutateError("--gate <sufficient|insufficient> is required")
        round_no = None
        if opts.get("round") is not None:
            raw = opts["round"]
            round_no = _parse_nonneg_int(raw, "--round")
            if round_no <= 0:
                raise _UsageError("--round must be a positive integer (got %r)" % raw)
        return mutate.set_gate(root, ticket_id, gate, round_no=round_no)
    return _cmd_mutate(
        "set-gate", "set-gate <ticket-id> --gate <g> [--round N]",
        args, root, {"--gate", "--round"}, apply)


def cmd_set_review(args, root):
    def apply(ticket_id, opts):
        verdict = opts.get("verdict")
        if not verdict:
            raise _UsageError("--verdict <pass|changes_requested> is required")
        return mutate.set_review(
            root, ticket_id, verdict,
            review_context=opts.get("review-context"),
            report_path=opts.get("report"),
            handoff_path=opts.get("handoff"))
    return _cmd_mutate(
        "set-review",
        "set-review <ticket-id> --verdict pass|changes_requested "
        "[--review-context <dir> --report <candidate-review.md> --handoff "
        "<candidate-handoff.md>]",
        args, root,
        {"--verdict", "--review-context", "--report", "--handoff"}, apply)


def cmd_prepare_review(args, root):
    """Snapshot preparation: usage -> 2, contract refusal -> 1, success -> 0."""
    rest = args[1:]
    if not rest or rest[0].startswith("--"):
        sys.stderr.write("usage: ai-workflow prepare-review <ticket-id> "
                         "--commit <literal-oid> --output <new-directory>\n")
        return 2
    ticket_id = rest[0]
    opts, err = _parse_options(rest[1:], {"--commit", "--output"})
    if err:
        sys.stderr.write("prepare-review: %s\n" % err)
        return 2
    if not opts.get("commit") or not opts.get("output"):
        sys.stderr.write("usage: ai-workflow prepare-review <ticket-id> "
                         "--commit <literal-oid> --output <new-directory>\n")
        return 2
    try:
        review_snapshot.prepare(root, ticket_id, opts["commit"],
                                opts["output"])
    except contracts.ContractError as exc:
        sys.stderr.write("prepare-review: %s\n" % exc)
        return 1
    print("prepared review snapshot for %s in %s"
          % (ticket_id, opts["output"]))
    return 0


def _run_review_status(exit_code):
    """Map the verifier's own status to a process exit status.

    A failing verifier stays failing: the status is passed through untouched
    when it is expressible, and an unexpressible one (a signal-reported or
    Windows NTSTATUS value) becomes 255 rather than silently reading as
    success. Failure is never transformed into success.
    """
    if exit_code == 0:
        return 0
    if isinstance(exit_code, int) and 0 < exit_code <= 255:
        return exit_code
    return 255


def cmd_run_review(args, root):
    """Boundary run: usage -> 2, contract/boundary refusal -> 1, else the
    command's own exit status."""
    usage = ("usage: ai-workflow run-review <ticket-id> --review-context "
             "<directory> --kind baseline|probe -- <argv...>\n")
    rest = args[1:]
    if not rest or rest[0].startswith("--"):
        sys.stderr.write(usage)
        return 2
    ticket_id = rest[0]
    rest = rest[1:]
    separator = next((index for index, item in enumerate(rest) if item == "--"),
                     None)
    if separator is None:
        sys.stderr.write("run-review: the verifier command must follow a '--' "
                         "separator\n%s" % usage)
        return 2
    options, inner = rest[:separator], rest[separator + 1:]
    opts, err = _parse_options(options, {"--review-context", "--kind"})
    if err:
        sys.stderr.write("run-review: %s\n" % err)
        return 2
    context_path = opts.get("review-context")
    kind = opts.get("kind")
    if not context_path:
        sys.stderr.write(usage)
        return 2
    if kind not in review_boundary.KINDS:
        sys.stderr.write("run-review: --kind must be baseline or probe (got "
                         "%r)\n" % (kind,))
        return 2
    if not inner:
        sys.stderr.write(usage)
        return 2
    # The root/Ticket context is verified before anything is launched: a stale
    # preparation baseline is refused up front, not discovered afterwards.
    try:
        review_snapshot.assert_current(root, ticket_id, context_path)
    except contracts.ContractError as exc:
        sys.stderr.write("run-review: %s\n" % exc)
        return 1
    try:
        receipt = review_boundary.run(context_path, kind, inner)
    except contracts.ContractError as exc:
        sys.stderr.write("run-review: %s\n" % exc)
        return 1
    summary = ("kind=%s exit=%s changed=%d added=%d removed=%d boundary=%s"
               % (receipt["kind"], receipt["exit_code"],
                  len(receipt["changed_paths"]), len(receipt["added_paths"]),
                  len(receipt["removed_paths"]),
                  "enforced" if receipt["boundary"]["enforced"] else "not-enforced"))
    line = "run-review: %s; receipt %s" % (summary, _receipt_path(context_path,
                                                                   receipt))
    stream = sys.stdout if receipt["exit_code"] == 0 else sys.stderr
    stream.write(line + "\n")
    return _run_review_status(receipt["exit_code"])


def _receipt_path(context_path, receipt):
    return os.path.join(context_path, "meta", "runs",
                        "%s.json" % receipt["run_id"])


def cmd_set_status(args, root):
    def apply(ticket_id, opts):
        st = opts.get("status")
        if not st:
            raise mutate.MutateError("--status <s> is required")
        return mutate.set_status(root, ticket_id, st)
    return _cmd_mutate(
        "set-status", "set-status <ticket-id> --status <s>",
        args, root, {"--status"}, apply)


def cmd_release(args, root):
    def apply(ticket_id, opts):
        return mutate.release(root, ticket_id)
    return _cmd_mutate(
        "release", "release <ticket-id>",
        args, root, set(), apply)


def cmd_escalate(args, root):
    rest = args[1:]
    if not rest or rest[0].startswith("--"):
        sys.stderr.write("usage: ai-workflow escalate <ticket-id> "
                         "--scope <machine|human> --reason \"...\" | --clear "
                         "[--resolution TEXT]\n")
        return 2
    ticket_id = rest[0]
    rest = rest[1:]
    clear = "--clear" in rest
    rest = [r for r in rest if r != "--clear"]
    opts, err = _parse_options(rest, {"--scope", "--reason", "--resolution"})
    if err:
        sys.stderr.write("escalate: %s\n" % err)
        return 2
    try:
        if clear:
            print(mutate.escalate(root, ticket_id, clear=True,
                                  resolution=opts.get("resolution")))
        else:
            scope = opts.get("scope")
            if not scope:
                raise mutate.MutateError("--scope <machine|human> is required "
                                         "(or pass --clear)")
            print(mutate.escalate(root, ticket_id, scope=scope, reason=opts.get("reason")))
    except mutate.MutateError as exc:
        sys.stderr.write("escalate: %s\n" % exc)
        return 1
    return 0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    cmd = argv[0]
    if cmd not in COMMANDS:
        sys.stderr.write("unknown command %r\n\n%s" % (cmd, USAGE))
        return 2
    root = _resolve_root(argv)
    if cmd == "init":
        return cmd_init(argv, root)
    if cmd == "install-skills":
        return cmd_install_skills(argv, root)
    if cmd == "status":
        return cmd_status(argv, root)
    if cmd == "resume":
        return cmd_resume(argv, root)
    if cmd == "archive-artifacts":
        return cmd_archive_artifacts(argv, root)
    if cmd == "validate":
        return cmd_validate(argv, root)
    if cmd == "adopt":
        return cmd_adopt(argv, root)
    if cmd == "start":
        return cmd_start(argv, root)
    if cmd == "upgrade":
        return cmd_upgrade(argv, root)
    if cmd == "upgrade-ticket":
        return cmd_upgrade_ticket(argv, root)
    if cmd == "advance":
        return cmd_advance(argv, root)
    if cmd == "claim":
        return cmd_claim(argv, root)
    if cmd == "complete-task":
        return cmd_complete_task(argv, root)
    if cmd == "register-plan":
        return cmd_register_plan(argv, root)
    if cmd == "set-gate":
        return cmd_set_gate(argv, root)
    if cmd == "set-review":
        return cmd_set_review(argv, root)
    if cmd == "prepare-review":
        return cmd_prepare_review(argv, root)
    if cmd == "run-review":
        return cmd_run_review(argv, root)
    if cmd == "escalate":
        return cmd_escalate(argv, root)
    if cmd == "set-status":
        return cmd_set_status(argv, root)
    if cmd == "release":
        return cmd_release(argv, root)
    return 2  # unreachable: COMMANDS gates dispatch above


if __name__ == "__main__":
    sys.exit(main())