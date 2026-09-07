# ROMVERSE Product Assurance

## Reviewed checkpoint: ddd9714

- Handoff commit: `ddd9714402f59a4a521aa725d535c173e4b5ad3d`
- Implementation commit: `c0b140bbebe7b8fd107819c911703ac9a07e2954`
- Product Assurance authorization: `b0ba30681623e0fc97617f607fbb24dfa7d3cf73`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — COMPANION LINK LISTENER IS INTENT-BOUND**

### Decision

The optional Companion Link no longer binds, listens, or advertises during a fresh unpaired Windows
startup. One existing explicit pairing action starts the endpoint once; a valid remembered session
may resume it; failure remains bounded and unavailable. The corrected source and rebuilt frozen
application reached Command Deck with zero TCP listeners and zero UDP endpoints before Link intent.

The still-visible Windows Security notification is the original pre-correction `PickerHost.exe`
instance, not a new prompt created by either corrected launch. Product Assurance cannot automate or
dismiss an operating-system security decision. Steve should choose **Cancel** when present so the
Device Engine readiness journey can resume without granting unnecessary inbound access.

That stale prompt does not block the next source-only correctness task. To prevent duplicate platform
work, this Windows branch is now the single owner of the already-recorded emulator-versus-physical-USB
classification defect in the same Desktop subsystem.

### Independent repository and verification evidence

- `c0b140b` changes only Companion transport/center source and their directly affected tests;
  `ddd9714` changes only the Build handoff. Companion Android source and protected files are untouched.
- `CompanionTransport` now creates its TLS identity without constructing a server. Its locked
  `start()` performs one bounded bind/TLS/thread transition, reuses an existing live endpoint, and
  records a terminal unavailable result after failure rather than looping.
- `CompanionCenter` resumes only a valid approved session. Fresh/unpaired construction keeps Generate
  available and the endpoint idle; explicit generation starts Link before producing a pairing code.
- Windows Build reports 21 focused tests passed with one pre-existing layout test deliberately outside
  this lifecycle slice; Ruff and whitespace checks passed.
- Product Assurance independently reproduced the exact selected transport/center group on Fedora
  against the pushed source: **21 passed, 1 deselected**, followed by a clean Ruff result. The initial
  reproduction accidentally resolved an older editable install; it was discarded and rerun with the
  current worktree explicitly first on the import path. Only the current-source result is accepted.
- Source and the once-rebuilt frozen application each owned zero inbound TCP and zero UDP endpoints
  before Link intent. The frozen executable is unsigned development evidence at SHA-256
  `0d54ed4588c6337a7bee194ee9b3541593fe3e8ab9222f35489d339a5eae6cc9`.
- The retained stale prompt process predates both corrected launches by hours; no new prompt process
  appeared. No firewall rule, Allow/Cancel choice, global PATH, system package, phone, device command,
  Recovery, signing, publication, release, or relock action occurred.

### Safety, freeze, and Guided-friction review

- Optional Link no longer interrupts an unrelated offline Device Engine journey at application start.
- TLS identity, exact safety-code comparison, separate approval, read-only telemetry, revocation,
  shutdown, privacy filtering, and `execution_authority: none` remain intact.
- One terminal start failure is explained in the existing UI and is not retried automatically.
- Guardian-only execution, exact-device evidence, UNKNOWN-on-uncertainty, no blind retry, and the
  permanent no-relock rule are unchanged.
- This is a lifecycle correctness repair within the existing Link feature and preserves the freeze.

### Acceptance criteria result

- Fresh unpaired construction owns no listener/discovery endpoint: **PASS**
- Explicit intent starts one endpoint; repeated intent does not duplicate it: **PASS**
- Bounded fail-closed start and clean shutdown: **PASS**
- Valid remembered-session resume: **PASS**
- Windows focused verification: **21 PASS / 1 unrelated deselected**
- Independent Fedora reproduction: **21 PASS / 1 unrelated deselected**
- Fresh corrected source/frozen startup without a new firewall prompt: **PASS**
- Device Engine readiness completion: **WAITING FOR HUMAN DISMISSAL OF STALE OS PROMPT**

### Approved next bounded task

Correct only the Desktop's existing connection-source truthfulness on
`windows-launcher-authorized-work`; do not interact with the stale Windows Security prompt:

1. Classify a local Android emulator distinctly from physical USB using current ADB discovery and
   read-only device evidence. Treat `emulator-*`/confirmed QEMU evidence conservatively as virtual;
   never promote it to physical USB evidence. Preserve network ADB as non-USB.
2. In Companion Center, set physical-USB readiness and enable USB-assisted pairing only for a normal
   Android target whose observed transport is genuinely `usb`.
3. An emulator or network ADB snapshot may still provide read-only development telemetry, but it must
   never render `USB connected`, `USB also connected`, `USB read-only evidence remains available`, or
   another physical-cable claim.
4. Preserve the current genuine physical-USB path, multiple/unauthorized/offline fail-closed states,
   wireless Link behavior, and all Guardian/Recovery boundaries.
5. Add only focused Device Engine and Companion Center tests covering emulator, network ADB, and
   physical USB. Run the smallest affected tests and lint. Do not rebuild the executable/ZIP, rerun
   the Guided or Link journeys, or launch the app while the stale OS prompt remains.

Commit and push the exact source/test/handoff checkpoint, then stop for independent review. Linux is
explicitly not authorized to duplicate this correction.

### Gate status

- Fedora runnable build and direct Companion Link: **VERIFIED**
- Windows runnable development build and inert Guided journey: **VERIFIED**
- Optional Link listener lifecycle: **VERIFIED**
- Emulator/physical-USB classification: **WINDOWS NEXT BOUNDED CORRECTION**
- Windows Device Engine/toolchain readiness: **PAUSED FOR HUMAN CANCEL OF STALE OS PROMPT**
- v0.2 Golden Foundation: **CLOSED pending physical, production-trust, signing, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: f8413bf

- Handoff commit: `f8413bfe465e8bfd33d62a0a6cd92d3aa6572167`
- Evidence commit: `ae13356696915189ad73e9b3cd9bfdfcefa11b3b`
- Product Assurance authorization: `f5a06a7664c67c35d14a20286c1acc9ee1b6ba2e`
- Branch: `windows-launcher-authorized-work`
- Review status: **CORRECTION REQUIRED — OPTIONAL LINK LISTENER BLOCKS UNRELATED WINDOWS STARTUP**

### Decision

Build stopped at the correct boundary. The real frozen application starts with a truthful missing-
Platform-Tools state, but a Windows Security firewall dialog for inbound `ROMVERSE.exe` networking
appears before the user can select `Resolve Platform Tools`. Automating that operating-system security
decision or silently changing firewall policy is not acceptable.

Repository inspection identifies the product cause: every `CompanionCenter` construction immediately
constructs, binds, listens on, and starts the wireless `CompanionTransport` plus LAN discovery even in
a fresh workspace with no remembered Companion session and before the user opens or requests Link.
ROMVERSE Link is optional. It must not open an inbound network surface—or trigger a system permission
prompt—while the user is pursuing an unrelated offline Device Engine action.

This is a minimum Guided-friction and least-authority lifecycle correction within the existing Link
feature, not a new feature and not a request to weaken Windows security.

### Independent evidence

- `ae13356` contains only the blocker screenshot; `f8413bf` contains only the Build handoff. The
  application, frozen artifact, tests, host policy, and protected Companion files are unchanged.
- Product Assurance independently verified the screenshot hash
  `85a2e6fcfde4f4c0742eb8aaa795cbe2d05cec7d996ea2114e262d05f60b3e7e` and visually confirmed the
  real Command Deck's `Device Engine needs attention` / `Resolve Platform Tools` state beneath the
  modal Windows Security prompt.
- The fresh isolated workspace had no Android tool bytes or receipts; host PATH contained neither
  `adb` nor `fastboot`. No tool acquisition began, so no false readiness claim exists.
- Source inspection confirms `CompanionCenter.__init__` unconditionally calls
  `self.transport.start()`. `CompanionTransport` has already created and activated an
  `0.0.0.0` HTTP server socket during construction, and `start()` launches both the HTTPS serving
  thread and broadcast discovery thread.
- The product was closed, no ROMVERSE process remained, and no firewall choice, global PATH change,
  download, driver, phone, ADB/Fastboot device command, or Recovery action occurred.

### Required minimum correction

Correct only the existing Desktop Companion-Link network lifecycle:

1. In a fresh workspace with no remembered approved session, constructing/opening ROMVERSE must not
   bind or listen on an inbound Companion socket, start LAN discovery, or request firewall access.
2. Start the existing Link endpoint only after the user invokes an existing pairing action such as
   `Generate wireless code` or an eligible USB-pairing action. The UI must remain able to present that
   action before a socket is opened and must surface a bounded unavailable result if startup fails.
3. Preserve legitimate remembered-session reconnection. A previously explicit, still-valid approved
   Link may resume according to the existing contract; fresh/unpaired startup may not manufacture that
   authorization.
4. Preserve TLS identity, short-lived code, exact safety-code comparison, Desktop approval,
   read-only telemetry, revocation/reset, shutdown, fixed bounded listener behavior, privacy filtering,
   and `execution_authority: none`.
5. Add/update only directly affected lifecycle tests proving no fresh-start listener/discovery, one
   explicit start on pairing intent, fail-closed startup error, remembered-session behavior, and clean
   shutdown. Do not redesign Link or Device Engine.

Expected scope is the minimum relevant Desktop Companion transport/center source and its focused
tests, plus required build/handoff evidence. Do not alter Windows Firewall, add an exemption, suppress
the system prompt, use a different port as a workaround, disable TLS, change Companion Android source,
or touch Guardian/Recovery authority.

### Acceptance criteria

- A focused deterministic test proves a fresh unpaired `CompanionCenter` owns no listening socket or
  discovery thread until an existing explicit pairing action is invoked.
- The directly affected Companion transport/center tests pass on Windows and Linux; no broad suite is
  required.
- One Windows source launch in a fresh isolated workspace reaches the visible Command Deck and
  `Resolve Platform Tools` without an unsolicited firewall dialog or Companion listener.
- Rebuild the unsigned frozen development executable once from the corrected source, then repeat that
  same fresh-workspace startup. Do not rebuild/repackage repeatedly and do not rerun the inert Guided
  journey.
- Resume the already approved real Device Engine/toolchain readiness journey in that corrected frozen
  application. If a new genuine product blocker appears, preserve it and stop; do not loop or broaden
  the change.
- No firewall/security policy change, system-wide install, global PATH mutation, phone, driver,
  ADB/Fastboot device operation, Recovery execution, relock, production signing, publication, or
  release occurs.
- Update `docs/sync/BUILD-STATUS.md`, commit and push the exact correction/result, and stop for
  independent review.

### Approved next bounded task

Implement only the lazy, intent-bound Companion listener lifecycle correction above and use the
single corrected frozen build to continue the interrupted Windows Device Engine readiness journey.
Testing is acceptance evidence for that product outcome, not a new test campaign.

### Gate status

- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Windows runnable development build and inert Guided journey: **VERIFIED**
- Windows Device Engine/toolchain operability: **BLOCKED BY MINIMUM OPTIONAL-NETWORK LIFECYCLE DEFECT**
- Windows Firewall/security change: **NOT AUTHORIZED OR REQUIRED**
- Companion Android source: separate Linux integration track; unchanged here
- v0.2 Golden Foundation: **CLOSED pending physical, production-trust, signing, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: 7642cad

- Handoff commit: `7642cad98d2501588d9b6829b132c01c1f8798b7`
- Test correction: `7353b0df797f37354864ace65b889e488c7a9b56`
- Product Assurance authorization: `8a4461d21be1a9a7d45cf4420b132a0b3dd90cf7`
- Branch: `windows-launcher-authorized-work`
- Review status: **APPROVED — WINDOWS DEVELOPMENT READINESS VERIFIED**

### Decision

The final portability defect is corrected exactly as authorized. The raw unsafe ZIP member remains
constructed and asserted through `ZipInfo.orig_filename`, and the cross-platform production boundary
still rejects it. Only the irrelevant host-specific `ZipInfo.filename` expectation was removed.

Combined with the previously verified native trusted launcher, readable frozen UI, private Windows
ACLs, exact development archive, source/frozen startup, and inert Guided journey, this closes the
Windows unsigned development-readiness gate. It does not authorize production signing, release,
physical Android operation, or Recovery execution.

### Independent evidence

- `7353b0d` deletes exactly one assertion from
  `tests/test_source_installation.py`; `7642cad` changes only the Build handoff. Production source,
  accepted-path validation, application, launcher, ACLs, artifacts, and protected Companion files
  are unchanged.
- Windows Build ran the corrected regression (**1 passed**) and the directly affected complete source-
  installation file (**32/32 passed**); its worktree and remote matched at the handoff.
- Product Assurance independently ran the exact previously failing Linux-focused group at the pushed
  checkpoint: **81 passed, 2 Windows-host skips, 0 failures**. The unsafe raw backslash member is
  still rejected on Linux without conditionalizing or skipping its safety contract.
- Previously accepted evidence remains applicable because no product or artifact byte changed:
  - native exact Windows launcher identity: **100/100 fresh processes** and focused launcher pass;
  - frozen visible window: readable, no square glyphs;
  - owner/SYSTEM-only private-file ACL contract;
  - unsigned development ZIP SHA-256
    `747d5b40dbc76f5fab3e777f40bbd3d586bcfb72eaeccadd6647df57996af239`;
  - source and frozen startup smoke;
  - simulation-only full Guided
    `Scan → Match → Prepare → Consent → Result → Reassessment → Verification` journey with no phone,
    wipe, relock, retry, or physical command.

### Vision, freeze, and safety review

- The correction is test-only and removes no safety assertion that belongs to the product contract.
- Guardian-only authority, exact-device evidence, one meaningful consent, durable UNKNOWN, no blind
  retry, independent reassessment/verification, and permanent no-relock remain preserved.
- Guided friction is unchanged; no extra user decision or technical dead end was introduced.
- The pre-v1.0 feature freeze is preserved. The artifact remains an unsigned local development build,
  not a release candidate or production package.

### Approved next bounded task

Prove the real Windows application's existing **Device Engine / toolchain readiness** journey on the
Legion host, so the runnable UI advances from its current “needs attention” state to a truthful usable
development state without a phone:

1. Use the already verified frozen Windows development application and a fresh isolated workspace.
   Do not rebuild the executable or ZIP and do not rerun the Guided journey or broad regression.
2. Open the existing Device Engine/Forge Arsenal readiness surface and record the actual missing,
   detected, or conflicting Android tool state before any action.
3. Exercise only existing product behavior. If tools are already available, verify their exact paths,
   versions, integrity/provenance receipts, and restart persistence. If the product's existing pinned,
   integrity-checked, workspace-local acquisition flow is required, it may obtain only those declared
   development tools into its isolated workspace. Do not perform an unverified/manual download.
4. Demonstrate that the real frozen UI reaches a truthful ready—or specific actionable blocked—state
   for its existing Android development toolchain and that reopening the app preserves the evidence.
5. Capture readable before/after Windows evidence and the exact local receipts. Keep all claims scoped:
   no connected-device, USB-driver, Fastboot communication, or physical-hardware verification claim
   is permitted without a phone.

This is a real Windows operability milestone, not authorization to implement a new tool manager. Do
not edit application source, install system-wide software or drivers, change global PATH/security,
connect or operate a phone, enable Recovery, sign, publish, or release. If the unchanged product cannot
complete its own existing readiness journey, commit the smallest reproducible blocker and handoff,
then stop for Product Assurance rather than modifying code or looping tests.

### Acceptance criteria

- The real frozen Windows application visibly and truthfully completes its existing host-toolchain
  readiness journey, or preserves one precise product blocker for review.
- Any acquired bytes are declared by the existing product manifest, integrity verified, and confined
  to the isolated ROMVERSE workspace; no broad host mutation occurs.
- Restarted UI state agrees with exact executable/version/provenance receipts.
- No phone, driver installation, ADB/Fastboot device operation, Recovery execution, relock, blind
  retry, production signing, publication, or release occurs.
- Update `docs/sync/BUILD-STATUS.md`, commit and push the bounded checkpoint, and stop for independent
  review. Do not substitute more tests for the actual visible product journey.

### Gate status

- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Windows unsigned frozen build and inert Guided journey: **VERIFIED**
- Windows native launcher, archive, visible UI, and private ACL readiness: **VERIFIED**
- Windows Device Engine/toolchain operability: **NEXT BOUNDED MILESTONE**
- Companion API-35 and fixture-backed Link runtime: **VERIFIED on Linux track**
- v0.2 Golden Foundation: **CLOSED pending physical, production-trust, signing, and release gates**
- Physical hardware, production Recovery/trust, signing, publication, and release: not authorized

## Reviewed checkpoint: 20e0c33

- Handoff commit: `20e0c3312ef5d995694f66119295007d1f8d2dac`
- Correction implementation: `0e2f895dfcb3507fdbda5c1a3f74096361aedf3d`
- Previous Product Assurance correction: `a924b2067b83d797be3742b3bdb81f02ac06a045`
- Branch: `windows-launcher-authorized-work`
- Review status: **CORRECTION REQUIRED — WINDOWS READINESS FUNCTIONALLY VERIFIED; ONE CROSS-PLATFORM TEST ASSERTION REMAINS**

### Decision

The four requested Windows readiness corrections are materially complete and independently verified.
The real Windows launcher is stable across 100 fresh processes, the visible frozen application is
readable, the private project artifacts have a Windows-native owner/SYSTEM-only ACL, and the source
parser rejects a ZIP member whose raw name contains a literal backslash.

Approval is held only because the new ZIP regression contains one Windows-specific expectation about
Python's normalized `ZipInfo.filename`. On Linux, `ZipInfo.orig_filename` and `ZipInfo.filename` both
retain the literal backslash; the production parser still correctly rejects the raw unsafe member.
This is a test portability defect, not an application defect. The exact minimum correction below does
not authorize any product-source, artifact, UI, launcher, packaging, or journey change.

### Repository and independent evidence

- `0e2f895` changes only the approved launcher, private-file, ZIP-validation, test, and visible-evidence
  surfaces; `20e0c33` changes only `docs/sync/BUILD-STATUS.md`.
- The Windows worktree was clean at the handoff and the protected Companion files were unchanged.
- Product Assurance independently ran the decisive Windows launcher/project/source cases:
  **24/24 passed**.
- Product Assurance independently repeated the exact handle/path test in 100 fresh Windows pytest
  processes: **100/100 passed**, with no failure.
- Native identity now compares volume serial, 64-bit file index, link count, size, last-write FILETIME,
  and creation FILETIME for both handles. Reparse rejection, single-link enforcement, the pinned
  write/delete-denying handle, one attempt, and fail-closed dispatch remain intact.
- The committed 1456x939 visible frozen-window evidence is readable and contains no square glyphs.
  Its SHA-256 is
  `346cbdbd3510ab812fbb203eb66457ca2f4db4053bc1ae7576aa64cb166c12f8`.
- The four private Windows artifacts are tested against exactly two non-inherited Full Control ACEs:
  Owner Rights and Local System. Existing POSIX `0600` behavior remains present.
- Product Assurance independently verified the rebuilt unsigned development ZIP on Windows:
  SHA-256 `747d5b40dbc76f5fab3e777f40bbd3d586bcfb72eaeccadd6647df57996af239`.
- The persisted inert-journey report remains simulation-only, records 53 actions/50 inert writes,
  preserves decline-before-acceptance and separate boot verification, and records no physical command,
  wipe, relock, or retry.
- Product Assurance independently ran the focused project/source/launcher suite on Linux:
  **80 passed, 2 skipped, 1 failed**. The only failure is the host-specific assertion that
  `ZipInfo.filename` must equal `windows/boot.img`; Linux correctly returns the raw
  `windows\\boot.img`. The subsequent `ProjectError` rejection remains the intended contract.

### Required minimum correction

Modify only
`tests/test_source_installation.py::test_literal_backslash_archive_path_is_rejected_before_windows_normalization`:

- Keep the unconditional assertion that `member.orig_filename == r"windows\boot.img"`.
- Make the `member.filename` expectation accurately reflect host behavior: normalized forward slash
  on Windows and retained literal backslash on non-Windows hosts, or remove that secondary assertion
  where normalization is not part of the safety contract.
- Keep the cross-platform call to `SourceInstallationService.prepare` and its required `ProjectError`
  path rejection.
- Do not change production source, the fixture's raw unsafe name, accepted-path validation, the
  Windows launcher, ACL implementation, application, artifact, or documentation outside the handoff.

### Acceptance criteria

- The corrected single ZIP regression passes on Windows and Linux while still proving the raw literal
  backslash is rejected.
- The same focused Linux suite completes with **81 passed, 2 skipped** and no failure.
- The directly affected Windows source-installation test file passes.
- No frozen rebuild, ZIP rebuild, visible launch, inert Guided journey, broad regression, dependency
  change, or physical-device action is required because product code and accepted artifacts are
  unchanged.
- Commit the single test correction and updated `docs/sync/BUILD-STATUS.md`, push the branch, and stop
  for Product Assurance review.

### Approved next bounded task

Apply only the portable ZIP-test assertion correction above. After it passes on both hosts, Product
Assurance may close Windows development readiness without repeating already-valid build, visual,
launcher, ACL, archive, or journey evidence.

### Gate status

- v0.2 Golden Foundation: **CLOSED**
- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Windows unsigned frozen artifact and inert Guided journey: **VERIFIED**
- Windows completed development-readiness gate: **HELD ONLY FOR ONE TEST-PORTABILITY CORRECTION**
- Guardian/exact-device/UNKNOWN/no-blind-retry/no-relock invariants: preserved
- Physical Android/Recovery verification: outstanding; not authorized here
- Pre-v1.0 feature freeze: preserved
- Production signing, publication, and release: not authorized

## Reviewed checkpoint: 824d6e7

- Handoff commit: `824d6e7b3f59e16d9d2bffe3e6f1049ddc55470b`
- Runnable-build correction: `2b121c1540be0cd6b000075913cd753018936fdc`
- Portability audit: `a20402e110a181c1bf2c6bf138a2e1e69c9ba573`
- Approved baseline: `1d679d5b2f78bd153cd2d349047bd5a3217c116b`
- Branch: `windows-launcher-authorized-work`
- Review status: **CORRECTION REQUIRED — RUNNABLE ARTIFACT VERIFIED; WINDOWS READINESS HELD**

### Decision

The Windows checkpoint has achieved two genuine milestones. Product Assurance independently verified
that the unsigned frozen application and its ZIP are runnable on the real Windows host, and the
repository's inert Guided simulation completed the full
`Scan → Match → Prepare → Consent → Result → Reassessment → Verification` chain without a physical
phone or production Recovery execution.

The checkpoint is not yet approved as the completed Windows development-readiness gate. Independent
review reproduced the supposedly transient trusted-launcher handle/path failure, the submitted
offscreen visual evidence renders all user-facing text as square glyphs, and the remaining project
privacy tests have not yet been replaced with a real Windows ACL assertion. These are narrow
platform-correctness issues; none authorizes a feature expansion or weakening of fail-closed safety.

### Repository scope and implementation review

- The pushed branch is an exact descendant of the approved `1d679d5` launcher checkpoint.
- `2b121c1` changes only:
  - `scripts/build_desktop_executable.py`
  - `src/romverse/rom/source_installation.py`
  - `tests/test_desktop_bundle.py`
  - `tests/test_source_installation.py`
- `a20402e` adds only the complete Windows portability audit.
- `824d6e7` changes only `docs/sync/BUILD-STATUS.md`.
- The Windows checkout was clean after handoff. Protected Companion files were unchanged.
- The approved trusted-launcher implementation and contract were not changed by the runnable-build
  commit.

The two implementation corrections are appropriately narrow:

- Windows source verification retains device, file index, size, and modification-time identity
  while omitting only unreliable nanosecond creation-time rounding; POSIX remains strict.
- The PyInstaller build temporarily removes only non-System32 PATH entries containing `icuuc.dll`
  and restores the original PATH afterward. This prevents unrelated Poppler ICU DLLs from
  shadowing the Windows system ICU API shim without changing application behavior.

### Independently verified runnable artifact

- Executable: `build/windows-dev-frozen/ROMVERSE/ROMVERSE.exe`
- Archive: `dist/ROMVERSE-Desktop-0.1.0-windows-x86_64-dev.zip`
- Archive SHA-256:
  `e442685566f9f2012a19bfe848cf8234469b994b46d92e41ddddb93a1272fba2`
- Archive size: 73,445,618 bytes
- Archive verification: 305 files; 164,585,215 expanded bytes; exact tree verifier passed.
- No `icu*.dll` is present in the frozen application directory.
- Product Assurance independently ran the frozen release-smoke launcher: passed.
- Product Assurance independently ran the source release-smoke launcher: exit 0. Qt emitted a
  non-fatal DPI-awareness warning under the SSH-hosted smoke process; application startup passed.
- Classification: unsigned development build only; not production-signed, published, or released.

### Independently verified journey evidence

The persisted simulation report confirms:

- synthetic target only; `physical_phone_changed=false` and `production_certified=false`;
- exact simulated Xiaomi/`popsicle` target and the reviewed source procedure;
- 53 simulated actions including 50 inert image writes;
- consent decline sent no changing command and later acceptance remained explicit;
- no wipe, relock, blind retry, or physical command;
- durable installation receipt remained unchanged;
- stable boot observation was separate from installation success and did not promote the
  installation receipt to boot-verified;
- 60 simulated seconds, 11 samples, valid audit, and unchanged source;
- same Guided/Expert operation session and zero commands or additional changes when history opened.

Recorded receipt SHA-256:
`e5a8a09ee3119a40d32cc938983ddd3932561fbfbd2f01f9c58211034a814bff`.

### Verification reviewed

- Build's final relevant regression: **250 passed, 4 failed, 2 skipped** in 314.90 seconds.
- Product Assurance independently reran the desktop bundle tests, the new Windows fingerprint test,
  and the complete Windows trusted-launcher test file: **31/31 passed**.
- Product Assurance then repeated the exact handle/path sharing-lock test. It passed 15 consecutive
  fresh runs and failed on run 16. This independently reproduces the intermittent failure and means
  it cannot be certified as deterministic.
- The broad portability audit honestly records 2,901 collected tests, bounded file groups, complete
  failure/error/skip inventories, and the test-harness limitations rather than representing the
  Windows branch as fully green.

### Required minimum correction

1. **Stabilize exact Windows launcher identity without weakening it.** Capture the path and open-
   handle identity fields on failure and correct only the proven unstable comparison. Prefer a
   native Windows volume/file-ID identity or a documented normalization of the unreliable timestamp
   representation. Preserve reparse rejection, single-link requirement, device/file identity,
   size/mtime checks, the write/delete-denying open handle through process creation, one-attempt
   dispatch, and fail-closed behavior. Do not skip, loosen, or delete the adversarial test.

2. **Prove readable text in the real frozen application.** The committed offscreen screenshots show
   square glyphs for all user-facing text and therefore do not satisfy Guided-friction or visual-
   readability evidence. Capture a screenshot from the actual visible frozen Windows window. If its
   text is readable, classify the square-glyph result as an offscreen-backend limitation and retain
   both pieces of evidence. If the visible window is affected, correct only Windows font
   resolution/bundling and reverify the same journey; do not redesign the UI or branding.

3. **Replace POSIX-only privacy assertions with a real Windows privacy contract.** For the project
   manifest, working-copy record, snapshot record, and snapshot artifact, verify owner-only Windows
   ACL behavior or an equivalently strong Windows-native access rule. Do not merely skip the tests
   or accept inherited broad read access. Keep the existing `0600` requirements unchanged on POSIX.

4. **Repair only the invalid ZIP test fixture.** Construct an archive member containing a literal
   backslash without allowing the Windows ZIP writer to normalize the name, then prove the existing
   `_safe_member` boundary rejects it. Do not weaken accepted-path validation or change product
   behavior unless the corrected fixture demonstrates a defect.

### Acceptance criteria

- The exact launcher sharing-lock test passes at least 100 consecutive fresh-process repetitions on
  the real Windows host, followed by the full Windows launcher file passing once as a group.
- The diagnostic evidence explains which field was unstable and why the correction preserves exact
  same-file binding and fail-closed execution.
- A real visible frozen-window screenshot proves readable text, or the minimum font correction is
  implemented and then proves it.
- Windows ACL tests prove that the four named project artifacts are not broadly readable; POSIX
  permission behavior remains unchanged.
- The literal-backslash archive fixture is valid and its rejection test passes.
- Source and frozen startup smoke, exact ZIP verification, and the inert Guided journey still pass.
- No physical phone, real Recovery command, production adapter enrollment, APK installation,
  production signing, publication, release, relock, or protected Companion-file change occurs.

### Approved next bounded task

Apply only the four minimum Windows corrections above. This is a correction pass, not authorization
for a new feature, production Recovery integration, platform merge, installer, signing, or release.
Update `docs/sync/BUILD-STATUS.md`, commit and push the exact correction checkpoint on
`windows-launcher-authorized-work`, and stop for Product Assurance review.

### Gate status

- v0.2 Golden Foundation: **CLOSED**
- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Windows unsigned frozen artifact: **RUNNABLE AND ARCHIVE-VERIFIED**
- Windows inert Guided journey: **VERIFIED**
- Windows completed development-readiness gate: **HELD FOR MINIMUM CORRECTION**
- Windows trusted-launcher safety: fail-closed; deterministic reliability correction required
- Companion instrumentation APK artifact readiness: **VERIFIED on Linux track**
- Physical Android/Recovery verification: outstanding; not authorized here
- Pre-v1.0 feature freeze: preserved
- Production signing, publication, and release: not authorized
