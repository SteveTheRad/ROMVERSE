# ROMVERSE Product Assurance Sync

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
