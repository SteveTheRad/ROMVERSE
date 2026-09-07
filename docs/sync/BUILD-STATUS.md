# ROMVERSE Build Status

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
