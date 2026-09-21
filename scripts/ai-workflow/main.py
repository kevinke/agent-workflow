"""`ai-workflow` CLI entry point (Python 3 stdlib, zero dependencies).

Usage:
    ai-workflow init [target]
    ai-workflow status [ticket-id]
    ai-workflow validate [ticket-id]

Subcommands implement the workflow state machine (spec §9 / TICKET-002).
`start` and `upgrade` are delivered by later tickets.
"""

import os
import sys

import adopt
import init
import status
import validate

COMMANDS = {"init", "status", "validate", "start", "adopt", "upgrade"}

USAGE = """ai-workflow — repo-native agent workflow protocol (subset)

commands:
  init [target]       install protocol + templates + AGENTS.md managed block
  status [ticket-id]  one-screen summary of a ticket (or the active ticket)
  validate [ticket-id] validate workflow state; ERROR -> non-zero exit
  adopt <ticket-id> [opts]  legacy repo adoption: migration report + state scaffold
      --phase <phase>       adopted phase (default: requirement)
      --title <title>       ticket title
      --spec <path> --ticket <path> --plan <path>   source-artifact references

`start` and `upgrade` are implemented in later tickets.
"""


def _resolve_root(args):
    return os.path.abspath(os.getcwd())


def _print_findings(findings):
    for f in sorted(findings, key=lambda x: (x.severity != "ERROR", x.message)):
        print("%-5s %s" % (f.severity, f.message))


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
    # start / upgrade — future tickets.
    sys.stderr.write("%s is not implemented yet (later ticket).\n" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main())