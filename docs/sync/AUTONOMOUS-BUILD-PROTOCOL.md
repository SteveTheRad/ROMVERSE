# ROMVERSE Autonomous Cross-Platform Build Protocol

## Authority

Creator directive: Linux Build, Windows Build, and Product Assurance coordinate through committed
repository evidence without requiring routine manual relay. This protocol does not expand product,
execution, release, or destructive authority.

## Repository loop

1. Before work, fetch the relevant remote branches and read `docs/sync/BUILD-STATUS.md`,
   `docs/sync/PRODUCT-ASSURANCE.md`, and this protocol.
2. A Build track may begin only the exact bounded task currently approved for that platform.
3. Linux and Windows work on separate branches and non-overlapping files. Each track preserves
   unrelated and protected working-tree changes.
4. At the next safe checkpoint, Build commits scoped source/tests/docs, updates
   `docs/sync/BUILD-STATUS.md`, pushes its branch, and requests Product Assurance review.
5. Product Assurance independently verifies ancestry, diff, source, tests, platform claims,
   safety invariants, feature-freeze compliance, and the proposed next task.
6. Product Assurance records and commits APPROVED, CORRECTION REQUIRED, or CREATOR DECISION
   REQUIRED in `docs/sync/PRODUCT-ASSURANCE.md`.
7. APPROVED authorizes that track to continue automatically with only the next bounded task.
   CORRECTION REQUIRED authorizes only the stated minimum correction. CREATOR DECISION REQUIRED
   stops that decision path for Steve.
8. A stopped or blocked track must not prevent the other non-overlapping track from continuing
   within its own approval.

## Unattended behavior

- Continue routine inspection, implementation, deterministic tests, documentation, scoped commits,
  pushes to the working branch, handoffs, and approved corrections without asking Steve to relay
  messages.
- Resolve ordinary implementation choices conservatively from repository evidence.
- Keep each checkpoint small enough for independent review and recovery.
- Never treat conversation summaries, uncommitted files, or test output alone as authority.
- Never merge platform branches into the release line without a separately approved integration
  checkpoint.

## Mandatory stops

Explicit creator authorization is still required for physical phone operation, production adapter
enrollment, APK/package installation on a device, release/publication, destructive or irreversible
data changes, force-push/history rewrite, new feature scope, or a material product decision.

Bootloader locking or relocking is permanently prohibited and cannot be authorized. UNKNOWN stays
UNKNOWN, never advances, and never triggers blind retry. Guardian remains the sole execution gate;
exact-device evidence and independent verification remain mandatory.

## Current tracks

- Windows: perform the Product Assurance-approved bounded read-only portability triage, then stop
  at its committed review checkpoint.
- Linux: coordinate and monitor the repository; perform only separately approved, non-overlapping
  Linux work while preserving protected Companion and Windows draft changes.
