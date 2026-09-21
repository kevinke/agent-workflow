"""`ai-workflow` CLI entry point (Python 3 stdlib, zero dependencies).

Usage:
    ai-workflow init [target]
    ai-workflow status [ticket-id]
    ai-workflow validate [ticket-id]
    ai-workflow start <ticket-id> [opts]
    ai-workflow adopt <ticket-id> [opts]
    ai-workflow advance <ticket-id> --to <phase>
    ai-workflow claim <ticket-id> [opts]
    ai-workflow complete-task <ticket-id> [--total N]
    ai-workflow set-gate <ticket-id> --gate <g> [--round N]
    ai-workflow escalate <ticket-id> [opts]
    ai-workflow upgrade

Subcommands implement the workflow state machine (spec §9); the semantic
mutators (advance/claim/complete-task/set-gate/escalate) are TICKET-010.
"""

import os
import sys

import adopt
import init
import mutate
import start
import status
import upgrade
import validate

COMMANDS = {"init", "status", "validate", "start", "adopt", "advance", "claim",
            "complete-task", "set-gate", "escalate", "upgrade"}

USAGE = """ai-workflow — repo-native agent workflow protocol (subset)

commands:
  init [target]       install protocol + templates + AGENTS.md managed block
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
  complete-task <ticket-id> [--total N]  mark one implementation task done
  set-gate <ticket-id> --gate G [--round N]  record evidence verdict (G: sufficient|insufficient)
  escalate <ticket-id> --scope S --reason "..." | --clear  set/clear escalation
  upgrade             explicit protocol upgrade using workflow_version
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
    target = args[1] if len(args) > 1 else root
    created = init.init(target)
    if created:
        print("installed into %s:" % target)
        for p in created:
            print("  %s" % os.path.relpath(p, target))
    else:
        print("nothing to do: protocol already installed (idempotent).")


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
        updated, bumped = upgrade.upgrade(root)
    except upgrade.UpgradeError as exc:
        sys.stderr.write("upgrade: %s\n" % exc)
        return 2
    installed = upgrade.installed_workflow_version(root)
    if not updated and not bumped:
        print("nothing to do: protocol already at workflow_version %s (idempotent)."
              % installed)
        return 0
    print("upgraded protocol to workflow_version %s:" % upgrade.kit_workflow_version())
    for p in updated:
        print("  %s" % os.path.relpath(p, root))
    if bumped:
        print("bumped tickets:")
        for t in bumped:
            print("  %s" % t)
    return 0


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
    except mutate.MutateError as exc:
        sys.stderr.write("%s: %s\n" % (name, exc))
        return 1
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
        total = int(opts["total"]) if opts.get("total") is not None else None
        return mutate.complete_task(root, ticket_id, total=total)
    return _cmd_mutate(
        "complete-task", "complete-task <ticket-id> [--total N]",
        args, root, {"--total"}, apply)


def cmd_set_gate(args, root):
    def apply(ticket_id, opts):
        gate = opts.get("gate")
        if not gate:
            raise mutate.MutateError("--gate <sufficient|insufficient> is required")
        round_no = int(opts["round"]) if opts.get("round") is not None else None
        return mutate.set_gate(root, ticket_id, gate, round_no=round_no)
    return _cmd_mutate(
        "set-gate", "set-gate <ticket-id> --gate <g> [--round N]",
        args, root, {"--gate", "--round"}, apply)


def cmd_escalate(args, root):
    rest = args[1:]
    if not rest or rest[0].startswith("--"):
        sys.stderr.write("usage: ai-workflow escalate <ticket-id> "
                         "--scope <machine|human> --reason \"...\" | --clear\n")
        return 2
    ticket_id = rest[0]
    rest = rest[1:]
    clear = "--clear" in rest
    rest = [r for r in rest if r != "--clear"]
    opts, err = _parse_options(rest, {"--scope", "--reason"})
    if err:
        sys.stderr.write("escalate: %s\n" % err)
        return 2
    try:
        if clear:
            print(mutate.escalate(root, ticket_id, clear=True))
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
    if cmd == "status":
        return cmd_status(argv, root)
    if cmd == "validate":
        return cmd_validate(argv, root)
    if cmd == "adopt":
        return cmd_adopt(argv, root)
    if cmd == "start":
        return cmd_start(argv, root)
    if cmd == "upgrade":
        return cmd_upgrade(argv, root)
    if cmd == "advance":
        return cmd_advance(argv, root)
    if cmd == "claim":
        return cmd_claim(argv, root)
    if cmd == "complete-task":
        return cmd_complete_task(argv, root)
    if cmd == "set-gate":
        return cmd_set_gate(argv, root)
    if cmd == "escalate":
        return cmd_escalate(argv, root)
    return 2  # unreachable: COMMANDS gates dispatch above


if __name__ == "__main__":
    sys.exit(main())