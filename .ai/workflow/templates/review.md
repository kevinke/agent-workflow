# Review — <ticket-id>

The Reviewer's verdict on the current change and Plan (see
`.ai/workflow/ARTIFACTS.md`). A scaffold is not a verdict: `set-review` rejects
this file until the Metadata is filled in and the four sections carry real
content (structural validity is not proof that acceptance criteria passed).

An isolated review writes this report as a **candidate** inside the prepared
review snapshot's scratch area, never as a live record; publication happens only
through the guarded `set-review` (PROTOCOL.md §"Reviewer verification isolation
and publication").

## Metadata

```yaml
artifact_type: review
format_version: 1
ticket_id: <ticket-id>
reviewed_commit: <commit hash reviewed by this Review>
plan_sha256: <SHA-256 of the registered Plan>
verdict: <pass | changes_requested>
```

## Acceptance results

<the observable acceptance-criterion outcomes for the reviewed change>

## Verification results

<the commands run and their observed results — never infer a pass from tests alone>

Under this section, a new isolated review carries the reserved
`## Isolation provenance` section below. It is a DRAFT PLACEHOLDER: every value
is read from the supervisor's own receipts for that review context, so an
unfilled scaffold proves nothing and will be refused. Fill it from
`meta/context.json`, `meta/preflight.json` and `meta/runs/<run_id>.json`, or
omit the section entirely for a review that is not an isolated one.
ARTIFACTS.md §"Verification provenance for new isolated reviews" owns the key
list and the reserved-heading rule; the `probe_changes` entries below keep that
contract's pairing rule — a path is `deleted` only when `after_sha256` is null,
so an edited or added path carries its real `after_sha256` — and they are shape
examples, not evidence.

A guarded publication needs both kinds of run named: `runs` must carry at least
one `baseline` acceptance run **and** at least one `probe` run, because
publication refuses a report whose cited runs do not distinguish the two, and a
baseline-only review is unpublishable however honest it is. Every receipt the
supervisor recorded under `meta/runs/` has to be cited — a shorter report is not
an acceptable one.

## Isolation provenance

```json
{
  "format_version": 1,
  "reviewed_commit": "<draft: meta/context.json reviewed_commit — not a receipt yet>",
  "context_sha256": "<draft: SHA-256 of the meta/context.json bytes>",
  "live_manifest_sha256": "<draft: context.json live_manifest identity>",
  "snapshot_manifest_sha256": "<draft: context.json snapshot_manifest identity>",
  "plan_sha256": "<draft: context.json plan sha256>",
  "input_hashes": {"<draft: captured input path>": "<draft: raw sha256>"},
  "boundary": {
    "profile": "linux-bwrap-v1",
    "enforced": false,
    "preflight": "meta/preflight.json",
    "preflight_sha256": "<draft: SHA-256 of the persisted preflight bytes>"
  },
  "runs": [
    {
      "run_id": "<draft: meta/runs receipt id>",
      "kind": "baseline",
      "argv": ["<draft: the argv the receipt recorded>"],
      "exit_code": 0,
      "stdout_sha256": "<draft: receipt stdout hash>",
      "stderr_sha256": "<draft: receipt stderr hash>",
      "snapshot_before": "<draft: receipt snapshot_before identity>",
      "snapshot_after": "<draft: receipt snapshot_after identity>"
    },
    {
      "run_id": "<draft: meta/runs receipt id>",
      "kind": "probe",
      "argv": ["<draft: the argv the receipt recorded>"],
      "exit_code": 0,
      "stdout_sha256": "<draft: receipt stdout hash>",
      "stderr_sha256": "<draft: receipt stderr hash>",
      "snapshot_before": "<draft: receipt snapshot_before identity>",
      "snapshot_after": "<draft: receipt snapshot_after identity>"
    }
  ],
  "probe_changes": [
    {"path": "<draft: snapshot-relative path a probe run named, edited>",
     "before_sha256": "<draft: receipt-era hash of the prepared bytes>",
     "after_sha256": "<draft: hash of the bytes the snapshot holds now>",
     "deleted": false},
    {"path": "<draft: snapshot-relative path a probe run named, deleted>",
     "before_sha256": "<draft: receipt-era hash of the prepared bytes>",
     "after_sha256": null,
     "deleted": true}
  ],
  "residual_changes": {"modified": [], "added": [], "removed": []},
  "limits": ["<what these records do and do not prove>"]
}
```

## Findings

<the review findings, or the explicit None for a passing review>

## Required rework

<the appended rework tasks needed, or the explicit None for a passing review>
