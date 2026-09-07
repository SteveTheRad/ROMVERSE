# ROMVERSE Product Assurance

## Reviewed checkpoint: b38ae23

- Handoff commit: `b38ae23b3fd3cc492bfb90cd96d2be700289864a`
- Evidence commit: `507872cb3bd8cebab8c210af7de5fb2ef00e14f5`
- Built source baseline and prior authorization:
  `5057d62543de32cf6a3058f77a48d54136d00b16`
- Title: `Record Companion instrumentation assurance handoff`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — COMPANION INSTRUMENTATION APK READINESS VERIFIED**

### Decision

The committed Companion baseline successfully compiled all existing Android instrumentation sources
and assembled the exact debug application and debug instrumentation APKs. Product Assurance
independently verified both archives, package identities, SDK bounds, instrumentation runner and
target, debug signer, certificate, packaged DEX inventory, and locked brand assets.

This checkpoint is correctly classified as an artifact-readiness gate. The 12 instrumentation test
methods are compiled and packaged, not runtime passes. No APK was installed or executed, no emulator
or phone was used, and no Companion behavior, source, build configuration, resource, or authority
boundary changed. The checkpoint complies with the pre-v1.0 feature freeze.

### Repository and artifact evidence

- The checkpoint descends exactly from the approved `5057d62` baseline.
- The evidence commit adds only `docs/COMPANION-INSTRUMENTATION-APK-READINESS.md`; the handoff commit
  changes only `docs/sync/BUILD-STATUS.md`.
- The dedicated Linux worktree is clean and matches
  `origin/linux/stage1-desktop-readiness` at `b38ae23` before this review.
- The three protected Companion changes and old Windows launcher drafts remain isolated in the
  original checkout and were not edited, staged, discarded, built from, or committed.
- Application APK: `companion/app/build/outputs/apk/debug/app-debug.apk`
  - 9,060,239 bytes; 874 ZIP members
  - SHA-256: `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`
- Instrumentation APK:
  `companion/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk`
  - 383,843 bytes; 9 ZIP members
  - SHA-256: `ec6776528384b26c29b748299f80285474cc64ed40fe2b2519efa6b4040a86b5`
- Both ZIP archives pass complete compressed-data validation.

### Independent metadata and signing verification

- Application ID / label: `com.radforge.romverse.companion` / `ROMVERSE Companion`
- Version name / code: `0.2.0-alpha.5` / `8`
- Application minimum / target / compile SDK: `26` / `35` / `35`
- Instrumentation package: `com.radforge.romverse.companion.test`
- Instrumentation target: `com.radforge.romverse.companion`
- Runner: `androidx.test.runner.AndroidJUnitRunner`
- Instrumentation minimum / target / compile SDK: `26` / `35` / `35`
- Both artifacts are debuggable and verify with one Android Debug RSA-2048 signer.
- APK Signature Scheme v2 verifies for both; v1, v3, v3.1, v4, and SourceStamp are absent.
- Certificate SHA-256:
  `b1e1bd6e1c199d6bc1649998546a20559e3b0f979cb401ef487b0cde7f993cb1`
- No production signing identity or key was used.

### Instrumentation and brand evidence

Packaged DEX inspection and committed-source inspection confirm the complete existing inventory:

- `CompanionUpgradeContinuityInstrumentedTest` — 1 test method
- `LinkSessionVaultInstrumentedTest` — 3 test methods
- `MainActivityInstrumentedTest` — 8 test methods

Total: 3 classes and 12 committed test methods. No test was added, removed, or claimed as executed.

The application APK contains the approved brand assets byte-for-byte:

- ROMVERSE logo source/member SHA-256:
  `ab9286ce69e77abd82fe88105df70680186a4eb992289580c23f5d362c132a18`
- RadForge Labs logo source/member SHA-256:
  `d82ff146aab1f18474005d1a2d9ce0c3944467ae30ff7cb4fb3284387daa95cb`

### Verification reviewed

- Build's pinned offline Gradle gate completed successfully:
  `clean compileDebugAndroidTestKotlin assembleDebug assembleDebugAndroidTest`;
  **65/65 actionable tasks executed**.
- Product Assurance independently recomputed both APK hashes and member counts and ran complete ZIP
  integrity checks.
- Product Assurance independently read both packaged manifests with Android build-tools 35.0.0,
  verified both signatures and certificate identities with `apksigner`, inspected all packaged DEX
  files for the three test classes, counted the 12 committed `@Test` methods, and rehashed both
  source-to-APK brand assets.
- Git scope and protected-file checks pass.

### Guided friction and safety judgment

- No Guided or Expert UI, route, warning, confirmation, state, or execution surface changed.
- Companion grants no flash, wipe, root, unlock, relock, approval, or arbitrary-command authority.
- Guardian remains the sole execution gate.
- Exact-device evidence, UNKNOWN-on-uncertainty, no blind retry, durable evidence, and independent
  verification remain unchanged.
- Bootloader locking and relocking remain permanently prohibited with no override.

### Acceptance criteria satisfied

- Existing `androidTest` sources compile and package: satisfied.
- Exact application and instrumentation APK identities and integrity: satisfied.
- Exact debug signer, certificate, and signature scheme: satisfied.
- Exact packaged test-class inventory: satisfied.
- Approved brand-asset byte preservation: satisfied.
- Honest non-runtime classification: satisfied.
- Protected-file isolation, feature freeze, and release-gate preservation: satisfied.
- Android runtime, emulator, and physical-hardware execution: not claimed.

### Approved next bounded task

Perform the first **Companion Android emulator runtime verification** of these exact approved debug
artifacts. This is runtime validation of existing behavior, not a new feature or release task.

Use a clean disposable Android emulator compatible with API 35. Reuse an already installed official
Android SDK emulator/system image when available. If it is missing, Build may install only the
official pinned Android SDK command-line tools, emulator, platform-tools, and one API-35 x86-64
Google APIs system image into an isolated non-repository toolchain directory. Record exact package
versions and installation paths; do not modify system-wide packages or application dependencies.

Before emulator launch, verify that no ADB target is connected. After launch, require exactly one
unambiguous `emulator-*` target and reject any physical, simultaneous, unauthorized, or changing
target. ADB use is authorized only for that exact disposable emulator serial.

Install the exact APKs with the approved hashes above, run the exact
`com.radforge.romverse.companion.test/androidx.test.runner.AndroidJUnitRunner` suite, and record:

- emulator/system-image identity, API/ABI, clean-snapshot state, and exact target serial;
- APK hashes revalidated immediately before installation;
- install results, complete instrumentation test count, pass/fail/skip results, and full runner log;
- application launch evidence and a bounded visual smoke of the existing Guided shell, branding,
  navigation, privacy curtain, and Guided/Expert continuity where already covered;
- confirmation that no real phone, Recovery adapter, production trust, or mutating external action
  was reachable.

If any test or runtime check fails, preserve the failure evidence and return for Product Assurance
before changing Companion source, tests, manifest, resources, or Gradle configuration. Do not weaken,
skip, rewrite, or manufacture tests to obtain a pass. Do not connect or operate a physical phone,
use production signing, alter protected files or branding, merge platform branches, publish, or
release.

Update `docs/sync/BUILD-STATUS.md`, commit and push the exact checkpoint on
`linux/stage1-desktop-readiness`, then stop for independent Product Assurance review.

### Gate status

- v0.2 Golden Foundation: **CLOSED**
- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Companion debug application APK readiness: **VERIFIED**
- Companion instrumentation APK artifact readiness: **VERIFIED**
- Companion emulator runtime verification: **NEXT APPROVED BOUNDED TASK**
- Companion physical-device verification: outstanding; not authorized here
- Windows runnable development build and inert journey: **IN PROGRESS on separate Windows track**
- Production adapter enrollment and physical Android Recovery: outstanding release gates
- Pre-v1.0 feature freeze: preserved
- Production signing, publication, and release: not authorized
