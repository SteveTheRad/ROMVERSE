# Recovery Guardian consent checkpoint — 2026-09-05

## Outcome

ROMVERSE now presents one clear, informed human decision after Guardian has sealed an exact-stock
Recovery preparation and freshly verified the exact Fastboot phone. Accepting records a private,
short-lived Recovery consent receipt. It does not execute Recovery, invoke an adapter, change a
phone or grant execution authority.

The architectural boundary remains explicit:

> Recommendation ≠ Preparation ≠ Live Target ≠ Consent ≠ Execution ≠ Verification

This checkpoint implements **Consent** only. A governed Recovery executor and physical outcome
verification remain separate future gates.

## One meaningful decision

The Recovery consent dialog contains no typed phrase, safety-code loop or chain of acknowledgements
that a Guided user must navigate. It presents:

- the recognized phone product and current Fastboot mode;
- a prominent warning when the sealed plan may erase user data;
- every ordered prepared operation in plain language;
- each mode transition and step-specific wipe consequence;
- the no-blind-retry, post-repair verification and bootloader-relock boundaries;
- **Cancel** and one explicit **I understand — record consent** action.

Cancelling records nothing and leaves the current exact-phone evidence available until it expires.
Accepting shows **Recovery consent recorded** and explicitly states that no action started and that
execution is not available in this build. No execution control is hidden.

## Exact consent binding

The receipt binds:

- preparation ID and digest;
- live-target receipt digest and its exact expiry;
- incident ID/record digest, route and project;
- pseudonymous exact-device key and user-facing device name;
- protected-source SHA-256;
- Device Pack ID, version and SHA-256;
- signed transition-contract and Recovery-evidence digests;
- expected/observed product, Fastboot mode and applicable recorded pre-write slot;
- complete prepared step count, digest and rendered consequences;
- the accepted data-loss, no-blind-retry, verification, expiry and relock-prohibition boundaries.

Issuance revalidates both the current preparation and current live-target receipt at the shared
service boundary. A stale incident, changed project/source/Pack/action set, expired phone receipt,
different physical phone, mode/slot drift or receipt tampering prevents consent.

## Capability and privacy boundary

- Consent expires at the same instant as the two-minute live-target receipt.
- A fresh phone check, disconnect, substitution, ambiguity, context invalidation or expiry clears
  the in-memory consent grant.
- The persisted file is private at
  `diagnostics/recovery-preparations/<incident-id>/recovery-consent.romverse`.
- The raw 256-bit grant token is memory-only; only its SHA-256 is persisted.
- Raw device serials and command output are not stored.
- Recording consent issues no ADB or Fastboot command; the affected test proves discovery and probe
  call counts do not change during consent.
- Exact-schema parsing rejects added or duplicate keys, malformed data, content tampering and
  symbolic-link substitution.
- The receipt records `execution_authority=none`, `automatic_retry_allowed=false`,
  `bootloader_relock_allowed=false`, `runtime_invoked=false` and `phone_changed=false`.
- The service exposes no consume, execute, flash, restore, reboot, retry, wipe, unlock, relock or
  slot-change method.

## Guided and Expert behavior

Guided uses the single plain-language decision and shows the resulting consent state without hashes
or token mechanics. Expert shows the receipt prefix, expiry and zero-authority facts. Switching
experience modes does not lose or upgrade the consent. If persisted consent is missing, changed or
expired during revalidation, the in-memory grant is removed and the exact decision must be reviewed
again.

The final dialog was visually inspected at 820×680. The focused Guided recorded-consent state was
visually inspected at 1440×900. Both are readable and unclipped.

## Adversarial coverage

The affected suite covers:

1. exact preparation/live-target/consequence binding;
2. memory-only token validation and no raw token persistence;
3. explicit decline with no receipt;
4. same-model substitute and expired live-target rejection;
5. incident drift after consent;
6. receipt tampering, extra/duplicate keys and link substitution;
7. absence of executor or device-mutation methods;
8. one-dialog Guided acceptance and cancellation behavior;
9. expiry clearing both live-target and consent state;
10. the prior Recovery identity, preparation, live-target, Guardian, navigation and forward-consent
    boundaries in the same non-overlapping regression run.

## Verification evidence

- One non-overlapping affected Fedora/Linux run passed **236 unique tests** with zero failures,
  errors or skips in **181.13 seconds**.
- Changed-file Ruff format and lint checks passed.
- Python compilation and diff checks passed.
- Final dialog and Guided state renders passed visual inspection at 820×680 and 1440×900.
- Approved production logo assets remained byte-exact.

## Honest classification and remaining gates

- **Implemented:** exact Recovery consent receipt/grant service, private persistence, one-decision
  dialog, Guided/Expert result states, expiry and drift invalidation.
- **Simulated/Tested:** inert exact/stale/substitute/expired/tampered/declined scenarios and UI
  acceptance/cancellation on Fedora/Linux.
- **Hardware Verified:** no.
- **Released:** no.
- **Windows:** not exercised in this checkpoint.

No governed Recovery executor, adapter invocation, stock-package restoration, reboot orchestration or
post-repair physical proof was added. No physical phone operation, application restart, package
installation, Companion change, website update, publication or remote push occurred. Feature freeze
remains active, bootloader relocking remains strictly forbidden and the v0.2 Golden Foundation gate
remains closed.
