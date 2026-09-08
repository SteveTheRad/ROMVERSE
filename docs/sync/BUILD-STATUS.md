# ROMVERSE Product Assurance Sync

## Windows shared-core convergence and runnable-source checkpoint

### Exact integration

- Windows first parent: `698420728c1b86e2a85c9f7018783ad2ee6a9378` —
  `Authorize Windows shared-core convergence`.
- Verified shared-core second parent: `c0de9b2ab491120276f640628d159b51ab1dbcb6` —
  `Approve corrected Fastboot hardware round trip`.
- Common base: `fdb1692b0a5056cce0992b9045cd6f3a55cabf97`.
- Pre-merge unique history: 73 Windows commits and 98 shared-core commits.
- A normal non-rebase merge produced exactly the three predicted textual conflicts:
  `docs/sync/PRODUCT-ASSURANCE.md`, `tests/test_build_contracts.py`, and
  `tests/test_desktop_bundle.py`. Product Assurance retains both complete chronological histories
  with the current Windows authorization first. The test resolutions preserve the Windows private-
  file ACL helper and the union of Linux/shared-core and Windows bundle assertions.
- The source branch also contained three Companion paths. They were restored from the Windows first
  parent before verification; there is no staged or working-tree Companion diff.
- The pre-existing untracked
  `0001-Preserve-local-build-completion-across-restart.patch` remains untracked and byte-identical at
  SHA-256 `2358e0e9e1db390d6c02c18688a5ceca62b075b8460f7d4e3a13123befeff0bb`.

### Directly affected Windows verification

- Exact affected command:
  `.venv\Scripts\python.exe -m pytest -q tests/test_build_contracts.py tests/test_desktop_bundle.py tests/test_guardian_local_transition.py tests/test_external_firmware_intake.py tests/test_rom_inspection.py tests/test_build_control_ui.py tests/test_guardian_recovery_windows_launcher.py tests/test_windows_same_file_identity.py --basetemp C:\rvmrg-affected-69842072`.
- Collected: 177 unique tests. Initial result: **171 passed, 6 failed**.
- Four failures were genuine Windows portability differences in newly converged tests. The minimum
  test-only correction now verifies the repository's existing Windows private-file ACL contract,
  keeps POSIX directory mode assertions on POSIX, and accepts Windows' stronger fail-closed denial
  when an open firmware descriptor prevents path replacement. The four corrected nodes pass.
- The other two failures are the existing Build Control horizontal-overflow and footer-size fixture
  failures. Both were reproduced unchanged against the untouched first parent `69842072`; no Build
  Control source or test changed in this merge.

### One complete Windows Desktop/Python regression

- Exact command, run once:
  `.venv\Scripts\python.exe -m pytest -q --basetemp C:\rvmrg-full-69842072`.
- Collection cache: 2,983 unique nodes. The run reached 100% with **2,887 passed, 77 failed,
  2 errors, and 18 skipped**. There are 2,984 reported outcome events because one oversized OTA
  metadata case emitted both setup and teardown errors for the same collected node.
- The 78 unique failure/error identities remain the known Windows portability/fixture baseline:
  private-file POSIX mode assertions, Windows path/ZIP-writer expectations, compact-layout geometry,
  oversized process-environment setup, and related host-specific fixtures. No newly converged
  application path failed its focused acceptance after the four portability corrections above.
- No second complete suite was run. Further work uses focused diagnostics only.

### Static and genuine Windows runtime evidence

- Whole-source Ruff lint: **PASS**. Git whitespace check: **PASS**.
- Whole-source Ruff format check reports the same 36 pre-existing files as unformatted on both the
  converged tree and an isolated `69842072` baseline worktree. This merge does not add a formatting
  regression, and unrelated files were not mechanically reformatted.
- Supported source entry point:
  `.venv\Scripts\pythonw.exe -m romverse --workspace C:\Work\ROMVERSE-Stage1-Audit-20260908-1816 --skip-onboarding`.
- Genuine Windows result: `ROMVERSE Studio 0.2.0-alpha.1` opened a responding native window,
  initialized the fresh workspace, accepted `CloseMainWindow`, and recorded a clean runtime close.
  This is source-runtime evidence; no executable rebuild or packaged-artifact claim is made.
- The trusted interactive app-control RPC remains unavailable (`Trusted RPC service is not
  configured: sky`). No guessed-coordinate or keystroke automation substituted for it. Subsequent
  screen/action coverage uses deterministic production Qt surfaces with inert local fixtures.

### Scope and safety

- No executable/package was rebuilt. No UI Design Lab, protected Companion file, physical phone,
  emulator, ADB/Fastboot target, Recovery action, APK install, production adapter/trust/signature,
  publication, release, destructive Git action, force-push, unlock, lock, or relock was used.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze, and permanent no-relock remain preserved.

## Linux correction checkpoint — bounded Fastboot source reacquisition

### Authoritative checkpoint

- Product Assurance correction/base:
  `1a33372cac002c6142b8ac0d86eb71b099ef8c57` — `Require bounded Fastboot return reobservation`.
- Tested implementation commit:
  `03dc954fc0c5ec7f113c9696b6358c3500ab4349` — `Bound Fastboot source reacquisition`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, minimum Fastboot return-plan correctness correction.

### Exact correction

- `LocalDeviceTransitionService` now treats a successful but completely empty Fastboot product
  response as one narrowly typed transient observation. It permits at most one fresh,
  non-dispatching reacquisition; that reacquisition performs a new exact-target discovery plus new
  product and mode reads and reuses no historical Device Engine fact.
- A Fastboot-source transition plan can now be created only after **two complete, identical** live
  observations agree on exact serial, product identity and known bootloader/Fastbootd mode.
- A second empty product, absent/duplicate/changed target, changed product or mode, missing mode,
  failed discovery, failed product command, timeout, malformed/conflicting value or tool drift still
  rejects before plan creation and before any reboot command.
- The general Fastboot parser was not widened. Arrival observation and executor revalidation remain
  strict. No historical/pseudonymous identity was converted into live execution authority.

### Verification

- Focused `tests/test_guardian_local_transition.py`: **43/43 unique tests passed**.
- New adversarial coverage proves:
  1. one successful-empty product read may be followed by two complete identical observations;
  2. repeated empty product reads stop after one reacquisition with no reboot;
  3. discovery failure, product-command failure and missing mode do not reacquire or reboot;
  4. changed product or bootloader/userspace mode rejects with no reboot.
- Ruff static check: **2/2 changed source/test files passed**.
- Ruff format check: **2/2 changed source/test files passed**.
- `git diff --check`: passed.
- No broad or overlapping regression suite was run or double-counted. The firmware was not hashed
  or inspected.

### Hardware disposition

- The correction was implemented, tested and committed before any possible hardware use, as
  required.
- Steve manually returned the phone from the earlier stopped attempt, then explicitly authorized a
  fresh Fastboot acceptance when needed. Build ran one complete corrected production-path round
  trip with no retry.
- Reconnect-safe Device Engine observation first re-established the same pseudonymous Android
  `popsicle`. One reviewed Android-to-bootloader plan then completed and sealed journal
  `0e57c25452224b978fa29fe90cd45912.json`, digest
  `ca436f6393e045a82136f67b7bd3451ee68398391cec9421d432b26eac169325`.
- The fixed Device Engine Fastboot scan found exactly one bootloader target and no ADB target. It
  reported `popsicle`, slot `a`, and unlocked bootloader; all five authorized fixed variables were
  queried once. The pseudonymous Fastboot passport digest is
  `a436de0dae35b4fdd522f50c7d33d06778f128f5351a964d2a6c515824c477cd`.
- The corrected return review then earned **two complete identical fresh Fastboot source
  observations** before plan creation. No transient empty response occurred in this hardware run,
  so the one-reacquisition branch remains adversarially software-tested rather than hardware-hit.
- Exactly one reviewed Fastboot reboot returned the same pseudonymous phone to Android. Journal
  `b546399e5ab648cda8f0f6257045d914.json` completed with
  `command_completed=true`, `arrival_verified=true`, `phone_state_uncertain=false`, and digest
  `6865b376662edb1f96fd4cac6c79d5f9b64dd4fb9467112c4711f69484f9149c`.
- A new, uncached reconnect-safe Device Engine completed two Android discovery cycles and confirmed
  USB Android state, product/codename `popsicle`, and HyperOS `OS4.0.0.32.XPBCNXM`. The final
  privacy-safe passport digest is
  `0d1dc13d75ba5053e39a61090a74102e347657c64d0608a0128bc191cd2ae3cd`.
- The acceptance recorded exactly **104 redacted Guardian operations**: **102 read-only** bounded
  discovery/identity/arrival observations and **2 state-changing reboot commands**. All had
  measurable non-timeout results; the complete active/archive audit chain passed at sequence 181.

### Classification

- **Implemented:** bounded one-time successful-empty product reacquisition and two-identical-source
  observation requirement.
- **Simulated/Tested:** 43 deterministic transition tests on Fedora Linux, including the required
  new adversarial cases.
- **Hardware Verified:** one complete corrected Android → bootloader Fastboot → Android production
  round trip on the same pseudonymous `popsicle`, including two-identical Fastboot source review and
  final uncached reconnect-safe Android identity. The transient-empty reacquisition branch itself
  was not encountered on hardware.
- **Released:** no. Nothing was packaged, signed, installed, published or released.

### Guardian, Recovery and Guided impact

- The correction removes the identified one-read transient dead end without permitting a reboot on
  incomplete identity. Guided may reacquire once silently, then remains truthful and actionable.
- Plan creation, one-use consent, executor revalidation and command dispatch remain separate. The
  reacquisition grants only source-observation evidence.
- UNKNOWN-on-uncertainty, no blind retry, exact-device binding, same-incident attribution,
  independent verification and Guardian-only authority remain unchanged.
- Bootloader locking/relocking remains permanently prohibited and has no valid path.
- No Fresh Live Target, compatibility, source, installation, executor, Recovery or partition
  authority was created.

### Platform, freeze and version gate

- Fedora/Linux: correction implemented and deterministically verified.
- Physical Android: complete corrected round trip and exact final Android return verified on the
  connected Xiaomi 17 Pro Max.
- Windows: not tested or claimed.
- Feature freeze: compliant. This is the minimum Product Assurance-required correctness correction,
  with no new product capability or expanded parser/command surface.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance review and any separately
  approved hardware acceptance.

### Preservation and external actions

- Protected Companion files, Windows launcher work, website, Adaptive work, external firmware and
  unrelated user files were not edited, staged, discarded or committed.
- Physical phone actions after the correction commit: exactly one ADB reboot to bootloader, one
  Fastboot reboot to Android, and bounded allowlisted ADB/Fastboot observations. No dispatch was
  repeated.
- APK action, file transfer, firmware/source action, flash/boot-image/update, partition enumeration
  or read/write, fetch/upload, slot change, erase/wipe/format, unlock/lock/relock, root/debloat,
  signing, publication and release: **none**.
- External action after verification: one normal push of the scoped correction and handoff commits
  to the existing Linux branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance. Do not run another phone command or begin the queued external-package
metadata task until the latest verdict is reviewed.

### Product Assurance Review Requested

- Confirm the one-reacquisition maximum and two-complete-identical observation rule close the
  transient product-read dead end without weakening exact live identity authority.
- Confirm the complete corrected hardware round trip and final uncached Android observation satisfy
  this recovery acceptance while the transient-empty branch remains correctly classified as
  software-tested only.

## Linux hardware checkpoint — Fastboot round trip stopped fail-closed

### Authoritative checkpoint

- Product Assurance authorization/base:
  `46cda9e3780857d7aa33af02926dac0cf1aefa7f` — `Approve popsicle Fastboot identity round trip`.
- Evidence checkpoint:
  `d02d459aae302326d5a5d2cfc29701a8d313887b` — `Record fail-closed Fastboot transition evidence`.
- Final handoff: the follow-up commit containing this exact identifier on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, bounded physical device-mode transition and Fastboot
  identity acceptance.
- Working tree before the attempt: clean and synchronized with the remote branch. The live
  ROMVERSE UI session was confirmed closed before the transition service started.

### Exact measured result

- The production reconnect-safe Device Engine first re-established exactly one authorized USB ADB
  `popsicle` target and matched its sealed pseudonymous identity.
- `LocalDeviceTransitionService` created a one-use, tool-hash-bound Android-to-bootloader plan and,
  under the creator's exact consent recorded by Product Assurance, sent one ADB
  `reboot bootloader` command. The command returned success and the bounded arrival observer
  durably verified the same pseudonymous `popsicle` target in bootloader Fastboot.
- Transition journal `7f76f05f75eb4776b67c7d8b75518823.json` is `completed`, with
  `command_completed=true`, `arrival_verified=true`, `phone_state_uncertain=false`, and sealed
  digest `03d2b5201e8d9fbd92536ae7dd7139eb3d6e755da22557dde8a718dc4fe7d5b0`.
- One production `DeviceEngine.scan()` Fastboot observation then found no simultaneous ADB target,
  exactly one Fastboot target, product/codename `popsicle`, and bootloader rather than Fastbootd.
  It invoked only the fixed `product`, `current-slot`, `unlocked`, `secure`, and `is-userspace`
  variables. Product and bootloader mode were established; slot, unlock and secure values remained
  explicitly unconfirmed because the transport did not return parseable values for those fields.
- The Fastboot observation was persisted through the existing privacy-safe Device Intelligence
  store under the same pseudonymous key `ad74e54831f21bf55d75`, record digest
  `b75b42f09e7ba5a46633a00f684ac08e2817a4d35c9c583799f85fd33cd419d7`, and exact literal-product
  Pack match `xiaomi.popsicle.hyperos4.os4.0.0.23`.
- Before the authorized return command, `LocalDeviceTransitionService.inspect()` correctly
  re-observed the source transport. Fastboot discovery still returned success, but its immediately
  following exact `getvar product` result contained no value parseable by the transition contract.
  The service therefore rejected the return plan with: `The selected phone is no longer in its
  reviewed mode. Refresh devices and try again.`
- No return plan, return consent or Fastboot reboot command was created. In accordance with the
  no-blind-retry rule, Build issued no retry, alternative reboot or further device command. The last
  verified phone state is bootloader Fastboot; its state after the rejected revalidation was not
  guessed.

### Focused acceptance evidence

- **1/1 bounded physical round-trip acceptance attempted; 0/1 completed.** The Android-to-Fastboot
  half and fixed identity scan passed; the Fastboot-to-Android half was rejected before command
  dispatch. This is a truthful partial hardware result, not a completed round trip.
- The attempt produced exactly **75 redacted Guardian records**: **74 read-only observations** and
  **1 state-changing reboot**. Every recorded command was within the authorized transition or fixed
  identity surface and returned a measurable result; no timeout or runner exception occurred.
- The fixed production Fastboot identity scan itself used exactly **7/7 read-only operations**:
  one ADB discovery, one Fastboot discovery and the five approved `getvar` values.
- The complete active/archive Guardian chain passed strict verification at active sequence 77.
- No broad, overlapping or package test suite was run. The 11.8 GB firmware was not rehashed.

### Classification

- **Implemented:** no application code changed. Existing Device Engine, Local Device Transition,
  Device Intelligence and Guardian audit paths were exercised unchanged.
- **Simulated/Tested:** none claimed; this was a real physical target.
- **Hardware Verified:** Android-to-bootloader arrival and one fixed Fastboot identity observation
  are verified for this phone. Fastboot-to-Android return and a complete round trip are **not**
  hardware verified.
- **Released:** no. Nothing was signed, published, installed or released.

### Blocker and Product Assurance impact

- **New blocker:** the return transition cannot currently earn a fresh source-mode plan because a
  Fastboot product probe that immediately followed a successful fixed Device Engine scan returned
  no parseable product value. Product Assurance should determine whether this is expected transient
  transport behavior requiring a bounded non-dispatching observation strategy, a parser/protocol
  mismatch, or an external phone/tool condition. Build must not fix or retry it under this stopped
  hardware authorization.
- Guided impact: the phone can remain at the bootloader screen after the safe rejection. Guided
  needs a truthful recovery instruction and must never loop or silently retry a reboot command.
- Guardian correctly prevented the second mode change when fresh identity authority could not be
  re-earned. Historical/pseudonymous identity did not substitute for the missing live product fact.
- The result is not an execution `UNKNOWN`: the only dispatched reboot command completed and its
  requested bootloader arrival was verified. The proposed return command never reached INTENT or
  dispatch. The phone's later current mode is operationally unconfirmed until reassessed.
- No Fresh Live Target receipt, source compatibility, plan consent, executor admission, Recovery
  incident, adapter action, partition evidence or flash authority was created.
- Permanent no-relock, exact-device binding, consent separation, UNKNOWN-on-uncertainty, no blind
  retry and independent verification remain preserved.

### Platform, freeze and version gate

- Fedora/Linux: partial real hardware verification as stated above.
- Windows: not tested or claimed.
- Feature freeze: compliant. This is an evidence-only acceptance attempt with no new feature,
  product code, route, Device Pack, adapter or execution capability.
- v0.2 Golden Foundation remains **CLOSED**. The incomplete return and identified transition
  revalidation blocker require Product Assurance review before further device work.

### Preservation and external actions

- Protected Companion files, Windows launcher work, website, Adaptive work, external firmware and
  unrelated user files were not edited, staged, discarded or committed.
- Physical phone action: one ADB reboot to bootloader plus bounded read-only ADB/Fastboot identity
  and arrival observations.
- Fastboot reboot to Android: **not dispatched**. Retry or alternative reboot: **none**.
- Flash, boot image, partition enumeration/read/write, fetch/upload, slot change, erase/wipe/format,
  unlock/lock/relock, APK action, root/debloat, source authority, signing, publication and release:
  **none**.
- External action after documentation: one normal push of this evidence handoff to the existing
  Linux branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance. Do not issue another device command or begin the queued external-package
metadata task until the latest verdict is reviewed. If the user needs the phone immediately, use a
manual hardware-button reboot rather than an unreviewed host-side retry.

### Product Assurance Review Requested

- Review why the transition service's fresh Fastboot product observation became unparseable after
  the immediately preceding production Device Engine identity scan succeeded.
- Define the minimum safe reassessment/recovery path for returning this exact phone to Android
  without converting a missing live fact into guessed authority or a blind retry.

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

## Refreshed Windows alpha artifact — packaged UI journey incomplete; Product Assurance review requested

- Product Assurance authorization:
  `f75b9f6db9e9aec06df1918495d9153f049fa27a`, approving Windows checkpoint `88f0b160`.
- Approved source/build base: `f75b9f6db9e9aec06df1918495d9153f049fa27a`.
- Branch: `windows-launcher-authorized-work`.
- Status: exactly one refreshed unsigned Windows `0.2.0-alpha.1` internal-development build and
  one canonical ZIP were produced and structurally verified. Packaged startup, clean shutdown and
  one restart pass, but the required interactive packaged Guided journey is **INCOMPLETE** because
  the host's trusted Windows app-control RPC service is not configured. No alternate keystroke/UI
  automation was used, and no runtime presentation claim is invented. Stop for Product Assurance.

### Exactly one refreshed unsigned build

- Command, run exactly once:
  `.venv\\Scripts\\python.exe scripts\\build_desktop_executable.py --output-directory build\\windows-alpha-0.2.0-alpha.1-signing-preparation --work-directory build\\windows-alpha-0.2.0-alpha.1-signing-preparation-pyinstaller`
- Result: **PASS** with PyInstaller `6.22.2`, Python `3.12.10`, and
  `Windows-11-10.0.26200-SP0`.
- Executable:
  `build/windows-alpha-0.2.0-alpha.1-signing-preparation/ROMVERSE/ROMVERSE.exe`.
- Executable size: `6,285,439` bytes.
- Executable SHA-256:
  `84eb54a8934e982a6660c6f09f5a65517e94934384fc7f4858546404eb7a7194`.
- Authenticode: **NotSigned**, as required for this internal-development checkpoint.
- No rebuild was performed.

### Exactly one canonical bundle

- Command, run exactly once:
  `.venv\\Scripts\\python.exe scripts\\package_desktop_bundle.py build\\windows-alpha-0.2.0-alpha.1-signing-preparation\\ROMVERSE --platform windows-x86_64 --output dist\\ROMVERSE-Desktop-0.2.0-alpha.1-windows-x86_64.zip`
- ZIP:
  `dist/ROMVERSE-Desktop-0.2.0-alpha.1-windows-x86_64.zip`.
- ZIP size: `73,469,641` bytes.
- ZIP SHA-256:
  `bdf144fb716a6193a5d9a910a244c8d9363b66731c43c61dd7827efd3b04cc8a`.
- Safe archive verification: **PASS** — 305 unique regular-file members, `164,609,774`
  expanded bytes, exactly one expected `ROMVERSE/ROMVERSE.exe`, successful CRC validation, and no
  link, absolute, duplicate, parent-traversal, directory, oversized, or missing-executable member.
- The archive was verified again before extraction. The extracted executable has the same SHA-256
  and remains `NotSigned`.

### Bounded no-phone packaged evidence

- Disposable root:
  `C:\\Work\\ROMVERSE-Windows-Packaged-Journey-f75b9f6d`.
- The extracted packaged executable launched successfully, remained responsive, and displayed the
  native top-level title `Welcome to ROMVERSE` on the first fresh launch.
- The installed Computer Use client was initialized as required, but its trusted RPC service
  returned `Trusted RPC service is not configured: sky`. Native app input was therefore unavailable.
  The onboarding window was closed through its normal window-close request and exited cleanly.
- No substitute SendKeys, guessed coordinates, direct PowerShell UI Automation, accessibility
  injection, or unobserved click was attempted.
- The packaged `--skip-onboarding --release-smoke` lifecycle then initialized the disposable
  workspace and closed cleanly. One normal restart against the same workspace returned exit code
  `0`; the runtime log records exactly two starts and two clean closes.
- Durable restart evidence: seven workspace files before and after, with workspace-manifest SHA-256
  unchanged at `74f2c14de0e18ec9b3c5218ad47908647354b622ce3971fe782f6201cd0158f9`.
- Packaged startup/shutdown/restart: **PASS**.
- Interactive Guided entry, Command Deck, Platform Tools remediation presentation, one offline
  Knowledge/Device DNA lookup, and candidate/signing-preparation presentation: **NOT EXECUTED**.
  Their accepted source evidence was not repeated and is not relabeled as packaged evidence.
- No concrete ROMVERSE runtime or Guided defect was established, so no product correction or
  second build is justified.

### Precise next proposed action

Enable or restore the trusted Windows app-control RPC service, then run exactly one bounded
interactive journey against this already built and verified artifact in a new disposable no-phone
workspace. Do not rebuild or repackage. Exercise only the five approved visible checkpoints and one
clean restart; if they pass, append the evidence-only handoff and return for review. If a concrete
ROMVERSE defect appears, apply only its minimum freeze-safe fix with one focused regression and use
the single conditionally authorized rebuild.

### Scope and safety handoff

- The pre-existing untracked patch
  `0001-Preserve-local-build-completion-across-restart.patch` remains unchanged, unstaged and
  uncommitted. Protected Companion files remain clean and untouched.
- No phone/emulator was present, requested, awaited, connected, selected, or targeted. No
  ADB/Fastboot device command, system-wide installation, consent/admission, Guardian execution,
  Recovery, real signing, production trust, publication, release, destructive action, force-push,
  unlock, lock, or relock occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze, and permanent no-relock remain preserved.
- Stop for independent Product Assurance review of the verified artifact and explicit packaged-UI
  evidence limitation.

## Windows same-file identity portability correction — Product Assurance review requested

- Product Assurance correction authorization:
  `c4adb738b5daddcc82dd5388ff8270901f2fa3f2`, reviewing Windows handoff `3bd3d074`.
- Correction commit: `7b79a4b077bf62ae1b2c669b1ed631f18d282696`.
- Branch: `windows-launcher-authorized-work`.
- Status: the exact Windows-only same-file identity portability correction is implemented. All 24
  previously failing nodes and all five new focused Windows regressions pass; stop for independent
  Product Assurance review.

### Minimum correction

- `candidate_avb._fingerprint()` and Guardian private-staging `_file_identity()` now compare the
  Windows-stable descriptor/path fields: device/file identity, inode/file index, size and
  modification time.
- Other platforms retain the existing `st_ctime_ns` comparison in addition to those fields.
- Fresh content hashing, descriptor-before/after comparison, path containment, no-follow/symlink
  rejection, expected path/receipt binding, size validation and replacement detection remain in
  place and unchanged.
- `tests/test_windows_same_file_identity.py` adds five Windows nodes proving both affected helpers
  accept only a descriptor/path ctime difference, both reject a changed file identity even when
  size and mtime are preserved, and fresh hashing exposes same-size byte drift after mtime restore.

### Exact Windows verification

- New regression command:
  `.venv\\Scripts\\python.exe -m pytest -q tests/test_windows_same_file_identity.py --basetemp C:\\rvpt-file-identity-new`
- New regression result: **5/5 passed**.
- Previously failing-node rerun: the exact 24 node IDs recorded by the decisive
  `3bd3d074` handoff were rerun with `--basetemp C:\\rvpt-file-identity-24`.
- Previously failing-node result: **24/24 passed**. This includes the no-phone production dialog,
  candidate AVB preparation/reconstruction/drift cases and Guardian final-byte private staging.
- The 95 previously passing nodes were not repeated.
- Ruff command:
  `.venv\\Scripts\\python.exe -m ruff check src/romverse/rom/candidate_avb.py src/romverse/guardian/source_installation.py tests/test_windows_same_file_identity.py`
- Ruff result: **PASS — all checks passed**.
- Whitespace command: `git diff --check` before the correction commit.
- Whitespace result: **PASS**.

### Scope and safety handoff

- Only the two authorized identity helpers, one focused Windows regression file and this Build
  handoff changed after Product Assurance commit `c4adb738`.
- The pre-existing untracked patch
  `0001-Preserve-local-build-completion-across-restart.patch` remains unchanged, unstaged and
  uncommitted. Protected Companion files remain clean and untouched.
- No Windows executable or package was rebuilt or launched. No phone/emulator was present,
  requested, awaited, connected, selected, or targeted. No ADB/Fastboot device command, Recovery,
  installation, real signing, production trust, publication, release, destructive action,
  force-push, unlock, lock, or relock occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze, and permanent no-relock remain preserved.
- Stop for independent Product Assurance review. Do not rebuild the Windows artifact or begin
  another synchronization, simulation, hardware, packaging, or product slice before a matching
  verdict.

## Batched signing/preparation source convergence — Product Assurance review requested

- Windows Product Assurance authorization: `88c8edf2351ab35bc96d70deab1c9ea263d575fe`,
  approving Windows checkpoint `5e4a43fb` and authorizing this batch only after Linux approval of
  final signed-byte binding.
- Gate-clearing Linux Product Assurance approval:
  `9ca297b4ad048fee89bb7686128f40d35b441456` for checkpoint `44db4a6` and implementation
  `b1748036`.
- Windows base: `88c8edf2351ab35bc96d70deab1c9ea263d575fe`.
- Branch: `windows-launcher-authorized-work`.
- Status: the four approved platform-neutral source/test commits are synchronized exactly. Ruff
  and whitespace pass, but the focused Windows regression exposes two pre-existing Windows file-
  identity portability false positives. No source correction was attempted outside the authorized
  synchronization batch; stop for Product Assurance.

### Exact synchronized commits

- Linux `14de58e376bbd5cf14369f605bdfd6355f892cca` became Windows
  `fa088e620431910f4d758a198e3d4e2d546dcc0f` — unsigned AVB
  completion stops at the offline-signing boundary. Stable patch ID:
  `2d965c2d09d6596bdc8f85742e0d9e49cd1030e3` on both commits.
- Linux `5319ee61f0324b0bb4d1c45e178b308defbced90` became Windows
  `7efceb04fd76186eaa18ea6733b9c1305cf23438` — signing-ready state remains truthful across reload.
  Stable patch ID: `d23dfda47b4004a35ba69c3f8e7614a30d47aeed` on both commits.
- Linux `4a4c61c027790954655e584a07d38ed54650dcf6` became Windows
  `f7340b74acdf30b67c115c4fc27e2da488fcfeab` — exact candidate
  preparation remains stable across reconstruction. Stable patch ID:
  `4b15474c879a2bd724da9ea8481ab5c1ac8b4a6c` on both commits.
- Linux `b174803639e0d5a5d2aa6c3be470e03d691eba53` became Windows
  `6d15156e6a98225525f6403bd1fc0da81ac6f528` — candidate preparation binds the final signed
  installation bytes and receipts. Stable patch ID:
  `04082da0ddb24e2ffa2a3007fea221711947c81d` on both commits.
- No Linux handoff/assurance documentation, Adaptive Online Device DNA work, unrelated Linux
  history, or conflict adaptation was copied. Windows launcher, ACL, packaging and toolchain source
  was not changed.

### Focused Windows regression

- First affected-module command:
  `.venv\\Scripts\\python.exe -m pytest -q tests/test_build_control_ui.py tests/test_candidate_installation.py tests/test_candidate_installation_desktop.py tests/test_candidate_installation_history.py tests/test_candidate_installation_integration.py tests/test_candidate_installation_ui.py tests/test_guardian_candidate_installation.py --basetemp build\\pytest-signing-preparation-sync-20260908`
- First result: **97 passed, 47 failed, 17 errors**. The repository-local temporary path made the
  deepest Windows fixture paths exceed the host's effective path limit, so this run was not used as
  the decisive product result.
- Decisive short-path command:
  `.venv\\Scripts\\python.exe -m pytest -q tests/test_build_control_ui.py::test_reopened_signing_ready_candidate_stays_distinct_from_install_and_flash tests/test_build_control_ui.py::test_unsigned_avb_completion_stops_autopilot_at_offline_signing_boundary tests/test_candidate_installation.py tests/test_candidate_installation_desktop.py tests/test_candidate_installation_history.py tests/test_candidate_installation_integration.py tests/test_candidate_installation_ui.py tests/test_guardian_candidate_installation.py --basetemp C:\\rvpt-9ca297b4-win`
- Decisive result: **95 passed, 24 failed** across 119 focused nodes. The two synchronized
  Build-Control regressions pass. All 24 failures fail closed before any consequential action.
- Failure grouping:
  - **22 failures** in the production candidate AVB/integration/desktop path report an unchanged
    archive or AVB input as changed. On this Windows host, the same unchanged file produced equal
    device/inode/size/mtime values but different `st_ctime_ns` values between `os.fstat()` and
    `Path.stat()`. `candidate_avb._fingerprint()` currently compares those tuples directly.
  - **2 failures** in Guardian private staging reject unchanged rebuilt images for the same
    descriptor-versus-path `st_ctime_ns` mismatch in `_file_identity()`.
  - No failure advanced signing, installation, Guardian admission, device execution or Recovery;
    the behavior remained fail closed.
- Ruff command:
  `.venv\\Scripts\\python.exe -m ruff check src/romverse/guardian/source_installation.py src/romverse/rom/candidate_installation.py src/romverse/ui/build_control.py src/romverse/ui/source_installation.py tests/test_build_control_ui.py tests/test_candidate_installation.py tests/test_candidate_installation_desktop.py tests/test_candidate_installation_history.py tests/test_candidate_installation_integration.py tests/test_candidate_installation_ui.py tests/test_guardian_candidate_installation.py`
- Ruff result: **PASS — all checks passed**.
- Whitespace command: `git diff --check 88c8edf2..6d15156e`.
- Whitespace result: **PASS**.

### Precise proposed correction

Product Assurance should authorize one minimum Windows portability correction to make the candidate
AVB and Guardian snapshot same-file checks compare a stable descriptor/path identity on Windows
without removing size/mtime, fresh hash, containment, no-follow, or replacement checks. Add focused
Windows regressions proving an unchanged file is accepted while path replacement and byte drift
remain rejected, rerun only the 24 failed nodes plus Ruff/whitespace, then return for review. Do not
repeat the 95 already-passing nodes unless the correction's affected set requires them.

### Scope and safety handoff

- The pre-existing untracked patch
  `0001-Preserve-local-build-completion-across-restart.patch` remains unchanged, unstaged and
  uncommitted. Protected Companion files remain clean and untouched.
- No Windows executable or package was rebuilt or launched. No phone/emulator was present,
  requested, awaited, connected, selected, or targeted. No ADB/Fastboot device command, Recovery,
  installation, real signing, production trust, publication, release, destructive action,
  force-push, unlock, lock, or relock occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze, and permanent no-relock remain preserved.
- Stop for independent Product Assurance review before correcting the Windows portability defect or
  beginning any build, packaging, simulation, hardware, or product slice.

## Durable local-build completion synchronization — Product Assurance review requested

- Product Assurance authorization: Linux `a6d9bca06d35c4f0ca8b84ad6ebd990be7e5700a`.
- Approved upstream correction: Linux `b77ee3c03aac1746a8e8f18acd370ddcb3094360`.
- Windows synchronization commit: `f5521c4a`.
- Windows base checkpoint: `14d3739d6e833a18fb9662f56684e548eaf64164`.
- Branch: `windows-launcher-authorized-work`.
- Status: the single approved cross-platform correction is synchronized and focused-verified;
  no Windows executable or package was rebuilt.

### Exact synchronized scope

- `src/romverse/ui/build_control.py` now preserves a reopened unsigned local candidate as
  `LOCAL BUILD COMPLETE / INSTALL NOT AUTHORIZED` and routes its primary action to artifact
  verification rather than installation review.
- `tests/test_build_control_ui.py` adds the approved completed-but-unsigned focused regression.
- The two-file source/test patch was applied directly from the approved upstream commit without
  Linux documentation history, unrelated Linux commits, conflict adaptation, or branch rewriting.
- The pre-existing untracked local file
  `0001-Preserve-local-build-completion-across-restart.patch` was preserved unchanged and was not
  staged or committed.

### Exact focused Windows verification

- Command:
  `.venv\\Scripts\\python.exe -m pytest tests/test_build_control_ui.py::test_reopened_unsigned_local_candidate_remains_complete_and_routes_to_artifact_verification -q --basetemp build\\pytest-local-build-sync-20260908`
- Result: **1/1 passed** on Windows.
- Lint command:
  `.venv\\Scripts\\python.exe -m ruff check src/romverse/ui/build_control.py tests/test_build_control_ui.py`
- Lint result: **PASS — all checks passed**.
- Whitespace command: `git diff --check 14d3739d..f5521c4a`.
- Whitespace result: **PASS**.
- No broad suite, repeated journey, executable launch, artifact rebuild, package build, or signing
  operation was performed.

### Scope and safety handoff

- Protected Companion files remain clean and untouched. The previously approved Windows alpha
  artifact was not rebuilt or modified.
- No phone or emulator was present, requested, awaited, connected, selected, or targeted. No ADB,
  Fastboot, Recovery, Guardian execution, installation, production trust, signing, publication,
  release, destructive action, force-push, unlock, lock, or relock occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze, and permanent no-relock remain preserved.
- Stop for independent Product Assurance review before another Windows synchronization, build,
  package, simulation, hardware, or product slice.

## Windows Command Deck truthfulness convergence — Product Assurance review requested

- Product Assurance authorization: Linux `292cd09`.
- Approved upstream correction: Linux `64ad510532a18b5e26a6feec46791069aee0e8ec`.
- Windows synchronization commit: `0f64dd3b`.
- Branch: `windows-launcher-authorized-work`.
- Status: exact source correction synchronized and focused-verified; no artifact rebuild performed.

### Exact result

- `DeviceCenter` now uses the evidence-neutral subtitle `Current device, project, and
  evidence-derived next action at a glance.` instead of claiming one live device and one active
  project before either exists.
- Only `src/romverse/ui/device_center.py` and its focused dashboard regression changed. No conflict
  resolution, Windows adaptation, Linux handoff history or unrelated source was included.
- Focused Windows test: **1/1 passed**.
- Ruff: **PASS** for the changed source/test files.
- Git whitespace check: **PASS**.
- The approved Windows alpha artifact at `ab0f299` was not rebuilt or retested. It remains valid for
  its recorded onboarding evidence but predates this subtitle correction, which is intentionally
  deferred to the next batched artifact refresh.

### Scope and safety

- No phone/emulator, device-scoped ADB/Fastboot, Recovery, Companion change, system installation,
  signing, publication, release, force-push, lock or relock occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze and permanent no-relock remain preserved.

## Product Assurance Review Requested

Confirm the exact source convergence and focused Windows result. Do not authorize another immediate
artifact rebuild solely for this text correction; include it in the next normal cross-platform
artifact batch.

## Refreshed Windows v0.2.0-alpha.1 Guided onboarding — Product Assurance review requested

- Product Assurance authorization: Linux assurance commit `b59c3d8`.
- Approved upstream onboarding implementation: Linux `eaa3d615912a4eefddd44ee3b032562047ddadc3`.
- Windows synchronization commit: `74064de`.
- Branch: `windows-launcher-authorized-work`.
- Status: the approved source correction is synchronized, focused-tested and included in exactly
  one refreshed unsigned Windows alpha executable and canonical ZIP. Stop for independent Product
  Assurance.

### Exact synchronization and focused verification

- Only `src/romverse/app.py`, `src/romverse/ui/setup_wizard.py` and
  `tests/test_app_launch_settings.py` changed. The applied patch is the approved Linux onboarding
  patch; no Linux handoff/assurance history, Companion source or unrelated branch history was
  copied or merged.
- Focused `tests/test_app_launch_settings.py`: **5/5 passed** on Windows.
- Ruff for the three changed files: **PASS**.
- Git whitespace check: **PASS**.
- No broad suite, full Guided ROM journey or Recovery test was run.

### Refreshed unsigned Windows alpha

- Build command, run exactly once:
  `.venv\\Scripts\\python.exe scripts\\build_desktop_executable.py --output-directory
  build\\windows-alpha-0.2.0-alpha.1-guided --work-directory
  build\\windows-alpha-0.2.0-alpha.1-guided-pyinstaller`.
- Executable:
  `build/windows-alpha-0.2.0-alpha.1-guided/ROMVERSE/ROMVERSE.exe`.
- Executable size: `6,281,239` bytes.
- Executable SHA-256:
  `7ee304d55731fa6ca291f8e9d780246642e37c79c6331ce3ba8ee6718a1532c1`.
- Authenticode: `NotSigned`, as required for this internal checkpoint.
- Canonical ZIP: `dist/ROMVERSE-Desktop-0.2.0-alpha.1-windows-x86_64.zip`.
- ZIP size: `72,689,076` bytes.
- ZIP SHA-256:
  `17eb961d8022d0b0774bb1cc616b9a9746961c0805552d4210430df39069b863`.
- Archive tree: **PASS** — 262 entries, 162,253,374 expanded bytes, expected
  `ROMVERSE/ROMVERSE.exe` present and no absolute or parent-traversal member found.

### Bounded first-run evidence

- The executable was launched once with a fresh dedicated `ROMVERSE_HOME` and a host path containing
  no ADB/Fastboot. After five seconds it remained alive and responsive at the unapplied first-run
  boundary, then the harness terminated it. No onboarding completion settings or device operation
  were created.
- Because a process launched through the SSH service has no interactive desktop UI Automation
  surface, no visible-widget claim is made from that packaged process. Instead, the built
  PyInstaller payload was independently inspected and contains all four required corrected strings:
  `INTERNAL DEVELOPMENT`, `Continue in Guided Mode`, `No phone is required during setup`, and the
  accessible action `Choose Guided Mode and open Command Deck`.
- The focused production-widget test supplies the exact corrected interaction evidence: Guided is
  selected and carried forward, Command Deck opens, the Platform Tools route opens with managed
  auto-start disabled, and the state remains no-engine/no-device.

### Scope, safety and release truthfulness

- This refresh replaces the stale canonical Windows alpha ZIP with the artifact containing the
  approved onboarding correction. The earlier artifact remains historical evidence only.
- No phone/emulator, device-scoped ADB/Fastboot, managed download, Recovery, Companion change,
  driver/firewall/global PATH change, production signing/trust, publication, release, force-push,
  lock or relock occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze and permanent no-relock remain preserved.

### Gate status

- Windows v0.2.0-alpha.1 onboarding-corrected artifact: **IMPLEMENTED AND REVIEW REQUESTED**.
- Fedora matching refresh: proceeding independently on its authorized Linux branch.
- Public release, production signing/trust and physical Recovery: **NOT AUTHORIZED**.

## Product Assurance Review Requested

Review the exact source synchronization, focused 5-case result, executable/ZIP hashes and split
packaged/source-level first-run evidence. Confirm or correct the refreshed Windows internal alpha
before further Windows product work.

## Consolidated Windows v0.2.0-alpha.1 development build — Product Assurance review requested

- Product Assurance authorization: `018d07cbae87f4afb472ca8abff8ddaf6d636c15`.
- Windows base: `06e9deaf31b0d061543e2a9b20ea2fecf806ff91`.
- Approved synchronized implementation commits:
  - `fc11d38` — durable exact local-build resume, from Linux `3475b45`;
  - `3654646` — pre-intent stop and log binding, from Linux `dcd73cc`;
  - `ae2c91b` — `0.2.0a1` package / `0.2.0-alpha.1` desktop identity, from Linux `07b5b17`;
  - `dd1572d` — alpha release-version ordering, from Linux `9e6762a`.
- Windows portability correction: `a5527a0`.
- Branch: `windows-launcher-authorized-work`.
- Status: one consolidated unsigned Windows alpha development build and one matching ZIP are
  complete, focused-tested and no-device smoke-verified. Stop for independent Product Assurance.

### Exact synchronization and Windows correction

- The four approved platform-neutral commits were applied in their required order without merging
  Linux handoff/assurance history. The Fedora-only development guide remained absent from the
  Windows branch; the existing Windows PyInstaller path-sanitization test was retained alongside the
  new alpha identity test.
- The first focused Windows run exposed two genuine portability issues in the synchronized local-
  build coverage. POSIX mode bits were not a valid Windows privacy assertion, and the toolchain
  snapshot's redundant 106-character staging component could exceed the ordinary Windows path
  limit in a realistic nested project workspace.
- `a5527a0` replaces only those assumptions: local-build attempt/final receipts now use the already
  approved Windows owner-only ACL verifier in the test, slash-independent versioned-tool path
  matching is retained, and the unpublished staging directory is shortened to a UUID-based
  `.stage-*` name. The final slot still binds the full approved SHA-256, and the receipt/hash/source
  checks are unchanged.

### Focused Windows verification

- Final affected selection: **48/48 passed** across local-build contract/resume, cooperative
  shutdown, durable schema inventory, reopened Forge resume/UNKNOWN presentation, desktop bundle /
  visible alpha identity and release-version ordering.
- Ruff checks: **PASS** for all synchronized and corrected source/test files.
- Git whitespace check: **PASS**.
- Earlier runs were not counted: the first found the two corrected portability issues; one harness
  invocation used a missing temporary parent; a later single failure identified the literal-slash
  test assumption. No broad suite or duplicate Guided journey was run.

### Windows alpha artifact

- Classification: **unsigned internal development artifact only**; not published or released.
- Executable:
  `build/windows-alpha-0.2.0-alpha.1/ROMVERSE/ROMVERSE.exe`.
- Executable size: `6,280,733` bytes.
- Executable SHA-256:
  `bcd30985ca8590e323039ea3e037cbb382d6147b2a63f3e592d5b9233e13aa60`.
- Authenticode: `NotSigned`, as required for this checkpoint.
- ZIP: `dist/ROMVERSE-Desktop-0.2.0-alpha.1-windows-x86_64.zip`.
- ZIP size: `72,428,464` bytes.
- ZIP SHA-256:
  `11aac7b0425417abda5049d26ebbb1c601649dcd49cf111ab7170751abaf9ccd`.
- Exact archive verification: **PASS** — 262 regular files, 162,252,868 expanded bytes, expected
  `ROMVERSE/ROMVERSE.exe` present and safe tree verification completed.
- Fresh frozen startup/no-device smoke: **1/1 passed** with a new disposable workspace, offscreen Qt
  and an executable-search path containing no ADB/Fastboot. No target was discovered or contacted.

### Scope, safety and release truthfulness

- The build contains the approved Windows launcher, digest-pinned Platform Tools acquisition,
  Guided/Forge corrections, durable local-build resume and exact `0.2.0-alpha.1` identity.
- No phone or emulator was present, requested, selected or targeted. No device-scoped ADB/Fastboot,
  Recovery, install, flash, Companion change, driver/firewall/global PATH change, production trust,
  signing, publication, release, force-push, lock or relock occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze and permanent no-relock remain preserved.
- Protected Companion files remain clean and untouched.

### Gate status

- Fedora v0.2.0-alpha.1 internal development build: **VERIFIED at `87af660`**.
- Windows v0.2.0-alpha.1 internal development build: **IMPLEMENTED AND REVIEW REQUESTED**.
- Cross-platform public release, production signing/trust and physical Recovery: **NOT CLAIMED OR
  AUTHORIZED**.

## Product Assurance Review Requested

Review the exact synchronization, `a5527a0` Windows path/ACL portability correction, focused 48-case
result, artifact hashes/tree and frozen no-device smoke. Confirm or correct the Windows internal
alpha milestone before any further rebuild, platform merge, signing, publication, release or
physical-device work.

## Approved platform-neutral Guided/Forge synchronization — Product Assurance review requested

- Product Assurance approval: `a0740bd0d718d82e1c3c649aee86aec1564652e2`.
- Reviewed Windows checkpoint: `61efda1847f2f740eeb5874918c3f2c5fcf2f125`.
- Approved upstream commits, applied in order:
  - `392b21eb90966b09f089ed9b8f3dac29e5fedf8d` — truthful Forge Control pause label;
  - `37e2ee27d9373d90e6a3cd71cb31fcadb64f415b` — refreeze exact source-derived inputs before planning.
- Windows synchronization commits:
  - `ab2c650b6391c4f1f369df712c0d5258452ca5f6` — patch-identical to `392b21e`;
  - `e73f72dd36f975fd504b2f6b2663cc42e3e8f869` — patch-identical to `37e2ee2`.
- Branch: `windows-launcher-authorized-work`.
- Status: the two already approved platform-neutral patches are synchronized without Linux handoff,
  approval, simulation, or unrelated branch history. Focused Windows checks and one inert source-level
  affected segment pass. Stop for independent Product Assurance review.

### Exact synchronized scope

- `src/romverse/ui/guided_mission.py` now names `Forge Control` when automatic Genesis pauses at the
  local build/sign stage; the separate optional install stage still names `Guardian review`.
- `src/romverse/ui/build_control.py` refreezes the deterministic build plan after successful exact
  input preparation has produced the final source-derived tree and before the worker reports
  completion.
- `tests/test_rom_studio_ui.py` and `tests/test_build_control_ui.py` contain the two matching focused
  regressions.
- Stable patch IDs match their approved upstream sources exactly:
  - Guided label: `f0de2e4427782afaa91d1b0d62e5a306f56b560d`;
  - final-tree refreeze: `13bb12c29e7e442ae67f4ccfaf562f5084fb2cac`.
- No conflict resolution or context adaptation was required. No Linux documentation history was
  copied or merged.

### Exact focused Windows verification

- Command:
  `.venv\\Scripts\\python.exe -m pytest tests/test_rom_studio_ui.py::test_genesis_opens_forge_control_as_a_visible_child_and_releases_autopilot tests/test_build_control_ui.py::test_exact_input_worker_refreezes_the_final_source_derived_tree -q --basetemp build\\pytest-platform-neutral-sync-20260908`
- Result: **2/2 passed** on Windows.
- Lint command:
  `.venv\\Scripts\\python.exe -m ruff check src/romverse/ui/guided_mission.py src/romverse/ui/build_control.py tests/test_rom_studio_ui.py tests/test_build_control_ui.py`
- Lint result: **PASS — all checks passed**.
- Whitespace command: `git diff --check a0740bd..e73f72d`.
- Whitespace result: **PASS**.
- No broad suite, unrelated regression, executable rebuild, packaging, or duplicate Guided journey
  was run.

### One source-level no-phone affected segment

- Classification: **SIMULATED**. This is source-level production-UI behavior with an offscreen Qt
  surface, production `GuidedBuildMission`, `RomStudio`, `RebuildMetadataWorker`, project store,
  inspection service, and deterministic planner. It is not executable-artifact, physical-device, or
  production verification.
- Fresh disposable workspace:
  `C:\\Work\\ROMVERSE-Platform-Neutral-Sync-Simulated-20260908`.
- Sanitized 144-byte source SHA-256:
  `71cab237b8afc882b2f45c274d88c56f59ea0f43339bb0c12f6f0d9744ca1cfd`.
- One execution result: **PASS**.
- Observed Guided text:
  `Automatic Genesis paused at Forge Control. Complete its highlighted requirement, then choose Auto-resolve & continue again.`
  The affected build stage did not name Guardian review, and Forge Control was opened as the Guided
  child surface.
- The inert exact-input service added `partition_files/source-derived.input`. The production worker
  refroze the final tree; the reloaded plan contained that exact file and verified successfully.
- Recorded safety result: `phone_changed: false`, `physical_targets: 0`,
  `adb_fastboot_commands: []`, `production_execution_authority: none`, no Guardian authority, no
  Recovery execution, and `bootloader_relock: false`.

### Scope and safety handoff

- The synchronized commits and this handoff are the only Windows-branch changes after `a0740bd`.
  Protected Companion files remain clean and untouched.
- The previously accepted pinned unsigned executable was not rebuilt or launched. No artifact,
  installer, ZIP, APK, production signature, publication, or release was produced.
- No phone or emulator was present, requested, awaited, connected, selected, or targeted. No ADB or
  Fastboot command ran; no device scan, Recovery action, driver/firewall/global PATH change,
  production adapter/trust, destructive action, force-push, unlock, lock, or relock occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze, and permanent no-relock remain intact.
- Stop for independent Product Assurance review. Do not rebuild the Windows executable or begin
  another product, hardware, packaging, signing, or release slice until a matching verdict is
  committed.

## Pinned Windows development build and fresh no-phone readiness — Product Assurance review requested

- Product Assurance approval: `a561c1f5bc5ab370c810a728a28a1a935e34c96f`.
- Approved checkpoint: `6dbe7ef7f3cf0b9afe8c5ad1ccca88a93ea05284`.
- Platform Tools pin implementation: `1908689733771a97dc1ec6e845adc4f169cb943f`.
- Branch: `windows-launcher-authorized-work`.
- Status: exactly one new unsigned Windows development build was produced from the approved source.
  In one fresh disposable workspace, the existing visible Platform Tools setup accepted the approved
  archive digest, reached the truthful ready/no-device Command Deck, and retained that state after
  one normal restart. Stop for independent Product Assurance review.

### Exactly one approved unsigned build

- Exact command, run once:
  `.venv\\Scripts\\python.exe scripts\\build_desktop_executable.py --output-directory build\\windows-dev-platform-tools-pin --work-directory build\\windows-dev-platform-tools-pin-pyinstaller`
- Result: successful with PyInstaller `6.22.2`, Python `3.12.10`, and
  `Windows-11-10.0.26200-SP0` on Windows 11 Home 64-bit.
- Executable:
  `build/windows-dev-platform-tools-pin/ROMVERSE/ROMVERSE.exe`.
- Size: `6,269,143` bytes.
- SHA-256: `dded5c0daa92a280349e931e7138cb2d63113ef2f9f94327a6c29fe03010c22b`.
- Authenticode status: `NotSigned`, as required for this development-only checkpoint.
- No second build, installer, ZIP, APK, signature, publication, or release was produced.

### One fresh visible Platform Tools setup

- Fresh workspace, confirmed absent before first launch:
  `C:\\Work\\ROMVERSE-Platform-Tools-Pin-Fresh-20260908`.
- Both launches used the new executable with:
  `--workspace C:\\Work\\ROMVERSE-Platform-Tools-Pin-Fresh-20260908 --skip-onboarding`.
- The first launch truthfully showed `Device Engine needs attention` and
  `Resolve Platform Tools`. The visible setup was opened exactly once and selected only the existing
  ROMVERSE-managed ADB / Windows Platform Tools requirement.
- ROMVERSE reported:
  `Downloaded and prepared: platform-tools (45f4d63113e8…) ROMVERSE refreshed the tool inventory automatically.`
- The retained managed receipt binds the exact official source
  `https://dl.google.com/android/repository/platform-tools-latest-windows.zip` to archive size
  `8,044,989` bytes and SHA-256
  `45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99`.
- The installed package reports `Pkg.Revision=37.0.1`. The exact workspace-local component hashes
  are:
  - `adb.exe`: `b4a6b455702684652cccf7b46258b29e653538904359a58fd4931cf3ef286b3f`;
  - `fastboot.exe`: `b2d9cbff4ce9ae7eb448cfc831bafc867935f50f5be38f8f81057fd7eb3b8d86`.
- Closing setup performed only the approved workspace-local host verification before the Command
  Deck changed to `Connect your Android device`, `No Android device detected`, and
  `No device connected`. No `Scan for device` or other device control was selected.

### One normal restart and truthful retained state

- ROMVERSE closed cleanly after the first ready state. Process inspection confirmed no remaining
  `ROMVERSE.exe` before the one restart.
- The same executable and workspace were launched exactly once more. The restarted Command Deck
  again showed `Connect your Android device`, `No Android device detected`, `No device connected`,
  and `No Android transport is visible` without reopening setup or redownloading the archive.
- ROMVERSE then closed cleanly again. `logs/crash/runtime-fault.log` records two starts and two clean
  closes with no runtime fault.
- The no-phone readiness route generated only bounded, read-only, host-targeted empty inventory
  records: three `adb devices -l` and eight `fastboot devices -l` checks. All returned without a
  device target; the audit contains zero non-host targets and zero non-read-only operations.

### Verification reuse, scope, and safety

- Per the approved bounded task, no test suite was rerun. Product Assurance approval `a561c1f`
  already records the accepted focused result of **36/36 passed**, Ruff success, and whitespace
  success for the exact pinned source at checkpoint `6dbe7ef`.
- This checkpoint changes only this Build handoff. Protected Companion files remain clean and
  untouched; no application, Guardian, Device Engine, Recovery, launcher, test, or release source
  changed.
- No phone or emulator was present, requested, awaited, connected, selected, or targeted. No
  device-scoped ADB/Fastboot, Recovery, APK installation, production adapter/trust, driver,
  firewall, global PATH, signing, publication, release, force-push, destructive action, blind retry,
  unlock, lock, or relock occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty,
  independent verification, feature freeze, and permanent no-relock remain intact.
- Stop for independent Product Assurance review. Do not begin another correction, product slice,
  hardware task, packaging task, or release activity until an exact matching verdict is committed.

## Windows Platform Tools 37.0.1 archive pin — Product Assurance review requested

- Product Assurance approval: `08826543ace12b621828f86e74877dcdd20e8e0c`
- Approved checkpoint: `894f588d0e488654332e9feb088b943293b44428`
- Implementation commit: `1908689733771a97dc1ec6e845adc4f169cb943f`
- Branch: `windows-launcher-authorized-work`
- Status: the exact approved Windows Platform Tools 37.0.1 archive pin is implemented and focused-
  tested. The existing ready workspace remains accepted without receipt changes or redownload. Stop
  for independent Product Assurance review.

### Exact bounded correction

- Official Windows source retained exactly:
  `https://dl.google.com/android/repository/platform-tools-latest-windows.zip`.
- Approved version: `37.0.1`.
- Approved archive SHA-256:
  `45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99`.
- `install_official_archive` binds that source to the approved digest internally. A caller may omit
  the digest or supply the same approved value, but cannot substitute another purported pin.
- The complete bounded download is hashed and compared before ZIP parsing, staging-directory
  creation, extraction, receipt publication, or replacement of the previous managed package.
- A mismatch fails with the actionable message that Windows Platform Tools 37.0.1 did not match the
  approved SHA-256 and a ROMVERSE pin update is required. It does not learn or approve the observed
  digest.
- The production worker passes the same explicit approved digest for Windows. Linux behavior remains
  unchanged and does not inherit the Windows pin.
- The production receipt verifier independently requires the exact same digest whenever the receipt
  names the official Windows Platform Tools source. A self-recorded different digest cannot activate.
- Existing canonical/legacy path handling, source/schema/size bounds, exact file set, per-file hashes,
  containment, regular-file, no-link/no-junction, and idempotent workspace-local PATH gates remain.

### Focused Windows verification

- Exact final command:
  `.venv\\Scripts\\python.exe -m pytest tests/test_toolchain_download.py tests/test_toolchain_progress.py::test_forge_arsenal_unknown_length_download_stays_indeterminate tests/test_toolchain_progress.py::test_forge_arsenal_worker_pins_windows_platform_tools -q --basetemp build/pytest-platform-tools-pin-20260908-final`
- Result: **36/36 passed** on Windows 11 x64 / Python 3.12.10.
- Correct-digest coverage proves the bounded archive reaches the existing extraction, receipt, and
  activation gates only when it matches its approved digest.
- Wrong-digest coverage proves failure occurs before extraction/publication and retains the prior
  package unchanged; the temporary partial file is removed.
- Receipt coverage proves a Windows receipt with any other archive digest cannot activate even when
  its per-file hashes are internally consistent.
- Worker coverage proves Windows routes the exact official source, `adb.exe`/`fastboot.exe`, and the
  approved 37.0.1 digest together; the adjacent Linux progress test proves no Windows pin leaks into
  the Linux route.
- Existing focused receipt security/persistence coverage remains included in the 36 passing cases.
- Ruff lint passed for the source and both affected test files. The changed download test file is
  Ruff-formatted. `git diff --check` passed. No broad suite was run.

### Existing workspace and build evidence reused

- Source-backed production verification still accepts the retained receipt at:
  `C:\\Work\\ROMVERSE-Link-Lazy-Frozen-20260907\\tools\\downloads\\platform-tools\\managed-package.romverse`.
- The receipt remains 520 bytes with its original `8 September 2026 05:24:02` timestamp, proving the
  correction did not edit it or redownload Platform Tools.
- The previously verified unsigned executable remains:
  `build/windows-dev-receipt-fixed/ROMVERSE/ROMVERSE.exe`, size `6,268,565` bytes, SHA-256
  `c6dcafcf56164b75c896c6195417299f9caebc8d2f60d592c73a7e0c2b2b11b9`.
- Product Assurance explicitly allowed reuse unless the source correction strictly required a new
  build. The digest gate and worker/verifier behavior were decisively exercised in-process, while the
  ready/no-device runtime and restart evidence were already accepted at `0882654`; therefore no
  duplicate build, app launch, or user journey was performed.

### Safety, scope, and next gate

- Only `src/romverse/ui/toolchain_center.py`, the two focused toolchain test files, and this handoff
  changed. Protected Companion files remain clean and untouched.
- No phone, emulator, network ADB target, USB target, physical-device request/wait, ADB/Fastboot
  execution, Recovery action, APK/driver/package installation, global PATH or firewall/security
  change, production trust/signing, publication, release, destructive action, force-push, blind
  retry, or bootloader lock/relock occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty,
  independent verification, feature freeze, and permanent no-relock remain intact.
- If Google changes the moving archive, acquisition now remains blocked until a separately reviewed
  ROMVERSE update changes the approved version and digest.
- Stop for independent Product Assurance review. Do not begin another product, runtime, hardware,
  signing, or release slice without the exact matching committed verdict.

## Windows managed-receipt persistence correction — Product Assurance review requested

- Product Assurance correction: `a556d7da7b4d3525bc5fb1a516cbcdcedaaed799`
- Implementation commit: `b881d5ac128bc4e6f3d03be1781ec200037ef00a`
- Integration commit preserving the concurrent Build/Assurance history:
  `6150e0ba2ef5a47514132972dc4887c13bd7706d`
- Branch: `windows-launcher-authorized-work`
- Status: the exact bounded receipt portability correction is implemented, focused-tested, built
  once, and genuinely Windows-verified against the existing workspace. Device Engine recognizes the
  existing ADB/Fastboot pair before and after one restart. Stop for independent Product Assurance.

### Exact correction

- `install_official_archive` now serializes every newly generated managed-package entry with a
  canonical forward-slash relative path.
- Receipt parsing separates canonical POSIX-form entries from one compatibility path. Backslashes
  are accepted only when every entry uses the legacy form and the package is the exact official
  Windows Platform Tools package/source already emitted by ROMVERSE.
- A legacy component is rejected if it is drive-qualified, rooted, UNC, empty, `.`, `..`, contains
  `:`, mixes slash forms, or attempts to leave the package.
- The existing per-component `lstat`, no-symlink/no-junction, regular-file, resolved-boundary,
  exact-file-set, schema/source, bounded receipt, and exact-file-hash checks still run after parsing.
- Existing Windows receipts are verified in place; no receipt was edited and no package was
  redownloaded. The original receipt and install plan retain their `05:24:02` and `05:24:01`
  timestamps, respectively, from before the corrected build and launches.
- No Companion, Device Engine, Guardian, Recovery, launcher, project, artifact contract, or product
  behavior outside managed-package path portability changed.

### Focused Windows verification

- Final command:
  `.venv\\Scripts\\python.exe -m pytest tests/test_toolchain_download.py -q --basetemp build/pytest-toolchain-receipt-20260908-final`
- Final result: **31/31 passed** on Windows 11 x64 / Python 3.12.10.
- The new deterministic coverage proves:
  - canonical new receipt entries are `platform-tools/adb` and `platform-tools/fastboot`;
  - the exact legacy `platform-tools\\adb.exe` / `platform-tools\\fastboot.exe` pair activates from
    the existing receipt form without redownload and without duplicating PATH entries;
  - drive, rooted, UNC, empty-component, dot, traversal, mixed-form, hash-tamper, and linked-component
    inputs remain rejected.
- The same file retains the existing archive traversal, ambiguous-binary, redirected-root, linked
  package, candidate-flood, schema/source, exact-file-set, tamper, and boundary tests.
- Two intermediate test-authoring runs reported **24 passed / 7 failed** because the new fixture
  looked up a double-backslash literal instead of the exact one-backslash legacy key. The test data
  was corrected; no product relaxation was made. The first run also encountered the known default
  pytest temp-root cleanup permission error, so all decisive runs used a repository-local basetemp.
- Ruff lint passed for both changed files. Ruff format passed for the changed test file. The source
  file's pre-existing unrelated format-check findings remain unchanged and were not mechanically
  reformatted outside this correction. `git diff --check` passed.
- A source-backed production probe against the real workspace returned the exact managed Platform
  Tools directory from both `verified_managed_directories` and `activate_verified_managed_tools`.

### One authorized unsigned Windows build

- Exact command:
  `.venv\\Scripts\\python.exe scripts\\build_desktop_executable.py --output-directory build\\windows-dev-receipt-fixed --work-directory build\\windows-dev-receipt-fixed-pyinstaller`
- Result: successful once with PyInstaller 6.22.2, Python 3.12.10, and
  `Windows-11-10.0.26200-SP0`.
- Executable:
  `build/windows-dev-receipt-fixed/ROMVERSE/ROMVERSE.exe`
- Size: `6,268,565` bytes.
- SHA-256: `c6dcafcf56164b75c896c6195417299f9caebc8d2f60d592c73a7e0c2b2b11b9`.
- Authenticode status: `NotSigned`, as required for this development checkpoint.
- No ZIP, installer, APK, production signature, publication, or release was produced.

### Genuine ready state and restart persistence

- Both launches used the exact existing workspace:
  `C:\\Work\\ROMVERSE-Link-Lazy-Frozen-20260907`.
- First corrected launch reached the real Command Deck with `Connect your Android device`,
  `Scan for device`, `No Android device detected`, and `No device connected`. The former
  `Resolve Platform Tools`, `Device Engine needs attention`, and Platform Tools inactive error were
  absent.
- ROMVERSE was closed normally with the exact app window and reopened once. The restarted process
  rendered the same ready/no-device state, proving restart persistence without redownload.
- Exact workspace-local versions:
  - ADB protocol `1.0.41`, Platform Tools `37.0.1-15733141`;
  - Fastboot `37.0.1-15733141`.
- The final restarted ROMVERSE process owned zero TCP listeners and zero UDP endpoints and was then
  closed at the review checkpoint.
- No phone, emulator, network ADB target, USB target, or physical device was connected, selected, or
  operated. The only direct tool executions were the approved local `adb version` and
  `fastboot --version` checks; no device-scoped command ran.

### Provenance limitation retained for review

- This correction follows Product Assurance commit `a556d7d` exactly and does not alter download
  provenance or source selection. The existing route still records the measured digest from Google's
  official moving `platform-tools-latest-windows.zip` URL rather than comparing it with a separately
  predeclared upstream digest. Windows Build makes no stronger independent pinning claim; Product
  Assurance should explicitly decide whether the existing receipt/source contract is sufficient.

### Safety, scope, and next gate

- Protected Companion files are clean and untouched. Only managed receipt source/tests and this
  Build handoff changed after the same-branch assurance integration.
- No physical execution, device authority, Recovery command, APK install, production adapter/trust,
  global PATH or package installation, driver/firewall/security change, signing, publication,
  release, destructive action, force-push, blind retry, or bootloader lock/relock occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty,
  independent verification, feature freeze, and permanent no-relock remain intact.
- Stop for independent Product Assurance review. Do not begin another correction, product slice,
  hardware task, or release activity until the exact matching verdict is committed.

## Windows Platform Tools readiness — actionable blocked checkpoint

- Product Assurance authorization: `6bbb86a8cad296a88392b808f0a9787c0c661afd`
- Reviewed Windows checkpoint: `bd5dd95f7e1308dff917713f9549f09ef93cf2a4`
- Branch: `windows-launcher-authorized-work`
- Frozen executable reused without rebuilding:
  `build/windows-dev-frozen/ROMVERSE/ROMVERSE.exe`
- Existing readiness workspace reused:
  `C:\\Work\\ROMVERSE-Link-Lazy-Frozen-20260907`
- Status: the stale Windows Security prompt is gone and the existing Resolve Platform Tools journey
  was exercised. The download completed with matching file hashes, but ROMVERSE rejected its own
  Windows-generated managed-package receipt, so Platform Tools remain inactive after restart. This
  is the required specific actionable blocked result; stop for independent Product Assurance review.

### Genuine Windows journey evidence

- The prior stale `PickerHost.exe`/Windows Security blocker was absent before interaction. Windows
  process inspection found no `PickerHost.exe` and no security prompt was automated.
- The real frozen ROMVERSE window exposed `Resolve Platform Tools`. The existing flow selected only
  ADB, wrote `logs/toolchain-install-plan.json`, and downloaded the Windows Platform Tools archive
  into the workspace-local managed-tool directory.
- The setup dialog reported:
  `Downloaded and prepared: platform-tools (45f4d63113e8…) ROMVERSE refreshed the tool inventory automatically.`
- At the required run boundary, Steve explicitly confirmed the local version/readiness checks. No
  phone was connected or selected.
- The restarted frozen process used the same executable and workspace and reached Command Deck, but
  still truthfully rendered `Device Engine needs attention` and
  `Verified Android Platform Tools are not active yet.` It did not claim readiness.
- The restarted ROMVERSE process owned zero TCP listening endpoints and zero UDP endpoints during
  the final read-only inspection.

### Download and integrity evidence

- Managed receipt:
  `C:\\Work\\ROMVERSE-Link-Lazy-Frozen-20260907\\tools\\downloads\\platform-tools\\managed-package.romverse`
- Declared source:
  `https://dl.google.com/android/repository/platform-tools-latest-windows.zip`
- Archive size: `8,044,989` bytes.
- Recorded archive SHA-256:
  `45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99`.
- Downloaded `source.properties`: `Pkg.Revision=37.0.1`.
- `adb.exe` measured SHA-256:
  `b4a6b455702684652cccf7b46258b29e653538904359a58fd4931cf3ef286b3f`;
  this exactly matches the receipt.
- `fastboot.exe` measured SHA-256:
  `b2d9cbff4ce9ae7eb448cfc831bafc867935f50f5be38f8f81057fd7eb3b8d86`;
  this exactly matches the receipt.
- No downloaded executable was invoked manually and no ADB/Fastboot device operation was run.

### Exact actionable blocker

- The downloader records each required file with
  `str(candidate.relative_to(staging))`. On Windows this serializes native backslashes, producing
  `platform-tools\\adb.exe` and `platform-tools\\fastboot.exe` in the receipt.
- `_contained_receipt_file` rejects every receipt entry containing a backslash before it can resolve
  or hash the file.
- A read-only invocation of the production receipt path against the exact workspace returned:
  `verified_managed_directories(...) == ()` and `verified_managed_package_roots(...) == ()`.
- Therefore `activate_verified_managed_tools` adds no managed directory to the frozen process PATH;
  the subsequent tool inventory cannot locate the downloaded pair. The fail-closed UI state is
  correct, and persistence remains correctly not-ready rather than becoming a false success.
- The frozen artifact's relevant receipt/tool-verifier source is unchanged between its implementation
  commit `c0b140bbebe7b8fd107819c911703ac9a07e2954` and this checkpoint.

### Pinning limitation discovered during the approved acceptance gate

- The existing Platform Tools route uses Google's moving `platform-tools-latest-windows.zip` URL.
  It records the measured archive digest after download, but current source does not compare that
  digest with a predeclared approved Platform Tools digest before extraction or activation.
- Accordingly, Windows Build does **not** claim that this acquisition satisfied Product Assurance's
  `pinned` condition. Matching receipt/file hashes prove download-to-workspace consistency, not an
  independently approved upstream version pin.

### Verification classification and commands

- Genuine Windows: frozen app interaction, workspace-local download, dialog outcome, fresh process
  restart observation, fail-closed Command Deck state, filesystem hashes, and zero listener check.
- Read-only source-backed probe:
  `.venv\\Scripts\\python.exe -c "...verified_managed_directories(...); verified_managed_package_roots(...)"`
  returned two empty tuples for the exact readiness workspace.
- Repository history check:
  `git log c0b140b..HEAD -- src/romverse/ui/toolchain_center.py src/romverse/infrastructure/tools.py`
  returned no changes.
- Repository status before this handoff edit: clean at
  `6bbb86a8cad296a88392b808f0a9787c0c661afd`, exactly matching
  `origin/windows-launcher-authorized-work`.
- Tests run: none. No source changed and the acceptance result is direct genuine-Windows evidence;
  repeating the accepted listener/build/journey suites would not alter this receipt incompatibility.
- Build/rebuild/package: none. The previously approved frozen executable was reused exactly.

### Safety and scope

- No phone, emulator, network ADB target, USB target, or physical device was connected or operated.
- No device-scoped ADB/Fastboot command, Recovery command, APK install, production adapter, production
  trust, signing, publication, release, merge, force-push, destructive action, blind retry, or
  bootloader lock/relock occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty,
  independent reassessment/verification, feature freeze, and permanent no-relock remain unchanged.
- Protected Companion files and all application source remain untouched at this checkpoint.

### Precise next proposed correction

Product Assurance should review and, if approved, authorize one bounded Platform Tools receipt/pin
correction only:

1. Serialize newly generated managed-package paths canonically with forward slashes (for example,
   `candidate.relative_to(staging).as_posix()`) while preserving the existing linked-path, boundary,
   regular-file, exact-file-set, and hash gates.
2. Define and enforce an approved version/digest pin for the Windows Platform Tools archive before
   extraction or activation; do not accept a digest merely because the same download wrote it into
   its own receipt.
3. Add deterministic Windows-path and wrong-digest cases proving fail-closed behavior, then run only
   the focused managed-tool tests plus lint.
4. Reuse the existing frozen executable/build evidence until Product Assurance explicitly decides
   whether a corrected source build is required. Do not edit the external receipt by hand, operate a
   phone, or advance Device Engine authority.

Stop here for Product Assurance. Do not implement this correction without the matching verdict.

## Fail-closed ADB transport default — Product Assurance review requested

- Implementation commit: `efeb854e9203ee39f8849a2b7bd2f5ee6a4a7197`
- Product Assurance correction: `47b3262945fb2738e02c98b78d5cfd8ce9e3da59`
- Branch target: `windows-launcher-authorized-work`
- Working branch: `pa/windows-runnable-review`
- Stage: Stage 1 — v0.2 Golden Foundation Device Engine/Companion truthfulness
- Status: required minimum follow-up implemented and focused-tested; stop for independent review.

### Exact correction

- `_adb_transport` now returns physical `usb` only when the current parsed ADB discovery row carries
  a non-empty `usb:` field.
- Network endpoint serials still take precedence as `network`; `emulator-*` and positive QEMU/virtual
  properties still classify as `emulator`.
- A local-looking serial with no explicit USB, emulator, or QEMU evidence now remains stable
  non-authorizing `adb` evidence and is described as an unconfirmed local ADB transport.
- The original physical Device Engine fixture now contains explicit `usb:1-2.3` evidence rather than
  relying on serial shape.
- The focused Device Engine case now proves explicit USB, emulator serial, QEMU evidence, network ADB,
  and unconfirmed local ADB independently.
- The existing Companion Center non-USB test now includes the unconfirmed `adb` case and proves that
  emulator, network, and unconfirmed local ADB retain telemetry but never gain `_usb_ready`, a USB
  serial, USB assist, `USB connected`, or `USB also connected` before pairing, after wireless pairing,
  or after reset.
- No Companion Center production source change was necessary because its prior exact
  `device.transport == "usb"` boundary already fails closed for `adb`.
- No other source, Companion Android, Link protocol, Windows launcher, Guardian, Recovery, artifact,
  packaging, or approved asset changed.

### Classification and focused verification

- Implemented: fail-closed Device Engine ADB transport default and explicit evidence fixture.
- Simulated/Tested: deterministic fake-ADB and offscreen Qt verification on Fedora/Linux against this
  exact Windows-branch worktree.
- Hardware Verified: no.
- Released: no.
- Final directly affected result: **10/10 passed**.
- Ruff lint: passed for the four directly inspected Device Engine/Companion Center source/test files.
- Ruff formatting: all four files already formatted.
- Git whitespace validation: passed.
- Earlier 10/10 correction evidence is superseded by this final run and is not double-counted.
- No broad suite, complete test file, journey, application launch, artifact build, or package check
  was run.

### Guided, Guardian, and safety impact

- Absence of USB evidence can no longer become a physical-cable claim or USB-assist capability.
- Unconfirmed local ADB remains useful for read-only telemetry while authority stays closed.
- Genuine explicitly observed USB, emulator, QEMU, network, multiple, unauthorized, offline, Link,
  and reset behavior remain intact.
- Guardian remains the only execution authority; connection labels grant none.
- Exact-device evidence, consent separation, durable UNKNOWN, no blind retry, same-incident Recovery,
  and independent reassessment/verification are unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override.

### Platform, freeze, blockers, and next task

- Fedora and Windows runnable/inert Guided checkpoints remain previously verified and unchanged.
- This correction is Linux-host verified only; no genuine Windows or Android hardware claim is made.
- Windows Device Engine readiness remains paused for Steve's human dismissal of the stale Windows
  Security prompt. This task did not interact with it.
- 5 September 2026 feature freeze: preserved; this is the exact minimum truthfulness correction.
- v0.2 Golden Foundation remains **CLOSED** pending physical, production-trust, signing, and release
  gates.
- Stop for independent Product Assurance review. Do not begin another source/platform/hardware slice.

### External actions

- Physical phone, emulator, network ADB target, ADB/Fastboot command, Windows app, or Windows prompt:
  none.
- Build/rebuild, executable/ZIP/APK installation, dependency/package/driver/PATH/security change:
  none.
- Recovery, firmware, partition, flash, wipe, root, unlock, relock, signing, publication, release,
  merge, or force-push: none.
- Linux branch and Companion Android source: untouched.
- Remote action: normal push of this implementation and handoff to
  `origin/windows-launcher-authorized-work` is intended after final repository verification.

### Product Assurance questions

- Confirm explicit discovery `usb:` is now the only physical USB classification path.
- Confirm the unconfirmed local `adb` path remains read-only and cannot enable or claim USB assist.
- Confirm the final 10/10 focused result and lint/format checks close this correction.

## Android connection-source truthfulness — Product Assurance review requested

- Implementation commit: `e685eee873c170821f876c049d14625961c9bf40`
- Product Assurance authorization: `a27b1858f53fe41a81e50354b88703561cf6a825`
- Branch target: `windows-launcher-authorized-work`
- Working branch: `pa/windows-runnable-review`
- Stage: Stage 1 — v0.2 Golden Foundation Device Engine/Companion truthfulness
- Status: the bounded source/test correction is implemented and Linux-host verified; stop for
  independent Product Assurance review.

### Exact correction

- Device Engine now classifies ADB connection source conservatively:
  - serials containing a network endpoint remain `network`;
  - `emulator-*` serials are `emulator` immediately;
  - read-only `ro.kernel.qemu`, `ro.boot.qemu`, or `ro.hardware.virtual_device` proof promotes a
    local-looking target to `emulator` as soon as `getprop` completes;
  - the existing remaining local Android path stays `usb`.
- Reconnect-safe scanning no longer puts an `emulator-*` target through the physical-USB
  stabilization path or emits a temporary USB snapshot for it.
- Device Engine connection notes distinguish local emulator, network ADB, and physical USB. An
  emulator/network transport failure no longer presents cable troubleshooting.
- Companion Center sets `_usb_ready`, retains a USB serial, and enables USB-assisted pairing only
  for a normal `DeviceState.DEVICE` snapshot whose exact observed transport is `usb`.
- Emulator and network ADB snapshots still supply existing read-only development telemetry, but
  render their real source and never present `USB connected`, `USB also connected`, or
  `USB read-only evidence remains available`.
- Unauthorized, offline, multiple-target, and no-selection states remain fail-closed and now use
  transport-neutral or source-specific wording rather than inventing a cable.
- The genuine physical-USB route remains unchanged: it still reports USB evidence, supports the
  separate Link approval flow, and enables USB assist only when Companion is actually installed.
- Unconditional fallback copy now says Device Engine remains read-only rather than claiming USB
  evidence is available when no physical USB target has been established.
- No Companion Android source, Link protocol, Windows launcher, Guardian, Recovery, artifact,
  packaging, or approved asset changed.

### Classification

- Implemented: Desktop Device Engine transport classification and Companion Center readiness/copy.
- Simulated/Tested: deterministic fake-ADB and offscreen Qt tests on Fedora/Linux against this exact
  Windows-branch worktree.
- Hardware Verified: no. No Android target, emulator, Windows app, or physical cable was used.
- Released: no.

### Focused verification

- Final directly affected result: **10/10 passed**.
- Device Engine coverage proves:
  - genuine local physical ADB remains `usb`;
  - `emulator-5554` is `emulator`;
  - a nonstandard local serial with fresh QEMU evidence is `emulator`;
  - `192.168.1.17:5555` remains `network`;
  - reconnect-safe scan never stabilizes an emulator as physical USB;
  - physical USB stabilization/cache behavior remains intact.
- Companion Center coverage proves:
  - physical USB retains its existing read-only and USB-assisted pairing route;
  - local emulator and network ADB provide telemetry without `_usb_ready`, retained USB serial, USB
    assist, or physical-cable presentation;
  - paired emulator/network state never gains `USB also connected`;
  - emulator unauthorized, network offline, and mixed multiple-target states remain fail-closed;
  - physical disconnect clears readiness and presents a neutral no-target state.
- Ruff lint: passed for the exact four changed source/test files.
- Ruff formatting: all four files already formatted.
- Git whitespace validation: passed.
- The first 9/9 run is a subset of the final 10/10 result and is not added.
- No full suite, broad Device Engine file, broad Companion Center file, app journey, executable/ZIP
  rebuild, or artifact verification was run.
- The existing verified listener lifecycle result remains 21 passed / 1 unrelated deselected and is
  not counted again.

### Guided friction and safety implications

- The prior direct Fedora journey's emulator can no longer be presented as physical USB evidence.
- Virtual/network development remains usable and read-only without enabling a cable-only shortcut.
- Genuine physical USB behavior, multiple/unauthorized/offline fail-closed handling, wireless Link,
  certificate pinning, safety-code comparison, separate approval, session revocation, and
  `execution_authority: none` remain intact.
- Guardian remains the only execution authority. No connection label grants device-changing power.
- Exact-device evidence, consent separation, durable UNKNOWN, no blind retry, same-incident Recovery,
  and independent reassessment/verification are unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override.

### Platform, freeze, and gate status

- Fedora runnable build, inert Guided journey, and direct Companion Link: previously verified and
  unchanged.
- Windows runnable development build, inert Guided journey, and intent-bound optional listener:
  previously verified and unchanged.
- This source correction: verified on Linux using the existing Python 3.14.7/PySide6 environment
  with this worktree explicitly first on `PYTHONPATH`; no genuine Windows execution is claimed.
- Windows Device Engine/toolchain readiness remains paused for Steve's human dismissal of the stale
  Windows Security prompt. This task did not interact with it.
- 5 September 2026 feature freeze: preserved; this is a minimum truthfulness/safety correction to
  existing connection-source behavior.
- v0.2 Golden Foundation remains **CLOSED** pending physical, production-trust, signing, and release
  gates.

### Blockers and limitations

- No real emulator, network ADB target, or physical USB device was used; current evidence is
  deterministic software verification, not hardware proof.
- Windows-native regression for this correction was not run because ownership was temporarily
  transferred specifically for Linux-hosted source verification after the Windows runner timed out.
- The stale Windows Security prompt and Windows Device Engine readiness continuation remain outside
  this task.

### Next task

Stop for independent Product Assurance review. Do not start Windows app interaction, Device Engine
readiness, another source correction, hardware work, Recovery, signing, packaging, publication, or
release without the next repository verdict.

### External actions

- Physical phone/emulator/network ADB connection or operation: none.
- ADB/Fastboot command: none.
- Windows application/prompt interaction: none.
- Executable/ZIP/APK rebuild or installation: none.
- Dependency, package, driver, firewall, SELinux, PATH, or host-security change: none.
- Recovery, firmware, partition, flash, wipe, root, unlock, relock, signing, publication, release,
  merge, or force-push: none.
- Linux branch and Companion Android source: untouched.
- Remote action: normal push of this scoped implementation and handoff to
  `origin/windows-launcher-authorized-work` is intended after final verification.

### Product Assurance questions

- Confirm the classifier and Companion Center boundary close the emulator/physical-USB truthfulness
  defect without weakening genuine USB or wireless Link behavior.
- Confirm the focused 10/10 Linux-hosted result and lint/format gates are proportional.
- Confirm no Windows-native rerun or hardware check is required before assigning the next bounded
  task.

## Intent-bound Companion Link correction — checkpoint blocked by stale Windows prompt

- Reviewed checkpoint: `f8413bfe465e8bfd33d62a0a6cd92d3aa6572167`
- Product Assurance correction: `b0ba30681623e0fc97617f607fbb24dfa7d3cf73`
- Correction implementation: `c0b140bbebe7b8fd107819c911703ac9a07e2954`
- Branch: `windows-launcher-authorized-work`
- Status: the approved listener lifecycle correction, focused Windows verification, and single
  frozen rebuild are complete. The resumed Device Engine readiness action remains blocked only by
  the still-open Windows Security notification created before this correction; no security decision
  was automated.

### Minimum listener lifecycle correction

- Fresh `CompanionTransport` construction now creates the existing TLS identity and remembered-
  session broker without constructing, binding, listening on, or advertising a network server.
- Fresh `CompanionCenter` construction leaves the endpoint idle while keeping the existing
  `Generate wireless code` and eligible USB-assisted pairing actions available.
- An existing explicit pairing action invokes one bounded `start()` operation. Repeated pairing
  actions reuse the same live server and discovery thread; a failed operation records one bounded
  unavailable state and is not retried automatically.
- A still-valid remembered approved session resumes the endpoint during construction. A failed
  resume remains unavailable rather than rendering a live approved Link.
- TLS identity, short-lived pairing code, exact safety-code comparison, Desktop approval,
  read-only telemetry, session reset/revocation, transfer revocation, clean shutdown, privacy
  filtering, and `execution_authority: none` are unchanged.

### Focused Windows verification

- Command:
  `.venv\\Scripts\\python.exe -m pytest tests/test_companion_transport.py tests/test_companion_center.py -k "not keeps_pairing_controls_readable" -vv --basetemp build/pytest-companion-lifecycle-final`
- Result: **21 passed, 1 deselected in 8.68 seconds** on Windows 11 / Python 3.12.10.
- The selected set includes the new deterministic fresh-idle, one-explicit-start, bounded startup-
  failure, remembered-session resume, TLS transport, revocation, privacy, and shutdown evidence.
- The one deselected test is
  `test_companion_link_keeps_pairing_controls_readable_in_a_scroll_surface`. It is the exact
  unrelated Windows baseline failure already recorded in
  `docs/WINDOWS-PORTABILITY-AUDIT-2026-09-07.md` as the pre-correction `12 passed, 1 failed`
  Companion Center result; this lifecycle correction did not alter its consent layout.
- Ruff command:
  `.venv\\Scripts\\python.exe -m ruff check src/romverse/companion/transport.py src/romverse/ui/companion_center.py tests/test_companion_transport.py tests/test_companion_center.py`
- Ruff result: passed. `git diff --check`: passed.
- Linux reproduction is not claimed by Windows Build and remains for independent Product Assurance.

### Real source and frozen startup evidence

- Source launch used fresh workspace
  `C:\\Work\\ROMVERSE-Link-Lazy-Source-20260907` and reached the real visible Command Deck with
  `Device Engine needs attention` and `Resolve Platform Tools` present.
- The source process owned **zero TCP listening endpoints and zero UDP endpoints** before any Link
  action. No Link discovery thread or inbound listener was observed.
- The single authorized frozen rebuild command was:
  `.venv\\Scripts\\python.exe scripts/build_desktop_executable.py --output-directory build/windows-dev-frozen --work-directory build/windows-dev-pyinstaller`.
- PyInstaller 6.22.2 completed successfully once using Python 3.12.10 on
  `Windows-11-10.0.26200-SP0`. No ZIP was rebuilt.
- Corrected unsigned development executable:
  `build/windows-dev-frozen/ROMVERSE/ROMVERSE.exe`
  - size: `6,266,277` bytes;
  - SHA-256: `0d54ed4588c6337a7bee194ee9b3541593fe3e8ab9222f35489d339a5eae6cc9`.
- Frozen launch used fresh workspace
  `C:\\Work\\ROMVERSE-Link-Lazy-Frozen-20260907` and again reached the real visible Command Deck
  with `Resolve Platform Tools` present.
- Frozen PID `43080` owned **zero TCP listening endpoints and zero UDP endpoints** before any Link
  action. Only an unrelated outbound online-status connection was present.

### Exact remaining external blocker

- Windows still shows the pre-existing `Windows Security` firewall notification for `ROMVERSE.exe`.
  Its authoritative process is `PickerHost.exe` PID `38940`, created at **2026-09-07 20:52:22
  +10:00**—about three hours before the corrected source and frozen launches.
- The same PID and creation time persisted across both corrected launches. No new firewall prompt
  process was created, and the corrected processes had no inbound listener or Link discovery socket.
  This establishes that the corrected fresh startup did not request a new Link firewall decision.
- Computer-use policy and Product Assurance both prohibit Build from acting on Windows Security.
  The old modal intercepts the `Resolve Platform Tools` control, so the readiness journey cannot
  safely continue until Steve manually chooses **Cancel**. Build did not select Allow or Cancel,
  dismiss or terminate the prompt, change firewall policy, or use a port workaround.
- After Steve dismisses the stale prompt, resume the existing frozen workspace and existing rebuilt
  executable. Do not rebuild again. Open `Resolve Platform Tools`, capture the product's declared
  toolchain state, and continue only the approved workspace-local integrity-checked readiness flow.

### Scope and safety

- The implementation commit changes only Desktop Companion transport/center source and their
  directly affected tests. This handoff changes only this Build Status document.
- Protected Companion Android files are unchanged and unstaged.
- No firewall/security policy, system package, system-wide tool, driver, global PATH, phone,
  ADB/Fastboot device operation, Recovery command, relock, APK, production trust, signing,
  publication, release, force-push, or destructive history change occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze, and permanent no-relock remain intact.

## Windows Device Engine / toolchain operability blocker — Product Assurance review requested

- Approved readiness checkpoint: `7642cad98d2501588d9b6829b132c01c1f8798b7`
- Product Assurance authorization: `f5a06a7664c67c35d14a20286c1acc9ee1b6ba2e`
  (`Approve Windows development readiness`)
- Blocker evidence commit: `ae13356696915189ad73e9b3cd9bfdfcefa11b3b`
- Branch: `windows-launcher-authorized-work`
- Status: specific actionable operating-system permission blocker captured; unchanged product could
  not complete its Device Engine readiness journey without a prohibited Windows Security action.

### Fresh isolated workspace and exact initial state

- Frozen executable reused unchanged:
  `build/windows-dev-frozen/ROMVERSE/ROMVERSE.exe`.
- Fresh isolated workspace:
  `C:\Work\ROMVERSE-Toolchain-Readiness-20260907-1246`.
- Workspace did not exist before launch and initialized successfully.
- Real visible Command Deck state:
  - `Device Engine needs attention`;
  - `Verified Android Platform Tools are not active yet`;
  - `DEVICE ENGINE ERROR`;
  - `Resolve Platform Tools` was the existing actionable product control;
  - device remained `NOT CONNECTED` and Guardian remained `VERIFY REQUIRED`.
- Host PATH discovery found no `adb` and no `fastboot` executable. Therefore there were no paths,
  versions, hashes, or competing installations to record.
- The isolated workspace's `tools` directory contained no files. No toolchain manifest, managed
  acquisition receipt, or install plan existed before action.

### Exact blocker

Before the `Resolve Platform Tools` control could be exercised, Windows Security opened a modal:
`Do you want to allow public and private networks to access this app?` for unsigned
`ROMVERSE.exe`. The permission window covered and blocked the ROMVERSE workspace.

Computer-use policy prohibits automating Windows Security or permission dialogs, and this bounded
task explicitly prohibited changing global Windows security. Neither `Allow` nor `Cancel` was
selected. No attempt was made to bypass or dismiss the permission surface, and the ROMVERSE process
was stopped after evidence capture.

- Screenshot: `docs/evidence/windows-toolchain-readiness-blocked.png`
- Screenshot SHA-256: `85a2e6fcfde4f4c0742eb8aaa795cbe2d05cec7d996ea2114e262d05f60b3e7e`
- Screenshot size: 138,563 bytes.
- The image is readable and records both the truthful missing-tools state and the exact blocking
  Windows Security prompt.

### Result and precise review question

The unchanged product did not reach ready state and did not begin its declared workspace-local,
integrity-checked Platform Tools acquisition. This is not a failed download: the acquisition action
was never safely reachable. Restart persistence and executable/provenance receipts cannot be claimed
because no receipt was created.

Product Assurance should determine the next smallest authorized path: either require a human to
choose the non-expansive Windows Security outcome before Build continues, or authorize a separate
minimum product correction that prevents an unrelated inbound-listener permission surface from
blocking the host-toolchain readiness journey. Build must not infer either authority.

### Scope and safety

- No application source, test, executable, ZIP, dependency, system package, driver, global PATH,
  or Windows security setting was changed.
- No download, tool acquisition, install plan, manual source, or unverified executable ran.
- No phone was connected or operated; no ADB/Fastboot device command, USB-driver action, Recovery
  command, APK installation, production trust, signing, publication, release, retry, or relock
  occurred.
- Protected Companion files were not edited, staged, discarded, tested, or committed.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze, and permanent no-relock remain intact.

## Portable raw-ZIP regression correction — Product Assurance review requested

- Reviewed checkpoint: `20e0c3312ef5d995694f66119295007d1f8d2dac`
- Product Assurance correction: `8a4461d21be1a9a7d45cf4420b132a0b3dd90cf7`
- Exact test-only correction: `7353b0df797f37354864ace65b889e488c7a9b56`
- Branch: `windows-launcher-authorized-work`
- Status: the sole cross-platform assertion defect is corrected; stop for independent Product
  Assurance review.

### Exact change and evidence

- Modified only
  `tests/test_source_installation.py::test_literal_backslash_archive_path_is_rejected_before_windows_normalization`.
- Retained the unconditional raw-name assertion:
  `member.orig_filename == r"windows\boot.img"`.
- Removed only the secondary `member.filename` assertion because Python normalizes that field to a
  forward slash on Windows but retains the literal backslash on non-Windows hosts. That host detail
  is not part of the safety contract.
- Retained the manually constructed raw unsafe ZIP member and the required cross-platform
  `SourceInstallationService.prepare` `ProjectError` rejection.
- Single corrected regression on Windows: **1 passed** in 0.17s.
- Directly affected Windows source-installation file: **32 passed** in 1.46s.
- Ruff lint, Ruff formatting, and Git whitespace checks: passed.
- The Linux focused-suite result is left for independent Product Assurance reproduction; removing
  the sole host-specific assertion does not conditionalize or skip the safety test.

### Scope and safety

- No production source, accepted-path validation, launcher, ACL code, application, artifact, UI,
  packaging, journey evidence, dependency, or unrelated documentation changed.
- No frozen rebuild, ZIP rebuild, visible launch, inert Guided rerun, or broad regression was
  performed, as Product Assurance explicitly said they were unnecessary for this test-only change.
- No phone connection or operation, Recovery command, APK installation, production trust,
  physical execution, signing, publication, release, relock, force-push, or protected Companion
  file change occurred.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze, and permanent no-relock remain intact.

## Windows minimum-readiness correction checkpoint — Product Assurance review requested

- Reviewed checkpoint: `824d6e7b3f59e16d9d2bffe3e6f1049ddc55470b`
- Product Assurance correction verdict: `a924b2067b83d797be3742b3bdb81f02ac06a045`
  (`Require minimum Windows readiness correction`)
- Correction implementation: `0e2f895dfcb3507fdbda5c1a3f74096361aedf3d`
- Branch: `windows-launcher-authorized-work`
- Status: all four required minimum corrections implemented and verified on the real Windows host;
  stop for independent Product Assurance review

### 1. Exact Windows launcher identity stabilization

- Cause: CPython's `os.fstat` and path `lstat` independently converted the same NTFS timestamps to
  nanoseconds with intermittent sub-millisecond differences. The comparison could therefore reject
  the same locked file even though device/file identity, size, and file bytes were unchanged.
- Correction: both the pinned descriptor and a second non-write/non-delete-sharing path handle now
  use `GetFileInformationByHandle`. The exact comparison fields are native volume serial, 64-bit
  file index, link count, 64-bit size, last-write `FILETIME`, and creation `FILETIME`.
- Reparse-component rejection, `FILE_FLAG_OPEN_REPARSE_POINT`, single-link requirement, regular-file
  requirement, byte-exact hash/size verification, write/delete-denying pinned handle through process
  creation, fixed launch surface, one attempt, and fail-closed behavior remain unchanged.
- One captured successful identity comparison:
  - volume serial: `951229823` / `951229823`
  - file index: `281474977206815` / `281474977206815`
  - link count: `1` / `1`
  - size: `33` / `33`
  - last-write FILETIME: `134332548504913093` / `134332548504913093`
  - creation FILETIME: `134332548504913093` / `134332548504913093`
  - the original pinned descriptor identity also remained equal after hashing.
- Required fresh-process repetition: **100/100 passed**, zero failures; 0.870–1.167 seconds per
  process, 0.919-second mean.
- The first repetition harness attempt is excluded because its parent `--basetemp` directory had
  not been created, making all processes fail during pytest setup before the test ran. After the
  short parent root was explicitly created, the authoritative 100 consecutive runs above passed.
- Full Windows launcher file after the repetition: **21/21 passed** in 0.58s.

### 2. Real visible frozen-window readability

- Evidence: `docs/evidence/windows-frozen-visible-readable.png`
- Screenshot SHA-256: `346cbdbd3510ab812fbb203eb66457ca2f4db4053bc1ae7576aa64cb166c12f8`
- Capture: the actual rebuilt frozen `ROMVERSE.exe` main window on Windows, 1456×939, title
  `ROMVERSE Studio v0.1`, captured through the Win32 window rendering surface while visible.
- Result: headings, navigation, controls, status labels, project and Guardian content are readable;
  no square glyphs are present. The prior square-glyph screenshots are classified as an offscreen
  Qt backend limitation. No font, branding, layout, or application UI change was required.
- The visible application accepted a normal close request and exited normally.

### 3. Windows-native private-file contract

- Windows local evidence writes now publish a protected DACL with exactly two non-inherited Full
  Control allow ACEs: Owner Rights (`S-1-3-4`) and Local System (`S-1-5-18`). Inherited broad access
  is removed. ACL application happens to the private temporary file before atomic publication, or
  before an exclusive record becomes usable; failure is fail-closed.
- The project manifest, working-copy record, snapshot record, and snapshot artifact each produced:
  `(('S-1-3-4', 2032127, False), ('S-1-5-18', 2032127, False))`.
- The tests require exactly those two Full Control (`0x1f01ff`) non-inherited ACEs on Windows.
- Existing POSIX `0600` assertions and behavior remain unchanged.

### 4. Literal-backslash ZIP fixture

- The fixture now writes a normal equal-length member and patches both the local header and central
  directory name bytes to a literal `windows\\boot.img`, avoiding Windows `zipfile` writer
  normalization.
- The test proves `ZipInfo.orig_filename` retains the literal backslash while `filename` is
  normalized. Source parsing now validates `orig_filename` through the existing `_safe_member`
  boundary, so the raw unsafe path is rejected before normalization can hide it.
- Accepted-path validation was not weakened.

### Correction verification

- Focused launcher/project/source tests: **83 passed** in 4.82s.
- Required launcher repetition: **100/100 passed** in fresh pytest processes.
- Full launcher contract file: **21 passed** in 0.58s.
- Final affected regression — local store, desktop bundle, project store, source installation,
  source integration, Guided mission, and Windows launcher: **185 passed** in 245.88s.
- Follow-up exact four-artifact ACL cases: **2 passed** in 0.46s (a subset, not added to 185).
- Ruff lint, Ruff formatting, and Git whitespace checks: passed.
- Source startup smoke after correction: passed, exit 0.
- Rebuilt frozen startup smoke: passed.
- Exact development ZIP verification: 305 files, 164,589,574 expanded bytes.

### Rebuilt unsigned artifact

- Executable: `build/windows-dev-frozen/ROMVERSE/ROMVERSE.exe`
- Archive: `dist/ROMVERSE-Desktop-0.1.0-windows-x86_64-dev.zip`
- Archive size: 73,449,374 bytes
- SHA-256: `747d5b40dbc76f5fab3e777f40bbd3d586bcfb72eaeccadd6647df57996af239`
- Classification: unsigned Windows development build only; not production-ready, signed,
  published, or released.

### Reverified inert Guided journey

- Completed `Scan → Match → Prepare → Consent → Result → Reassessment → Verification`.
- Simulation only; `physical_phone_changed=false`, `production_certified=false`.
- Exact simulated Xiaomi/`popsicle` target; 53 actions and 50 inert image writes.
- Consent decline sent no changing command; later acceptance remained explicit.
- No wipe, relock, blind retry, or physical command.
- Independent stable-boot observation: 60 simulated seconds, 11 samples; audit valid; installation
  receipt remained separate and unchanged.
- Guided/Expert used the same operation session; history reopening sent zero commands and made zero
  additional changes.
- Report: `C:\Work\ROMVERSE-Windows-Guided-Correction-20260907\simulation-report.json`.
- Receipt SHA-256: `bcc1d234ac7d9a5f70a7856ef6b9821e28d7574bf25e43a943deb10588124bae`.

### Safety and scope confirmation

- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze, and permanent no-relock are preserved.
- No phone connection or operation, Recovery command, APK installation, production trust
  enrollment, physical execution, production signing, publication, release, or force-push occurred.
- Protected Companion files were not edited, staged, discarded, tested, or committed.
- No feature, installer, platform merge, production adapter, or expanded product scope was added.

## Runnable Windows development checkpoint — Product Assurance review requested

- Branch: `windows-launcher-authorized-work`
- Approved starting checkpoint: `1d679d5b2f78bd153cd2d349047bd5a3217c116b`
  (`Approve Windows trusted launcher checkpoint`)
- Autonomous-protocol baseline: `4b1382fb81a74c81535dd085f5219dd7a0486e63`
- Minimum Windows blocker correction: `2b121c1` (`Make Windows development build runnable`)
- Committed portability audit: `a20402e110a181c1bf2c6bf138a2e1e69c9ba573`
- Status: unsigned Windows development build is runnable; inert Guided journey completed; stop for
  independent Product Assurance review

### Runnable artifact

- Executable: `build/windows-dev-frozen/ROMVERSE/ROMVERSE.exe`
- Development archive: `dist/ROMVERSE-Desktop-0.1.0-windows-x86_64-dev.zip`
- SHA-256: `e442685566f9f2012a19bfe848cf8234469b994b46d92e41ddddb93a1272fba2`
- Archive size: 73,445,618 bytes; 305 files; 164,585,215 expanded bytes
- Classification: unsigned development build only; not signed, production-ready, published, or
  released

### Exact Windows evidence

Host: Windows 11 Home x64, Python 3.12.10, pytest 9.1.1, Ruff 0.16.6,
PyInstaller 6.22.2.

- Source startup smoke:
  `.venv\Scripts\python.exe -m romverse --workspace C:\Work\ROMVERSE-Dev-Smoke
  --skip-onboarding --release-smoke` — passed, exit 0, 3.75s.
- Frozen build:
  `.venv\Scripts\python.exe scripts/build_desktop_executable.py --output-directory
  build/windows-dev-frozen --work-directory build/windows-dev-pyinstaller` — passed. No
  non-system `icu*.dll` was bundled.
- Frozen startup smoke:
  `.venv\Scripts\python.exe scripts/smoke_frozen_desktop.py
  build/windows-dev-frozen/ROMVERSE/ROMVERSE.exe C:\Work\ROMVERSE-Frozen-Smoke-Fixed` — passed,
  5.97s.
- Visible Windows launch: `ROMVERSE Studio v0.1` opened a responding main window, initialized a
  fresh workspace, accepted `CloseMainWindow`, and exited normally.
- Static checks: Ruff lint, Ruff formatting, and Git whitespace checks passed.

### Bounded full Windows portability triage

- Collected: 2,901 tests across 214 files at `4b1382f`.
- Limit: 60 seconds per file group; both groups reaching the bound were reproduced node-by-node
  with a 20-second limit.
- Completed-group events: 2,398 passed, 314 failed, 80 errors, 18 skipped.
- Including individual timeout-group reproductions: 2,460 passed, 344 failed, 80 errors,
  18 skipped; zero individual timeouts or stalls. There are 2,902 outcome events for 2,901 nodes
  because one OTA metadata node emitted both setup and teardown errors.
- Full commands, all failure/error/skip identities, timeouts, harness limitations, and
  classifications are in `docs/WINDOWS-PORTABILITY-AUDIT-2026-09-07.md` at commit `a20402e`.
- Environment limitations: an inherited global pytest-temp ACL, MAX_PATH with long temp roots, and
  one oversized OTA process environment. The authoritative pass used unique short temp roots.

### Minimum confirmed corrections

- Windows NTFS handle/path creation timestamps can differ only in sub-millisecond rounding for the
  same file. Source verification now retains device, file index, size, and modification-time
  binding on Windows while leaving POSIX creation-time comparison strict.
- PyInstaller inherited a non-system Poppler ICU 78 directory from the host PATH, which shadowed
  the Windows ICU API shim and prevented QtCore loading. The build now removes only non-system PATH
  entries containing `icuuc.dll`, then restores PATH after packaging.
- The approved trusted-launcher implementation and contract were not modified.

### Affected and final regression

- Source/Guided affected run after the identity fix: 149 passed, 2 failed in 583.66s. Both failures
  were pre-existing Windows fixture assertions; source integration and Guided mission passed.
- Focused source/build run: 40 passed, 1 failed; the one failure is the same Windows ZIP writer
  backslash-normalization fixture.
- Final relevant command:
  `.venv\Scripts\python.exe -m pytest -o addopts='' --basetemp C:\Work\rvfinal
  tests/test_desktop_bundle.py tests/test_app_launch_settings.py tests/test_workspace.py
  tests/test_rom_projects.py tests/test_rom_studio_ui.py tests/test_expert_lifecycle_desktop.py
  tests/test_source_installation.py tests/test_source_installation_integration.py
  tests/test_guided_mission.py tests/test_guardian_recovery_windows_launcher.py
  tests/test_guardian_recovery_runtime_adapter.py`
- Final result: **250 passed, 4 failed, 2 skipped in 314.90s**.
- Two failures are POSIX mode-bit assertions, one is the Windows ZIP fixture, and one launcher
  handle/path check failed once in the combined run then passed immediately when reproduced alone
  (**1 passed in 0.45s**). The latter is reported as transient evidence for independent review,
  not silently treated as a pass. The two skips are Linux-only sealed-memfd tests.

### Simulated Guided journey

The inert local simulation completed:
`Scan → Match → Prepare → Consent → Result → Reassessment → Verification`.

- Exact simulated `popsicle`/Xiaomi identity matched the reviewed recipe.
- Prepare exposed 53 actions including 50 inert image writes.
- Declining consent sent zero mutating commands; later acceptance remained explicit.
- Result was durably recorded; no wipe, relock, retry, or physical command occurred.
- Independent boot observation was stable for 60 simulated seconds over 11 samples; the audit and
  unchanged receipt were verified without automatically promoting the installation result to
  boot-verified.
- Guided and Expert retained the same `SourceOperationSession`; reopening history sent zero
  commands and made zero additional changes.
- Evidence report:
  `C:\Work\ROMVERSE-Windows-Guided-Simulation-20260907\simulation-report.json`.
- Receipt SHA-256: `e5a8a09ee3119a40d32cc938983ddd3932561fbfbd2f01f9c58211034a814bff`.

### Remaining failures and precise next proposal

No remaining failure blocks the unsigned desktop application from building, opening, persisting a
workspace, navigating, or completing the inert journey. The next bounded task, only after Product
Assurance approval, should make the remaining test fixtures platform-aware: use Windows ACL
semantics instead of POSIX mode bits, construct an actually ambiguous ZIP member without Windows
writer normalization, and investigate/repeat the transient launcher identity comparison without
weakening fail-closed behavior.

### Safety and scope confirmation

- Guardian-only authority, exact-device evidence, separate consent, UNKNOWN-on-uncertainty, no
  blind retry, independent verification, feature freeze, and permanent no-relock remain intact.
- No phone connection or operation, Recovery command, APK installation, production adapter,
  physical execution, production signing, application publication, or release occurred.
- Protected Companion files were not edited, staged, discarded, tested, or committed.
- No force-push was used.

## Authoritative Windows launcher checkpoint

- Commit: `ea292e75db8de3d2ed44feb0e8fb070c70ebf849`
- Title: `Add Windows trusted Recovery launcher contract`
- Deterministic coverage commit: `7124a89aefac8cf6e957a0805d4576f2a960ea0c`
- Base: `fdb1692b0a5056cce0992b9045cd6f3a55cabf97` (`Approve Stage 1 closure audit`)
- Branch: `windows-launcher-authorized-work`
- Stage: Stage 1 — Windows trusted-launcher anti-TOCTOU correctness contract
- Build status: implemented, committed, independently reproduced on Windows and fully regression-
  tested on Linux; Product Assurance review pending

### Exact changes

- Added `WindowsSubprocessRecoveryAdapterProcessRunner` behind the existing package/request/timeout
  process-runner protocol.
- Revalidates the signed package, platform, exact artifact name, byte length and SHA-256 before
  opening the Windows launch boundary.
- Rejects reparse path components, non-regular files and hard-linked artifacts.
- Opens the exact artifact with `CreateFileW`, without following the final reparse point, while
  denying write/delete sharing; the handle remains open through process creation.
- Binds the path and open handle to the same device/inode, link count, size, modification time and
  creation time immediately before dispatch.
- Preserves fixed protocol arguments/environment, no shell, bounded request/output, bounded timeout,
  no automatic retry and UNKNOWN-on-ambiguous-result behavior.
- Requires the exact platform launcher class for production-trust packages; test-only fake runners
  remain explicitly separate.
- Added the normative Windows launch contract and deterministic adversarial tests.
- Added no production adapter enrollment, UI, consent, physical execution or phone integration.

Files in the implementation commit:

- `src/romverse/guardian/recovery_runtime_adapter.py`
- `docs/WINDOWS-RECOVERY-LAUNCH-CONTRACT.md`
- `tests/test_guardian_recovery_windows_launcher.py`

### Verification evidence

Host: Windows 11 x64, Python 3.12.10, pytest 9.1.1.

- Focused Windows launcher contract tests: **21/21 passed**.
- Combined affected Recovery launcher/package/runner regression: **61 passed, 2 skipped** from 63
  collected tests. This total includes the 21 focused tests and is not added to it.
- Existing affected regression excluding the focused file: **40 passed, 2 skipped**.
- The two skips are existing Linux-only sealed-memfd path-substitution and timeout tests; they are
  not claimed as Windows evidence.
- Linux Build independently reproduced the exact pushed checkpoint at
  `f94bd7389526d373f6233ceb41406e7ae3b4fc9a` on Fedora 44, kernel 7.1.13, Python 3.14.7:
  - Combined affected Recovery regression: **61 passed, 2 skipped** from 63 collected tests. The
    skips are the two Windows-host-specific handle-identity and sharing-lock cases.
  - Full Linux Python regression: **2,899 passed, 2 skipped** from 2,901 collected tests. The
    affected 61-pass result is a subset of this total and is not added again.
- Linux Build also reran the combined affected suite over authenticated SSH on the real Legion and
  independently reproduced **61 passed, 2 skipped**. This is the same suite already reported above,
  so it is corroborating evidence and is not counted again.
- Ruff lint and formatting checks for the launcher source and new tests: passed.
- Git whitespace/diff check: passed.
- An optional full-repository Windows baseline was stopped after 67% when an unrelated integration
  test stalled. It had already exposed numerous pre-existing Windows/platform-fixture failures
  outside this slice, so it is not reported as a passing or completed regression.

### Classification and limitations

- Implemented: Windows trusted-launcher anti-TOCTOU software boundary and contract.
- Windows-hosted deterministic verification: yes. Tests exercised real Windows file-handle,
  hard-link and replacement-lock behavior with inert local bytes; process dispatch used fakes.
- Linux regression: full suite passed at the exact pushed checkpoint; the two Windows-only cases
  were skipped honestly and are covered by genuine Windows-hosted evidence.
- Production adapter verified: no.
- Physical Android hardware verified: no.
- Released or published: no.

Passing these tests does not claim that a production Recovery executable or phone command ran. It
does not open production enrollment, physical execution, hardware verification, release or
publication gates.

### Guardian and safety invariants

- Guardian remains the only higher-level execution gate.
- Callers cannot supply executable paths, commands, arguments, environment overrides or retries.
- Start failure is attempted once only.
- Timeout, truncation, malformed/ambiguous results and contradictory identity become failure or
  `UNKNOWN`, never inferred success.
- Bootloader locking/relocking remains permanently prohibited with no override.
- Protected Companion files were not edited, staged, discarded, tested or committed.

### External actions

- Physical phone operation: none.
- Recovery command execution: none.
- Package/APK installation: none.
- Physical execution enablement: none.
- Production adapter enrollment: none.
- Publication/release: none.
- Working branch publication: `origin/windows-launcher-authorized-work` only; no force-push,
  release or publication of an application artifact.
- Companion source change: none.

### Product Assurance review requested

Review implementation commit `ea292e75db8de3d2ed44feb0e8fb070c70ebf849` and deterministic coverage
commit `7124a89aefac8cf6e957a0805d4576f2a960ea0c` against
`docs/WINDOWS-RECOVERY-LAUNCH-CONTRACT.md`, particularly Windows handle-sharing semantics,
reparse/hard-link rejection, final path-to-handle identity, fixed process surface, timeout/output
uncertainty and production/test launcher separation. Do not begin another feature or consequential
slice until this review is complete.

## Historical Stage 1 closure checkpoint

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
