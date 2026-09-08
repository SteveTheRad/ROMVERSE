# ROMVERSE Product Assurance Sync

## Linux hardware checkpoint — one fresh read-only popsicle observation

### Authoritative checkpoint

- Product Assurance authorization/base:
  `bccc0b1eb7fc3585a8c65006d07076f334f6b2d8` — `Authorize read-only popsicle observation`.
- Evidence checkpoint:
  `60e7e85b260b9ae368bd81733c02febdc014babe` — `Record read-only popsicle hardware evidence`.
- Final handoff: the follow-up commit containing this exact identifier on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, production Device Engine / Device DNA read-only
  hardware acceptance.
- Working tree before the checkpoint: clean and synchronized with the remote branch.

### Exact observed result

- The production `DeviceEngine.scan_reconnect_safe()` path observed exactly one stable USB ADB
  target over two required unchanged discovery cycles. The second cycle completed the existing
  fixed, allowlisted detail probes; both cycles also confirmed that no Fastboot target was present.
- The target resolved as Xiaomi 17 Pro Max: manufacturer/brand `Xiaomi`, model `2509FPN0BC`,
  product/codename `popsicle`, SoC `SM8850`, Android `17`, HyperOS
  `OS4.0.0.32.XPBCNXM`, build ID `CP2A.260605.016`, security patch `2026-08-01`,
  China firmware region, active slot `a`, Virtual A/B and dynamic-partition evidence.
- Read-only safety state reported bootloader `unlocked` and Verified Boot `orange`. Battery was
  100%; the bounded live telemetry contained no warning.
- The live build fingerprint was observed by the allowlisted aggregate-property probe and used by
  the existing firmware relationship assessment. The privacy-safe passport deliberately excludes
  the raw fingerprint and serial. Device DNA records the result as
  `SAME INSTALLED OTA BUILD • 17OS4.0.260902.070444909.QCPECN.S`.
- `DevicePackRegistry` matched `xiaomi.popsicle.hyperos4.os4.0.0.23` version `0.1.1` to the live
  device identity. The current project does not have that exact source-bound Pack/execution
  contract, so Device DNA correctly reports `guardian_flash: UNCONFIRMED` and the Compatibility
  Matrix reports `Unknown`; execution remains locked.
- The local Device Intelligence passport is bound to pseudonymous device key
  `ad74e54831f21bf55d75` and sealed record digest
  `1217107ab1e2b287d3576fc3a672c93b6e14aea58de2325444fb8e98d32af092`.
  Strict reload succeeded and a byte scan of the affected evidence, identity and Guardian audit
  stores confirmed that the raw serial was not persisted.
- Device DNA digest:
  `73016d262e6957bdc7383a861fa6933b7a15dbec9db05fcbfa2a0b399092601b`.
  Compatibility Matrix digest:
  `4cd90f4391d03c6f0ef9166cbec78f9072088229814f1045bc2a55d2df944e02`.

### Focused acceptance evidence

- **1/1 production hardware acceptance path passed.** This is the only acceptance total for this
  checkpoint; no broad, overlapping or package suite was run.
- Guardian recorded exactly **14/14 allowed read-only operations** for this acceptance: two ADB
  discovery calls, two Fastboot discovery calls, and ten fixed ADB detail probes. Every operation
  was redacted in the audit; expected absent-package probes returned a normal non-zero result and
  did not alter the phone.
- The complete active and archived Guardian audit chain passed verification; the current active
  ledger contains 28,005 entries.
- Passport, Device DNA and Compatibility Matrix passed their strict production loaders after the
  observation.
- The acceptance reporting wrapper referenced the Pack-resolution boolean by its wrong attribute
  name after all phone probes and evidence validations had completed. No probe was repeated; the
  final sanitized report was reconstructed exclusively from the sealed local receipts. This was a
  harness-only reporting mistake, not an application defect or uncertain phone result.

### Classification

- **Implemented:** unchanged production Device Engine, privacy-safe Device Intelligence, Device
  DNA and Compatibility Matrix paths were exercised; this checkpoint adds no product code.
- **Simulated/Tested:** none claimed. The result came from a real physical Android target.
- **Hardware Verified:** yes, limited strictly to one fresh read-only ADB identity/state and
  project-compatibility observation of the connected `popsicle` phone on Fedora Linux.
- **Released:** no. Nothing was signed, published, installed or released.

### Guided, Guardian and Recovery impact

- The production Fresh Live Target receipt service is intentionally Fastboot-only. Because mode
  change was prohibited and the phone remained safely in Android/ADB, no Fresh Live Target receipt
  was created. This checkpoint therefore ended at reviewed Device DNA evidence.
- No recommendation, preparation, plan consent, executor admission, adapter dispatch, durable
  execution result, Recovery incident, reassessment or post-repair verification was created.
- The observed exact device identity does not become flash authority. Missing exact source-bound
  execution evidence remains `UNCONFIRMED` / `Unknown`, never guessed or misreported as proven
  incompatibility.
- Bootloader locking/relocking remains `UNSUPPORTED` / `Known Incompatible`, permanently
  prohibited, and has no authorization path.
- Exact-device evidence, Guardian-only authority, UNKNOWN-on-uncertainty, no blind retry,
  same-incident attribution and independent verification remain unchanged.

### Blockers, platform status and freeze

- Blockers/failures in the authorized observation: none.
- Fedora/Linux: genuine production-path hardware verification passed on the current host.
- Windows: not tested or claimed by this checkpoint.
- Guided friction/dead ends: none introduced; Fresh Live Target and all later consequential stages
  remain truthfully unavailable in Android/ADB mode.
- Feature freeze: compliant. This is evidence-only acceptance of existing Stage 1 behavior, with
  no new feature, architecture, route, Device Pack, adapter or execution capability.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance review of this hardware
  evidence and later explicitly authorized work.

### Preservation and external actions

- The protected Companion files, Windows launcher work, website, Adaptive work, external firmware
  package and unrelated user files were not edited, staged, discarded or committed.
- Physical action: read-only ADB/Fastboot discovery and allowlisted ADB identity/state probes only.
- Phone reboot/mode change, APK installation, file push/pull, backup, settings write, root/unlock,
  debloat, partition access, consent, Guardian admission, adapter execution, flash/wipe, signing,
  publication, release and relock: **none**.
- External action after verification: one normal push of the scoped evidence handoff to the existing
  Linux branch only; no force-push.

### Next proposed Build task

Stop for independent Product Assurance review. The previously approved bounded external-package
metadata and untrusted-procedure inventory remains queued and was not run concurrently. Do not
begin it or another consequential slice until the latest repository verdict is reviewed.

### Product Assurance Review Requested

- Confirm that the real observation remained within the exact read-only authorization and that the
  pseudonymous passport plus sealed Device DNA/Compatibility evidence are sufficient for this
  checkpoint.
- Confirm the truthful boundary: Device DNA was hardware-verified, but Fresh Live Target, consent,
  execution and Recovery remain unverified and unavailable.

## Authoritative checkpoint

- Product Assurance correction/base:
  `56f0c4f117124f5718bfabdbcea7c174f0787359` — `Require same-handle firmware inspection`.
- Tested implementation commit:
  `aad0f2a934d069623b658a957632c4bee1002ec6` — `Bind external inspection to hashed descriptor`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, external firmware evidence-integrity correction.
- Working tree at handoff: clean. Ignored local artifacts from the previously reviewed packaged
  checkpoint remain local and unchanged.

## Exact correction

Product Assurance found that external intake hashed one open descriptor, closed it, then reopened
the pathname for container inspection. A transient directory-entry replacement could therefore have
combined one file's SHA-256 with another file's structure evidence.

The minimum correction changes four files:

- `src/romverse/rom/inspection.py` adds a bounded seekable-stream inspection entry point. Container
  detection plus ZIP/TAR/raw inspection now operate on the supplied stream. The existing path API is
  retained as a compatibility wrapper that opens once and delegates to the shared implementation.
- `src/romverse/rom/external_intake.py` keeps the original no-follow regular-file descriptor open
  continuously through identity validation, SHA-256 hashing, rewind, container detection, bounded
  metadata inspection, final descriptor identity validation, and final pathname identity validation.
- `tests/test_external_firmware_intake.py` proves the selected path is not reopened for inspection
  and that replacing its directory entry cannot mix replacement metadata with the original hash.
- `tests/test_rom_inspection.py` proves the stream entry point preserves ZIP, TAR, and raw results.

The replacement adversary test observes the original descriptor's SHA-256 and `super` signal even
after the pathname is replaced by a different ZIP containing `vbmeta`; the final pathname binding
then rejects the intake and writes no receipt. This preserves internally consistent evidence and
fails closed.

## Verification

- Focused external-intake and directly affected inspector regression: **38/38 unique tests passed**.
- Required adversarial groups:
  1. selected content path cannot be reopened after descriptor admission: passed;
  2. directory-entry replacement cannot mix evidence and fails before receipt persistence: passed;
  3. ZIP/TAR/raw results plus no-copy/no-authority receipt behavior remain unchanged: passed.
- Ruff static check: **4/4 changed source/test files passed**.
- Ruff format check: **4/4 changed source/test files passed**.
- `git diff --check`: passed.
- The real 11.8 GB firmware was **not rehashed**.
- The prior packaged journey was **not replayed**.
- The Fedora package was **not rebuilt**.
- No broad or overlapping regression suite was run or double-counted.

## Classification

- **Implemented:** same-open-handle hash/container/structure evidence binding and final fail-closed
  path identity check.
- **Simulated/Tested:** deterministic fixture-based ZIP/TAR/raw and adversarial directory-entry
  replacement tests on Fedora Linux.
- **Hardware Verified:** no. No phone, emulator, ADB target, Fastboot target, or other device was
  used.
- **Released:** no. No artifact was signed, published, installed, or released.

## Guided, Guardian, and Recovery impact

- Guided presentation and decisions are unchanged; no new prompt, interruption, route, or dead end
  was introduced.
- External evidence remains `UNCONFIRMED`; Compatibility Matrix remains `Unknown` until exact
  evidence exists.
- The receipt remains evidence-only and creates no protected source, build input, Device Pack match,
  device selection, consent, Guardian authority, Recovery incident, execution, or durable result.
- Exact-device evidence, Guardian-only authority, UNKNOWN-on-uncertainty, no blind retry,
  same-incident attribution, independent verification, and permanent no-relock remain unchanged.
- Bootloader locking/relocking has no authorization or execution path.

## Blockers and platform status

- Blockers/failures: none in the authorized correction.
- Fedora/Linux: correction implemented and deterministically tested on Fedora 44 x86-64.
- Windows: not tested or claimed by this checkpoint.
- Physical Android: not connected, observed, or operated.
- The previously reviewed unsigned Fedora artifact remains superseded for this source correction;
  Product Assurance explicitly prohibited rebuilding it at this checkpoint.

## Freeze and version gate

- Feature freeze: compliant. This is the exact evidence-integrity correction required by Product
  Assurance and adds no device, build, Recovery, Adaptive, Companion, Windows, or product capability.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance approval and later authorized
  Stage 1 work.

## Preservation and external actions

- Protected Companion files, Windows launcher work, Adaptive work, website, logos, and unrelated
  user changes were not edited, staged, discarded, or committed.
- Firmware copy/extraction/mutation/hash/build/sign/execute, physical phone operation, APK
  installation, system package installation, publication, release, and force-push: **none**.
- Remote action after verification: one normal push of the scoped implementation and handoff commits
  to the existing `linux/stage1-desktop-readiness` branch only.

## Next proposed Build task

Stop at this committed checkpoint for Product Assurance. Do not begin another consequential slice.
Continue only from the next top verdict in `docs/sync/PRODUCT-ASSURANCE.md`.

## Product Assurance Review Requested

- Confirm that the original open descriptor now binds SHA-256, container detection, structural
  evidence, and final identity validation without a pathname reopen.
- Confirm that the three focused regression groups close the identified TOCTOU gap while preserving
  the external receipt's zero-authority boundary.
