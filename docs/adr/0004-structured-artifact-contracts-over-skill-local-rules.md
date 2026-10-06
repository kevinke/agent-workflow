---
status: proposed
---

# Structured artifact contracts over Skill-local rules

Retain ADR-0001's repo-native Workflow Protocol and make its artifact contracts
the portable interface between models: Decision Question-linked Evidence first,
then bounded execution contracts, Review, and continuation identity. Skills remain
thin entry points. This preserves cross-Harness portability while making cheap
Scout output usable without a senior model repeating the whole investigation.

This proposal comes from the 2026-10-07 discussion and
[the implementation spec](../../.scratch/decision-scout-port/spec.md). Its stricter
gates are planned, not installed. Version 1 history remains valid until explicit
per-Ticket upgrade; structural checks cannot prove natural-language facts or
authenticate model tiers.

The alternatives are placing full rules in each Harness's Skills, which permits
drift, or introducing a new orchestration service, which adds deployment and
coupling before the handoff contract is proven. The cost of the chosen direction
is maintaining concise shared contracts and a deliberate upgrade path.
