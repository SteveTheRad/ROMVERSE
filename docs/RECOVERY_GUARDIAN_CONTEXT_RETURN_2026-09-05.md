# Recovery to Guardian context and return

This bounded Stage 1 checkpoint completes the first consequential typed-owner continuation from
Recovery Autopilot. A Guided user can inspect a Guardian-owned recovery recommendation and return
to the same sealed incident and ranked route without reselecting the phone, project or incident.

## Implemented behavior

- Every rendered Recovery route carries its sealed route identity. Recovery reloads the active
  incident from the integrity-checked shared service before exposing a typed handoff context.
- A Guardian-owned, device-changing recommendation opens a dedicated **Recovery Autopilot
  handoff** card. It preserves the incident, project, Device Pack, diagnosis, rank, confidence,
  risk, current evidence and prerequisites that explain why the user arrived there.
- Guardian accepts only an active integrity-verified incident and one route that belongs to that
  incident, is owned by Guardian, requires confirmation, changes a device, has explicit
  requirements and grants no execution authority.
- The card is visibly labelled **Advisory • Zero authority**. It provides no approve, execute,
  flash, retry, wipe, slot or restore control.
- **Return to Recovery incident** revalidates the exact incident and route, reopens Recovery Bay,
  makes a lower-ranked route visible when necessary and restores focus to that same route. The
  user is not asked to select the phone, project, firmware or incident again.
- If the active incident or route has changed, return stops visibly in Guardian instead of guessing
  or attaching a stale context.

## Safety boundary

This is a contextual and reversible UI handoff only. It does not create a Guardian approval or
execution plan, does not turn historical identity into authority and does not implement any
device-changing recovery operation. All future execution still requires its typed service,
fresh exact-device evidence, complete required evidence and separate meaningful confirmation.
Unknown in-flight writes remain unknown and are not retried. Bootloader relocking remains forbidden.

## Verification

The final affected regression run passes **112 tests with zero failures, errors or skips in about
120.1 seconds** across Guardian UI, Recovery UI, Recovery Autopilot and desktop navigation. It
checks the full Recovery → Guardian → same Recovery incident/route journey, exact context identity,
context-only copy, mutual exclusion with other Guardian review contexts, owner mismatch rejection,
stale incident rejection, route restoration and `phone_changed == false`.

Changed-file Ruff passes on Fedora/Linux. Windows and physical hardware were not exercised.

## Honest status

This behavior is implemented and simulated/tested, not hardware verified or released. It remains a
Stage 1 Guided-friction correction under the active feature freeze and does not open the v0.2 Golden
Foundation gate. No physical phone operation, application restart, package installation, Companion
or website change, publication or remote push occurred. Approved ROMVERSE and RadForge Labs
production logo assets were not edited.
