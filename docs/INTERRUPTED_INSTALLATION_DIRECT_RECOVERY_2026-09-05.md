# Interrupted installation direct recovery — 2026-09-05

## Implemented behavior

- A safely sealed source-installation record retains a recovery-only pseudonymous device key and
  product identity after application restart. This identity can attribute diagnosis to a freshly
  observed matching phone; it cannot authorize a boot check, installation, command or retry.
- Guided **Flash** and **First boot** stages show one **Diagnose interrupted installation…** action
  for failed, uncertain or partially cancelled installation outcomes. Completed and non-mutating
  outcomes continue to the read-only results view.
- The direct handoff revalidates the selected project and protected-source digest, reconstructs the
  ordered action ledger, builds a typed Knowledge Archives failure fingerprint and opens Recovery
  Autopilot. Known failures, unknown in-flight commands and not-started work remain distinct.
- When the freshly scanned exact phone is present, Recovery is bound to that phone. When it is
  absent, ambiguous or replaced by another phone, the incident remains project-bound and
  deliberately has no device target. Recovery asks for the recorded phone and cannot fall back to
  whichever unrelated device is selected.
- If a fresh USB scan is active, the single recovery request waits for that scan and resumes once.
  An older explicit History → Recovery journey reaches the same direct diagnosis path.

## Guardian and recovery boundary

This checkpoint performs diagnosis and offline knowledge lookup only. Historical pseudonyms and
action evidence provide attribution, not execution authority. No boot observation is permitted
without a complete typed terminal receipt, and an uncertain command is never automatically retried.
Recovery routes remain advisory until their own exact-device, verified-input and explicit-confirmation
requirements are met. Bootloader relocking remains forbidden.

## Verification

- One affected regression run covered 500 source/candidate/project/local-installation, Guided,
  Expert, history, Guardian, Recovery, Knowledge Archives and lifecycle tests with zero failures,
  errors or skips in 167.672 seconds. Focused reruns are subsets and are not added to this count.
- Changed-file Ruff, Python compilation and diff checks pass.
- Verification ran on the current Fedora/Linux development host. Windows runtime behavior was not
  exercised by this checkpoint.

## Honest status

The behavior is implemented and simulated/tested on Linux. It is not hardware verified or released.
No physical phone operation, running-app restart, package installation, Companion change, website
update, publication or remote push was performed. The approved ROMVERSE and RadForge Labs logo files
were not edited. This removes one Stage 1 restart/recovery dead end; it does not complete Stage 1 or
the twenty-stage master goal.
