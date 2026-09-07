# ROMVERSE Product Assurance

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
