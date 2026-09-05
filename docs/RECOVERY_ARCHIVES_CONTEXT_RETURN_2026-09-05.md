# Recovery to Archives context and return

This Stage 1 checkpoint removes the generic Archives-page dead end from Recovery Autopilot. It
binds the knowledge review to the exact source-labelled records that informed one current Recovery
route, then returns to the same incident without granting action authority.

## Root cause corrected

Recovery created an Archives review route with human-readable evidence labels but omitted the
matched record identifiers from that route. The UI therefore had no exact identity to open and
could only navigate to a generic knowledge page. The shared route constructor now seals the first
three ranked record IDs and their evidence labels into the informational Archives route.

No text search or approximate title match is used as a substitute for a missing record.

## Exact Archives workspace

Before opening Archives, ROMVERSE reloads the current tamper-evident Recovery incident and verifies
that the selected route:

- still belongs to that incident;
- is the informational Archives owner route;
- changes no device state and carries execution authority `none`; and
- contains a unique non-empty set of record IDs that all exist in the current integrity-checked
  offline archive.

Archives then displays only those exact records, with their provenance, confidence, device/build
scope, known incompatibilities, recovery guidance and explicit zero-authority boundary. Search,
category, evidence-lane and quick-search controls remain disabled for the focused review so the
user cannot accidentally replace the incident evidence set with unrelated results. The broader
Synapse dashboard panels collapse to give the evidence list and document enough reading space.

An integrity-checked archive refresh preserves and revalidates the same exact record set. If a
record disappears or changes identity, the context expires visibly rather than substituting a
different guide.

## Same-incident return

**Return to Recovery incident** reloads the incident and route through the shared Recovery service.
Only the same current incident and exact Archives route are restored. A repaired, removed or
re-ranked incident leaves the user in Archives with a visible expired-context explanation and no
record substitution. A valid return focuses the same route in Recovery Bay and restores the normal
Synapse workspace for later independent browsing.

The handoff and return start no worker, network request, repair, approval, command, boot, retry,
write, wipe, flash or phone operation. Knowledge remains evidence-ranked guidance; Guardian and
typed owners retain their existing boundaries. Bootloader relocking remains strictly forbidden.

## Verification and limits

The final non-overlapping Fedora/Linux affected suite covers Recovery Autopilot, Recovery UI,
Archives UI, offline knowledge and full desktop navigation: **157 tests, 0 failures, 0 errors and 0
skips in about 132 seconds**. It verifies exact record identity, no fallback substitution, refresh
retention, control locking, valid round-trip restoration, stale-context refusal and unchanged
zero-authority semantics.

A 1440×900 offscreen visual inspection confirms that the focused Recovery evidence view is aligned,
readable and unclipped, with all three exact records, the evidence detail and the return action
visible. Changed-file Ruff, Python compilation and diff checks pass.

This is implemented and simulated/tested on Fedora/Linux. Windows and physical hardware were not
exercised. No physical phone operation, app restart, package installation, Companion or website
change, publication or remote push occurred. Approved ROMVERSE and RadForge Labs production logo
assets were not edited. Feature freeze remains active and the v0.2 Golden Foundation gate remains
closed.
