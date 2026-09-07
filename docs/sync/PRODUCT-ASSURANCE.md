# ROMVERSE Product Assurance

## Reviewed checkpoint: b482de8

- Handoff commit: `b482de8813143037a1ade3ca97cff123932b7caf`
- Evidence commit: `67ff3a29a3f06b84c3b43989b61cd37e9dcff587`
- Built source baseline: `550a27563aeca4b52a1f519291eefe84e481a431`
- Title: `Record Companion debug APK readiness`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — COMPANION DEBUG APK READINESS VERIFIED**

### Decision

The committed Companion baseline reproducibly assembles as a genuine local Android-debug-signed APK
using the pinned offline Java 17, Gradle 8.11.1, Android Gradle Plugin 8.7.3, Kotlin 2.0.21, and
Android SDK 35 toolchain. The artifact identity, version, SDK bounds, archive integrity, signer,
certificate, and locked brand assets are exact and independently reproducible.

This is correctly classified as development readiness, not Android runtime, hardware, production
signing, publication, or release evidence. No Companion source, resource, manifest, build
configuration, behavior, brand asset, Desktop runtime, or execution boundary changed. The
checkpoint is therefore compliant with the pre-v1.0 feature freeze.

### Repository and artifact evidence

- The checkpoint is exactly two documentation-only commits descended from the approved `550a275`
  base. Only `docs/COMPANION-DEBUG-APK-READINESS.md` and `docs/sync/BUILD-STATUS.md` changed.
- The dedicated worktree is clean. The three protected Companion modifications and the old Windows
  launcher drafts remain isolated in the original checkout and were not built, edited, staged,
  discarded, or committed.
- APK: `companion/app/build/outputs/apk/debug/app-debug.apk`
- Application ID / label: `com.radforge.romverse.companion` / `ROMVERSE Companion`
- Version name / code: `0.2.0-alpha.5` / `8`
- Minimum / target / compile SDK: `26` / `35` / `35`
- Size / ZIP members: 9,060,239 bytes / 874
- APK SHA-256:
  `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`
- Signing: one Android Debug RSA-2048 signer; APK Signature Scheme v2 verified; no SourceStamp.
- Debug certificate SHA-256:
  `b1e1bd6e1c199d6bc1649998546a20559e3b0f979cb401ef487b0cde7f993cb1`
- Approved ROMVERSE and RadForge Labs logo members inside the APK are byte-identical to their
  committed sources at the recorded `ab9286...` and `d82ff1...` hashes.

### Verification reviewed

- Build's clean offline gate completed successfully: `clean testDebugUnitTest lintDebug
  assembleDebug`; 52 actionable tasks, 51 executed and one up-to-date.
- Companion JVM tests: **162/162 passed** across 30 suites.
- Existing ROMVERSE Link/Lifeline subset: **29/29 passed**; correctly counted only within the 162.
- Distinct Desktop-side Companion/Link regression: **120/120 passed**.
- Android lint: zero fatal/error findings and 331 visible warnings; none was suppressed or
  reclassified for this checkpoint.
- Product Assurance independently verified the APK hash, size, 874-member ZIP integrity,
  package/version/SDK metadata, exact debug signer/certificate, and both packaged logo hashes.
- Product Assurance independently reran all Companion JVM tests with Gradle `--rerun-tasks`:
  **162/162 passed** across 30 suites.
- Git whitespace verification passes for the complete checkpoint.

### Lint and security judgment

The 331 warning-only findings do not block this artifact-assembly checkpoint. The one
`CustomX509TrustManager` warning was inspected rather than dismissed generically. The existing
ROMVERSE Link implementation requires a single certificate, checks its validity, compares the
complete SHA-256 certificate pin in constant time, rejects client certificates, and repeats the
exact pin check through the hostname verifier. The warning therefore does not demonstrate disabled
certificate validation in this local pinned-link design. It remains visible for formal pre-release
security review and must not be silently suppressed.

The remaining warning groups are existing localization, drawing-allocation, compatibility, icon,
and unused-resource debt. Fixing them would be a separate behavior/UI-quality task and is not
authorized under this assembly checkpoint.

### Guided friction and safety judgment

- Existing ROMVERSE Link readiness, USB-assist state, trust classification, Lifeline progression,
  and Lifeline session-integrity behavior passed their committed deterministic tests.
- No new route, confirmation, warning, dead end, or execution surface was introduced.
- Companion grants no flash, wipe, root, unlock, relock, approval, or arbitrary-command authority.
- Guardian remains the sole execution gate.
- Exact-device evidence, UNKNOWN-on-uncertainty, no blind retry, and independent verification remain
  unchanged.
- Bootloader locking and relocking remain permanently prohibited with no override.

### Acceptance criteria satisfied

- Clean offline Companion debug APK assembly: satisfied.
- Exact package, version, SDK, archive, debug signer, and certificate identity: satisfied.
- Approved brand-asset byte preservation: satisfied.
- Existing JVM and Desktop-side Link/Lifeline behavior: satisfied.
- Honest lint classification and visible technical debt: satisfied.
- Protected-file isolation, feature freeze, and release-gate preservation: satisfied.
- Android runtime, instrumentation execution, emulator, and physical hardware: not claimed.

### Approved next bounded task

Produce a local **Companion Android instrumentation APK readiness bundle** from the same committed
approved baseline. This is the final pre-runtime artifact gate; it is not authorization to install
or execute either APK.

Run the pinned offline toolchain to compile the existing `androidTest` sources and assemble the
debug application APK plus debug instrumentation APK. Verify and record:

- exact application and instrumentation APK paths, sizes, SHA-256 digests, and ZIP integrity;
- instrumentation package, target package, runner, SDK metadata, debug classification, signer,
  certificate, and signature schemes;
- the exact committed instrumentation test classes included and successful compile/package tasks;
- that the application APK identity and locked brand assets remain unchanged;
- that no source, manifest, Gradle configuration, or protected Companion file changed.

If the committed baseline cannot assemble the instrumentation APK, report the exact blocker and
return for Product Assurance before changing source or build configuration. Do not manufacture new
tests merely to increase totals.

Do not install an APK, start an emulator, connect to or operate a phone, run ADB, use a production
signing key, edit the three protected Companion files, change behavior or branding, merge a platform
branch, download dependencies, publish, or release.

### Gate status

- v0.2 Golden Foundation: **CLOSED**
- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Companion debug APK build readiness: **VERIFIED**
- Companion instrumentation APK readiness: **NEXT APPROVED BOUNDED TASK**
- Companion Android runtime/emulator/physical verification: outstanding; not authorized here
- Windows runnable development build and inert journey: **IN PROGRESS on separate Windows track**
- Production adapter enrollment and physical Android Recovery: outstanding release gates
- Pre-v1.0 feature freeze: preserved
- APK installation, physical execution, production signing, publication, and release: not authorized
