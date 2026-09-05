# Recovery in-place boot observation

This corrective Stage 1 checkpoint removes the Recovery-to-ROM-Studio boot-check dead end while
strengthening the shared exact-device evidence boundary.

## Guided continuation

- **Check boot progress now** stays inside the active Recovery journey and requests a fresh,
  read-only Device Engine scan.
- The same Recovery incident and timeline remain visible while ROMVERSE observes current boot
  state. Guided does not ask the user to rediscover the project, phone, route or incident in ROM
  Studio.
- A successful observation updates and closes that same incident. A wrong, missing, stale or
  malformed observation leaves the incident open and retains the previously accepted evidence.

The scan request has no boot, reboot, retry, partition-write or route-execution capability. The
existing Device Engine and boot-observation owners still gather the evidence; Recovery owns the
journey and decides whether the evidence belongs to its sealed incident.

## Shared evidence boundary

`RecoveryAutopilotService` now validates every supplied boot-observation receipt before assessment
or persistence. Acceptance requires:

- a currently observed device whose workspace pseudonym matches the sealed incident identity;
- the exact Recovery project;
- the exact resolved Device Pack and build contract;
- the exact protected firmware-source digest;
- every boot sample to identify that same currently observed device;
- a current receipt schema and structurally valid receipt/Guardian digests; and
- no phone-change evidence.

This rule is below Guided and Recovery Center UI code, so present and future callers cannot attach
boot evidence by bypassing a screen-level check. Historical identity alone grants no observation
authority: a targetless incident cannot consume even an apparently matching old receipt until the
original phone is freshly present. Rejected evidence is not retained in the UI or incident ledger.

## Recovery completion boundary

A post-flash incident becomes recovered only after current exact-phone evidence and a linked,
stable, verified-first-boot receipt agree. Command completion is not image verification; image
verification is not boot; boot is not stable Android userspace; and stable userspace is not full
subsystem health. First Light remains the later subsystem-health authority.

Guardian, recovery-evidence, confirmation and typed-owner requirements are unchanged. Unknown
in-flight writes remain unknown and are never blindly retried. Bootloader relocking remains strictly
forbidden.

## Verification and limits

The final non-overlapping Fedora/Linux affected suite covers Recovery Autopilot, Recovery UI,
desktop navigation, boot observation, Time Machine and recovery evidence: **151 tests, 0 failures,
0 errors and 0 skips in about 162 seconds**. It includes a same-model/different-physical-phone boot
receipt presented while the original phone is selected, project/Pack/contract/source substitutions,
phone-change evidence, targetless historical evidence, correct-phone recovery and UI evidence
rollback. Changed-file Ruff, Python compilation and diff checks also pass.

This is implemented and simulated/tested on Fedora/Linux. Windows and physical hardware were not
exercised. No physical phone operation, app restart, package installation, Companion or website
change, publication or remote push occurred. Approved ROMVERSE and RadForge Labs production logo
assets were not edited. The feature freeze remains active and the v0.2 Golden Foundation gate
remains closed.
