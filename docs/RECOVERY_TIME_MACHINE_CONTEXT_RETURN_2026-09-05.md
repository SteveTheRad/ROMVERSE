# Recovery to Time Machine context and return

This bounded Stage 1 checkpoint removes the generic-dashboard dead end from a Recovery Autopilot
route whose exact stock-package evidence is not yet registered. The Guided journey now carries the
same sealed incident and exact ROM project into Time Machine, keeps local evidence work scoped to
that project, and returns to the same Recovery route.

## Implemented behavior

- Recovery reloads the active incident from the integrity-checking shared service before opening a
  Time Machine handoff.
- Time Machine accepts only an active, integrity-verified, device-bound incident and its own exact
  stock-restoration route when that route requires confirmation, grants no execution authority and
  retains explicit evidence requirements.
- The incident's project must still exist, contain a protected original and match the sealed Device
  Pack identity. Time Machine selects that exact project and temporarily disables project
  reselection while the handoff is active.
- The dedicated handoff explains why the user arrived, the incident/device/Device Pack/project
  context, the protected source digest, current evidence and every route prerequisite.
- The contextual controls register an external backup, register the exact stock package or reverify
  existing evidence through the established local hashing service. These controls select and read
  external files only; they do not copy them into the project or send anything to a phone.
- **Return to Recovery incident** freshly reassesses the exact project's evidence, re-ranks the same
  sealed incident and restores the same route. When both evidence records become ready after an
  operation, Time Machine returns automatically. A route may consequently move from Time Machine
  evidence preparation to Guardian review, but it never receives execution authority.
- Changed project, route, incident or Device Pack context is refused rather than guessed.

## Safety boundary

The handoff is labelled **Evidence needed • Zero authority** or **Evidence ready • Zero authority**.
It creates no Guardian approval or execution plan and cannot restore, flash, wipe, switch slots,
observe boot or retry an unknown write. Exact-device incident identity remains immutable and fresh
Recovery service validation remains authoritative. Bootloader relocking remains forbidden.

## Verification

One final affected regression run passes **130 tests with zero failures, errors or skips in about
127.3 seconds** across Time Machine UI, desktop navigation, Recovery UI, Recovery Autopilot and
Recovery evidence. The focused checks are included in, not added to, this total.

The tests cover exact project/Pack/route presentation, disabled project reselection, local evidence
registration, evidence-ready automatic return, manual return, same-incident restoration,
re-ranking through the shared Recovery service, unchanged phone state and the preceding Guardian
continuation. Changed-file Ruff, Python compilation and diff checks pass on Fedora/Linux.

The 1440×900 offscreen visual inspection shows the full context, status, requirements, relevant
controls and return action together without clipping. Windows and physical hardware were not
exercised.

## Honest status

This is implemented and simulated/tested, not hardware verified or released. It remains a Stage 1
Guided-friction correction under the active feature freeze and does not open the v0.2 Golden
Foundation gate. No physical phone operation, application restart, package installation, Companion
or website change, publication or remote push occurred. Approved ROMVERSE and RadForge Labs
production logo assets were not edited.
