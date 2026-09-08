# ROMVERSE Product Assurance Sync

## Linux checkpoint — runnable Stage 1 desktop and Guided journeys

### Authoritative checkpoint

- Source checkpoint: `fc342914868a938f7ba9dfc5108a01f130a1b43a`, including the newly completed
  external-package evidence boundary.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, runnable Fedora Desktop and inert Guided acceptance.

### Product result

- The actual current source application launched through the documented `python -m romverse`
  entry point, initialized a new isolated workspace and remained stable. Its visible acceptance
  instance is running from `build/visible-stage1-fc34291`; ADB and Fastboot were deliberately absent
  from that process environment, so it cannot scan or operate a physical phone.
- The documented installed-style smoke initialized a fresh workspace, loaded 22 verified Device
  Packs, 170 known fixes and 281 offline evidence records, exposed all 19 desktop routes, exercised
  the actionable Time Machine empty state, created a project/working copy/snapshot and reopened all
  tracked bytes exactly.
- The representative inert Guided Recovery journey completed the existing production boundaries:
  Scan → Match → Prepare → Consent → Result → Reassessment → Verification. Three test-only adapter
  actions completed; result and reassessment remained distinct from final verification. No external
  process, production adapter, persistent test trust, automatic retry or physical target existed.
- Every current top-level navigation destination, Guided-visible nested feature, Command Deck launch
  card, exact owner/return handoff, Guided/Architect shared state boundary and representative no-tool,
  no-phone or stale-evidence action was exercised through the targeted real-widget acceptance set.
  All visible tested actions either performed their inert/read-only function or presented their
  existing truthful actionable boundary. No new inert button, crash, silent failure, navigation loss
  or Guided dead end was found.

### Verification without double-counting

- Actual source entry release-smoke startup/shutdown: **passed**.
- Installed-style production smoke: **passed once**. This is acceptance-harness evidence, not added
  to the pytest count.
- Manual inert Guided Recovery script: **passed once**. Its matching pytest coverage was included in
  the targeted test run and is therefore not counted again.
- Targeted desktop/navigation/action regression: **108/108 unique tests passed** in one combined
  run. It covered navigation vocabulary, command palette, workspace shell, app launch/settings,
  dashboard rendering, Guided Recovery simulation and candidate-installation Desktop behavior.
- Frozen executable launch smoke: **passed once**.
- No full Python suite, repeated packaging loop, screenshot loop or physical-device suite was run.

### Runnable Fedora development artifact

- Built once on Fedora 44 x86-64 with Python 3.14.7 and PyInstaller 6.22.2.
- Runnable executable:
  `build/frozen-stage1-fc34291/ROMVERSE/ROMVERSE`, SHA-256
  `9f3e225384244b121cebac56fc79d76407187201d25d99ee4a2cb22208b70a9f`.
- Portable unsigned archive:
  `dist/ROMVERSE-Desktop-0.2.0-alpha.1-linux-x86_64-stage1-fc34291.zip`,
  **150,981,736 bytes**, SHA-256
  `8b817aad6548519f02130e697935e65feb2a56371a6b23fe7301a88987280b6b`.
- Packaging verification passed for **460 files** and **360,288,306 expanded bytes**. The archive is
  a local internal-development artifact only; it was not installed, signed, uploaded or released.

### Classification and safety

- **Implemented:** current Stage 1 source plus the approved external-package evidence slice at the
  source checkpoint above. This evidence-only milestone adds no further application source change.
- **Simulated/Tested:** 108 unique targeted UI tests, two distinct desktop launch smokes, one
  installed-style smoke, one inert Guided journey and one frozen-bundle verification on Fedora.
- **Hardware Verified:** none in this checkpoint. The earlier Fastboot acceptance was not repeated.
- **Released:** no. The new package is unsigned, local and explicitly not a release.
- Guardian-only authority, consent separation, exact-device/evidence rules, UNKNOWN-on-uncertainty,
  no blind retry, independent verification and same-incident Recovery remain unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override or route.

### Guided, platform, freeze and version gate

- Guided friction/dead ends: none reproduced in the exercised no-phone, missing-tool, inert-device,
  candidate-preparation, Recovery or exact-context navigation paths. Consequential controls remain
  disabled until their own evidence/authority boundaries are earned.
- Fedora/Linux: source launch, isolated workspace initialization, persistence, all 19 routes, focused
  user actions, inert end-to-end Recovery and current frozen package verified.
- Windows: not run or claimed. Separate Windows work remains on its own branch and was not merged.
- Feature freeze: compliant. No post-v1 feature, speculative architecture or unapproved UI Design
  Lab work was introduced.
- v0.2 Golden Foundation remains **CLOSED**. This is runnable-development and simulated/inert
  acceptance, not physical execution, signing or release evidence.

### Preservation, blockers and external actions

- Protected Companion files, Windows launcher/convergence work, local UI Design Lab, website and
  unrelated user files were not modified, staged, discarded or committed.
- No Linux runtime blocker or tested Stage 1 Guided dead end remains from this acceptance pass.
  Physical-device-changing and signed-release gates remain intentionally outside this milestone.
- Physical phone access, ADB/Fastboot invocation, APK action, file transfer, flash/boot/update,
  partition access, slot change, erase/wipe/format, unlock/lock/relock, root/debloat, production
  signing, installation, publication and release: **none**.
- External network action after verification: one normal push of this handoff to the existing Linux
  branch only; no force-push and no publication.

### Next proposed Build task

Continue with the next concrete Linux usability defect only when repository evidence identifies one.
Do not manufacture a rebuild/test loop, merge the isolated UI Design Lab, operate a phone or cross a
new consequential boundary without its own authorization.

### Product Assurance Review Requested

- Confirm the source, installed-style, navigation/action, inert Guided and frozen-bundle evidence is
  sufficient for the current runnable Linux Stage 1 development milestone without re-running a full
  suite.
- Confirm the intentionally tool-less visible launch preserves the no-phone boundary while giving
  Steve a real current application to inspect.

## Linux checkpoint — bounded external-package metadata and untrusted-procedure inventory

### Authoritative checkpoint

- Product Assurance authorization/base: `c0de9b2` — approved corrected Fastboot round trip, with
  this package-evidence task queued after the separate Windows convergence handoff.
- Windows convergence prerequisite: `3936d934224294544981c505aba98275c910cd60` exists on
  `origin/assurance/windows-core-convergence`; it was inspected as a prerequisite only and was not
  merged or modified by this Linux checkpoint.
- Tested implementation commit:
  `bc6e0ef66399df2fbfed0e9418c8d8931c254122` — `Inventory external package evidence safely`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, bounded read-only external package evidence.

### Exact implementation

- `ExternalFirmwareIntakeService` now inventories only four root-level, case-insensitive metadata
  names from the already admitted and hashed ZIP descriptor: `BUILD-INFO.txt`,
  `CUSTOMIZATION-MANIFEST.tsv`, `SHA256SUMS` and `android-info.txt`. Each admitted member records
  exact path, bounded size and SHA-256. Only an explicit identity-field allowlist can be parsed;
  every parsed value remains package-declared and unverified.
- `.sh`, `.bat`, `.cmd`, `.ps1` and the Android updater-script path are recorded separately as
  untrusted procedure presence by exact path, bounded size and SHA-256 only. Procedure bodies are
  never persisted, parsed into actions, adopted as routes or executed.
- ZIP directories are safely ignored. Relevant ambiguous/case-folded duplicate paths, unsafe paths,
  symlink/special-file entries, encryption, malformed or non-UTF-8 metadata, duplicate identity
  declarations, bounded-size/count overflow, command-like or relock identity text, and a declared
  SHA-256 mismatch reject before either durable receipt is written.
- The strict inventory loader rejects extra/hidden fields, boolean schema confusion, unbound
  manifest paths, malformed members, source-receipt drift and altered record digests. It grants no
  build, device or execution authority and permanently records bootloader relock as `never`.
- ROM Studio renders metadata claims as `UNVERIFIED`, procedures as `NEVER EXECUTED`, and the full
  build/install/Guardian/flash boundary as `LOCKED`. The untrusted evidence label is forced to plain
  text so package values and paths cannot become UI markup.
- The durable-schema compatibility inventory now declares both the existing external intake receipt
  and the new external package metadata record as version-1, strict, fail-closed evidence formats.

### Deterministic verification

- `tests/test_external_firmware_intake.py`: **19/19 unique tests passed**.
- `tests/test_rom_inspection.py`: **32/32 unique adjacent regression tests passed**.
- `tests/test_durable_schema_inventory.py`: **6/6 unique schema checks passed**.
- Total: **57/57 non-overlapping tests passed**. No broad suite was run or double-counted.
- Ruff static check: **5/5 changed source/test files passed**.
- Ruff format check: **5/5 changed source/test files passed**.
- `git diff --check`: passed.

### Real source evidence

- One permitted read-only reinspection used the existing in-place file
  `adbb99b9d6e6c3e6-HyperOS4-Xiaomi17ProMax-Debloated-CustomRom.zip`; it was not copied, extracted,
  modified or reopened through a replacement path.
- Exact source: **11,797,532,065 bytes**, SHA-256
  `adbb99b9d6e6c3e62520c144d8b841ff6f34543feddf2969cfc38f4acf90f89a`, complete ZIP inspection,
  68 entries, zero critical findings and zero warnings.
- The package contains no member from the four-name metadata allowlist. Therefore it produced no
  package identity facts and no manufacturer, device, build, Android, region, channel or base claim.
  That absence remains explicitly `UNCONFIRMED`; ROMVERSE does not infer identity from procedure
  names or contents.
- Eleven untrusted procedure members were inventoried: four `.sh`, five `.bat` and two `.ps1`
  files. The exact durable list retains only path, size and SHA-256; it contains no procedure body.

| Package-relative path | Bytes | SHA-256 |
| --- | ---: | --- |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/flash_all.sh` | 5,330 | `589afffba7bc1e3528f936caeb9fe3bfd43da8d4017d0b5d4562c6f9e2be41ac` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/flash_all_except_data_windows.bat` | 211 | `f4b58a3dc91d5a0d66a41c6439c332c6b5bf71c78ee664bed2c4bbdbe7cfd4bb` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/flash_all_windows.bat` | 134 | `974945bf7168b7d1e53016a749cbfe08f24a4c8a9ae9f90056e52b0e075385e4` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/post_boot_check.ps1` | 1,461 | `b451a9ac15f9c3af8a0d16ebd878d5c52279014b7b03383b9c94bec1869739f0` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/post_boot_check.sh` | 1,239 | `a78ca4a8c8dadcc2879d8c0e964ae3f61899e345cba97837903d1b4dffd7341f` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/post_boot_check_windows.bat` | 145 | `b8c077cdcaf685f610f84b21a24eda0f3f73a9fac63f57d92ede493066bd305e` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/repair_signed_root_vbmeta.sh` | 1,353 | `760e2c855253c33e0b7adc8b59dcc65041801fdf2f25efbba7c86babcb932817` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/verify.bat` | 223 | `650ffb3c955a745d6b4e8f42197fe37d34ff67fdd0b1f6c0b058a638bda59d82` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/verify.ps1` | 1,139 | `9886ee971c960dea27e4559f0908f2d8505cd1f2b7f86c16f883651fc53b875d` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/verify.sh` | 294 | `19fb9dc3af66d882c38e1cd634a8ab35500df1d0be19cbc49f22ec64903d53c3` |
| `outputs/popsicle_OS4.0.0.23_AA_Gboard_Themes_Chrome_BOOT_TESTED/windows_flash_common.bat` | 4,061 | `d7736caeafe87d466908463a8b15efeca67da09e879fed7a648f26892859e9cb` |

- Inventory digest: `6613af442b27157a4116fc150e5a1f72e7cf7602c3d7453a520055215d7e0b54`.
- Durable external intake receipt digest:
  `782b1e5e2ca167e71d72939b611e35c242bbe30d607fec48578e998e91a755f2`.
- Evidence was written only inside the ignored disposable workspace
  `build/external-metadata-inventory-c0de9b2`; the external package stayed at its original path.

### Classification and safety

- **Implemented:** strict metadata/member inventory, procedure-presence evidence, durable loader,
  locked/plain-text ROM Studio presentation and schema declarations.
- **Simulated/Tested:** 57 deterministic tests on Fedora Linux plus one production-service read of
  the real external package.
- **Hardware Verified:** none in this checkpoint. No phone, emulator, ADB or Fastboot target was
  accessed. The earlier approved Fastboot round trip was not repeated.
- **Released:** no. Nothing was packaged, installed, signed, published or released.
- Guardian-only authority, exact evidence, UNKNOWN-on-uncertainty, no blind retry, independent
  verification and same-incident Recovery rules are unchanged. The inventory is evidence-only and
  cannot create a build, consent, live-target, Guardian, Recovery or execution route.
- Bootloader locking/relocking remains permanently prohibited and has no valid path.

### Guided, platform, freeze and version gate

- Guided now exposes the useful evidence without adopting package procedures or creating another
  decision. No new Guided loop or dead end was found; absence of recognized metadata remains calm
  and truthful rather than being labelled incompatible.
- Fedora/Linux: implementation, UI boundary, durable reload and real-source service path verified.
- Windows: not run or claimed here. The separate Windows convergence checkpoint was only confirmed
  present on its remote branch.
- Feature freeze: compliant. This is the previously approved minimum evidence/correctness slice;
  it adds no format/vendor support, dynamic route, adapter, device command or execution capability.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance review and later explicitly
  approved boundaries.

### Preservation, blockers and external actions

- Protected Companion files, Windows launcher/convergence source, website, Adaptive work and all
  unrelated user files were not edited, staged, discarded or committed.
- Remaining limitation: the real package supplies no allowlisted metadata identity. Its relationship
  to any phone/source contract remains unconfirmed, and all consequential controls remain locked.
- Physical phone operation, ADB/Fastboot command, APK action, file transfer, firmware execution,
  flash/boot/update, partition read/write, slot change, erase/wipe/format, unlock/lock/relock,
  root/debloat, package installation, signing, publication and release: **none**.
- External network action after verification: one normal push of the scoped implementation and
  handoff commits to the existing Linux branch only; no force-push and no unrelated push.

### Next proposed Build task

Stop for independent Product Assurance review. Do not adopt any inventoried procedure, infer package
identity, operate a phone or begin another consequential Stage 1 slice.

### Product Assurance Review Requested

- Confirm the four-name metadata allowlist, strict identity fields and failure behavior preserve the
  evidence-only boundary without turning absence into incompatibility.
- Confirm that retaining procedure path/size/hash only, combined with plain-text UI and zero
  authority, closes the approved untrusted-procedure inventory milestone.

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
