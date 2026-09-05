# Recovery Guardian live-target checkpoint — 2026-09-05

## Outcome

ROMVERSE now performs an automatic, read-only live-phone check for an exact-stock Recovery
preparation before any later consent or execution work can exist. The check creates short-lived
evidence only. It cannot approve, flash, restore, reboot, wipe, unlock, relock, change slots, invoke
a Recovery adapter or claim that the phone changed.

The implementation preserves the architectural separation:

> Recommendation ≠ Preparation ≠ Live Target ≠ Consent ≠ Execution ≠ Verification

This checkpoint implements only the **Live Target** boundary. Recovery consent and Recovery
execution remain deliberately absent.

## Exact binding

One receipt is bound to all of the following sealed facts:

- preparation ID and digest;
- incident ID, incident record digest and route ID;
- project ID and protected source SHA-256;
- pseudonymous exact-device key;
- Device Pack ID, version and SHA-256;
- signed transition-contract digest and prepared action-set digest;
- Recovery evidence digest;
- expected and observed product, entry mode and applicable recorded pre-write slot;
- bounded observation timestamps and expiry.

The live service first revalidates the current Recovery incident, route, project, source, Device
Pack, evidence, signed action sequence and exact pseudonymous phone identity through the shared
Recovery/Guardian preparation boundary. It then performs three stable USB discovery passes and two
identical rounds of allowlisted Fastboot reads for product, unlocked state, Fastboot versus
Fastbootd mode and the current slot when the prepared sequence requires a recorded slot.

The operation fails closed if there is no Fastboot phone, an ADB target is also present, more than
one phone is visible, the physical phone is different even when it is the same model, transport
changes mid-check, a probe changes between rounds, a required value differs or the sealed
preparation is no longer current.

## Receipt and privacy boundary

- The receipt expires 120 seconds after its completed bounded observation.
- It is stored privately at
  `diagnostics/recovery-preparations/<incident-id>/live-target.romverse`.
- It contains no raw serial, command output, stdout or stderr.
- Discovery and probe evidence is represented by pseudonymous and cryptographic digests.
- Exact-schema parsing rejects duplicate keys, added fields, malformed values, tampering and
  symbolic-link substitution.
- The receipt explicitly records `recovery_consent_available=false`, `execution_authority=none`,
  `runtime_invoked=false` and `phone_changed=false`.
- Cryptographic device attestation is not claimed; the evidence is a short-lived, repeated
  read-only USB/Fastboot observation tied to the sealed pseudonymous identity.

## Target availability and race handling

Incident identity and the sealed preparation remain immutable while target availability may
change. A missing phone, different phone or ambiguous multi-phone scan revokes the in-memory live
receipt and leaves Guided visibly waiting for the phone involved in the incident. It does not adopt
the currently selected device and does not create a second incident.

Each background observation has a generation number. If the phone disappears or the scan becomes
ambiguous while an observation is running, its later callback is discarded even if it completed
against the same preparation digest. When one freshly scanned exact phone returns in the required
mode, ROMVERSE automatically starts a new check. A stale callback cannot resurrect authority or
replace the newer scan state.

## Guided and Expert experience

Guided Mode hides receipt hashes and probe machinery. It briefly says **Checking your phone…**,
then shows **Exact phone verified** or one actionable reconnect/waiting state. It continues
automatically after the original phone is freshly recognized. Missing verified platform tools
route directly to Forge Arsenal, and an expired Recovery context returns to Recovery Bay rather
than presenting a dead button.

Expert Mode exposes the product, observed Fastboot mode, unlocked state, applicable slot, receipt
prefix and expiry while still stating that Recovery consent is locked, execution is none and the
phone has not changed. Technical plan evidence is scrollable. Both focused views were visually
inspected at 1440×900 and are readable without clipping.

## Adversarial coverage

The affected regression set covers:

1. exact original phone and sealed preparation success;
2. different-model and same-model/different-physical-phone rejection;
3. absent phone, ADB/Fastboot ambiguity and multiple-Fastboot-phone rejection;
4. transport substitution during the observation;
5. product, unlock state and Fastboot/Fastbootd mismatch;
6. stale scan mode, expired receipt, stale incident and changed evidence;
7. receipt tampering, extra/duplicate keys and link substitution;
8. phone disappearance during an active check and rejection of its late result;
9. original-phone reconnection with automatic fresh verification;
10. targetless incident identity preservation, no duplicate incident and no historical-evidence
    authority through the shared Recovery regression cases.

## Verification evidence

- One non-overlapping affected run passed **228 tests** with zero failures, errors or skips in
  **181.04 seconds** on Fedora/Linux.
- Changed-file Ruff format and lint checks passed.
- Python compilation and final diff checks passed.
- Guided and Expert renders were visually inspected at exactly 1440×900.
- Approved production logo hashes remained byte-exact:
  - ROMVERSE PNG: `ab9286ce69e77abd82fe88105df70680186a4eb992289580c23f5d362c132a18`
  - ROMVERSE ICO: `bcfe1c5b960de2327c5e706cc22b872923c8ce2c254aa0b125c4f9b1dd4036b2`
  - RadForge Labs PNG: `d82ff146aab1f18474005d1a2d9ce0c3944467ae30ff7cb4fb3284387daa95cb`

## Honest classification and remaining gates

- **Implemented:** exact Recovery live-target receipt service, private persistence, expiry,
  fail-closed revalidation, automatic Guided continuation, focused Guided/Expert evidence and
  no-dead-end navigation.
- **Simulated/Tested:** inert ADB/Fastboot fixtures, adversarial identity/transport/context cases,
  background-result races, navigation and 1440×900 rendering on Fedora/Linux.
- **Hardware Verified:** no.
- **Released:** no.
- **Windows:** not exercised in this checkpoint.

Recovery consent, an execution adapter, physical stock restoration and post-repair boot proof are
not implemented by this slice. No physical phone operation, application restart, package
installation, Companion change, website update, publication or remote push occurred. Bootloader
relocking remains strictly forbidden. Feature freeze remains active and the v0.2 Golden Foundation
gate remains closed.
