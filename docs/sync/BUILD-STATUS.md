# ROMVERSE Product Assurance Sync

## Linux product checkpoint — packaged simulated Guided journey reaches the locked Forge handoff

### Authoritative checkpoint and scope

- Product Assurance approval/base: `5d3e36fdb8a3bf436a7e078e8f72d5504da45173` approved one
  explicit, no-phone packaged Fedora journey through Device DNA, safest customization, project
  preparation, Build Readiness and the existing local dry-run/Forge handoff.
- Implementation commit: `d10500eea47bb88e870db70cff5b74069cfa3c7c` — `Enable explicit
  packaged Device DNA simulation` on `linux/stage1-desktop-readiness`.
- Exact source files: `src/romverse/app.py`, `src/romverse/ui/main_window.py`,
  `tests/test_desktop_bundle.py`, and `tests/test_development_device_simulation.py`.
- Stage: Stage 1 — v0.2 Golden Foundation, explicit ROM Studio-only development simulation and
  connected packaged Guided-to-Forge evidence only.

### Minimum correction

- The first real packaged dead end was the absence of any normal visible way to initiate the
  already-supported deterministic Device DNA simulation. A hidden
  `--development-device-simulation` launch flag now supplies one fixed `simulation`-transport
  Xiaomi/popsicle fixture to ROM Studio only.
- The development session is unmistakably labelled **Development simulation**, **Device:
  deterministic ROM Studio fixture**, **SIMULATION ONLY • NO HARDWARE**, and **No physical device
  selected**. Periodic physical scanning is disabled for this launch mode.
- A simulated scan empties the observed physical-device collection and selected serial, never
  invokes Device Engine, and passes the fixture only to ROM Studio. APK Installer, Terminal and
  general device surfaces remain empty. A non-simulation fixture is rejected at construction.
- The resulting Device DNA records `device.simulation`, classifies Guardian flash as
  `UNCONFIRMED`, and keeps bootloader relocking permanently `UNSUPPORTED`. It grants no live-target,
  consent, Guardian, Recovery, signing, install or execution authority.

### Exact packaged journey

- One PyInstaller one-folder development build was produced on Fedora 44 with Python 3.14.7 and
  PyInstaller 6.22.2. Executable:
  `build/linux-pa-simulated-5d3e36f/frozen/ROMVERSE/ROMVERSE`, 6,322,320 bytes, mode `0755`,
  SHA-256 `7f6f061cc4cc20ecff20ea974466ae3fe654d17cc48f2196c0298cbad5e87929`.
  It remains an ignored local development artifact and was not published or released.
- The package ran unelevated through Fedora XWayland against the isolated workspace
  `/run/media/stevetherad/Data/ROMVERSE-Packaged-Simulation-5d3e36f`. USB inventory showed no
  Android phone before and after the journey.
- Normal visible actions completed Command Deck → new ROM project → protected firmware import →
  contained working lab → simulated Device DNA → **Keep verified base unchanged • Recommended** →
  source-scoped toolchain → deterministic Build Readiness plan → Forge Control local handoff.
- The user-supplied source
  `/home/stevetherad/Downloads/popsicle-ota_full-OS4.0.0.32.XPBCNXM-user-17.0-9c98b42553.zip`
  was copied into the isolated workspace as a protected original: 9,110,512,435 bytes, SHA-256
  `24bf9292a19b95c0b3d1db62853491d8bf0e967d6e4c24052cea6c5684e2960e`. The original Downloads
  file was not modified.
- The only missing source-scoped dependency was Payload Dumper. The existing visible
  **Install and verify requirements** action downloaded version 2.0.2 into the isolated private
  workspace from its official GitHub release, verified archive SHA-256
  `8d81854caeacd9223a6882340959869b0a210d44a1e597329830713abd2b4dcc`, and bound executable
  SHA-256 `6e87cedaf0a5fb821a0721a071e942ae6e9957233b28346b35d87f02cb85321d`.
  There was no administrator prompt, global `PATH` change or system-wide installation.
- The exact local plan is `local_only: true`, `flashable: false`, `execution_locked: true`, and
  `execution_authority: none`. Forge Control verified a 58-partition source-bound OTA blueprint,
  recognized the unchanged protected OEM-signed baseline as the local candidate, and rendered
  **SIGNING READY / INSTALL NOT STARTED / FLASH NOT AUTHORIZED**.
- Genesis then rendered **13 of 13 local build stages verified • 2 optional install stages
  deferred**. The verified local handoff was saved and the application closed normally. No
  installation preparation was opened and no new ROMVERSE-signed or flashable artifact was emitted.

### Verification without double-counting

- Final directly affected regression selection: **4/4 passed** — the explicit phone-neutral
  release-smoke flag, inert simulation fixture, ROM Studio-only scan isolation, and rejection of
  forged simulation success evidence bound to another tree.
- Ruff and Git whitespace validation passed for all four changed files. Earlier overlapping runs
  and the visible acceptance journey are not added to the pytest total.
- Durable project evidence records seven local activity events: protected import, contained working
  copy/extraction, two local Project Vault checkpoints, dry-run plan creation and exact plan
  verification. Forge Control additionally committed the source blueprint and refreshed Device DNA
  and Compatibility Matrix evidence.
- The final readiness report has ten passing local/build/signing gates, three attention-only future
  flash/recovery inputs and five blocked physical/release gates. `local_candidate_ready` and
  `signing_ready` are true only for the unchanged protected OEM baseline; `flash_ready` is false.

### Classification, failures, safety and gates

- **Implemented:** explicit hidden development-simulation launch mode, visible simulation labelling,
  ROM Studio-only injection and physical transport isolation.
- **Simulated/Tested:** 4/4 focused software checks plus one genuine packaged Fedora GUI journey
  using deterministic simulated Device DNA. The firmware source and local file operations were
  real; the phone identity was simulated.
- **Hardware Verified:** no. No Android phone was connected or operated.
- **Released:** no. The desktop artifact is unsigned, local and ignored by Git.
- **Failure retained:** the first packaged acceptance attempt crashed in Qt's accessibility cache
  while an external AT-SPI client was simultaneously traversing the widget tree and issuing the
  Guided-entry action. The fault log preserves the full segmentation-fault trace. The unchanged
  package was restarted once; the complete journey then succeeded using native pointer events and
  ended with a clean-close record. This checkpoint does not erase, reclassify or claim to fix the
  accessibility crash.
- Guided friction/dead ends: the missing visible simulation entry is fixed. The final ROM Studio
  handoff copy says `NO BUILD OR PHONE ACTION STARTED` after local build evidence exists; phone
  safety is truthful, but the build half is stale status copy and remains a non-blocking polish
  defect. No silent functional dead end remained in the bounded journey.
- Guardian/Recovery/safety: simulation stays evidence-only; exact-device authority is absent;
  `guardian_flash` remains `UNCONFIRMED`; flash, physical validation, battery and boot-state gates
  remain closed. UNKNOWN/no-blind-retry, exact incident attribution, independent verification,
  Guardian-only authority and permanent no-relock are unchanged.
- Linux/Fedora: packaging, focused tests and the packaged GUI journey were genuinely verified on
  Fedora 44/XWayland. Windows was not run. Physical Android remains unverified.
- Feature freeze: compliant minimum Stage 1 continuity correction; no Device Pack, adapter,
  autonomous route, production execution, Recovery execution, signing, release or product-feature
  expansion was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all physical, Windows,
  accessibility and release gates.
- External actions: one official Payload Dumper archive was downloaded into the isolated private
  workspace. The scoped branch is pushed normally with this checkpoint. No phone operation,
  ADB/Fastboot device dispatch, APK installation, system/global package installation, firmware
  signing, Guardian/Recovery execution, publication, release, merge, force-push, lock or relock
  occurred.

### Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice until the
verdict for this exact packaged simulated Guided checkpoint is recorded in
`docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm the explicit ROM Studio-only simulation boundary, focused tests and visible 13/13 local
  build result satisfy the approved connected packaged journey without granting physical authority.
- Independently classify the retained Qt/AT-SPI accessibility crash and decide whether a separate
  bounded asynchronous-dialog/accessibility correction and one focused packaged reproduction are
  required before another product slice.
- Confirm the unchanged protected OEM baseline is a valid local-candidate/Forge handoff stop despite
  no separate unsigned Forge Bundle being emitted, and whether the stale post-build handoff copy
  should be corrected within the next bounded UX continuity checkpoint.

## Linux product checkpoint — packaged Platform Tools self-repair reaches no-device readiness

### Authoritative checkpoint and scope

- Product Assurance approval/base: `332767e0a934018861731ee6ad581bf27eaff9c7` approved one
  packaged, fresh-workspace Fedora journey through the existing visible **Resolve Platform Tools**
  action. No application source change or second package build was authorized or required.
- Exact unchanged executable: `build/linux-pa-17c133f/frozen/ROMVERSE/ROMVERSE`, SHA-256
  `7ad1064eacaaae66f9e5c62f1c4431f59f8665ca3bce88f17254374c03f59b52`.
- Exact unchanged unsigned ZIP: `dist/ROMVERSE-Desktop-0.2.0-alpha.1-linux-x86_64-17c133f.zip`,
  SHA-256 `6d15d8b9557cfe09ac9f4e6cb91753d3a63fd8a1d6c5a4b2a1d0e11464376959`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing packaged private Platform Tools self-repair
  and Device Engine no-target readiness only.

### One visible packaged journey

- USB inventory confirmed no Android phone was connected before launch. The exact packaged app
  ran once, unelevated, through Fedora XWayland against the fresh isolated workspace
  `/tmp/romverse-tools-selfrepair-332767e` with an intentionally empty discovery `PATH` and no
  managed tool directory.
- Command Deck initially rendered **Device Engine needs attention**, truthfully stated that verified
  Android Platform Tools were not active and exposed one enabled **Resolve Platform Tools** action.
- One native accessibility **Press** on that existing action opened `ROMVERSE • Start Device
  Engine`. Its visible plan selected only ADB through the single ROMVERSE-managed Platform Tools
  package; no manual source, operating-system package, administrator prompt or global installation
  was selected.
- Existing automatic verified-tools preference began the bounded official download and verification
  without another confirmation chain. The dialog showed **Downloading and verifying official
  platform-tools…**, then closed automatically after success and refreshed the runtime inventory in
  the same process. No terminal instruction, application restart or global `PATH` change was needed.
- Command Deck repainted from missing tools to the truthful final state: **No device connected**,
  **No Android device detected**, **No Android transport is visible**, and an enabled **Scan for
  device** action. The missing-Platform-Tools warning was gone; Device Engine did not crash or leave
  a silent dead end.
- A standard `WM_DELETE_WINDOW` close exited the packaged process with code 0. No ROMVERSE or
  Fastboot process remained, and `logs/crash/runtime-fault.log` contains only runtime start followed
  by runtime closed cleanly.

### Exact package, receipt and executable evidence

- Official package source:
  `https://dl.google.com/android/repository/platform-tools-latest-linux.zip`.
- Downloaded archive: 9,054,187 bytes; SHA-256
  `d230f13842f60f782a8645f9c813f8f845bf36089ea7289f28c48f17979313f1`.
- Private receipt:
  `tools/downloads/platform-tools/managed-package.romverse`, schema 1, mode `0600`, SHA-256
  `c741176ed5a97bbbcd384a0eb86491a069883ca19357312c8e8ddb5ca0002c77`.
- Private package root is mode `0700`. Managed ADB is 10,642,368 bytes, mode `0700`, version
  `37.0.1-15733141`, SHA-256
  `a902be8f45c6c62e76c9efaf6947a0fa747c9cabd89a2ac8e0d16ecb30b3ed01`.
- Managed Fastboot is 3,333,552 bytes, mode `0700`, version `37.0.1-15733141`, SHA-256
  `a686e2c7e8dc9cf4cba0cb8a2eef05f7b2bd682c925abd032fe203215d80b618`.
- The receipt's source, archive digest and exact two executable digests match the observed files.
  The durable install plan records Linux, required/selected tool `ADB`, the official Android
  Platform Tools documentation source, no manual requirement and contract-scoped managed policy.

### No-target audit and classification

- ROMVERSE's hash-chained Guardian audit contains **34/34 allowed read-only host discovery
  records**: 17 `adb devices -l` and 17 `fastboot devices -l`. Every record has category
  `read_only`, risk `none`, target `host`, successful result and continuous sequence/previous-hash
  linkage. First record hash: `e02b7c75fab56ca2953ce6b15af05bd5dcd9e1bb953073075dd8764c97d80f51`;
  final record hash: `395f1a98f8ce890f7d8a785e68ba833ad30a806a8b534871597c64a2bd5bc041`.
- No record contains a device serial or any install, reboot, flash, erase, wipe, lock or relock
  operation. Direct ADB/Fastboot version queries recorded versions only and targeted no hardware.
  The pre-existing idle host ADB server retained its original PID; no phone was discovered.
- **Implemented:** no new source behavior; the established packaged private self-repair path is now
  evidenced end to end on the current approved Fedora artifact.
- **Simulated/Tested:** one genuine packaged GUI/network/private-install/repaint/clean-close journey
  in an intentionally no-phone environment. No pytest or previous package suite was replayed or
  double-counted.
- **Hardware Verified:** no. Host USB was observed only to establish that no Android phone was
  connected; no device identity or phone behavior was tested.
- **Released:** no. The desktop artifact remains unsigned and local.
- Blockers/failures: none in the bounded journey. One harmless typo in an external close-driver
  command failed before interacting with ROMVERSE; the corrected standard close succeeded and is
  not classified as an application failure.
- Guided friction/dead ends: missing tools now self-repair from the existing visible action to a
  truthful waiting-for-device state in the same session, without administrator access, global
  installation, restart or terminal instructions.
- Guardian/Recovery/safety: only allowlisted host-level discovery ran. No consent, device-bound
  target, phone write, Recovery execution or flash authority existed. UNKNOWN/no-blind-retry,
  exact-device evidence, same-incident Recovery, independent verification and permanent no-relock
  remain unchanged.
- Linux/Fedora: genuinely verified on Fedora 44/XWayland. Native Wayland input automation and
  Windows were not part of this checkpoint.
- Feature freeze: compliant evidence of an existing Stage 1 self-repair journey; no source, UI,
  feature, adapter, Device Pack, signing or execution expansion.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all remaining gates.
- External actions: one official Google Platform Tools ZIP was downloaded into the disposable
  private workspace and verified. The existing branch is pushed normally with this documentation
  handoff. No phone, APK, global/system installation, ROM candidate, signing, publication, release,
  merge, force-push, device change, lock or relock occurred.

### Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice until the
verdict for this exact packaged self-repair checkpoint is recorded in
`docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm the one-click private acquisition, same-process receipt verification/runtime activation,
  truthful repaint and clean close satisfy the approved packaged Platform Tools self-repair gate.
- Confirm the 34 exact host-only discovery records remain within the explicitly authorized
  no-target scanner allowance and grant no device or execution authority.

## Linux product checkpoint — current unsigned Fedora desktop artifact and native smoke

### Authoritative checkpoint and scope

- Product Assurance approval/base: `17c133f7b10a462075cbb698169ce9ef0a72e4e0` approved the
  Forge rollover checkpoint and authorized exactly one current unsigned Linux artifact plus one
  proportional package-integrity check and isolated no-phone native smoke.
- Exact approved Git tree: `9617f42fbab7b619756b51657ed1068c84d5b0b7`; canonical
  `git archive` SHA-256: `fdd64a99b7e11d6834374becd117d9214af9aa934aacf5d734b76d3292e1a582`.
- Stage: Stage 1 — v0.2 Golden Foundation, tangible Fedora development artifact/readiness only.
- Source changes: **none**. This checkpoint reuses the established PyInstaller one-folder build,
  deterministic packaged assets and bounded ZIP verifier without redesigning packaging.

### Fresh artifact and integrity evidence

- Build host: Fedora 44 x86-64, Linux `7.1.13-200.fc44.x86_64`, Python 3.14.7 and
  PyInstaller 6.22.2. The existing release dependencies were already present; nothing was
  downloaded or installed.
- Runnable development binary:
  `build/linux-pa-17c133f/frozen/ROMVERSE/ROMVERSE` — 6,320,120 bytes, owner-executable,
  SHA-256 `7ad1064eacaaae66f9e5c62f1c4431f59f8665ca3bce88f17254374c03f59b52`.
- Unsigned development ZIP:
  `dist/ROMVERSE-Desktop-0.2.0-alpha.1-linux-x86_64-17c133f.zip` — 151,017,698 bytes,
  SHA-256 `6d15d8b9557cfe09ac9f4e6cb91753d3a63fd8a1d6c5a4b2a1d0e11464376959`.
- The established package verifier performed the one proportional integrity check: **460/460
  members accepted**, 360,324,026 expanded bytes, bounded/safe member paths, required executable
  present and full ZIP CRC validation passed.
- The ignored `build/` and `dist/` outputs remain local development artifacts and are not committed,
  published, released or represented as signed packages.

### Isolated no-phone native smoke

- The exact packaged executable was launched unelevated against the fresh disposable workspace
  `/tmp/romverse-native-smoke-17c133f-xcb` on the real Fedora desktop. Its process environment used
  a deliberately empty tool-discovery `PATH`, so packaged ROMVERSE could not resolve or dispatch
  the host's ADB or Fastboot executables.
- Live AT-SPI inspection confirmed the native `ROMVERSE Studio 0.2.0-alpha.1` main frame, current
  **Command Deck**, persisted **Guided Arcana** experience and enabled **Continue Genesis
  Sequence** entry all rendered.
- The no-device state was truthful and actionable: **Device Engine needs attention**, **Verified
  Android Platform Tools are not active yet**, and enabled **Resolve Platform Tools** / **Connect
  Device** actions were visible. Neither action was invoked, so no tool resolution, installation,
  network request or device scan began.
- One native accessibility **Press** on the existing Guided entry opened `ROMVERSE • Genesis
  Sequence`. The dialog rendered **No device connected**, **Connect by USB to scan Device DNA**,
  an enabled **Create ROM project** route and **Save & exit**. No project or ROM artifact was created.
- Standard X11 `WM_DELETE_WINDOW` events closed the Guided dialog and main window. The packaged
  process exited normally with code 0, `ps` found no remaining ROMVERSE process, and the runtime
  fault log contains only `runtime started` followed by `runtime closed cleanly`.
- A preceding Wayland automation attempt rendered the same required controls and opened Genesis,
  but Wayland blocked external focus/close synthesis. That harness attempt was terminated and the
  allowed smoke retry used the same unchanged artifact through Fedora's XWayland compatibility
  path. This is an automation-platform limitation, not a claimed packaged defect or second build.

### Verification, classification and gates

- **Implemented:** one fresh unsigned, self-contained Fedora development artifact from the exact
  approved source; no application source change was required.
- **Simulated/Tested:** one deterministic ZIP integrity verification and one genuine native
  packaged GUI lifecycle on Fedora/XWayland with a synthetic empty/no-phone environment.
- **Hardware Verified:** no. No Android or other physical hardware evidence was collected.
- **Released:** no. The artifact is unsigned and local only.
- Regression evidence: no pytest suite was run or double-counted; Product Assurance explicitly
  requested the proportional artifact integrity check and native smoke instead of replaying Forge
  tests. Both final acceptance activities passed.
- Blockers/failures: none in the bounded artifact/native lifecycle. Wayland input synthesis could
  not complete external automation, so the final genuine run used XWayland and this limitation is
  reported explicitly. Native Windows and physical Android remain unverified here.
- Guided friction/dead ends: the packaged fresh-workspace route visibly offers Guided entry, local
  project creation and truthful device/tool prerequisites. No Device Engine crash, silent dead end,
  modal installation prompt or unexpected work occurred.
- Guardian/Recovery/safety: the packaging and smoke granted no Guardian, consent, device, flash,
  Recovery or execution authority. UNKNOWN/no-blind-retry, exact-device evidence, same-incident
  Recovery, independent verification and permanent no-relock remain unchanged.
- Feature freeze: compliant artifact/readiness evidence for existing Stage 1 behavior; no new
  feature, adapter, Device Pack, UI redesign, signing path or execution capability.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all remaining gates.
- External actions: the existing Git branch is pushed normally with this documentation handoff.
  No phone connection/operation, ADB/Fastboot dispatch, APK, tool download/install, ROM candidate,
  signing, publication, release, merge, force-push, lock or relock occurred.

### Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice until the
verdict for this exact artifact/smoke checkpoint is recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that the exact source/artifact hashes, one bounded integrity verifier and genuine
  no-phone packaged lifecycle satisfy the approved Fedora development-artifact gate.
- Confirm the XWayland automation limitation is accurately classified without reducing the native
  Fedora application, clean-close or zero-device evidence claims.

## Linux correction checkpoint — seamless Forge plan rollover with preserved evidence

### Authoritative checkpoint and scope

- Product Assurance correction/base: `b20efa7dad3cab4b1ad124156c93f3052b0a248f` required the
  stale-receipt route to preserve exact historical evidence and remain actionable.
- Implementation commit: `b648e418d61f7dfa7906f20871b030f838706074` — `Preserve Forge
  evidence through plan rollover` on `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, minimum Forge continuity/correctness correction only.
- Exact files: `src/romverse/rom/forge.py`, `src/romverse/ui/rom_studio.py`,
  `tests/test_build_control_ui.py`, and `tests/test_forge_bundle.py`.

### Exact correction

- On the user's existing explicit **Forge Bundle** action, a valid `latest` receipt from a
  different exact Build Readiness generation is first independently verified, then exclusively
  preserved in the project's private, content-addressed `forge-history` directory. Its immutable
  archive remains in place.
- History creation is non-overwriting. An existing content address is accepted only when its
  parsed receipt mapping is exactly identical; malformed evidence, read ambiguity or a collision
  fails closed without replacing history or `latest`.
- The previous `latest` receipt remains present until the current-plan bundle is completely
  created and its new receipt is atomically installed. A failure after historical preservation
  leaves both the old `latest` and historical receipt recoverable; no success or retry is inferred.
- Current and historical receipts can be verified through one exact verification boundary without
  changing the latest evidence pointer. Historical loading validates its SHA-256 content address,
  receipt schema and project identity before returning evidence.
- ROM Studio now keeps the existing Forge action focused and actionable for a stale generation,
  truthfully explains preservation and starts no work automatically. One explicit choice starts
  one existing Forge worker; its established automatic verifier then verifies the current result.
  No additional confirmation or screen was added.

### Verification without double-counting

- Final directly affected regression selection: **30/30 passed**. It contains the complete
  17-check Device Build contract suite, four Forge schema/history checks, three exact Forge
  Control/UI checks and the six durable-schema inventory checks.
- The connected same-tree adversary creates schema-3 plan A, Forge A and Device Build plan A; then
  replaces the current plan with schema-3 plan B whose tree digest is identical but whose exact
  Guided-choice and plan digests differ.
- A simulated insufficient-space interruption after preservation proves Forge A remains `latest`,
  its history receipt loads and verifies independently, and no replacement receipt is inferred.
- The old Device Build admission remains rejected with **zero runner calls**. One explicit UI
  Forge choice then starts exactly one plan-B Forge worker and the existing verifier, produces a
  verified current plan-B receipt, and retains both plan-A and plan-B immutable archives plus the
  independently verifiable plan-A history receipt.
- A collision adversary replaces a history path with different bytes and proves a repeat preserve
  attempt fails without overwriting those bytes or the valid latest receipt.
- Python compilation, Ruff lint and Git whitespace validation passed for all four changed files.
  Earlier overlapping focused runs are not added to the final total. No broad suite, desktop
  package, native-app smoke, CI matrix or hardware workflow ran.

### Classification, safety, platforms and gates

- **Implemented:** exact stale-generation history preservation, fail-closed collision handling,
  latest-pointer continuity and the actionable one-choice Forge rollover route.
- **Simulated/Tested:** deterministic Linux service and offscreen Qt journey; **30/30** unique
  directly affected checks.
- **Hardware Verified:** no. No physical hardware claim was made.
- **Released:** no.
- Blockers/failures: none within the bounded correction. Signing, Guardian review, physical
  execution and release remain closed and were not attempted.
- Guided friction/dead ends: the stale-receipt loop is removed. Guided/Command Deck can now use the
  existing deliberate Forge action without manual file management while preserving prior evidence.
- Guardian/Recovery/safety: Forge evidence remains local, unsigned, non-bootable, non-flashable and
  grants no consent, Guardian, device, flash or execution authority. Exact-device evidence,
  same-incident Recovery, UNKNOWN-on-uncertainty, no blind retry, independent verification and
  permanent no-relock remain unchanged.
- Linux/Fedora: Python and offscreen Qt verification passed genuinely on Linux. Windows and
  physical Android hardware were not run.
- Feature freeze: compliant minimum correction to an existing Stage 1 continuity defect; no new
  product feature, screen, adapter, Device Pack, signing path or execution capability.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all release gates.
- External actions: the scoped implementation and this handoff are committed and the existing
  branch is pushed normally. No phone, ADB/Fastboot, APK, firmware/device operation, system/global
  installation, real candidate, signing, Guardian consent/execution, publication, release, merge,
  force-push, lock or relock occurred. Test artifacts existed only in disposable test workspaces.

### Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice until the
verdict for `b648e41` is recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that private content-addressed preservation, exact-equality collision handling and the
  old-latest-until-new-success ordering satisfy the continuity and evidence-retention invariant.
- Confirm that the connected interruption and success adversaries prove the former Guided dead end
  is removed without weakening exact Build Plan or Device Build admission.

## Linux correction checkpoint — durable exact-plan identity through Forge

### Authoritative checkpoint and scope

- Product Assurance correction/base: `11c19a0` accepted fresh schema-3 validation at `743a0f2`
  but required the exact plan generation to remain durable downstream.
- Implementation commit: `601b9f6a4dfdc1a232b15ecfdce332c4726cd015` — `Bind Forge
  artifacts to exact build plans` on `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, exact Forge/Device Build evidence identity only.
- Exact files: `src/romverse/core/durable_schemas.py`,
  `src/romverse/rom/build_contracts.py`, `src/romverse/rom/forge.py`,
  `src/romverse/ui/rom_studio.py`, `tests/test_build_control_ui.py`, and
  `tests/test_forge_bundle.py`.

### Exact correction

- Schema-3 Forge creation now emits manifest schema 4 and receipt schema 3. Both durably carry the
  exact Build Readiness `plan_digest`, protected-source SHA-256, toolchain-manifest digest and
  Guided-choice digest in addition to the existing tree digest and inert safety contract.
- Forge verification requires those four exact bindings to be present, valid and identical across
  manifest and receipt. A schema-3 receipt cannot be downgraded to legacy to bypass this check.
  Legacy schema-1/2 receipts and schema-1/2/3 manifests remain readable as historical evidence but
  are never represented as schema-3 plan certainty.
- Device Build plan schema 2 now binds the exact current schema-3 workspace-plan digest as well as
  its tree digest. Immediately before local execution, both must still match. Legacy schema-1
  Device Build plans remain readable only with legacy workspace plans and retain their old shape.
- ROM Studio accepts and enables verification only for a Forge receipt matching the exact current
  plan generation. A stale same-tree receipt is preserved, shown as **PLAN CHANGED**, focuses the
  existing plan regeneration/reverification route and starts no worker. Forge creation likewise
  refuses to overwrite historical evidence from another exact plan generation.
- The durable-schema inventory now truthfully records Build Plan 3, Device Build Plan 2, Forge
  manifest 4 and Forge receipt 3 with their supported legacy read versions.

### Verification without double-counting

- Final directly affected regression selection: **29/29 passed**. It contains the complete
  17-check Device Build contract suite, three schema-3/legacy Forge compatibility checks, three
  exact Forge Control/UI checks and the six durable-schema inventory checks.
- The required same-tree adversary created valid schema-3 plan A plus its Forge receipt/artifact and
  Device Build plan, then created valid plan B with a different sealed Guided-choice digest while
  retaining the identical tree SHA-256. The old Device Build admission was rejected with **zero
  runner calls**; the stale Forge admission started zero workers and did not overwrite its receipt.
- The plan-A Forge archive remained independently verifiable as historical evidence after plan B
  replaced the current plan. It was not accepted as the current generation.
- Success coverage verifies the exact plan/source/tool/choice digests in the new receipt, a
  schema-2 Device Build plan bound to the same exact plan, and the existing unsigned,
  non-bootable, non-flashable and zero-phone contract.
- Legacy coverage verifies schema-2 Forge receipts/schema-3 manifests remain legacy and contain no
  exact-plan claim. The downgrade adversary proves a schema-4 exact manifest cannot be consumed
  through a forged legacy receipt classification.
- Python compilation, Ruff lint and Git whitespace validation passed for all six changed files.
  Earlier overlapping individual/27-test runs are not added to the final total. No broad suite,
  CI matrix, desktop package or native application smoke ran.

### Classification, safety, platforms and gates

- **Implemented:** durable exact-plan bindings across Forge and Device Build; stale-generation UI
  rejection; truthful legacy schema compatibility and inventory.
- **Simulated/Tested:** deterministic Linux service/UI evidence; **29/29** non-overlapping directly
  affected checks.
- **Hardware Verified:** no. No hardware or real ROM-build claim was made.
- **Released:** no.
- Blockers/failures: none in the bounded correction. Signing, Guardian review, phone installation
  and verification remain closed and did not start.
- Guided friction/dead ends: a same-tree generation change now routes visibly to the existing plan
  regeneration/reverification path instead of silently consuming or overwriting stale evidence.
- Guardian/Recovery/safety: Forge and Device Build evidence remains local and grants no signing,
  Guardian, consent, phone, flash or execution authority. UNKNOWN/no-blind-retry, exact-device,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Linux/Fedora: Python and offscreen Qt checks passed genuinely on Linux. Windows and physical
  Android hardware were not run.
- Feature freeze: compliant minimum correctness repair to existing durable evidence boundaries; no
  new screen, adapter, Device Pack, build feature, signing path or phone capability.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all release gates.
- External actions: the approved branch was fetched and the scoped implementation/handoff will be
  pushed normally. No phone, ADB/Fastboot, APK, firmware/device operation, real candidate build,
  system/global installation, signing, Guardian consent/execution, publication, release, merge,
  force-push, lock or relock occurred. Disposable artifacts existed only in test workspaces.

### Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice until the
verdict for `601b9f6` is recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm manifest/receipt and Device Build schema evolution preserves legacy truth while binding
  all new schema-3 evidence to one exact Build Readiness generation.
- Confirm the same-tree replacement adversary, historical-evidence preservation, zero runner/worker
  calls and existing regenerate/reverify route satisfy all four correction criteria.

## Linux product checkpoint — schema-3 evidence survives Forge Control

### Authoritative checkpoint and scope

- Product Assurance approval/base: `f2eea95f834676ac141b6763c36a155cd0b273d8` approved
  `aaadeac` and authorized only the existing Build & Sign / Forge Control local-candidate boundary.
- Implementation commit: `743a0f2bbcf8aff80610e00fd6bcae528b8a4a04` — `Preserve exact plan
  evidence through Forge Control` on `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing unsigned local-candidate continuation only.
- Exact files: `src/romverse/rom/build_contracts.py`, `src/romverse/rom/forge.py`,
  `src/romverse/rom/guided.py`, `src/romverse/ui/build_control.py`,
  `src/romverse/ui/rom_studio.py`, `tests/test_build_contracts.py`,
  `tests/test_build_control_ui.py`, and `tests/test_forge_bundle.py`.

### Concrete defect and bounded correction

- Forge Control's exact Device Pack assessment and execution path loaded the schema-3 workspace
  plan through a generic planner. That validated its durable seal but did not freshly fingerprint
  its source-scoped tools. A tool could therefore drift after Build Readiness without closing the
  downstream local-build admission.
- The shared Device Build contract boundary now accepts a schema-3 workspace plan only after fresh
  source, current-tree, Guided-choice and bound-tool revalidation with the current tool inventory.
  It repeats that validation when creating the exact Device Build plan and immediately before the
  local executor is admitted. Drift stops before any external build command.
- Exact build-input preparation legitimately changes the contained tree. Its re-freeze previously
  regenerated a generic schema-2 plan and discarded the stronger bindings. It now carries the
  current schema-3 required-tool scope and current verified statuses into the replacement plan.
- Forge Bundle creation also requires fresh current bound-tool evidence whenever its input is a
  schema-3 plan; the ROM Studio worker supplies its current verified inventory. Schema-2 legacy
  dry runs remain compatible.
- After one local candidate is durably verified, Guided now presents one precise next blocker:
  the candidate remains unsigned and the existing offline signing ceremony requires an approved
  identity. It does not claim a signed artifact or open signing automatically.

### Verification without double-counting

- Final directly affected regression selection: **20/20 passed**. This comprises the complete
  exact Device Build contract suite plus the focused schema-3 Forge admission adversary, metadata
  re-freeze continuity and production-UI Forge Control candidate journey.
- The representative journey used an exact source-bound test Device Pack, schema-3 plan, private
  executable fixtures, production ROM Studio/Forge Control/services and the existing deterministic
  local-build test runner. Opening Forge Control remained inspection-only; one explicit existing
  **Build verified local candidate** action ran exactly once.
- The local executor durably recorded seven completed steps, byte-verified three expected outputs,
  reloaded the exact receipt and output hashes from a reopened store, and issued no ADB or Fastboot
  command. The preceding Forge intermediate remained unsigned, non-bootable and non-flashable.
- A changed bound executable makes the Frozen working-tree/evidence gate blocked and stops the
  executor with zero runner calls. Missing current tool evidence and changed tool bytes also stop
  schema-3 Forge creation before a receipt is written.
- The explicit simulated device remained labelled simulation, survived the journey, and granted no
  Guardian or flash handoff. Guided reported the local candidate ready, signing unavailable and one
  actionable offline-signing blocker.
- Python compilation, Ruff lint and Git whitespace validation passed for all eight changed files.
  Earlier overlapping 4/4 and individual development runs are not added to the final total. No
  broad suite, generic Forge suite, CI matrix, desktop package or native application smoke ran.

### Classification, safety, platforms and gates

- **Implemented:** fresh schema-3 admission at Forge Bundle, Device Build planning and local
  execution; binding-preserving metadata re-freeze; one truthful unsigned-signing blocker.
- **Simulated/Tested:** production UI/services with deterministic exact-contract tools and runner;
  **20/20** non-overlapping directly affected checks.
- **Hardware Verified:** no. The retained device is explicitly simulated and the build runner is a
  deterministic test transport, not physical ROM-build hardware evidence.
- **Released:** no.
- Blockers/failures: none in the bounded journey. The durable local candidate remains unsigned;
  signing, Guardian review, phone installation and verification remain closed and did not start.
- Guided friction/dead ends: exact-plan drift now produces the existing actionable Frozen
  working-tree blocker before work; success retains Build & Sign with one precise offline-signing
  action instead of two descriptive warnings or a false signed state.
- Guardian/Recovery/safety: no authority is granted by the Forge intermediate or local candidate.
  Exact-device evidence, Guardian-only execution, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain intact.
- Linux/Fedora: Python and offscreen Qt verification passed genuinely on Linux. Windows was not
  run. No physical Android hardware was connected or operated.
- Feature freeze: compliant minimum continuity/correctness work at the approved existing Stage 1
  boundary; no new screen, format, adapter, Device Pack, signing path or execution capability.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all release gates.
- External actions: the approved branch was fetched and the scoped implementation/handoff will be
  pushed normally. No phone, ADB/Fastboot dispatch, APK, firmware/device operation, real candidate
  build, system/global installation, signing, Guardian consent/execution, publication, release,
  merge, force-push, lock or relock occurred. Disposable candidate bytes existed only in test
  workspaces.

### Next proposed Build task

Stop for independent Product Assurance review. Do not begin signing, Guardian work or another
consequential slice until the verdict for `743a0f2` is recorded in
`docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm the shared fresh schema-3 validation and binding-preserving metadata re-freeze close the
  plan/tool drift gap at every existing Forge/local-build admission.
- Confirm the inspection-only opening, one explicit local-build action, durable byte verification,
  simulation-only device classification and single unsigned-signing blocker satisfy this boundary.

## Linux product checkpoint — exact inert Guided Build Readiness plan

### Authoritative checkpoint and scope

- Product Assurance approval/base: `7e23971053ed4c2da10aee3d575afb6720885b19` approved Guided
  Toolchain continuity and authorized only the existing Build Readiness stage.
- Implementation commit: `aaadeac6a622b4fca95980904c8ac1a4e454d1cb` — `Bind Guided build
  plans to exact evidence` on `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing simulated Guided Build Readiness only.
- Exact files: `src/romverse/rom/builds.py`, `src/romverse/ui/guided_mission.py`,
  `src/romverse/ui/rom_studio.py`, `tests/test_rom_builds.py`, and
  `tests/test_rom_studio_ui.py`.

### Concrete defects and bounded correction

- Guided Build Readiness previously produced the older generic dry-run plan. It bound the current
  tree and optional Recipe but did not seal the protected source SHA-256, exact source-required
  host tools or the user's unchanged/unrooted choices. It also did not make its local-only,
  non-flashable and zero-execution-authority contract self-verifying.
- A schema-3 Guided plan now seals the protected source, current tree, exact required-tool evidence
  manifest, current Guided choice digest and its own canonical plan digest. It explicitly persists
  `local_only=true`, `flashable=false`, `execution_locked=true` and
  `execution_authority=none`.
- Independent verification rechecks protected-source integrity and current Guided choices, reloads
  the sealed private toolchain evidence, and freshly fingerprints the current required tools before
  accepting the current tree. Tool, choice, source, plan or project-identity drift fails closed.
- The normal Command Deck dry-run retains its existing schema-2 compatibility and one-pass
  verification. It can safely read and verify a schema-3 Guided plan without replacing it.
- The final successful plan verification previously saved the mission before recalculating its
  evidence-derived next stage. Guided therefore appeared to advance to Build & Sign but durably
  restored on completed Build Readiness. It now selects and then saves the truthful next stage.
- No Forge bundle, candidate ROM build, signing operation, Guardian handoff or device operation was
  added or started.

### Verification without double-counting

- Final directly affected regression selection: **31/31 passed**. This comprises the complete
  build-plan and Guided mission/state suites plus the exact simulated Device DNA → unchanged route
  → Toolchain → Build Readiness journey, forged simulation-evidence rejection and existing Command
  Deck simulation handoff.
- The representative real-widget Qt journey used deterministic simulated device and fake local
  tool fixtures. It created and independently verified one exact source/tool/choice-bound schema-3
  plan, preserved the protected original and current tree, advanced visibly and durably to Build &
  Sign, and created no Forge bundle, boot observation or Guardian directory.
- Adversarial coverage rejects changed Guided choices, freshly changed tool executables and a
  tampered plan attempting to become flashable. Existing working-tree and symbolic-link drift
  checks remain passing.
- Python compilation, Ruff lint and Git whitespace validation passed for all five changed files.
  Earlier overlapping individual runs are not added to the final total. No broad suite, CI matrix,
  candidate build, package build or native application smoke was run.

### Classification, safety, platforms and gates

- **Implemented:** exact evidence-bound schema-3 Guided plan, fail-closed independent revalidation,
  explicit inert authority contract and truthful final-stage persistence.
- **Simulated/Tested:** deterministic offscreen Qt journey and **31/31** non-overlapping affected
  checks.
- **Hardware Verified:** no. Device evidence remains explicitly simulated.
- **Released:** no.
- Blockers/failures: none after the bounded correction. Build & Sign is now the truthful next stage
  but is outside this checkpoint and has not started.
- Guided friction/dead ends: the completed Build Readiness stage no longer restores as the current
  step after restart. The normal plan/verify sequence adds no user decision or modal.
- Guardian/Recovery/safety: the plan grants no build, signing, phone, Guardian, consent, flash or
  execution authority. Exact-device evidence, Guardian-only execution, UNKNOWN-on-uncertainty, no
  blind retry, same-incident Recovery, independent verification and permanent no-relock remain
  intact.
- Linux/Fedora: Python and offscreen real-widget verification passed. Windows was not run. Physical
  Android was not connected or operated.
- Feature freeze: compliant minimum correctness and continuity work for an approved existing Stage
  1 boundary; no new screen, format handler, Device Pack, adapter, build capability or execution
  route was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all release gates.
- External actions: the scoped implementation and this handoff will be pushed normally to the
  existing Linux branch. No network download, phone, ADB/Fastboot, APK, firmware/device operation,
  candidate build, system/global installation, signing, publication, release, merge, force-push,
  lock or relock occurred.

### Next proposed Build task

Stop for independent Product Assurance review. Do not begin Build & Sign or another consequential
slice until the verdict for `aaadeac` is recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm schema-3 plan identity and fresh verification bind the exact source, current tree,
  source-required tools and unchanged/unrooted choices without granting downstream authority.
- Confirm schema-2 Command Deck compatibility, truthful durable Build & Sign continuation and the
  31/31 directly affected selection are sufficient for this bounded checkpoint.

## Linux product checkpoint — Guided Toolchain resolution continuity

### Authoritative checkpoint and scope

- Product Assurance approval/base: `3295905d27119d7435811c57c6408bba587a0937` approved the
  one-choice unchanged Customize route and authorized only the existing Toolchain stage.
- Implementation commit: `5976ced726f4297cee7032a88f2b5d7d2defe711` — `Complete Guided
  toolchain resolution` on `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing source-scoped Toolchain action only.
- Exact files: `src/romverse/ui/guided_mission.py`, `src/romverse/ui/rom_studio.py`,
  `tests/test_rom_studio_ui.py`, and `tests/test_app_launch_settings.py`.

### Real isolated resolution and concrete correction

- The exact OTA route required only Python, Payload Dumper and AVBTool. Fresh host verification
  found Python 3.14.7 and system AVBTool 1.4.0 valid; Payload Dumper was the sole missing managed
  dependency.
- One normal Toolchain action in a disposable isolated workspace downloaded and receipt-verified
  Payload Dumper 2.0.2. It resolved to the private managed-tools directory with package digest
  prefix `6e87cedaf0a5…`; no system package manager, administrator prompt or global PATH change ran.
- That journey exposed two concrete continuity defects: the successfully completed automatic setup
  dialog remained open until a second manual Close action, and Guided visibly and durably remained
  on completed Toolchain while its evidence-derived current stage was Build Readiness.
- Automatic managed resolution now requests automatic dialog close only when the existing
  `auto_download_verified_tools` preference is enabled. When automatic downloads are disabled, the
  dialog remains explicitly user-controlled as before.
- A successful Toolchain action clears stale error state, selects the evidence-derived Build
  Readiness stage and persists it. An unresolved dependency remains on Toolchain with one durable,
  precise `toolchain:` blocker instead of being silently treated as complete.

### Verification without double-counting

- Final directly affected regression selection: **28/28 passed**. This comprises the complete
  Guided mission/state suite, the same simulated Device DNA → unchanged route → Toolchain real-
  widget journey, managed resolver continuation, fail-closed missing-tool behavior, empty automatic
  setup closure and manual-download-preference preservation.
- The corrected deterministic UI journey invoked resolution once, verified exactly `Python`,
  `Payload Dumper`, and `AVBTool`, advanced to and persisted Build Readiness, and created no build
  plan.
- Exact project/source identity, unchanged/unrooted choice and
  `SIMULATION ONLY • NOT HARDWARE VERIFIED` classification remained intact. Guardian handoff,
  flash handoff and flash-complete remained false; no Recipe, boot observation or Guardian
  directory appeared.
- Ruff lint and Git whitespace validation passed for all four changed files. An earlier overlapping
  4/4 development run is not added to the final total. No broad suite, CI matrix, build, package or
  native application smoke was run.

### Classification, safety, platforms and gates

- **Implemented:** automatic managed-setup closure and truthful success/failure persistence at the
  existing Toolchain boundary.
- **Simulated/Tested:** corrected normal Qt route and **28/28** non-overlapping affected checks.
  The pre-correction reproduction performed one real managed Payload Dumper download and host
  verification in a disposable workspace; it is not hardware evidence.
- **Hardware Verified:** no. Device evidence remains explicitly simulated.
- **Released:** no.
- Blockers/failures: none after the bounded correction. Build Readiness is the truthful next stage
  and remains outside this checkpoint. A missing managed/system tool continues to fail closed with
  an actionable persisted blocker.
- Guided friction/dead ends: the redundant post-download Close action and completed-Toolchain stop
  are closed for automatic managed setup. Manual preference mode remains deliberately manual.
- Guardian/Recovery/safety: Toolchain evidence grants no phone, Guardian, consent, build or
  execution authority. Exact-device evidence, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain intact.
- Linux/Fedora: genuine host-tool verification and isolated managed download were performed; final
  corrected behavior was verified with focused offscreen Qt tests. Windows was not run. Physical
  Android was not connected or operated.
- Feature freeze: compliant minimum continuity/error-recovery correction to an approved existing
  Stage 1 action; no feature, screen, format, adapter, Device Pack, build route or execution
  capability was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all release gates.
- External actions: one outbound read-only official managed-package download occurred in a
  disposable workspace, which was removed automatically. One normal push of this scoped
  implementation and handoff to the existing Linux branch is the only remote write. No phone,
  ADB/Fastboot, APK, firmware/device operation, actual candidate build, system/global installation,
  signing, publication, release, merge, force-push, lock or relock occurred.

### Next proposed Build task

Stop for independent Product Assurance review. Do not begin Build Readiness or another
consequential slice until the verdict for `5976ced` is recorded in
`docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm automatic close is correctly bound to the existing automatic-download preference while
  manual mode remains user-controlled.
- Confirm the truthful success continuation, durable failure blocker and 28/28 affected selection
  are sufficient for this Toolchain-only checkpoint.

## Linux product checkpoint — one-choice unchanged Guided route

### Authoritative checkpoint and scope

- Product Assurance approval/base: `ddd765d6ef01f95a0616acf8227058cc817d7b84` approved the
  simulated Device DNA boundary and authorized only the next existing Customize-stage journey.
- Implementation commit: `7e3520ad708cf216f36e59f909d360e87240b872` — `Streamline unchanged
  Guided route` on `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing safest Customize choice only.
- Exact files: `src/romverse/rom/guided.py`, `src/romverse/ui/guided_mission.py`,
  `tests/test_guided_mission.py`, and `tests/test_rom_studio_ui.py`.

### Concrete defect and correction

- The visible Customize secondary action said **Continue to Nebula Debloat**, persisted only
  `recipe_skipped`, and left the selected UI/durable stage on the already-completed Customize card.
  Its evidence-derived next stage was Debloat, so the button did not perform the continuation it
  advertised. It also did not represent the approved safest no-customization/no-debloat/unrooted
  route.
- The existing choice is now explicit: **Keep verified base unchanged • Recommended**. One normal
  click selects no Recipe changes, no optional app removal, and the standard unrooted route. The
  same choice is described consistently in the optional Customize dialog.
- The successful choice reuses the existing rooted-input rollback protection, then atomically saves
  `customization_skipped`, `recipe_skipped`, `root_choice=skip`, and the evidence-derived Toolchain
  stage. There is no extra confirmation chain or stale completed-card stop.
- Guided treats Debloat as complete only because the user deliberately kept the verified base
  unchanged; a modified route still requires a verified Debloat receipt. Existing Recipe Forge,
  Nebula Debloat and Ascension routes remain available when deliberately selected.

### Verification without double-counting

- Final directly affected regression selection: **27/27 passed**. This comprises the complete
  Guided mission/state suite plus four focused real-widget cases covering the same simulated
  Device DNA journey, Device scan continuity and existing root-choice evidence safeguards.
- The normal visible-button journey retained the exact project, protected-source digest and
  `SIMULATION ONLY • NOT HARDWARE VERIFIED` evidence, advanced directly from Customize to
  Toolchain, and durably restored there with the unchanged/unrooted decision.
- The journey created no Recipe, Debloat mutation, build plan, boot observation or Guardian
  directory. Guardian handoff, flash handoff and flash-complete remained false.
- Ruff lint and Git whitespace validation passed for all four changed files. An earlier overlapping
  3/3 development run is not added to the final total. No broad suite, CI matrix, build, package or
  native smoke was run.

### Classification, safety, platforms and gates

- **Implemented:** one-choice existing unchanged/unrooted/no-debloat route and truthful immediate
  continuation to Toolchain.
- **Simulated/Tested:** normal offscreen Qt user action with deterministic simulated Device DNA;
  **27/27** non-overlapping affected checks passed.
- **Hardware Verified:** no. The retained device evidence remains explicitly simulated.
- **Released:** no.
- Blockers/failures: none in the bounded journey or final affected regression. The next Toolchain
  evidence is outside this checkpoint and remains unresolved normally.
- Guided friction/dead ends: the misleading Customize → completed Customize stop is closed; the
  safest standard route now requires one clear choice and no follow-up optional dialogs.
- Guardian/Recovery/safety: no new authority. Exact-device evidence, Guardian-only execution,
  UNKNOWN-on-uncertainty, no blind retry, same-incident Recovery, independent verification and
  permanent no-relock remain intact. Any existing rooted integration must still be rolled back
  successfully before the unrooted decision can be accepted.
- Linux/Fedora: focused Python and offscreen real-widget verification passed. Windows was not run.
  Physical Android was not connected or operated.
- Feature freeze: compliant minimum continuity/truth correction to existing Stage 1 choices; no new
  screen, feature, format, adapter, Device Pack, build route or execution capability.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all release gates.
- External actions: one normal push of this scoped implementation and handoff to the existing Linux
  branch is the only remote write. No phone, ADB/Fastboot, APK, firmware/device operation, build,
  package installation, signing, publication, release, merge, force-push, lock or relock occurred.

### Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice until the
verdict for `7e3520a` is recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that the one visible recommended choice truthfully and atomically represents the
  unchanged, no-optional-debloat, unrooted route without weakening the deliberately modified paths.
- Confirm direct continuation to Toolchain and the 27/27 affected selection are sufficient for this
  bounded checkpoint.

## Linux product checkpoint — simulated Device DNA truth and zero authority

### Authoritative checkpoint and scope

- Product Assurance approval/base: `0582f4c37f14757b7295fa82769a7f048323e478` approved the
  existing Guided working-lab continuity and authorized one deterministic simulated Device DNA →
  compatibility journey through the normal UI.
- Implementation commit: `8ce24b22e0ead8beaaf9987f2b03e728f1e67448` — `Classify simulated Device
  DNA without authority` on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Genesis task 05/15 Device DNA continuation
  only.
- Exact implementation/test files: `src/romverse/device/models.py`,
  `src/romverse/device/dna.py`, `src/romverse/rom/readiness.py`,
  `src/romverse/ui/guided_mission.py`, `src/romverse/ui/rom_studio.py`,
  `tests/test_device_dna.py`, `tests/test_build_readiness.py`, and
  `tests/test_rom_studio_ui.py`.

### Concrete defect and correction

- The existing normal Guided scan action did reach the next customization/compatibility state,
  but an injected deterministic test device was persisted as `device.live` / live ADB properties
  and the visible Device DNA panel did not explicitly say that hardware was unverified. Binding
  that simulated device could also create an incidental boot-observation record.
- ROMVERSE now recognizes only the explicit `simulation` transport as simulated evidence. Device
  DNA persists it separately as `device.simulation` / `deterministic-device-simulation`, at
  `UNCONFIRMED` evidence confidence, with a durable
  **SIMULATION ONLY • NOT HARDWARE VERIFIED** classification and warning.
- Simulated identity agreement remains useful for inert flow validation but is classified as
  `CAUTION`; Compatibility Matrix therefore reports **Limited Evidence**, while Guardian Flash
  remains **Unknown / UNCONFIRMED**. Permanent bootloader relock prohibition remains
  **Known Incompatible / UNSUPPORTED**.
- Both ROM Studio Device DNA and the Guided identity deck now display the simulation label
  conspicuously. The normal Guided action preserves the exact project, protected source and mission
  and advances from Device DNA to Customize without presenting simulation as hardware proof.
- Simulation is structurally excluded from build-readiness live-target selection, boot observation,
  Guardian handoff matching, Guardian result registration and manifest-review device selection.
  It creates no live-target, consent, Guardian or execution authority.

### Verification without double-counting

- Final directly affected regression selection: **36/36 passed**. This comprises the complete
  Device DNA and Compatibility Matrix suites, the simulated build-readiness boundary, and three
  focused real-widget Guided scan/continuation cases.
- The representative normal-button journey produced durable simulated Device DNA and advisory-only
  compatibility, advanced to Customize, retained the exact protected source digest and project,
  and created no build plan, boot observation or Guardian directory.
- Ruff lint passed for all eight changed source/test files. Git whitespace validation passed.
- An earlier 14/14 development run overlaps the final selection and is deliberately not added to
  the total above. No broad suite, CI matrix, build, package or native smoke was run.

### Classification, safety, platforms and gates

- **Implemented:** durable simulated-evidence classification, conspicuous truth labels and shared
  authority-boundary exclusion.
- **Simulated/Tested:** deterministic local device simulation through the normal Qt Guided action;
  **36/36** non-overlapping affected checks passed.
- **Hardware Verified:** no. Simulation is explicitly and durably not hardware verification.
- **Released:** no.
- Blockers/failures: none in the bounded journey or final affected regression. Physical-device
  identity and every consequential execution gate remain unverified and closed.
- Guided friction/dead ends: the existing Device DNA action continues directly to the next
  evidence-derived state; no extra decision or modal was added. The previous misleading live label
  is closed.
- Guardian/Recovery/safety: simulation grants zero authority. Exact-device evidence,
  Guardian-only execution, UNKNOWN-on-uncertainty, no blind retry, same-incident Recovery,
  independent verification and permanent no-relock remain intact.
- Linux/Fedora: focused Python and offscreen real-widget verification passed. Windows was not run.
  Physical Android was not connected or operated.
- Feature freeze: compliant minimum correctness fix to an approved existing Stage 1 journey; no
  new feature, screen, adapter, Device Pack, build route or execution capability.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all existing release
  gates.
- External actions: one normal push of this scoped implementation and handoff to the existing Linux
  branch is the only remote write. No phone, ADB/Fastboot, APK, firmware/device operation, build,
  package installation, signing, publication, release, merge, force-push, lock or relock occurred.

### Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice until the
verdict for `8ce24b2` is recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that deterministic simulation remains useful for existing Guided continuity while its
  separate evidence type, confidence and shared exclusions prevent every hardware/execution claim.
- Confirm the normal-button Device DNA → Customize journey, advisory-only Compatibility Matrix and
  36/36 directly affected checks are sufficient for this bounded checkpoint.

## Linux product checkpoint — existing Guided working-lab continuity

### Authoritative checkpoint and scope

- Product Assurance approval/base: `e3f91877c5fc50061d4c294c7476fb99fbea0e09` approved
  `ac77205`/`7c62f12` and authorized this single existing no-phone working-lab journey.
- Tested source: `ac772057c6dc9510bf4d30f7e7a1c296f446352c` with approval/handoff history
  through `e3f9187` on `linux/stage1-desktop-readiness`.
- Final handoff: the documentation-only commit containing this sync. No source or test file changed.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Genesis task 04/15 working-lab action only.

### Real-widget journey and durable result

- A fresh disposable real `GuidedBuildMission` opened from the existing ROM Studio/Command Deck
  handoff with one already-imported and inspected deterministic Android boot-image project at
  task 04/15. The normal visible **Prepare working lab** action was invoked once.
- The existing queue completed exactly `working-copy` then `extract`. It produced one sealed
  `working-copy.romverse` record, one private `working-tree-index.romverse` record and one contained
  staged tree file. There was no duplicate working-copy record or unexplained dead end.
- The protected original remained byte-identical at SHA-256
  `beb7b61e814e2e7c7dcd737b569892757258b4a5bbfb76b0335afdf07c304baa`, retained mode `0444`, and
  matched both the project source digest and the working-copy source/current digest.
- The representative sealed working-copy receipt digest was
  `c235c1dc1b4b46138d5e0f997f4e68520affacf8fd65408289bf4e3dbbb79634`. This digest belongs only to
  the disposable journey and grants no build or device authority.
- After modal return, the durable mission selected `device`; the flight plan, project row and
  Genesis handoff all displayed truthful task 05/15 Device DNA state. ROM Studio detail reported
  `7/8 steps complete • Next: Create and verify build plan`.
- No `BuildPlan` existed, no worker or queued operation remained, no device was present, and no
  compatibility, Guardian or execution authority was created.

### Verification without double-counting

- Representative real-widget working-lab journey: **1/1 passed**.
- Directly affected regression selection: **4/4 passed** — post-Genesis modal continuity,
  existing safe-local-stage autopilot pause at Device DNA, working-copy verification/deduplication,
  and contained clean-archive extraction.
- Git whitespace validation: **passed**. Repository application/test source remained unchanged.
- Two preliminary harness observations were rejected and are not counted: one observer sampled the
  intentional idle gap before the queued extraction was dispatched, and one invalid synchronous
  worker substitution correctly triggered the existing fail-closed `worker is None` guard. The
  final journey used the repository's established controlled-worker pattern and completed both
  registered steps normally.
- No broad suite, CI matrix, application package, native smoke or repeated firmware import was run.

### Classification, safety, platforms and gates

- **Implemented:** no new implementation; the approved existing working-lab action is sufficient.
- **Simulated/Tested:** one real Qt modal/UI journey with sanitized local bytes plus 4/4 directly
  affected checks.
- **Hardware Verified:** no new hardware evidence; the journey was explicitly no-phone.
- **Released:** no.
- Blockers/failures: none in the valid journey or focused regression. No product defect justified a
  source change.
- Guided friction/dead ends: none observed between task 04 preparation and the truthful task 05
  no-phone Device DNA pause.
- Guardian/Recovery/safety: unchanged. Exact source identity, immutable original, Guardian-only
  execution, UNKNOWN-on-uncertainty, no blind retry, same-incident Recovery, independent
  verification and permanent no-relock remain intact.
- Linux/Fedora: real widget journey and focused tests verified offscreen. Windows was not rerun.
  Physical Android was not used.
- Feature freeze: compliant verification of an existing Stage 1 action; no feature, screen, format,
  engine, adapter or execution capability was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and existing release gates.
- External actions: one normal documentation-only push is planned. No phone, ADB/Fastboot, APK,
  device firmware operation, build candidate, signing, installation, publication, release, remote
  merge, force-push, lock or relock occurred.

### Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice until the
verdict for this working-lab checkpoint is recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm the existing two-step working-lab action preserves one immutable source and one isolated,
  durable working state without a source correction.
- Confirm the valid real-widget journey plus the directly affected 4/4 regression selection is
  sufficient and the two rejected harness observations are correctly excluded.

## Linux product checkpoint — post-Genesis ROM Studio continuity

### Authoritative checkpoint and scope

- Product Assurance approval/base: `0a45e81dc75669698e532129c73105b3e9da310d` approved the
  shared current-version CI contract and authorized this single platform-neutral continuity fix.
- Implementation commit: `ac772057c6dc9510bf4d30f7e7a1c296f446352c` — `Refresh ROM
  Studio after Genesis returns`.
- Final handoff: the follow-up documentation commit containing this sync on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing modal Genesis → ROM Studio continuity only.
- Exact implementation/test files: `src/romverse/ui/rom_studio.py` and
  `tests/test_rom_studio_ui.py`.

### Exact correction

- After the existing modal Genesis journey returns, ROM Studio now reloads its project list and
  selected-project detail from the current exact durable project identity.
- If and only if an existing visible handoff card belongs to Genesis, ROM Studio recalculates that
  card from the same current `GenesisFlightPlan`. Non-Genesis handoffs remain untouched.
- The refreshed card preserves its originating title/eyebrow and reports the current stage,
  evidence-derived progress and saved-error attention state. It explicitly states that no build or
  phone action started.
- The correction adds no import, worker, activity, build, compatibility, device, Guardian or
  execution action. It reuses the normal read/render refresh after the modal has already persisted
  its state.

### Focused real-widget continuity proof

- One real modal `GuidedBuildMission` began with an existing deterministic no-phone project at
  stage 2, accepted one sanitized inert Android boot-image fixture through the existing protected
  import and bounded structural-inspection path, and reached the evidence-derived stage 4 working
  lab state.
- On modal return, all visible/current owners agreed immediately: the durable mission selected
  `workspace`, `genesis_flight_plan()` reported stage 4, the project list displayed
  `GENESIS • 4/15 • WORKING LAB`, and the existing handoff displayed
  `Stage 4/15: Prepare an isolated working tree` with `CURRENT STAGE`.
- Exact source identity was retained. There was one protected original and exactly one validated
  `import` completion signal; the repaint did not emit a duplicate completion/activity event.
  No build plan, worker, phone or device context existed after the journey.

### Verification without double-counting

- Final exact-source focused selection: **4/4 passed** — authoritative project-card state,
  shared Genesis flight-plan assessment, the new real-modal post-return journey, and existing
  Command Deck ROM Studio handoff behavior.
- Focused Ruff lint: **passed** for the two changed files.
- Focused Ruff format check: **passed** for the two changed files.
- Git whitespace validation: **passed**.
- An initial harness invocation loaded ROMVERSE from the older dependency environment because
  `PYTHONPATH` was not set; it was rejected as invalid branch evidence. The final run explicitly
  used `PYTHONPATH=src` and is the only product result counted above.
- No broad regression suite, CI matrix, package build or native application smoke was run, as
  required by Product Assurance for this bounded state-refresh correction.

### Classification, safety, platforms and gates

- **Implemented:** immediate post-Genesis project/list/detail and visible Genesis-handoff refresh.
- **Simulated/Tested:** real Qt widget/modal journey with sanitized local bytes; 4/4 directly
  affected checks and focused static validation passed.
- **Hardware Verified:** no new hardware evidence. The journey was explicitly no-phone.
- **Released:** no.
- Blockers/failures: none in the final exact-source validation. No additional Guided dead end was
  observed within this bounded journey.
- Guided friction: the known stale earlier-stage list/handoff mismatch is closed; reopening Genesis
  is no longer needed merely to see the current persisted stage.
- Guardian/Recovery/safety: unchanged. The refresh grants no authority and preserves exact-device
  evidence, Guardian-only execution, UNKNOWN-on-uncertainty, no blind retry, same-incident Recovery,
  independent verification and permanent no-relock.
- Linux/Fedora: focused Qt behavior verified offscreen on the Fedora host. Windows: not rerun; the
  original packaged Windows journey supplied the cross-platform reproduction. Physical Android:
  not used.
- Feature freeze: compliant minimum correctness fix to an existing Stage 1 journey; no new screen,
  feature, engine, format, adapter or execution capability.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all existing release
  gates.
- External actions: one normal push of the implementation and this handoff is planned. No phone,
  ADB/Fastboot, APK, firmware/device operation, signing, package installation, publication,
  release, remote merge, force-push, lock or relock occurred.

### Next proposed Build task

Stop for independent Product Assurance review. Do not begin another consequential slice until the
verdict for `ac77205` is recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm the post-modal refresh uses the exact current project and durable mission state without
  duplicating import/activity or creating build/device authority.
- Confirm the focused 4/4 selection is sufficient for this platform-neutral presentation-only
  continuity correction.

## Linux product checkpoint — current unsigned Fedora development artifact

### Authoritative checkpoint and scope

- Source commit built: `c8c07c05316b660c345775ffc4fcf088d9d60033` — Product Assurance's
  approved inspection-only Forge Control checkpoint.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`; the source tree remained clean throughout assembly and will be
  pushed normally after this handoff is committed.
- Stage: Stage 1 — v0.2 Golden Foundation, current runnable Fedora development artifact only.
- Source changes: **none**. The approved existing one-folder/windowed pipeline completed without a
  frozen-only launcher, asset, dependency or startup defect.

### Fresh development artifact

- One-folder application:
  `/run/media/stevetherad/Data/ROMVERSE-Linux-Desktop-Readiness/build/fedora-c8c07c0/ROMVERSE`
  — 422 regular files and 243,056,224 apparent bytes.
- Native executable:
  `/run/media/stevetherad/Data/ROMVERSE-Linux-Desktop-Readiness/build/fedora-c8c07c0/ROMVERSE/ROMVERSE`
  — stripped Linux x86-64 ELF with the standard `/lib64/ld-linux-x86-64.so.2` interpreter.
- Verified archive:
  `/run/media/stevetherad/Data/ROMVERSE-Linux-Desktop-Readiness/dist/ROMVERSE-Desktop-0.2.0-alpha.1-linux-x86_64-c8c07c0.zip`
  — 151,002,857 bytes — SHA-256
  `50715b7ef51610d1077fd7812269a54d6dcb68cbfe7458cd8ff3c14729184a0d`.
- Bundle inventory: 460 regular archive members and 360,309,514 expanded bytes. The required
  executable, approved ROMVERSE/RadForge artwork, legal documents and exact Xiaomi HyperOS 4
  Device Pack are present.
- Tool identity: Fedora 44 x86-64 host, kernel 7.1.13, Python 3.14.7, PyInstaller 6.22.2,
  PySide6 6.11.2 and cryptography 46.0.7.

### Exact source and bundle verification

- The repository branch/worktree was clean at exact source commit `c8c07c0` before and after the
  pipeline. The new output and work directories did not previously exist.
- PyInstaller's module graph contains 258 references to this exact Linux readiness checkout and
  zero ROMVERSE module references to the older environment checkout. The current `src/romverse`
  tree is therefore the frozen source identity despite reuse of its isolated dependency runtime.
- The existing packager verified platform identity, safe relative paths, duplicate/link rejection,
  required executable presence, archive CRC and expanded-size/file-count bounds while producing the
  ZIP. A separate `unzip -t` pass found no compressed-data error, and independent `sha256sum`
  reproduced the exact digest above.
- PyInstaller reported only standard conditional/platform/optional missing-module observations.
  No required ROMVERSE module was absent, and the native launch completed without import or runtime
  failure.

### Native no-phone launch and visible state

- The frozen ELF was launched once as a normal Wayland window with the application's supported
  1440×900 initial sizing path and a fresh isolated workspace. The existing bounded release-smoke
  timer performed the clean close after startup.
- The launched process used `PATH=/nonexistent`, making both ADB and Fastboot unavailable by
  construction. ROMVERSE therefore created no device engine and followed the existing truthful
  default Command Deck state: no live phone, no scan and missing Platform Tools rather than invented
  device readiness.
- The isolated workspace contains expected initialization, local knowledge, Companion Link key
  material and empty activity/live-console locks. It contains no device, operation or Guardian audit
  record.
- Native process exit: 0. Console output: none. Runtime crash log records exactly one start and one
  clean close with no exception or native fault.

### Classification, safety, platforms and gates

- **Implemented:** no new implementation; this checkpoint assembles the exact approved source.
- **Simulated/Tested:** one real Fedora one-folder build, one native Wayland no-phone launch/close,
  one package/verification pass and one independent archive-integrity pass.
- **Hardware Verified:** native Fedora desktop host only; no Android/device hardware verification.
- **Released:** no. The artifact is unsigned, local, unpublished and explicitly development-only.
- Regression evidence: no prior suite or local-candidate journey was repeated, per Product
  Assurance. Artifact construction/integrity/native startup are the acceptance evidence for this
  checkpoint.
- Guided friction/dead ends: no frozen-only launcher, asset, dependency, startup, initial-size,
  Command Deck or shutdown defect was observed. Interactive navigation was outside the one-launch
  bounded check and is not newly claimed.
- Guardian/Recovery/safety: no execution boundary changed. Exact evidence, Guardian-only authority,
  UNKNOWN-on-uncertainty, no blind retry, same-incident Recovery and permanent no-relock remain
  unchanged.
- Fedora/Linux: genuinely built, packaged and natively launched. Windows: not run or claimed in this
  checkpoint. Physical Android: not used.
- Feature freeze: compliant artifact/readiness evidence only; no source or product scope changed.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and existing release gates.
- Current limitations: this is an unsigned Fedora 44 development artifact, not a signed portable
  release; no clean-machine compatibility, distro matrix, genuine external Android toolchain,
  physical phone, signing, installation, update or release proof is claimed.
- Protected Companion, Windows launcher/CI, Knowledge/UI Design Lab, website and unrelated files
  were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot, APK installation, firmware/device operation, ROM/local
  candidate build, signing, flash/boot, partition/slot/wipe/unlock/lock/relock, desktop package
  installation, publication and release: **none**. External action after final verification: one
  normal push of this documentation-only Linux checkpoint; no force-push or unrelated remote change.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice. Continue only from the
next bounded direction recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm the exact checkout graph, independent archive checks and one native PATH-isolated launch
  sufficiently establish the current unsigned Fedora development artifact without repeating prior
  regression suites.
- Confirm that no source correction is appropriate because no genuine frozen-only defect appeared.

## Linux product checkpoint — Forge Control opens inspection-only before explicit local build

### Authoritative checkpoint and scope

- Tested implementation: `527cb2be3be34d7bef844189d643cc7a7212d2fe` — `Keep Forge Control
  inspection-only on open`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`; the branch was clean immediately after the implementation
  commit and will be pushed normally after this handoff is committed.
- Product Assurance approval/base: `897f30e` — approved the intentional verified Forge Bundle and
  authorized one representative existing exact-contract local-candidate journey.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Forge Control opening/build continuity only.
- Exact changed implementation/test files: `src/romverse/ui/rom_studio.py` and
  `tests/test_build_control_ui.py`. No build executor/service, artifact format, package, platform,
  device, Companion, Recovery adapter or broader product file changed.

### Reproduced defect and minimum correction

- The exact verified intermediate correctly focused Forge Control as its next intentional
  inspection, but ROM Studio constructed the ordinary Forge Control dialog with its default
  automatic resolver enabled. Opening the inspection surface could therefore begin preparation
  without the user choosing the existing local Build action.
- The production correction is one call-site argument: ordinary ROM Studio Forge Control opening
  now passes `auto_start=False`, matching the existing Smart Solution inspection-only opening.
- No control, service, pipeline, evidence schema or build semantics changed. The existing
  **Build verified local candidate** button remains the sole trigger for the bounded pipeline.

### Representative durable journey

- A disposable sanitized project uses an existing exact source-bound Device Pack/build contract,
  protected source, inspected/contained tree, deterministic dry-run plan, verified non-flashable
  Forge Bundle, exact extracted partition evidence, rebuild metadata, locked local build plan and
  versioned test tool identities.
- Opening Forge Control through the real ROM Studio button starts no worker, preparation mission or
  autopilot and creates no local candidate receipt.
- The harness then explicitly clicks the existing Build button once. The production
  `LocalDeviceBuildExecutor` runs the exact seven-step bounded pipeline through a deterministic
  external-tool runner; no build result or durable receipt is mocked.
- The UI receives the typed result, refreshes to `LOCAL BUILD COMPLETE / INSTALL NOT AUTHORIZED`,
  and reports the exact output count, receipt digest and `phone changed: NO`.
- A fresh `RomProjectStore` and executor reload and reverify the same durable receipt and all output
  files. The exact Forge Bundle receipt also reloads unchanged.

### Verification without double-counting

- One focused affected run: **5/5 unique tests passed** across
  `tests/test_build_control_ui.py`, `tests/test_build_contracts.py` and
  `tests/test_forge_bundle.py`.
- The new production-widget journey proves inspection-only opening, the single explicit build
  trigger, one complete real executor invocation, durable candidate/receipt/output reload and zero
  ADB/Fastboot command dispatch.
- Direct executor checks prove exact versioned candidate output and every-partition verification,
  hostile or incomplete durable receipt rejection, and UNKNOWN in-flight interruption with no
  retry dispatch.
- Existing Forge service evidence proves the incoming intermediate is deterministic, verified,
  unsigned, non-bootable and non-flashable.
- Ruff static checks passed for both changed files. Ruff format check passed for the changed
  production source; `test_build_control_ui.py` retains one pre-existing unrelated formatting
  difference outside this checkpoint's hunk and was not mechanically reformatted. `git diff
  --check`: passed.
- No broad suite was run. This five-test total is not combined with prior checkpoint totals.

### Classification, safety, platforms and gates

- **Implemented:** inspection-only ordinary Forge Control opening.
- **Simulated/Tested:** 5 Linux-hosted UI/executor/receipt/Forge journeys. One complete disposable
  local candidate was produced through deterministic test tool behavior in an isolated temporary
  workspace.
- **Hardware Verified:** no. **Released:** no.
- Guided friction/safety: opening Forge Control no longer silently starts an automatic resolver.
  One explicit existing Build choice completes the already-bounded local pipeline. Known failure,
  invalid evidence and interrupted UNKNOWN state retain their existing actionable/no-retry paths.
- Guardian/Recovery/safety: the local candidate remains unsigned and has no install, Guardian,
  flash, device or execution authority. Exact evidence, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery and permanent no-relock remain unchanged.
- Fedora/Linux: genuinely exercised in the existing Fedora offscreen Qt development runtime using
  production UI, stores and build services with deterministic external-tool behavior. Windows:
  not run or claimed. Physical Android/hardware: not used.
- Feature freeze: compliant single-defect continuity/correctness work; no screen, feature, engine,
  service, artifact format or device capability was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and existing release gates.
- Current blockers/limitations: Product Assurance has not independently reviewed this checkpoint;
  the deterministic runner is simulation rather than genuine platform tool execution; signing,
  AVB trust, Guardian, installation and physical verification remain separate closed boundaries.
- Protected Companion, Windows launcher/CI, Knowledge/UI Design Lab, website and unrelated files
  were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot, APK installation, firmware/device operation, real external
  toolchain build, signing, flash/boot, partition/slot/wipe/unlock/lock/relock, desktop package
  installation, publication and release: **none**. External action after final verification: one
  normal push of this scoped Linux branch only; no force-push and no unrelated remote change.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice. Continue only from the
next bounded direction recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm the one-line `auto_start=False` ROM Studio call-site correction is the minimum proper
  enforcement of inspection-only Forge Control opening without changing other specialized flows.
- Confirm the production-service journey with deterministic external-tool behavior accurately
  demonstrates durable local-candidate continuity without claiming real toolchain or hardware
  verification.

## Linux product checkpoint — one explicit Forge choice completes artifact verification

### Authoritative checkpoint and scope

- Tested implementation: `c363e8a82c6503c691186f93ef8de3f0984cf679` — `Verify intentional
  Forge Bundle results`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`; the branch was clean immediately after the implementation
  commit and will be pushed normally after this handoff is committed.
- Product Assurance approval/base: `6f935de` — approved the verified-Simulation Forge handoff and
  authorized one existing Forge producer plus one automatic existing read-only verifier only after
  the user explicitly chooses Forge Bundle.
- Stage: Stage 1 — v0.2 Golden Foundation, existing intentional Forge Bundle continuity only.
- Exact changed implementation/test files: `src/romverse/ui/rom_studio.py` and
  `tests/test_rom_studio_ui.py`. No Forge service, package, platform, device, Companion, Recovery
  adapter or product-scope file changed.

### Exact implemented behavior

- The existing Forge Bundle button remains the sole user intent. Its click now binds one request to
  the complete exact persisted `BuildPlan` and starts the existing `forge-bundle` worker once; the
  preceding Simulation still never starts Forge automatically and no second confirmation was added.
- ROM Studio independently reloads and accepts only the exact typed persisted `ForgeBundleReceipt`,
  exact project/current plan/tree digest and explicit unsigned/non-bootable/non-flashable flags.
  Changed or mismatched terminal evidence is rejected before it can become accepted completion.
- Only after that receipt boundary succeeds, ROMVERSE invokes the existing read-only `verify-forge`
  worker once. Its terminal boundary binds the exact plan and receipt, requires matching expected
  and actual archive SHA-256 values and accepts only the verifier's internally consistent typed
  success state.
- Exact success presents the verified intermediate's digest, file count, byte count and explicit
  no-authority contract, then focuses the existing Forge Control inspection as the next intentional
  continuation. Forge Control does not start automatically.
- Known creation failure and verification failure have separate visible stopped states. Both
  preserve available evidence, clear transient continuation authority and schedule no retry. An
  interrupted process cannot restore the memory-only continuation and therefore cannot blindly
  resume either producer.
- The existing manual Verify Forge control remains compatible and retains persisted receipt/result
  validation; automatic continuation is accepted only when its stronger exact request binding is
  present.

### Verification without double-counting

- One focused affected run: **5/5 unique tests passed** across
  `tests/test_rom_studio_ui.py` and `tests/test_forge_bundle.py`.
- Real-widget success journey proves exact sequence
  `Simulation verify-plan → explicit Forge click → forge-bundle → automatic verify-forge`, with
  exactly one worker for each operation, exact persisted receipt, no second Verify click, final
  `VERIFIED INTERMEDIATE` state, Forge Control focus and no phone evidence.
- Adversarial real-widget journey modifies the created archive after receipt acceptance but before
  the queued verifier runs. The verifier reports an archive hash mismatch, retains the receipt and
  changed artifact for evidence, queues no retry and presents the focused verification-attention
  state without inferred success.
- Existing service checks prove deterministic verified non-flashable creation, refusal of tree
  drift before writing and independent archive-tamper detection.
- Ruff static and format checks passed for both changed files. `git diff --check`: passed.
- No broad suite was run. This five-test total is not combined with prior checkpoint totals.

### Classification, safety, platforms and gates

- **Implemented:** explicit-intent Forge request binding, persisted typed-receipt acceptance,
  one automatic read-only artifact verification and verified-result continuation.
- **Simulated/Tested:** 5 sanitized Linux-hosted Qt/store/Forge-service journeys. Disposable local
  non-flashable Forge archives were created only inside test workspaces.
- **Hardware Verified:** no. **Released:** no.
- Guided friction removed: one explicit Forge choice completes both the existing producer and its
  required technical verification without a second Verify click. Genuine creation or verification
  failure remains an actionable stop rather than a loop.
- Guardian/Recovery/safety: the artifact remains unsigned, non-bootable and non-flashable and grants
  no build, signing, Guardian, device, flash or execution authority. Exact evidence,
  UNKNOWN-on-uncertainty, no blind retry, same-incident Recovery and permanent no-relock remain
  unchanged.
- Fedora/Linux: genuinely tested in the existing Fedora offscreen Qt development runtime. Windows:
  not run or claimed. Physical Android/hardware: not used.
- Feature freeze: compliant continuity/correctness work around existing controls, workers and
  services; no screen, feature, engine, artifact format or device capability was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and existing release gates.
- Current blockers/limitations: Product Assurance has not independently reviewed this checkpoint;
  Forge Control remains a separate intentional inspection; no phone-capable image, signing,
  Guardian admission, physical execution or release authority follows from the verified bundle.
- Protected Companion, Windows launcher, Knowledge/UI Design Lab, website and unrelated files were
  not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot, APK installation, firmware/device operation, phone-capable
  build, signing, flash/boot, partition/slot/wipe/unlock/lock/relock, desktop package installation,
  publication and release: **none**. External action after final verification: one normal push of
  this scoped Linux branch only; no force-push and no unrelated remote change.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice. Continue only from the
next bounded direction recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm the memory-bound exact plan/receipt continuation plus independently reloaded terminal
  evidence correctly distinguishes intent, producer completion and read-only verification.
- Confirm Forge Control is the correct existing next intentional inspection after a verified
  non-bootable/non-flashable intermediate and must remain non-automatic.
- Confirm archive-drift failure preserves the correct evidence and no-retry behavior.

## Linux product checkpoint — verified Simulation points to intentional Forge Bundle

### Authoritative checkpoint and scope

- Tested implementation: `af061ac022d56548fcdceddabf19b36b47e78114` — `Guide verified
  Simulation to Forge Bundle`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`; the branch was clean immediately after the implementation
  commit and will be pushed normally after this handoff is committed.
- Product Assurance approval/base: `d4125cf` — approved automatic exact-tree verification and
  authorized only its immediate intentional Forge Bundle continuation.
- Stage: Stage 1 — v0.2 Golden Foundation, existing post-Simulation Guided continuity only.
- Exact changed implementation/test files: `src/romverse/ui/rom_studio.py`,
  `tests/test_navigation_vocabulary.py` and `tests/test_rom_studio_ui.py`. No Forge service,
  package, platform, device, Companion, Recovery adapter or product-scope file changed.

### Exact implemented behavior

- After an exact Simulation reaches independently validated `VERIFIED`, ROM Studio now focuses the
  existing enabled **Forge Bundle** control instead of the already-completed Verify plan control.
- The result handoff identifies Forge Bundle as the next intentional local action and states its
  precise boundary: an unsigned, non-bootable, non-flashable intermediate.
- Nothing is dispatched automatically. No Forge receipt or archive exists until the user chooses
  the existing action, and the existing Forge service remains responsible for fresh plan/tree
  revalidation before it can write.
- Verification drift/failure remains on the actionable stopped path, keeps Verify plan focused,
  preserves the exact plan/tree and creates no Forge Bundle or retry.

### Verification without double-counting

- One focused affected run: **7/7 unique tests passed** across the existing Command Deck,
  ROM Studio, representative fresh Guided Simulation and one existing Forge service adversary.
- The real-widget new-plan journey proves `VERIFYING → VERIFIED`, enabled/focused Forge Bundle,
  explicit non-flashable guidance, no remaining worker and no automatically created Forge receipt.
- The exact saved-plan journey proves the same Forge handoff after one fresh verification while
  preserving the saved plan and still creating no bundle automatically.
- The drifted/stopped widget journey proves current-tree mismatch keeps attention on Verify plan,
  schedules no retry and creates no Forge receipt.
- The existing service-level tree-drift adversary proves Forge refuses changed tree evidence before
  writing. Resource denial, forged verification evidence and fresh Guided continuity also pass in
  the same bounded selection.
- Ruff static and format checks passed for all three changed files. `git diff --check`: passed.
- No broad suite was run. This seven-test total is not combined with prior checkpoint totals.

### Classification, safety, platforms and gates

- **Implemented:** direct verified-Simulation focus/copy handoff to the existing Forge Bundle
  control.
- **Simulated/Tested:** 7 sanitized Linux-hosted Qt/store/planner/Forge-service journeys.
- **Hardware Verified:** no. **Released:** no.
- Guided friction removed: the completed Verify action is no longer presented as the next step.
  The next local action is visible and understandable, but remains intentional rather than
  automatic. Evidence drift remains a necessary actionable stop, not a loop.
- Guardian/Recovery/safety: no authority boundary changed. Forge Bundle remains an unsigned,
  non-bootable, non-flashable local intermediate. Exact evidence, Guardian-only execution,
  UNKNOWN-on-uncertainty, no blind retry, same-incident Recovery and permanent no-relock remain
  unchanged.
- Fedora/Linux: genuinely tested in the existing Fedora offscreen Qt development runtime. Windows:
  not run or claimed. Physical Android/hardware: not used.
- Feature freeze: compliant two-line production continuity correction using existing controls and
  services; no screen, feature, engine, artifact format or device capability was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and existing release gates.
- Current blockers/limitations: Product Assurance has not independently reviewed this checkpoint;
  Forge Bundle still requires the user's explicit action and its own service-side validation;
  neither a verified Simulation nor a Forge Bundle is a phone-capable build or execution authority.
- Protected Companion, Windows launcher, Knowledge/UI Design Lab, website and unrelated files were
  not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot, APK installation, firmware/device operation, real build,
  automatic Forge creation, flash/boot, partition/slot/wipe/unlock/lock/relock, package installation,
  publication and release: **none**. External action after final verification: one normal push of
  this scoped Linux branch only; no force-push and no unrelated remote change.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice. Continue only from the
next bounded direction recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that focusing the existing Forge Bundle control with explicit intermediate-artifact
  boundaries is the minimum correct continuation after verified Simulation.
- Confirm that the no-auto-dispatch widget evidence plus existing service-level tree-drift refusal
  preserves the intentional action and fresh revalidation boundaries.

## Linux product checkpoint — requested Simulation verifies its exact current tree

### Authoritative checkpoint and scope

- Tested implementation: `e931cb9649bb33507bd5ac31089c455cf93582c9` — `Verify automatic
  Simulation results`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`; the branch was clean immediately after the implementation
  commit and will be pushed normally after this handoff is committed.
- Product Assurance approval/base: `86efa4d` — approved one automatic invocation of the existing
  exact current-tree verifier after a newly completed or safely reloaded dry-run result.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Pre-Build Simulation verification continuation
  only.
- Exact changed implementation/test files: `src/romverse/ui/rom_studio.py`,
  `tests/test_navigation_vocabulary.py` and `tests/test_rom_studio_ui.py`. No platform, package,
  device, Companion, Recovery adapter or product-scope file changed.

### Exact implemented behavior

- One intentional Pre-Build Simulation request now continues from its newly completed exact typed
  `BuildPlan` into the existing `verify-plan` worker once. The same behavior applies when the exact
  final plan is safely reloaded; the saved plan is not regenerated or overwritten.
- ROM Studio keeps the complete immutable requested `BuildPlan` in memory only for this bounded
  continuation. At completion it independently reloads the durable plan, requires full object
  equality, requires the exact current project and accepts only a typed `ArtifactVerification`
  whose expected and actual tree digests match the plan and whose status is internally consistent.
- The in-progress handoff clearly says current-tree verification is read-only and starts no build,
  signing, execution or phone action. Exact success presents the existing dry-run result as
  `VERIFIED`, reports the verifier status and keeps the plan execution-locked.
- Tree drift, invalid verification, forged/mismatched success evidence or plan/project identity
  drift produces a visible actionable stop. The exact plan and current tree remain preserved, no
  success is inferred and no worker is automatically retried.
- Existing missing, malformed or interrupted-plan behavior remains unchanged: completion stays
  unknown, evidence is preserved and the user is directed to Build & Proof rather than placed in a
  retry loop.

### Verification without double-counting

- One focused affected run: **7/7 unique tests passed** across the existing Command Deck,
  ROM Studio and representative fresh Guided Simulation journeys.
- New-plan continuation proves exact production worker order
  `working-copy → extract → plan → verify-plan`, visible `VERIFYING → VERIFIED` state, durable
  exact plan reload, valid current-tree evidence, execution lock and no extra worker.
- Saved-plan continuation proves the exact plan is reloaded and verified once without running the
  planner again. Interrupted temporary evidence remains on disk, starts no worker and remains
  unknown without retry.
- The drift adversary changes the disposable contained tree after planning. Verification reports
  the exact mismatch, preserves the plan/tree, queues no retry and exposes no phone action.
- The forged-success adversary supplies a success-like typed result with digests from another tree.
  ROM Studio rejects it at its terminal evidence boundary, clears the transient continuation and
  presents the same actionable stopped state.
- Existing resource-admission denial and adjacent Recipes handoff checks pass in the same focused
  run. No overlapping prior suite total is added to this checkpoint.
- Ruff static and format checks passed for all three changed files. `git diff --check`: passed.
- No broad suite was run, matching the approved focused-test boundary.

### Classification, safety, platforms and gates

- **Implemented:** automatic exact-plan current-tree verification, full plan/result binding,
  verified result presentation and bounded no-retry failure handling.
- **Simulated/Tested:** 7 sanitized Linux-hosted Qt/store/planner journeys.
- **Hardware Verified:** no. **Released:** no.
- Guided friction removed: the user no longer needs a second technical Verify click after requesting
  Simulation. Genuine missing, malformed, changed, interrupted or ambiguous evidence remains an
  intentional actionable stop rather than a hidden dead end.
- Guardian/Recovery/safety: the result remains an inert execution-locked plan and independent
  current-tree observation only. It grants no real build, compatibility, consent, Guardian,
  Recovery, device or execution authority. UNKNOWN-on-uncertainty, no blind retry, exact-device
  evidence, same-incident Recovery and permanent no-relock rules remain unchanged.
- Fedora/Linux: genuinely tested in the existing Fedora offscreen Qt development runtime. Windows:
  not run or claimed. Physical Android/hardware: not used.
- Feature freeze: compliant continuity/correctness work in an existing Stage 1 journey. No screen,
  feature, engine, source format, adapter, device capability or product architecture was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and existing release gates.
- Current blockers/limitations: Product Assurance has not independently reviewed this checkpoint;
  successful dry-run verification is not a build or Recovery verification and cannot advance any
  consequential action; deliberately stopped evidence requires a new intentional Simulation
  request after the underlying evidence is resolved.
- Protected Companion, Windows launcher, Knowledge/UI Design Lab, website and unrelated files were
  not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot, APK installation, firmware/device operation, real build,
  flash/boot, partition/slot/wipe/unlock/lock/relock, package installation, publication and release:
  **none**. External action after final verification: one normal push of this scoped Linux branch
  only; no force-push and no unrelated remote change.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice. Continue only from the
next bounded direction recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that automatic reuse of the existing verifier removes the duplicate technical click
  while preserving independent current-tree verification and every later authority boundary.
- Confirm that full durable-plan equality plus exact expected/actual digest and status validation is
  the appropriate terminal evidence binding for this inert Simulation step.
- Confirm that drift, forged evidence and interrupted state remain sufficiently visible and
  actionable without introducing any automatic retry.

## Linux product checkpoint — requested Simulation completes its inert dry run

### Authoritative checkpoint and scope

- Tested implementation: `85aba5f2ff098b478d5f33dc8c887c281a774d06` — `Complete requested
  Simulation dry run`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`; the branch was clean immediately after the implementation
  commit and will be pushed normally after this handoff is committed.
- Product Assurance approval/base: `280a9a4` — approved fresh Guided continuity and authorized one
  automatic use of the existing bounded dry-run after the user's Simulation request.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Pre-Build Simulation continuation only.
- Exact changed files: `src/romverse/rom/builds.py`, `src/romverse/ui/rom_studio.py`,
  `tests/test_navigation_vocabulary.py` and `tests/test_rom_studio_ui.py`. No other implementation,
  platform or product file changed.

### Exact implemented behavior

- One intentional Command Deck Pre-Build Simulation request now remains active through the already
  approved exact-project working-copy/extraction preparation and then starts the existing `plan`
  worker once. It does not require a second technical Plan button click.
- The existing `RomBuildPlanner` remains the only dry-run engine. At its producer boundary it now
  verifies the protected original, requires current sealed inspection evidence and detects
  project/source/inspection metadata drift before atomically persisting its result.
- ROM Studio accepts the result only through its existing typed producer mapping and independent
  persisted-record equality check. The exact project-bound `BuildPlan` is presented with input,
  partition, tree-digest and Guardian preflight summary, remains execution-locked, and focuses the
  existing Verify plan continuation.
- Reopening Simulation with a structurally exact saved result presents that result without running
  the dry run again. A saved identity mismatch or malformed final record is preserved and stops
  visibly instead of being overwritten.
- A `build-plan.tmp` transaction marks completion unknown. ROMVERSE preserves it, starts no worker
  and offers the existing Build & Proof review path; it never infers success or blindly retries.
- A known planning failure—including fresh protected-source hash drift—records a bounded failure,
  preserves preparation evidence, starts no second worker and keeps the direct Build & Proof
  continuation visible.

### Verification without double-counting

- One focused affected run: **6/6 unique tests passed** across the Simulation UI, representative
  fresh Guided journey, existing ROM Studio handoff and existing locked planner contract.
- Success journey proves exact worker order `working-copy → extract → plan`, visible Simulation
  progress, a durable schema-two typed result, execution lock, valid current tree verification and
  zero additional worker after completion.
- The representative fresh-workspace production-service journey now durably reloads the exact
  project, protected original, inspection, working baseline, contained tree and BuildPlan after one
  initial Simulation request.
- At-most-once evidence proves reopening the same exact saved result starts zero workers. An
  additional interrupted temporary transaction reports unknown, remains on disk and also starts
  zero workers.
- Adversarial source-drift journey modifies only the disposable protected-source fixture after safe
  preparation; the planner rehash fails, no final BuildPlan is written, the contained tree remains,
  and no retry is queued.
- Existing insufficient-resource admission still starts no dry-run because preparation never
  becomes admissible.
- Ruff static check and format check passed for all four changed files. `git diff --check`: passed.
- No broad suite was run. The six-test total is not combined with or double-counted against prior
  checkpoints.

### Classification, safety, platforms and gates

- **Implemented:** request-bound automatic inert planning, producer-bound source/inspection drift
  validation, exact typed-result presentation, saved-result reuse and interrupted/no-retry stops.
- **Simulated/Tested:** 6 sanitized Linux-hosted Qt/store/planner journeys.
- **Hardware Verified:** no. **Released:** no.
- Guided friction removed: one Simulation choice now resolves safe local prerequisites and completes
  the intended bounded dry run without a duplicate technical click. Later tree verification remains
  a distinct visible evidence boundary.
- Guardian/Recovery/safety: the result is an inert execution-locked plan and Guardian preflight
  only. No real build, signing, approval, flash or execution authority exists. Exact-device,
  consent, UNKNOWN-on-uncertainty, no blind retry, independent verification, same-incident Recovery
  and permanent no-relock rules remain unchanged.
- Fedora/Linux: genuinely tested in the existing Fedora Qt development runtime. Windows: not run or
  claimed. Physical Android: not used.
- Feature freeze: compliant existing-journey continuity and correctness work; no parallel engine,
  new screen, format, feature, adapter or device capability was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and existing release gates.
- Current blockers/limitations: Product Assurance has not independently reviewed this checkpoint;
  the dry-run result still requires its separate existing current-tree verification before later
  build boundaries; malformed, drifted or interrupted saved evidence intentionally stops.
- Protected Companion, Windows launcher, Knowledge/UI Design Lab, website and unrelated files were
  not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot, APK installation, firmware/device operation, real build,
  flash/boot, partition/slot/wipe/unlock/lock/relock, package installation, publication and release:
  **none**. External action after final verification: one normal push of this scoped Linux branch
  only; no force-push and no unrelated remote change.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice. Continue only from the
next bounded direction recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that the existing persisted-record equality boundary plus producer-bound source,
  inspection and project stability checks satisfy typed exact-result validation for this inert
  planning step.
- Confirm that a saved exact plan should be presented without rerunning, while any interrupted temp,
  malformed record or identity drift stops for review with no automatic retry.
- Confirm that focusing the existing Verify plan control is the appropriate next independent
  boundary and that automatic tree verification is outside this checkpoint.

## Linux product checkpoint — fresh Guided project continuity

### Authoritative checkpoint and scope

- Tested implementation: `c15f0d3434591bd667ac26b33fb16554457597c8` — `Advance Genesis
  after project creation`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`; the branch was clean immediately after the implementation
  commit and will be pushed normally after this handoff is committed.
- Product Assurance approval/base: `e0a91f6` — approved the shared local-preparation coordinator and
  authorized one representative production-service fresh-workspace journey.
- Stage: Stage 1 — v0.2 Golden Foundation, first genuine continuity defect in the existing
  Start-ROM-Project → Simulation-readiness journey only.
- Exact changed files: `src/romverse/ui/guided_mission.py` and
  `tests/test_navigation_vocabulary.py`. No other implementation, platform or product file changed.

### Reproduced defect and minimum correction

- The real Command Deck `Start ROM Project` dispatch opened Genesis and project creation persisted
  the exact new workspace correctly, but Genesis refreshed while retaining the now-complete Project
  card. Firmware selection was available only after an unnecessary manual `Next` click. This was
  the first user-visible break in the requested fresh journey.
- The project-creation completion path now reselects the first stage lacking verified evidence,
  matching existing Genesis worker-completion behavior. A successful project creation therefore
  advances directly to Firmware; cancellation and failure behavior remain unchanged.
- The correction is one production-line behavior change. It does not automate firmware selection,
  change source responsibility, modify preparation services or alter Simulation/build semantics.

### Verification without double-counting

- One focused affected run: **3/3 unique tests passed**.
- The new representative MainWindow journey uses the real Command Deck primary button, real Genesis
  action controls, real project/import workers, real project/inspection stores and the approved real
  Simulation coordinator. Only the deterministic human project-name, local-file-selection and
  existing import-acknowledgement inputs are supplied by the harness; no navigation result,
  producer result or durable evidence is mocked.
- Demonstrated chain: fresh workspace → Start ROM Project → exact project manifest → automatic
  selection of Firmware → protected copy and SHA-256 ownership → saved bounded inspection →
  Simulation request → admitted working baseline → contained tree → Build & Proof readiness.
- A newly constructed project store/inspection service reloads the exact protected original,
  inspection, working-copy record and contained tree from disk after the journey. The external
  sanitized fixture remains byte-identical.
- The test proves the only production workers were exact-project `import`, `working-copy` and
  `extract`; no BuildPlan exists before or after the journey, no phone is present, and no modal is
  left open.
- Adjacent focused checks for the Genesis evidence-driven UI and transient new-project cancellation
  also passed.
- Ruff static check passed for both changed files. The changed test file passes Ruff format check.
  `guided_mission.py` retains unrelated pre-existing formatter drift outside this one-line hunk and
  was intentionally not mechanically reformatted. `git diff --check`: passed.
- No previously proven Recipes/Simulation unit journey and no broad suite was rerun. The 3-test
  total is not combined with or double-counted against earlier checkpoints.

### Classification, safety, platforms and gates

- **Implemented:** automatic Genesis continuation from verified project creation to the next
  unverified Firmware stage.
- **Simulated/Tested:** 3 sanitized Linux-hosted Qt/store journeys, including one production-service
  fresh-workspace journey.
- **Hardware Verified:** no. **Released:** no.
- Guided friction removed: a successful project no longer strands the user on a completed creation
  card. Firmware choice remains the intentional next human decision; after source inspection, the
  approved local coordinator resolves preparation and resumes Simulation readiness.
- Guardian/Recovery/safety: no build, plan, device, consent, Guardian, Recovery, durable-result or
  verification boundary changed. Exact-device evidence, UNKNOWN-on-uncertainty, no blind retry,
  independent verification and permanent no-relock remain authoritative.
- Fedora/Linux: genuinely tested in the existing Fedora Qt development runtime. Windows: not run or
  claimed. Physical Android: not used.
- Feature freeze: compliant one-line continuity correction to the existing Stage 1 Guided journey;
  no screen, format, feature, adapter or architecture was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all existing release gates.
- Current blockers/limitations: Product Assurance has not yet independently reviewed this
  checkpoint; firmware selection remains intentionally human-owned; Simulation still stops at
  readiness and does not create/run its dry-run plan automatically.
- Protected Companion, Windows launcher, Knowledge/UI Design Lab, website and unrelated files were
  not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot, APK installation, firmware/device operation,
  build/flash/boot, partition/slot/wipe/unlock/lock/relock, package installation, publication and
  release: **none**. External action after final verification: one normal push of this scoped Linux
  branch only; no force-push and no unrelated remote change.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice. Continue only from the
next bounded direction recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that selecting the first unverified stage immediately after successful project creation
  is the minimum zero-friction correction and preserves intentional firmware consent.
- Confirm the production-service durable-evidence journey sufficiently demonstrates the approved
  fresh-workspace continuity without rerunning previously proven unit slices.

## Linux product checkpoint — automatic exact-project Simulation preparation

### Authoritative checkpoint and scope

- Tested implementation: `a7c6857098d11a595fe5f627423c57d20894fc94` — `Automatically
  prepare exact Simulation inputs`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`; the branch was clean immediately after the implementation
  commit and will be pushed normally after this handoff is committed.
- Product Assurance approval/base: `e2f6b46` — approved the Recipes coordinator and authorized its
  minimum reuse for existing Pre-Build Simulation continuity.
- Stage: Stage 1 — v0.2 Golden Foundation, one existing Command Deck Pre-Build Simulation
  local-prerequisite gap only.
- Exact implementation files: `src/romverse/ui/rom_studio.py` and
  `tests/test_navigation_vocabulary.py`. No other implementation, platform or product file changed.

### Exact implemented behavior

- The already-approved Recipes-only preparation coordinator is minimally generalized into one
  destination-bound local coordinator shared by exactly `Recipes` and `Pre-Build Simulation`; no
  second preparation engine or persistent authority state was created.
- An exact Simulation request with a protected original and current valid inspection now admits the
  same existing bounded working-copy/extraction producers, whole-sequence storage budget, critical
  finding denial, exact project binding, independently reloaded completion evidence and visible
  progress already approved for Recipes.
- After the contained-tree result passes current readiness, ROMVERSE resumes the original
  Simulation request at existing Build & Proof dry-run readiness and focuses its existing plan
  control. It does not run the plan, generate a BuildPlan or start a build.
- Insufficient resource admission starts no worker or write and retains the exact project in Source
  Lab with a direct Simulation continuation. Known worker failures use the same destination-aware
  bounded-stop path proven by Recipes, preserve verified partial progress and schedule no retry.
- Recipe creation and execution, device compatibility, Guardian authority and all phone operations
  remain outside this coordinator.

### Verification without double-counting

- One bounded affected run: **7/7 unique tests passed** across
  `tests/test_navigation_vocabulary.py` and `tests/test_rom_studio_ui.py`.
- New real offscreen MainWindow success journey: exact project → Pre-Build Simulation → verified
  isolated baseline → verified contained tree → automatic Build & Proof readiness resume. The test
  proves no BuildPlan exists before, during or after this preparation.
- New admission adversary: deterministic insufficient storage starts zero workers, creates no
  baseline/tree/BuildPlan and leaves the exact Source Lab continuation visible.
- Shared-coordinator regressions: all three existing Recipes success, known-failure/no-retry and
  resource-denial journeys passed unchanged.
- Adjacent no-project Command Deck routing and already-ready ROM Studio Simulation/Recipes handoff
  journeys passed in the same seven-test run.
- Ruff static check: both changed files passed. Ruff format check: both changed files passed.
  `git diff --check`: passed.
- No broad suite was run, per the approved focused-test boundary. The seven-test total is not added
  to or double-counted against the prior five-test checkpoint.

### Classification, safety, platforms and gates

- **Implemented:** shared exact-project local-preparation coordination and Pre-Build Simulation
  automatic prerequisite/resume continuity.
- **Simulated/Tested:** 7 sanitized Linux-hosted Qt/store journeys.
- **Hardware Verified:** no. **Released:** no.
- Guided friction removed: an inspected exact project no longer requires two technical preparation
  choices before reaching Simulation dry-run readiness. Remaining intentional stops are missing or
  invalid evidence, critical findings, insufficient resources, producer failure, drift, ambiguity,
  or an already-busy project.
- Guardian/Recovery/safety: no build or device boundary changed. Guardian-only authority,
  exact-device evidence, consent separation, durable result/verification boundaries,
  UNKNOWN-on-uncertainty, no blind retry, same-incident handling and permanent no-relock remain
  authoritative.
- Fedora/Linux: genuinely tested in the existing Fedora Qt development runtime. Windows: not run or
  claimed; Windows launcher work was untouched. Physical Android: not used.
- Feature freeze: compliant correction to one existing Stage 1 continuity path; no new screen,
  format, product capability, adapter or architecture was added.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and existing release gates.
- Current blockers/limitations: the checkpoint awaits independent Product Assurance review;
  Simulation still requires the user to intentionally choose the existing dry-run action after
  preparation, and unsafe/ambiguous evidence remains an intentional stop.
- Protected Companion work, Windows launcher work, Knowledge/UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot, APK installation, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, package installation, publication and release: **none**.
  External action after final verification: one normal push of this scoped Linux branch only; no
  force-push and no unrelated remote change.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice. Continue only from the
next bounded direction recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that the destination-bound generalization preserves the previously approved Recipes
  behavior without introducing a second preparation engine.
- Confirm that automatic resume to current dry-run readiness—without generating or running the
  BuildPlan—is the correct boundary for this Simulation continuity checkpoint.
- Confirm the existing shared known-failure/no-retry coverage plus the new Simulation
  resource-admission stop are proportionate acceptance evidence for this bounded slice.

## Linux product checkpoint — automatic exact-project Recipes preparation

### Authoritative checkpoint and scope

- Tested implementation: `18a0537992b04a8e5e5373fe069da12f70af24a6` — `Automatically
  prepare exact Recipes inputs`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`; the branch was clean immediately after the implementation
  commit and will be pushed normally after this handoff is committed.
- Approved base: `b13481a62fe4d7abd0d2986550318d860cf88b38` — creator Guided Experience
  contract lock.
- Stage: Stage 1 — v0.2 Golden Foundation, one existing Command Deck Recipes automatic-resolution
  gap only.
- Exact implementation files: `src/romverse/ui/rom_studio.py` and
  `tests/test_navigation_vocabulary.py`. No other implementation, platform or product file changed.

### Exact implemented behavior

- An exact selected project with a protected original and current valid structure inspection may
  now satisfy the already-required Recipe Forge contained-tree prerequisite automatically.
- Before starting, ROMVERSE rejects critical inspection findings and proves an extraction budget.
  If an isolated baseline is also missing, admission reserves space for that baseline in addition
  to the extracted tree and retained Guardian reserve. Missing/invalid evidence or insufficient
  storage starts no worker and leaves a direct Source Lab continuation visible.
- After admission, ROMVERSE runs only the existing bounded local `working-copy` producer when
  needed, independently reloads its durable evidence at the existing completion boundary, then
  re-admits and runs only the existing bounded `extract` producer. Each worker remains bound to the
  exact project ID; progress states explicitly state that the protected source and phone are
  unchanged.
- Only the independently accepted contained-tree result resumes the original Recipes request and
  opens the existing Recipe Forge. Navigation creates no recipe and grants no build, approval,
  Guardian, device or execution authority.
- A known producer exception records `FAILED`, preserves any already-verified baseline, returns to
  the focused Source Lab continuation and schedules no retry. Project/evidence drift stops the
  coordinator rather than adopting another project or guessing. Existing UNKNOWN-on-uncertainty
  and interrupted-workspace recovery semantics were not changed.

### Verification without double-counting

- One bounded affected run: **5/5 unique tests passed** across
  `tests/test_navigation_vocabulary.py` and `tests/test_rom_studio_ui.py`.
- Real offscreen MainWindow success journey: exact project → Recipes → measured isolated baseline
  producer → measured contained-tree producer → independently reloaded evidence → automatic return
  to Recipe Forge. The RecipeStore stays empty and no modal appears.
- Real offscreen MainWindow bounded-failure journey: baseline succeeds, extraction producer raises a
  deterministic known failure, baseline remains valid, tree/recipe remain absent, failure is
  visible, and zero retry workers are queued.
- Admission adversary: a deterministic insufficient-resource result starts zero workers and creates
  neither a working baseline nor a tree.
- Adjacent existing no-project Command Deck routing and already-ready ROM Studio handoff journeys
  also passed in the same five-test run.
- Ruff static check: both changed implementation/test files passed. Ruff format check: both changed
  files passed. `git diff --check`: passed.
- No broad regression was run, as Product Assurance explicitly constrained this checkpoint to
  focused affected tests. The five-test total is not combined with or double-counted against any
  earlier suite.

### Classification, safety, platforms and gates

- **Implemented:** exact Recipes local-prerequisite admission, sequencing, producer-result
  revalidation, bounded-stop behavior and automatic destination resume.
- **Simulated/Tested:** 5 sanitized Linux-hosted Qt/store journeys; no device or hardware simulation
  was presented as physical verification.
- **Hardware Verified:** no. **Released:** no.
- Guided friction removed: a safely resolvable inspected project no longer strands the user at two
  technical Source Lab controls. Remaining intentional stops are missing/invalid source or
  inspection evidence, critical structure findings, insufficient storage, producer failure, drift,
  or a busy exact project.
- Guardian/Recovery: no device boundary, Recovery adapter, consent, execution, durable-result or
  verification contract changed. Guardian-only authority, exact-device evidence,
  UNKNOWN-on-uncertainty, no blind retry, same-incident handling, independent verification and
  permanent no-relock remain authoritative.
- Fedora/Linux: genuinely tested in the existing Fedora Qt development runtime. Windows: not run or
  claimed; Windows launcher work was not inspected or modified. Physical Android: not used.
- Feature freeze: compliant foundation/correctness repair to one existing Stage 1 journey; no new
  screen, format, product capability or architecture was introduced.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and all existing release gates.
- Current blockers/limitations: Product Assurance has not yet independently reviewed this
  checkpoint; missing evidence and unsafe/insufficient-resource states intentionally remain manual
  evidence-resolution stops; no hardware or Windows claim exists.
- Protected Companion work, Windows launcher work, Knowledge/UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot, APK installation, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, package installation, publication and release: **none**.
  External action after final verification: one normal push of this scoped Linux branch only; no
  force-push and no unrelated remote change.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice. Continue only from the
next bounded direction recorded in `docs/sync/PRODUCT-ASSURANCE.md`.

### Product Assurance Review Requested

- Confirm that the whole-sequence storage admission, exact-project coordinator and existing
  producer completion checks are sufficient for this reversible local preparation boundary.
- Confirm that a proven producer exception should remain `FAILED` while process/transport ambiguity
  retains the existing `UNKNOWN`/recovery treatment, with no automatic retry.
- Confirm the Guided success resume and bounded Source Lab failure continuation close exactly the
  approved Recipes gap without expanding Stage 1.

## Linux product checkpoint — connected exact-project Recipes handoff

### Authoritative checkpoint

- Product Assurance approval/base: `1f05268` — approved connected Simulation continuity and
  authorized the bounded existing Recipes handoff inspection.
- Creator connected-journey contract remained acceptance criteria only: retain exact context and
  open an existing resolvable prerequisite without weakening consequential safety boundaries.
- Tested implementation: `68c7cf5d6c7d5c44e65dccc905fb55ae80a1fd8b` — `Connect Recipes to
  exact project prerequisite`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Command Deck Recipes handoff.

### Reproduced defect and exact correction

- Command Deck's Recipes action always opened Recipe Forge, even when the exact current project
  lacked its contained working tree. ROM Studio truthfully described the prerequisite, but the
  responsible preparation action remained in Source Lab, leaving the user at a non-resolving tab.
- Recipes now retains the exact current project and opens Source Lab when project creation, source
  import, working-copy creation or safe-tree preparation is the current existing prerequisite. The
  appropriate existing control receives focus.
- Once the exact project's protected source and contained tree exist, the same action opens Recipe
  Forge and focuses its existing guided entry. If those inputs are complete but a bounded Studio
  worker is active, Recipe Forge remains visible with the existing truthful wait prerequisite.
- Navigation does not open the recipe designer modal, create a recipe, preview/apply an operation,
  mutate firmware or start any worker.

### Verification without double-counting

- One final bounded run: **4/4 unique focused tests passed** — the new exact-project two-state
  Recipes journey, the existing Command Deck route journey, the adjacent connected Simulation
  journey and the existing ready ROM Studio Simulation/Recipes handoff journey.
- New sanitized real MainWindow coverage proves an unprepared project opens Source Lab on that same
  project with working-copy preparation available; after test-created contained-tree evidence, the
  same project opens Recipe Forge with a truthful `READY` explanation.
- Before and after both navigation actions, `RecipeStore` remains empty, the genuine event ledger
  is unchanged, no ROM Studio worker exists and no modal decision opens.
- Ruff static check: **2/2 changed implementation/test files passed**. Ruff format check: **2/2
  passed**. `git diff --check`: passed.
- No broad regression, package build, screenshot loop or physical-device test was run.

### Classification, safety, platforms and gates

- **Implemented:** exact-project routing to Recipe Forge or its current existing Source Lab
  prerequisite.
- **Simulated/Tested:** four sanitized synthetic Qt widget/store journeys.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction/dead end: a prerequisite no longer leaves the user inside an unusable Recipe
  Forge tab or requires rediscovery of Source Lab/project context.
- This is navigation only. It creates no recipe/result, changes no project/firmware, starts no build,
  infers no compatibility and issues no device command.
- Exact-device/source/project evidence, Guardian-only authority, applicable consent,
  UNKNOWN-on-uncertainty, durable intent/result, no blind retry, same-incident Recovery,
  independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt widget/store journeys verified. Windows: not run or claimed;
  Windows managed-tool recovery work was untouched.
- Feature freeze: compliant correction to an existing Stage 1 journey. v0.2 Golden Foundation
  remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. Continue only from its next bounded existing-journey direction;
do not broaden Stage 1.

### Product Assurance Review Requested

- Confirm direct Source Lab prerequisite focus and exact-project Recipe Forge routing are the
  minimum correction for the existing Recipes dead end.
- Confirm navigation remains strictly inert because the RecipeStore, ledger, worker and modal state
  remain unchanged.

## Linux product checkpoint — connected exact-input Simulation handoff

### Authoritative checkpoint

- Product Assurance approval/base: `0f2d221` — approved Mission Pulse continuity and authorized
  inspection of Pre-Build Simulation first, with Recipes only if Simulation already worked.
- Creator experience contract received during the slice was applied as acceptance criteria only:
  unavailable states must retain exact context and open their existing responsible action without
  weakening any consequential safety boundary.
- Tested implementation: `c7ea82f00f0e9b74344d16e3cddaeb653cf1cfec` — `Connect Simulation
  readiness to exact inputs`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Command Deck Pre-Build Simulation handoff.

### Reproduced defect and exact correction

- Command Deck previously labelled Pre-Build Simulation `READY` whenever protected firmware
  existed, while ROM Studio correctly required a saved structure inspection and contained working
  tree. Clicking the apparently ready card then produced `PREREQUISITE` and opened Build & Proof,
  leaving the actual preparation action back in Source Lab.
- Command Deck now receives Simulation readiness from the same current-project ROM Studio contract
  used by the destination. Firmware without complete inputs reports `PREPARE INPUTS`; only the exact
  current project's inspection and contained tree report `READY`.
- A missing-input click retains the exact project and opens Source Lab with focus on the existing
  next responsible control: project creation, source import, structure inspection, working-copy
  creation or safe-tree preparation as applicable. A ready click opens Build & Proof and focuses
  the existing dry-run plan control.
- The busy-operation case retains Build & Proof and its truthful wait prerequisite because its
  inputs are already complete; no operation is cancelled or inferred.
- Recipes was not inspected or changed because a genuine defect was found in the first authorized
  path.

### Verification without double-counting

- One bounded affected run: **29/29 unique tests passed** — the complete Command Deck rendering
  widget suite, the real exact-project Simulation journey, the existing Command Deck route journey
  and the existing ready ROM Studio handoff journey.
- New sanitized real MainWindow coverage proves the same exact project first reports/previews its
  missing contained tree in Source Lab, then reports `READY` and opens Build & Proof after the test
  creates the existing working copy/tree evidence. Both destinations name the same project.
- The test proves navigation preserves the ledger byte-for-byte, starts no ROM Studio worker, opens
  no modal decision and claims only `Execution remains locked` on the ready dry-run path.
- Ruff static check: **5/5 changed implementation/test files passed**. Ruff format check passed for
  the four changed files without inherited drift; `device_center.py` retains unrelated pre-existing
  formatter drift and was not mechanically reformatted.
- `git diff --check`: passed. No broad regression, package build, screenshot loop or physical-device
  test was run.

### Classification, safety, platforms and gates

- **Implemented:** one shared current-project Simulation readiness result plus direct existing
  prerequisite/ready destination selection.
- **Simulated/Tested:** 29 sanitized synthetic Qt widget/store journeys.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction/dead end: the card no longer contradicts its destination, and missing evidence
  opens the owner/action that can provide it without making the user rediscover project context.
- This is navigation/readiness presentation only. It does not automatically prepare inputs, run a
  plan/build, create a mission result, claim compatibility, alter firmware or issue a device command.
- Exact-device/source/project evidence, Guardian-only authority, applicable consent,
  UNKNOWN-on-uncertainty, durable intent/result, no blind retry, same-incident Recovery,
  independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt widget/store journeys verified. Windows: not run or claimed;
  Windows Device Engine work was untouched.
- Feature freeze: compliant correction to an existing Stage 1 journey. v0.2 Golden Foundation
  remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. If approved, follow its next bounded existing-journey direction;
do not assume Recipes is next or broaden Stage 1.

### Product Assurance Review Requested

- Confirm sharing ROM Studio's exact current-project readiness result with Command Deck is the
  minimum correct defense against the false-ready handoff.
- Confirm direct Source Lab prerequisite focus and Build & Proof ready focus satisfy the connected
  Guided journey contract without starting work or adding another confirmation.

## Linux product checkpoint — durable Mission Pulse warning visibility

### Authoritative checkpoint

- Product Assurance approval/base: `fbf1f4d` — approved exact Command Deck mission resume and
  authorized the adjacent Mission Pulse/direct Live Operations continuity inspection.
- Tested implementation: `a19d2db60863239b6bb2d8e7d8d8ae77e717a2f5` — `Keep Mission Pulse
  warnings visible`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Command Deck Mission Pulse continuity.

### Reproduced defect and exact correction

- Mission Pulse previously displayed an urgent warning only when the newest ledger record itself
  was `FAILED`, `BLOCKED` or `ATTENTION`. A newer ordinary informational note therefore replaced
  the warnings panel with `No unresolved warning` even though the genuine warning remained in the
  verified ledger.
- Mission Pulse now selects the newest genuine warning record from its existing bounded ledger
  view independently of newer information/success records. It continues to show only one warning,
  preserving the existing compact presentation and event ordering.
- The adjacent direct `Open Live Operations` route was inspected and is correct: after leaving an
  exact project/mission Resume view, deliberate Mission Pulse navigation restores the complete
  global ledger, including unrelated genuine records. It was not rewritten or project-scoped.

### Verification without double-counting

- One bounded affected run: **30/30 unique tests passed** — the complete Command Deck rendering
  widget suite plus four focused Command Deck navigation/mission journeys.
- New synthetic ledger/widget coverage proves an older verified Recovery attention remains visible
  after a newer Device Engine information record and the false `No unresolved warning` copy is not
  displayed.
- New real MainWindow coverage proves a scoped current-project Resume view contains only its exact
  mission, then Mission Pulse direct navigation restores both current and unrelated genuine global
  records. The ledger is unchanged and no ROM Studio, Recovery host or online worker starts.
- Ruff static check: **3/3 changed implementation/test files passed**. Ruff format check passed for
  both changed test files; `device_center.py` retains unrelated pre-existing formatter drift and was
  not mechanically reformatted.
- `git diff --check`: passed. No broad regression, package build, screenshot loop or physical-device
  test was run.

### Classification, safety, platforms and gates

- **Implemented:** latest genuine warning selection for the existing Mission Pulse warning lane.
- **Simulated/Tested:** 30 sanitized synthetic Qt widget/store journeys.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: newer routine information can no longer make an existing genuine warning appear
  resolved or absent. The compact pulse still gives one clear next action.
- Mission Pulse and Live Console remain read-only views of producer-recorded evidence. Navigation
  creates no event, progress or result, changes no ownership, starts no worker and grants no build,
  consent, Guardian or execution authority.
- Exact-device evidence, Guardian-only authority, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt widget/store journeys verified. Windows: not run or claimed;
  Windows Device Engine/Build Control work was untouched.
- Feature freeze: compliant correction to an existing Stage 1 status surface. v0.2 Golden
  Foundation remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. If approved, inspect only the next adjacent shipped Command Deck
action with a reproducible continuity/dead-end defect; do not broaden Stage 1.

### Product Assurance Review Requested

- Confirm retaining the newest genuine warning independently of later informational events is the
  minimum correct Mission Pulse behavior.
- Confirm the direct Live Operations path remains the intentionally complete global ledger after
  leaving an exact Resume context.

## Linux product checkpoint — exact current Command Deck mission ledger

### Authoritative checkpoint

- Product Assurance approval/base: `50e3eec` — approved exact Command Deck Recovery context and
  authorized the bounded Resume Mission → Live Operations continuity check.
- Tested implementation: `46533cafaa75962c71f7551eb6c0689b7572f292` — `Bind Command Deck
  resume to current mission`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Command Deck mission-ledger continuity.

### Reproduced defect and exact correction

- Command Deck previously selected the newest running mission from the entire local ledger. A
  newer event from unrelated Project B could therefore replace Project A's real active mission in
  A's `Resume Mission` card; opening Live Operations then selected the unrelated newest event.
- Command Deck now retains the exact current project ID, derives its active mission only from that
  project's genuine ledger events, and labels Resume Mission from that project-owned state.
- The Resume action independently reloads and revalidates the exact mission/project pair at click
  time. Live Console opens a temporary mission-scoped view containing only records for that exact
  pair; direct Live Console navigation continues to expose the ordinary complete ledger.
- If the current mission becomes terminal or disappears between rendering and the click, ROMVERSE
  does not adopt another project's running mission. It follows the existing truthful current-
  project Genesis fallback without fabricating progress or starting work.
- Global Mission Pulse warnings and accomplishments remain global and unchanged; only active
  Resume ownership and its destination are project-scoped.

### Verification without double-counting

- One affected regression run: **40/40 unique tests passed** — the complete Command Deck rendering
  and Live Console widget suites plus four focused Command Deck continuity journeys.
- New sanitized synthetic widget/store coverage proves that a newer running event for Project B is
  excluded while Project A's exact mission opens alone, the selected project/device remain
  unchanged, both genuine events remain running and byte-for-byte ledger state is unchanged.
- A second adversarial journey proves that if Project A's event finishes after Command Deck renders
  but before the click, Project B is not substituted and the existing Genesis fallback opens for
  Project A with no new ledger event, modal decision or worker.
- Ruff static check: **5/5 changed implementation/test files passed**. Ruff format check passed for
  the four files without inherited drift; `device_center.py` retains unrelated pre-existing
  formatter drift and was not mechanically reformatted.
- `git diff --check`: passed. No broad regression, package build, screenshot loop or physical-device
  test was run.

### Classification, safety, platforms and gates

- **Implemented:** exact current-project mission selection, click-time revalidation and temporary
  exact-mission Live Console view.
- **Simulated/Tested:** 40 sanitized synthetic Qt widget/store tests.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: Resume Mission now opens the one relevant live record directly. A stale rendered
  action returns calmly to the existing Genesis journey instead of showing an unrelated stream.
- Ledger context is read-only navigation evidence. It creates no event or progress, changes no
  ownership, starts no worker and grants no build, consent, Guardian or execution authority.
- Exact-device evidence, Guardian-only authority, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt widget/store journeys verified. Windows: not run or claimed;
  Windows Build Control work was untouched.
- Feature freeze: compliant correction to an existing Stage 1 route. v0.2 Golden Foundation remains
  **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. If approved, inspect only the next adjacent existing Command
Deck continuity route with one reproducible defect; do not broaden Stage 1.

### Product Assurance Review Requested

- Confirm project-owned active selection plus click-time exact mission/project revalidation is the
  minimum correct boundary for Resume Mission.
- Confirm the temporary exact-mission view and stale-action Genesis fallback preserve the intended
  zero-friction Guided behavior without hiding the global ledger from direct navigation.

## Linux product checkpoint — exact-device Command Deck Recovery handoff

### Authoritative checkpoint

- Product Assurance approval/base: `0168582` — approved shared exact Command Deck ROM Mission
  entry and authorized inspection of the existing Diagnose/Recover routes.
- Tested implementation: `74092ee41e0ad50d818cd3767cf5382c02bb5a7d` — `Bind Command Deck
  recovery finding to exact device`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Command Deck Diagnose/Recover context
  continuity.

### Reproduced defect and exact correction

- `Diagnose Problem` was inspected first and already opens the current selected device's
  read-only Diagnostics owner; its passing path was not rewritten.
- `Recover Device` previously forwarded the actionable finding from Diagnostics by finding ID
  alone. If Diagnostics retained Phone A while Recovery was bound to Phone B, an identical finding
  ID on both phones (for example `storage.capacity`) allowed A's diagnostic context to be displayed
  as B's Recovery context.
- Command Deck now obtains its one explicitly selected device and requires it to match the current
  diagnostic report device before forwarding a finding. Recovery independently verifies the
  expected serial before accepting that context.
- A mismatch opens the existing calm general Recovery intake with `EXACT DIAGNOSTIC NEEDS FRESH
  EVIDENCE`; it keeps the selected Recovery target, current project and incident history unchanged,
  starts no worker and implies no recovery result.

### Verification without double-counting

- Affected regression: **36/36 unique tests passed** — five focused Command Deck/Recovery widget
  journeys plus all 31 Repair UI tests. The focused set includes the reproduced same-finding-ID
  cross-device collision, exact current handoff, general intake, mismatched Recovery evidence and
  existing primary routing.
- The new real-widget test uses a temporary isolated workspace and sanitized synthetic phones. It
  proves Phone A's diagnosis is rejected for selected Phone B, the project stays unchanged, no
  incident is created or duplicated, and no session, host worker or online worker starts.
- Post-audit rerun of the new regression: **1/1 passed** using the current branch source.
- Ruff static check: **4/4 changed implementation/test files passed**. The repository has unrelated
  pre-existing formatter drift in `device_center.py`; it was not reformatted or included.
- `git diff --check`: passed. No broad regression, package build, screenshot loop or physical-device
  test was run.

### Classification, safety, platforms and gates

- **Implemented:** exact-device validation at both Command Deck sender and Recovery owner boundary.
- **Simulated/Tested:** 36 sanitized synthetic Qt widget regressions.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: an unsafe cross-device context now degrades to one actionable, non-modal fresh-
  evidence message rather than a dead end or false plan. The correct-device path remains unchanged.
- Diagnostic context remains evidence only. It grants no Recovery incident, consent, Guardian or
  execution authority and cannot imply durable result, reassessment or verification.
- Exact-device evidence, Guardian-only authority, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt journeys verified. Windows: not run or claimed; Windows Build
  Control work was untouched.
- Feature freeze: compliant correction to an existing Stage 1 route. v0.2 Golden Foundation remains
  **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. Do not begin another consequential slice until this exact-device
Recovery boundary is independently reviewed.

### Product Assurance Review Requested

- Confirm that validating exact identity at both the Command Deck handoff and Recovery owner is the
  minimum correct defense against stale cross-device diagnostic attribution.
- Confirm the calm fresh-evidence intake is the correct Guided fallback without introducing another
  confirmation or duplicate incident.

## Linux product checkpoint — shared exact Command Deck ROM Mission entry

### Authoritative checkpoint

- Product Assurance approval/base: `e67f289` — approved zero-match ROM Mission handoff and
  completed Device Intelligence ownership sequence.
- Tested implementation: `312b3458b6f8f445f48d05cd83ce2010b9225067` — `Share exact ROM
  mission entry from Command Deck`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Command Deck primary ROM project/mission
  continuity.

### Reproduced defect and exact correction

- With one live synthetic device, one exact Pack-matching saved project and an unrelated retained
  ROM Studio project, Command Deck's primary `Start ROM Project` action bypassed the completed
  Device Intelligence ownership boundary and opened Genesis on the unrelated project.
- Command Deck `Build ROM` and `Continue Genesis` now reuse the already-approved Device
  Intelligence `Start ROM Mission` boundary whenever a current selected device and current Pack
  report exist. They therefore receive the same single/multiple/zero saved-project ownership rules
  and the same independent exact device, Device DNA, Compatibility Matrix and Pack/report
  validation.
- If no current Device Intelligence report/selected device exists, the established Command Deck
  behavior remains unchanged: ROM Studio opens its ordinary first-use or retained-project Genesis
  path. No duplicate Guided session, project mutation or worker is introduced.

### Verification without double-counting

- Focused/affected real-widget coverage: **6/6 unique tests passed** — the reproduced Command Deck
  primary-action journey, existing Command Deck routing, exact Device Intelligence handoff,
  single-match ownership, multiple-match selection/cancellation and zero-match transient project
  creation/cancellation.
- The new test uses a temporary isolated workspace and sanitized synthetic device evidence. It
  proves the primary button selects the one exact saved owner, opens exactly one Guided context,
  retains the current device and Pack, carries the current DNA digest and advisory
  `guardian_flash: Unknown` Matrix verdict, excludes the unrelated project and starts no worker.
- Ruff static check: **2/2 changed implementation/test files passed**.
- `git diff --check`: passed.
- No broad regression, package build, screenshot loop or physical-device test was run.

### Classification, safety, platforms and gates

- **Implemented:** shared exact mission entry for Command Deck's existing ROM primary actions.
- **Simulated/Tested:** six focused synthetic Qt widget journeys.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: Command Deck no longer creates a competing ownership path or silently enters an
  unrelated project when current Device Intelligence is available. It opens one shared mission.
- Device/Pack/DNA/Matrix context remains evidence and navigation only. `UNCONFIRMED` remains
  advisory `Unknown`; no compatibility, build, consent, Guardian or execution authority flows.
- Exact-device validation, Guardian separation, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt journeys verified. Windows: not run or claimed; Windows Build
  Control work was untouched.
- Feature freeze: compliant correction to an existing Stage 1 action. v0.2 Golden Foundation
  remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. If approved, inspect the next existing Command Deck primary
action with a concrete continuity/runtime defect; do not broaden Stage 1 or cross a consequential
boundary.

### Product Assurance Review Requested

- Confirm that reusing Device Intelligence's completed ownership/evidence boundary is the minimum
  correct way to prevent Command Deck from creating a second inconsistent ROM Mission path.

## Linux product checkpoint — zero-match Genesis new-project entry

### Authoritative checkpoint

- Product Assurance approval/base: `0458aa3` — approved explicit ROM Mission project choice.
- Tested implementation: `2e366b45725ede030e6d9999e866c5b5efaea580` — `Route unmatched
  device into new ROM project mission`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, adjacent existing Device Intelligence Hub zero-match
  `Start ROM Mission` journey.

### Exact behavior

- When the retained ROM Studio project is Pack-mismatched and no saved project matches Device
  Intelligence's current exact Pack, `Start ROM Mission` now routes to ROM Studio and opens the
  existing Genesis `New project` stage instead of stopping or entering the unrelated project.
- This entry is transient until the user completes the existing local project-name action. Genesis
  presents no firmware or Compatibility verdict from the unrelated project and persists no Guided
  state into it. The current live device and exact Pack ID are carried only as a suggestion for a
  potential new project.
- Cancelling the existing project-creation dialog leaves Genesis at `New project`. Closing Genesis
  and returning to Device Intelligence preserves the unrelated selected project, all saved
  projects and all project evidence unchanged.
- A completed existing project-creation action remains the only point at which a new project is
  created; it uses ROM Studio's existing suggested-Pack behavior and then reloads ordinary
  project-bound Genesis state. No project is created, associated, merged or modified merely by
  entering or cancelling this route.

### Verification without double-counting

- Focused and affected Qt widget run: **57/57 unique tests passed** — one new real zero-match
  journey, the three adjacent Device Intelligence ownership/evidence journeys and all 53 ROM Studio
  UI tests. The focused test was rerun once after formatting cleanup only as confirmation and is not
  double-counted.
- The new path uses a temporary isolated workspace and sanitized synthetic device evidence. It
  proves the transient context reports no project, retains the current live target and Pack
  suggestion, shows `AWAITING COMPARISON`, cancels project creation without a new manifest or
  Guided state, and returns to Device Intelligence with the unrelated project intact.
- Ruff static check: **4/4 changed implementation/test files passed**.
- `git diff --check`: passed.
- No broad regression, package build, screenshot loop or physical-device test was run.

### Classification, safety, platforms and gates

- **Implemented:** zero-match routing into the existing transient Genesis new-project stage.
- **Simulated/Tested:** sanitized synthetic Qt widget journey and 57 affected tests.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: zero-match users now receive the existing actionable first project step; cancel
  and return are calm and non-mutating. No new confirmation or product capability was introduced.
- The Pack suggestion, current Device DNA, historical evidence and navigation convenience grant no
  compatibility, build, consent, Guardian or execution authority. `UNCONFIRMED` remains advisory
  `Unknown`.
- Exact-device/DNA/Matrix validation, Guardian separation, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt journey verified. Windows: not run or claimed; Windows work was
  untouched.
- Feature freeze: compliant minimum completion of an existing Stage 1 journey. v0.2 Golden
  Foundation remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. Continue only with the next approved adjacent existing Device
Intelligence journey; do not broaden Stage 1 or cross a consequential boundary.

### Product Assurance Review Requested

- Confirm the transient no-project Genesis context correctly preserves the unrelated current
  project while retaining only suggestion-level live device/Pack context.
- Confirm project-dialog cancellation, mission close and owner return are sufficiently inert.

## Linux product checkpoint — explicit ambiguous ROM Mission ownership

### Authoritative checkpoint

- Product Assurance approval/base: `4e9c772` — approved exact ROM Mission project selection.
- Tested implementation: `f869f59e97aab0854ed8456b8c0dbbabe08305a7` — `Require explicit
  ambiguous ROM project choice`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, adjacent existing Device Intelligence Hub ambiguous
  saved-project ownership journey.

### Exact behavior

- When the current ROM Studio project does not match Device Intelligence's current exact Pack and
  multiple saved projects do, `Start ROM Mission` now presents one local, non-editable project
  choice. Each choice includes its saved name, exact project ID and protected-source filename or
  truthful `firmware not imported` status.
- ROMVERSE continues only with the user's explicitly selected saved owner, refreshes that
  project's current DNA/Compatibility evidence, then passes through the already-approved
  independent Device Intelligence → ROM Studio validation.
- Cancellation remains on Device Intelligence, reports that the choice was cancelled and starts no
  worker. No project or evidence is changed by presenting or cancelling the choice.
- The existing zero-friction automatic path remains limited to exactly one matching saved project.
  Zero matches now stop truthfully on Device Intelligence instead of opening an unrelated current
  project. Zero and multiple matches are never guessed.

### Verification without double-counting

- Focused real-widget coverage: **3/3 passed** — the multiple-match selection/cancellation journey,
  the sole-match automatic journey and the existing exact Device Intelligence mission handoff.
- The new journey uses a temporary isolated workspace and sanitized synthetic device evidence. It
  proves both matching projects are offered, explicit selection enters Guided with the selected
  exact owner, and cancellation retains the unrelated current project while remaining on Device
  Intelligence. No worker starts in either choice operation.
- Ruff static and format checks: **2/2 changed implementation/test files passed**.
- `git diff --check`: passed.
- No broad regression, package build, screenshot loop or physical-device test was run.

### Classification, safety, platforms and gates

- **Implemented:** explicit local owner choice for multiple exact Pack-matching saved projects;
  truthful zero-match refusal.
- **Simulated/Tested:** three focused synthetic Qt widget journeys.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: one choice appears only when ownership is genuinely ambiguous. This is a local
  context selection, not a consequential confirmation; the single-match path remains automatic.
- Project selection grants no compatibility, build, consent, Guardian or execution authority.
  `UNCONFIRMED` remains advisory `Unknown`.
- Exact-device/DNA/Matrix validation, Guardian separation, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt journeys verified. Windows: not run or claimed; Windows work
  was untouched.
- Feature freeze: compliant minimum completion of the existing saved-project ownership journey.
  v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. Continue only with the next approved adjacent existing Device
Intelligence journey; do not broaden Stage 1 or cross a consequential boundary.

### Product Assurance Review Requested

- Confirm the chooser is a proportionate local context decision, the cancellation path is calm and
  inert, and the explicit zero-match refusal closes the remaining ownership guess.

## Linux product checkpoint — exact saved-project ownership for ROM Mission

### Authoritative checkpoint

- Product Assurance approval/base: `47d5055` — approved exact Device Intelligence mission
  handoff.
- Tested implementation: `3ec7026f9168b3ad7a5d123129ff98723406d242` — `Select exact saved ROM
  mission project`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, adjacent existing Device Intelligence Hub
  `Start ROM Mission` saved-project ownership journey.

### Reproduced gap and exact correction

- First-use/no-project behavior was inspected and remains functional: Genesis begins at its
  existing `New project` stage and a newly created project receives the selected device's
  suggested Pack.
- The next adjacent real gap occurred when ROM Studio retained an unrelated current project while
  exactly one saved project matched Device Atlas's current Pack. `Start ROM Mission` opened
  Genesis on the unrelated project even though the correct saved owner was unambiguous.
- Immediately before the already-approved device/DNA/Matrix handoff revalidation, ROMVERSE now
  checks authoritative saved projects. Only when the current project is Pack-mismatched and
  exactly one saved project has the current exact Pack ID does it select that project and refresh
  its current Device DNA/Compatibility evidence. Zero or multiple matches are not guessed.
- Genesis then receives the existing independently validated selected device, current DNA/Matrix,
  Pack report and exact saved project. No project is created, modified, associated or executed by
  the selection itself.

### Verification without double-counting

- Focused real-widget journey: **1/1 passed** with a temporary isolated workspace, sanitized
  synthetic phone evidence, one deliberately unrelated selected project and one exact matching
  saved project. The real button selected the matching owner, refreshed advisory evidence and
  entered Guided with `guardian_flash: Unknown`; no worker started.
- Affected navigation regression: **65/65 unique tests passed** in one combined run. The focused
  journey is included in this total and is not counted again. It also retains first-use,
  stale-report, exact-device substitution, owner-return and existing Device Atlas/Nexus handoffs.
- Ruff static and format checks: **2/2 changed implementation/test files passed**.
- `git diff --check`: passed.
- No broad suite, package build, screenshot loop or physical-device test was run.

### Classification, safety, platforms and gates

- **Implemented:** unambiguous saved-project selection for the existing ROM Mission entry.
- **Simulated/Tested:** sanitized synthetic Qt widget journey and 65 affected tests.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction: the user no longer lands in a clearly unrelated project when one exact saved
  Pack owner exists. Ambiguous ownership is not guessed. No new prompt or confirmation was added.
- `UNCONFIRMED` remains advisory `Unknown`; project convenience grants no compatibility, consent,
  Guardian or execution authority.
- Exact-device/DNA/Matrix validation, Guardian separation, UNKNOWN-on-uncertainty, no blind retry,
  same-incident Recovery, independent verification and permanent no-relock remain unchanged.
- Fedora/Linux: actual offscreen Qt journey verified. Windows: not run or claimed; Windows work was
  untouched.
- Feature freeze: compliant minimum correction to an existing Stage 1 journey. v0.2 Golden
  Foundation remains **CLOSED** pending Product Assurance and release blockers.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware operation, build/flash/boot,
  partition/slot/wipe/unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped commits to the existing Linux
  branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. If approved, inspect the next repository-defined adjacent
Device Intelligence journey without broadening Stage 1 or crossing a consequential boundary.

### Product Assurance Review Requested

- Confirm that auto-selecting only one exact Pack-matching saved project is the correct
  zero-friction ownership rule, while leaving zero/multiple matches unguessed.

## Linux product checkpoint — Device Intelligence starts an exact ROM Mission

### Authoritative checkpoint

- Approved base: `43c133ea0260a04e4994dc50ad91c153c363d718` — runnable Linux Stage 1
  milestone approved by Product Assurance.
- Tested implementation: `78009cb89080f3e21421667bb31b4518dc9888cf` — `Preserve Device
  Intelligence mission context`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, existing Device Intelligence Hub `Start ROM Mission`
  handoff into shared ROM Studio/Guided state.

### Exact product correction

- A real widget journey exposed that Device Atlas already transferred the current Pack report and
  selected live device into ROM Studio/Guided, but omitted the current Device DNA digest and
  Compatibility Matrix verdict from the visible/shared mission evidence.
- `Start ROM Mission` now revalidates the current report against the selected device's
  manufacturer, model, product and codename, the current persisted Device DNA profile, and any
  current DNA-bound Compatibility Matrix before navigation.
- ROM Studio independently revalidates the one selected transport identity, report/device match,
  current persisted DNA digest, live-device evidence and advisory Compatibility Matrix binding.
  A same-model/different-device substitution is rejected and returned to Device Atlas before
  Genesis opens.
- The successful handoff visibly retains the privacy-masked selected target, current Device DNA
  digest, matched Pack/report and `guardian_flash` Compatibility verdict. Shared Guided evidence
  now includes the current DNA and advisory Matrix digests; `UNCONFIRMED` remains `Unknown`, never
  inferred compatible or terminally unsupported.
- Returning from ROM Studio to Device Atlas preserves the selected device, matched Pack, exact
  report and current Device DNA owner context. No new feature, action, confirmation or authority
  surface was added.

### Verification without double-counting

- One focused end-to-end Qt widget journey: **1/1 passed** after formatting. It uses a temporary
  isolated workspace and sanitized synthetic Xiaomi evidence, creates current source-bound Device
  DNA and a Compatibility Matrix, clicks the real `Start ROM Mission` button, inspects the actual
  shared Guided context, returns through the real owner/navigation signal, and adversarially tries
  a same-model/different-device substitution.
- One combined affected regression run: **139/139 unique tests passed** — 64 navigation vocabulary,
  53 ROM Studio UI and 22 Guided mission tests. The focused journey is included in this total and
  is not counted again.
- Ruff static check and format check: **3/3 changed implementation/test files passed**.
- `git diff --check`: passed.
- No broad suite, package rebuild, screenshot loop or physical-device test was run.

### Classification, safety and Guided behavior

- **Implemented:** exact Device Intelligence mission-context validation and visible/shared
  evidence continuity.
- **Simulated/Tested:** the synthetic widget journey and 139 affected tests above.
- **Hardware Verified:** none for this checkpoint.
- **Released:** no.
- Guided friction/dead ends: successful context now remains visible and available to Genesis; stale
  or substituted context calmly returns to Device Atlas with a specific stopped-handoff message.
  No extra user confirmation was introduced.
- Compatibility Matrix evidence is explicitly advisory and grants zero execution authority.
  `guardian_flash` remains `Unknown` for missing execution evidence. Guardian remains the only
  execution gate.
- Exact-device evidence, consent separation, UNKNOWN-on-uncertainty, no blind retry, independent
  verification, same-incident Recovery and permanent no-relock are preserved.

### Platform, freeze, version gate and external actions

- Fedora/Linux: implementation and actual offscreen Qt widget journey verified.
- Windows: not run or claimed; Windows/launcher work was untouched.
- Feature freeze: compliant correction to an incomplete existing Stage 1 user journey; no new
  capability, Pack, adapter, route or autonomous behavior.
- v0.2 Golden Foundation remains **CLOSED** pending Product Assurance and remaining release gates.
- Remaining limitations: this is sanitized synthetic evidence only; it proves no physical-device,
  firmware, build, consent, Guardian execution, installation or Recovery result.
- Protected Companion work, Windows work, Knowledge work, UI Design Lab, website and unrelated
  files were not modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, APK action, firmware copy/import from user data,
  build execution, flash/boot/update, partition access, slot change, wipe/erase/format,
  unlock/lock/relock, installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped implementation and this
  repository handoff to the existing Linux branch only; no force-push.

### Next proposed Build task

Stop for Product Assurance review. If approved, continue the same Device Intelligence milestone to
the next repository-evidenced incomplete existing action; do not broaden Stage 1 or cross a new
consequential boundary.

### Product Assurance Review Requested

- Confirm that independently validating the selected device plus current DNA/Matrix at the ROM
  Studio boundary is the minimum correct closure for this existing handoff.
- Confirm that visibly retaining an `Unknown` advisory compatibility verdict preserves the intended
  investigable `UNCONFIRMED` behavior without implying Guardian or execution authority.

## Linux correction checkpoint — fatal native file chooser fallback

### Authoritative checkpoint

- Base: `9b054b6997404e18993efa3f8b92adac23d3e935` — runnable Linux Stage 1 journey.
- Tested implementation:
  `30d157d1e050b6b6d15847ca995e9640b6dfff10` — `Fall back from unsafe Linux file dialogs`.
- Final handoff: the follow-up commit containing this document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, minimum Fedora runtime crash correction.

### Reproduced incident and cause

- Steve used the visible source application launched by Build and selected the Guided project flow
  that opens `Import original firmware`.
- The fatal record at
  `build/visible-stage1-fc34291/logs/crash/runtime-fault.log` binds the abort to
  `RomStudio._import_original()` → `QFileDialog.getOpenFileName()` at 18:29:11 local time.
- Build had deliberately removed the ordinary host `PATH` from that visible process to make ADB and
  Fastboot undiscoverable. GTK's native chooser then tried to start its `bwrap` image-loader sandbox
  helper by name, could not find it and asserted/aborted the entire process. `/usr/bin/bwrap` exists
  on the host; this was an invalid constrained launch environment, not firmware corruption or a
  Python exception in ROMVERSE's project logic.
- The interrupted workspace strictly reloads one project, `Hyperos 4`, with no protected original.
  No source selection, copy, import, extraction or project mutation had begun when the chooser
  aborted, so the saved project is intact.

### Exact correction

- Before creating `QApplication`, Linux startup now checks whether `bwrap` is discoverable. If it is
  unavailable, ROMVERSE sets Qt's application-wide `AA_DontUseNativeDialogs` safety attribute so all
  38 current file/folder chooser call sites use Qt's built-in chooser rather than entering the fatal
  GTK native path.
- When `bwrap` is available, normal Linux native chooser behavior is unchanged. Non-Linux platforms
  are explicitly unchanged. No device, project, firmware, Guardian, Recovery or authority logic was
  altered.

### Verification without double-counting

- Focused launch/settings and Guided candidate Desktop tests: **11/11 unique tests passed**.
- New tests prove missing `bwrap` selects the Qt fallback and that non-Linux startup remains
  unchanged.
- Exact constrained GUI reproduction: with `bwrap`, ADB and Fastboot all absent from `PATH`, a real
  `QFileDialog.getOpenFileName()` opened under the configured Qt fallback, was cancelled by timer,
  returned `("", "")` and exited normally instead of aborting.
- Ruff static check: **2/2 changed files passed**.
- Ruff format check: **2/2 changed files passed**.
- `git diff --check`: passed. No broad suite or package rebuild was run.
- The corrected source app is visibly running from a new isolated workspace
  `build/visible-crash-fix-9b054b6` with no device tools in its process path; its runtime fault log
  contains only the normal startup marker.

### Classification and safety

- **Implemented:** conditional Linux non-native chooser fallback.
- **Simulated/Tested:** 11 focused tests plus one exact constrained real-GUI chooser reproduction
  and a fresh visible corrected-source launch on Fedora.
- **Hardware Verified:** none. No Android transport was used.
- **Released:** no. The prior unsigned development package was not rebuilt or published here.
- Guided impact: the Import-original action now falls back safely instead of terminating the app
  when the native chooser's helper is missing. Cancellation returns to the same Guided project.
- Guardian-only authority, consent separation, exact-device/evidence rules, UNKNOWN/no-blind-retry,
  independent verification, same-incident Recovery and permanent no-relock are unchanged.

### Platform, freeze, preservation and external actions

- Fedora/Linux: exact crash cause reproduced and corrected fallback verified.
- Windows: behavior explicitly unchanged by the platform condition; no Windows runtime claim.
- Feature freeze: compliant minimum correctness fix; no feature or execution surface was added.
- v0.2 Golden Foundation remains **CLOSED** pending independent review and remaining release gates.
- Protected Companion files, Windows work, UI Design Lab, website and unrelated user files were not
  modified, staged, discarded or committed.
- Physical phone access, ADB/Fastboot invocation, firmware copy/import/extraction, APK action,
  flash/boot/update, partition access, slot change, wipe/erase/format, unlock/lock/relock,
  installation, signing, publication and release: **none**.
- External action after verification: one normal push of the scoped correction and handoff to the
  existing Linux branch only; no force-push.

### Next proposed Build task

Allow Steve to repeat the same visible Guided import action in the corrected app. Continue only if a
new reproducible application defect appears; do not re-enter device or packaging work for this fix.

### Product Assurance Review Requested

- Confirm the conditional application-wide Qt chooser fallback is the minimum correct defense for
  the observed fatal GTK dependency failure and does not alter normal Linux or Windows behavior.

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
