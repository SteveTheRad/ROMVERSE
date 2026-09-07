# ROMVERSE Product Assurance

## Reviewed checkpoint: b76843c

- Handoff commit: `b76843c6ca79b7a17ef31a905d202d6298f8c528`
- Implementation commit: `1300dde1b79304149b8acfafe0e3f272d800cd37`
- Title: `Assemble runnable Fedora recovery journey`
- Branch: `linux/stage1-desktop-readiness`
- Approved base: `fdb1692b0a5056cce0992b9045cd6f3a55cabf97`
- Review status: **APPROVED — RUNNABLE FEDORA DEVELOPMENT CHECKPOINT VERIFIED**

### Decision

The checkpoint provides a genuine runnable Fedora development build and a complete inert
product-level Guided Recovery journey. The source launcher, wheel, one-folder executable, and
portable ZIP are sufficient for this local development milestone. They are correctly classified as
unsigned development artifacts rather than an installer, native package, release, or hardware proof.

The simulator traverses the production Scan → Match → Prepare → Consent → Result → Reassessment →
Verification services with a disposable workspace, synthetic evidence, an in-memory target, and
ephemeral test-only adapter trust. The aggregate Result remains explicitly unverified until fresh
same-incident boot evidence completes verification. No ADB/Fastboot executable, external adapter
process, physical device, production trust root, automatic retry, or bootloader-relock path is used.

The work is feature-freeze compliant: it assembles and demonstrates the already approved Stage 1
chain without changing `src/romverse`, schema, production Device Packs, execution authority, UI, or
release behavior. Native RPM/Flatpak/desktop-entry integration and production adapter/hardware work
remain later, separately authorized release gates rather than defects in this checkpoint.

### Repository and implementation evidence

- The handoff is exactly two commits descended from the approved `fdb1692` base. The implementation
  adds only `docs/FEDORA-DEVELOPMENT-BUILD.md`, `scripts/simulate_guided_recovery.py`, and its focused
  integration test; the handoff changes only `docs/sync/BUILD-STATUS.md`.
- The dedicated Linux worktree is clean. The original checkout still contains only the three known
  protected Companion modifications and the pre-existing Windows launcher drafts; none appears in
  this branch or checkpoint.
- Git whitespace verification passes across the complete checkpoint diff.
- Build recorded a final Linux regression of **2,881/2,881 passed** in 920.49 seconds, with no
  failures, skips, or xfails. Product Assurance observed that full process run to completion and
  independently reran the new focused journey test successfully.
- Product Assurance independently launched the frozen executable in offscreen release-smoke mode,
  extracted and launched the portable ZIP, and verified both wheel and ZIP archive integrity.
- Independently observed artifact digests match the handoff:
  - wheel: `df40c6ca9da96154050f07dd4fa8a336b035ff394c68bf56c52d41b6c0cdddcc`
  - executable: `b94dc7788b4cce09d4a30e5aff44d6bf1104c717bac9bf843267538c5e1a68ea`
  - portable ZIP: `dd73842d1de7c18f545b6a4cba7141f758ad3802c8e98877a54de81cdc3afed2`
- The durable demonstration report records all seven stages, three exact adapter actions, project
  reopening, explicit `recovery_verified: false` at Result, and final same-incident `RECOVERED` only
  after stable fresh boot evidence. It also records no physical-device change, production execution,
  retry authority, persisted test key, or relock authority.

### Guided friction and safety judgment

- Guided reaches a result without a circular prerequisite or repeated consequential confirmation.
- Consent remains one scoped decision and grants no execution authority by itself.
- Result and Reassessment do not claim repair; exact fresh verification is still required.
- Missing, changed, stale, or ambiguous target evidence remains fail-closed.
- FAILED and UNKNOWN remain durable stop states with no blind or automatic retry.
- Guardian remains the sole execution gate.
- Bootloader locking and relocking remain permanently prohibited with no override.

### Acceptance criteria satisfied

- Runnable Fedora source and frozen development launches: satisfied.
- Portable development bundle integrity and extracted launch: satisfied.
- Complete inert Guided journey through production service boundaries: satisfied.
- Durable exact-incident result, reassessment, and independent verification: satisfied.
- Full Linux regression and focused journey coverage: satisfied.
- Feature freeze, platform truthfulness, protected-file isolation, and release-gate preservation:
  satisfied.

### Approved next bounded task

Produce a clean development-signed **Companion debug APK readiness checkpoint** from the committed
approved baseline. This is an artifact-assembly and existing-behavior verification task, not a new
feature slice.

The task may run the pinned Java 17/Gradle/Android toolchain, Companion JVM tests, lint/build checks,
and `assembleDebug`; verify the APK package identity, archive integrity, version metadata, debug
signing classification, and SHA-256; and exercise existing inert ROMVERSE Link/Lifeline state through
the committed non-hardware test boundaries. It may make only a minimum build-readiness correction if
the committed baseline cannot assemble, and must return for Product Assurance before expanding that
correction.

It must not edit, stage, discard, or commit the three protected Companion files in the original
checkout; install an APK; connect to or operate a phone/emulator; use a production signing key;
change Companion behavior or branding; merge a platform branch; publish; or release. If the protected
files are required for a future Companion feature checkpoint, ownership must first be resolved in a
separate reviewed handoff.

### Gate status

- v0.2 Golden Foundation: **CLOSED**
- Fedora runnable development build: **VERIFIED**
- Fedora inert end-to-end Guided Recovery journey: **VERIFIED**
- Windows runnable development build and inert journey: **IN PROGRESS on separate Windows track**
- Companion debug APK readiness: **NEXT APPROVED BOUNDED TASK**
- Companion hardware/instrumented verification: outstanding; not authorized here
- Production adapter enrollment and physical Android Recovery: outstanding release gates
- Pre-v1.0 feature freeze: preserved
- Physical execution, APK installation, production signing, publication, and release: not authorized
