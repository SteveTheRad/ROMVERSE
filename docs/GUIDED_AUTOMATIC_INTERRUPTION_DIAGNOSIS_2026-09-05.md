# Guided automatic interruption diagnosis

This bounded Stage 1 checkpoint removes the extra manual Recovery step after ROMVERSE has already
sealed evidence that an installation was interrupted.

## Implemented journey

- Opening Genesis with an exact current-project/current-source outcome in `failed`, `attention`, or
  partially completed `cancelled` state automatically shows **ROMVERSE found an interrupted
  installation. Checking what happened…** and hands the same sealed outcome to Recovery.
- The automatic handoff is queued once per exact project, protected-source digest, outcome state and
  measured action counts. Repeated refreshes cannot dispatch duplicate incidents.
- Active project work and root preview work prevent the handoff. A later idle refresh can continue
  it automatically.
- Immediately before handoff, Genesis reloads the project outcome and rechecks the exact binding.
  Project, source, state or action-count drift stops attribution.
- Completed installation history does not auto-open. Its explicit read-only results action remains
  available. The existing **Diagnose interrupted installation…** action remains as a fallback when
  automatic handoff cannot start.

## Safety boundary

This automation enters diagnosis only. It does not inspect a new installation plan, execute a
command, observe boot, write a partition or retry an uncertain action. The Desktop source-recovery
boundary reloads the typed sealed record, requires the current protected source, preserves the
incident's immutable pseudonymous device identity and waits for an active fresh scan to finish.
Recovery routes remain advisory and bootloader relocking remains forbidden.

## Verification

One non-overlapping affected regression run passes **209 tests with zero failures, errors or
skips in 144.310 seconds** across Genesis, ROM Studio, desktop history/Recovery, Recovery Autopilot,
source installation and history UI. Its end-to-end desktop journey uses a sealed
command-in-flight record and proves Genesis opens exactly one
device-bound Recovery incident without adding any phone call or phone-state change.

Changed-file Ruff, Python compilation and diff checks pass on Fedora/Linux. Windows and physical
hardware were not exercised.

## Honest status

This behavior is implemented and simulated/tested, not hardware verified or released. It is a
Stage 1 Guided-friction correction under the active feature freeze; it adds no new feature scope and
does not open the v0.2 Golden Foundation gate. No physical phone operation, running-app restart,
package installation, Companion or website change, publication or remote push occurred. Approved
ROMVERSE and RadForge Labs production logo assets were not edited.
