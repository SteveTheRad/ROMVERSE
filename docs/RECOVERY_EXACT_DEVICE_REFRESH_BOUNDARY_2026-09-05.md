# Recovery exact-device refresh boundary

This corrective Stage 1 checkpoint closes a cross-device attribution gap in Recovery Autopilot.
An interrupted installation can be operationally targetless while retaining the immutable,
pseudonymous identity of the phone to which its sealed evidence belongs.

## Domain invariant

**Incident identity is immutable; target availability is mutable.**

- A Recovery incident created from sealed installation or First Light evidence records the expected
  pseudonymous device key even when that phone is absent.
- A generic Recovery refresh is validated by `RecoveryAutopilotService`, not trusted because it
  came from a particular screen or caller.
- A fresh observation with another key is rejected before incident assessment or persistence. This
  includes another physical phone of the same model.
- A targetless incident without any sealed identity cannot adopt the first available phone.
- When the original phone returns, its freshly derived pseudonym matches and refreshes the same
  incident identifier. Repeated targetless refreshes do not create duplicate incidents.
- Separate incidents for separate devices keep distinct identities even when they share one ROM
  project.

The identity key is recovery attribution only. It grants no boot-observation authority, device
write, retry, route execution or Guardian approval. Unknown in-flight writes remain unknown and no
operation is automatically repeated. Recovery routes remain advisory and carry no execution
authority.

## Guided behavior

Guided does not expose serials, hashes or matching machinery. If the wrong or no phone is present,
Recovery says ROMVERSE is waiting for the phone involved in the incident and does not assign or
change the connected phone. When the correct phone is freshly recognized, diagnosis continues on
the same incident.

## Adversarial verification

The final, non-overlapping affected suite combines the installation-route and Recovery scopes:
**558 tests, 0 failures, 0 errors and 0 skips in 351.842 seconds**. It covers:

- absent, different-model and same-model/different-physical-phone substitutions;
- generic Recovery Center refresh after the wrong phone appears;
- the original phone returning to the same incident;
- repeated targetless refreshes without duplicate incidents;
- active-scan completion before attribution;
- stale, ambiguous and missing identity;
- multiple incidents and devices retaining separate sealed identities;
- complete candidate/source/manual installation, history, First Light, Guardian and desktop routes;
- inert transports proving the regression journey sends no boot, write or retry command.

Changed-file Ruff, Python compilation and diff checks pass on Fedora/Linux. Windows and physical
hardware were not exercised. No physical phone operation, app restart, package installation,
Companion or website change, publication or remote push occurred. Approved ROMVERSE and RadForge
Labs production logo assets were not edited.
