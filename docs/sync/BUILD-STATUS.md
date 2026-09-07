# ROMVERSE Build Status

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

- Commit: `3b61639e16ee21e033ed8eb17cb6b35065142992`
- Title: `Audit Stage 1 closure evidence`
- Stage: Stage 1 — v0.2 Golden Foundation closure audit
- Milestone: read-only closure assessment after Future-proofing 3/3
- Build status: audit committed; Product Assurance review required before another consequential slice
- Working tree: only the three pre-existing unrelated Companion modifications remain. The audit did
  not edit, stage, discard, test, or commit them.

## Exact changes

- Added `docs/STAGE-1-CLOSURE-AUDIT_2026-09-06.md`.
- Audited the authoritative Stage 1 and Guided Experience requirements against the committed
  Recovery chain, current source boundaries, tests, retained-schema inventory, three future-proofing
  checkpoints, and Product Assurance history.
- Confirmed the complete software separation of Recommendation, Preparation, Fresh Live Target,
  Consent, Executor, Durable Result, Recovery Reassessment, and Verification.
- Confirmed that the production app can continue an existing durable Recovery result but does not
  construct or enroll the governed Recovery adapter runner for physical execution.
- Confirmed that the current concrete trusted launcher is Linux-only: it rejects non-Linux hosts and
  depends on `memfd`, `/proc/self/fd`, `fcntl`, `pass_fds`, and process-group signals.
- Identified the previously approved Windows trusted-launcher anti-TOCTOU correctness contract and
  deterministic tests as the smallest remaining software gap.
- Made no application, test, schema, UI, Companion, asset, package, or execution change.

## Classification

- Implemented: the audit document only. The previously committed Linux software chain and
  Future-proofing 3/3 remain implemented.
- Simulated/Tested: no new execution or test run was performed for this documentation-only audit.
  The audit relies on the immediately preceding verified checkpoint's full **2,880/2,880** Python
  result and preserved Product Assurance evidence without recounting historical suites.
- Hardware Verified: no.
- Released: no.

## Verification evidence

- Immediate preceding implementation checkpoint `b9afd9f`: full Python regression
  **2,880/2,880 passed**.
- Its affected firmware/source regression **223/223** and new adversarial cases **11/11** are subsets
  of that full total and are not added again.
- Git history contains committed and approved boundaries for preparation, live target, consent,
  execution admission, per-step durable journal, trusted adapter protocol, aggregate result,
  same-incident reassessment, fresh boot verification, app-owned continuation, durable schemas,
  neutral contracts, and the bounded source-evidence registry.
- Audit Markdown and Git whitespace check: passed.
- Approved production assets were not edited and remain byte-exact at the prior verified hashes.

## Blockers and remaining limitations

- Windows trusted Recovery launch and anti-TOCTOU correctness are not implemented or verified.
- Controlled physical Android Recovery execution and post-repair verification have not been run.
- No production-signed Recovery adapter artifact, client trust enrollment, or app execution wiring
  exists; only test adapters and inert transports exercise the architecture.
- Android instrumented and physical Companion behavior remain outside this audit and unverified.
- v0.2 Golden Foundation remains closed.

## Guided friction and dead ends

- No new Guided dead end was found in the implemented software continuation. The same incident
  survives the complete evidence chain; wrong/missing phones wait, while FAILED and UNKNOWN stop
  without retry.
- The absence of a production physical Recovery runner is a truthful release boundary, not a
  circular Guided checklist. It must remain visible as unavailable until independently proven.
- No Guided screen, dialog, confirmation, route, or wording changed in this audit.

## Guardian, Recovery, and safety implications

- Guardian remains the only execution gate.
- Evidence, consent, and command completion remain insufficient to claim Recovery.
- FAILED and UNKNOWN remain distinct, durable, and non-retry states.
- Exact-device and same-incident attribution remain mandatory.
- Bootloader locking/relocking remains permanently prohibited with no override.
- The audit grants no authority and does not enable physical or Windows execution.

## Platform status

- Linux/Fedora: software chain and full Python regression verified at the preceding checkpoint.
- Windows: trusted-launcher contract and genuine Windows verification remain outstanding.
- Android physical hardware: not run for this Recovery chain.

## Feature-freeze and version-gate impact

- 5 September 2026 pre-v1.0 feature freeze: compliant. This is documentation-only analysis and adds
  no feature, UI, route, format, vendor, adapter, device operation, or release capability.
- Future-proofing checkpoints: **3/3 complete and Product Assurance approved**.
- v0.2 Golden Foundation: remains **CLOSED**.

## Next proposed Build task

After a new Product Assurance approval, implement only the previously approved Windows
trusted-launcher anti-TOCTOU correctness contract and deterministic Linux-hosted software tests.
The slice must preserve the existing process-runner interface, exact verified package binding,
fixed protocol/environment, bounded I/O, UNKNOWN-on-uncertainty, no retry, and no relock. It must not
launch a phone command, wire production execution, add UI, claim Windows verification, publish, or
release.

## External actions

- Physical phone operation: none.
- Package/APK installation: none.
- Publication/release: none.
- Remote push: none.
- Website change: none.
- Source-data migration: none.
- Companion source change: none.
- Application source change: none.
- Local action: read-only repository inspection followed by one documentation-only audit commit.

## Product Assurance Review Requested

- Confirm or correct the audit's Stage 1 evidence matrix and closed-gate conclusion.
- Confirm the production-runner absence is correctly classified as a deliberate unimplemented
  release boundary rather than a Guided navigation defect.
- Approve, narrow, or reject the Windows trusted-launcher anti-TOCTOU correctness contract as the
  next smallest Stage 1 software slice.
