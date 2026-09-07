# ROMVERSE Product Assurance

## Reviewed checkpoint: 7479c2c

- Handoff commit: `7479c2c11450ca1e88f863db523498f5df4a7b8b`
- Product Assurance authorization:
  `74da8577b09e5cccd33c2128f56e41b12189311c`
- Title: `Record Companion emulator runtime verification`
- Branch: `linux/stage1-desktop-readiness`
- Review status: **APPROVED — COMPANION API-35 EMULATOR RUNTIME VERIFIED**

### Decision

The exact approved Companion debug application and instrumentation artifacts have now completed a
genuine Android 15 / API-35 emulator runtime gate. Product Assurance independently verified the
committed scope, raw runner log, artifact and evidence hashes, visible screenshots, privacy-curtain
capture, host enforcement state, post-run target inventory, and absence of a new emulator crash.

The result is honestly bounded: 11 tests passed, none failed, and the one contained Desktop Link
fixture test assumption-skipped because the separate fixture was not part of this run. That skip is
neither a pass nor a ROMVERSE failure. It remains the next concrete integration boundary.

### Independent evidence

- Commit `7479c2c` changes only `docs/sync/BUILD-STATUS.md`; the dedicated worktree is clean and
  matches `origin/linux/stage1-desktop-readiness`.
- The approved application APK SHA-256 remained
  `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`.
- The approved instrumentation APK SHA-256 remained
  `ec6776528384b26c29b748299f80285474cc64ed40fe2b2519efa6b4040a86b5`.
- The sole admitted target was `emulator-5556`, reporting Android 15, API 35, x86-64,
  `ro.kernel.qemu=1`, and completed boot.
- Android Emulator 37.1.11 launched once through the approved visible `-gpu host` path using the
  existing clean, wiped, snapshot-disabled API-35 AVD.
- The raw 217-line runner log is 11,760 bytes and independently hashes to
  `fffa36efb5fa3d4a456de165f0fb4be37c3bdd120e9400dc7d5b006be383d51f`.
- Raw status codes independently count 11 success completions and one assumption skip; the runner
  ends `OK (12 tests)` with code `-1`.
- The assumption is explicit: the test requires the contained Desktop Link fixture. It was not
  hidden, weakened, rewritten, or counted as passed.
- Cold launch completed in 359 ms and the app-scoped AndroidRuntime error log remained empty.

### Independent visual review

The preserved screenshots are readable and their recorded hashes match. They visibly confirm:

- the approved ROMVERSE branding and Command Deck Guided shell;
- one coherent navigation drawer and the existing destination set;
- Guided and Expert Settings state, including the permanent bootloader-relock prohibition;
- persisted Expert presentation and expanded Vitalis evidence;
- correct Privacy Curtain protection: the Companion app region is black while Android system bars
  remain visible.

The evidence supports a runtime pass for existing emulator-safe UI and lifecycle behavior. It does
not imply physical-device, manufacturer, USB, production-trust, or release verification.

### Post-run and safety verification

- SELinux remains Enforcing; no policy or enforcement change occurred.
- ADB reports no target after the controlled emulator shutdown.
- No emulator/Android/Companion coredump was recorded during the successful authorized session.
- No Companion source, test, manifest, dependency, resource, behavior, or brand asset changed.
- The protected original-checkout Companion changes and old Windows drafts remain untouched.
- Guardian remains the sole execution gate; Companion has no flash, wipe, root, unlock, relock,
  approval, or arbitrary-command authority.
- UNKNOWN-on-uncertainty, no blind retry, exact-target evidence, and consent separation remain
  unchanged.
- Bootloader locking and relocking remain permanently prohibited with no override.
- The pre-v1.0 feature freeze is preserved.

### Acceptance criteria satisfied

- Exact approved artifacts revalidated immediately before install: satisfied.
- One exact disposable emulator target and no physical target: satisfied.
- Complete existing standalone instrumentation inventory executed honestly: satisfied, with
  11 pass / 0 fail / 1 explicit assumption skip.
- Readable app launch, branding, navigation, presentation continuity, and technical evidence:
  satisfied.
- Privacy Curtain secure-capture boundary: satisfied.
- Clean shutdown, empty target inventory, enforcing host, and no app changes: satisfied.
- Physical hardware, paired Desktop Link, production Recovery, signing, publication, and release:
  not claimed.

### Approved next bounded task

Complete the one remaining **contained Desktop-to-Companion Link integration runtime** using the
already committed `scripts/companion_link_emulator_fixture.py`. This is verification of an existing
encrypted read-only feature, not a new implementation slice or a generic test expansion.

Use the same isolated official API-35 toolchain and exact approved APK hashes. Start one clean,
visible-window host-GPU emulator with SELinux enforcing and require exactly the sole
`emulator-5556` target. Start one instance of the contained fixture from the approved committed
source and record its short-lived endpoint, pairing-code lifetime, certificate fingerprint, safety
code, and explicit `execution_authority: none` output without placing reusable credentials in the
repository.

Pass only those fixture values as the existing instrumentation runner arguments and execute the
complete packaged 12-test suite once. Require 12 passes, zero failures, and zero skips. Preserve the
full fixture and runner logs and their hashes. Confirm the fixture receives two fresh Companion
health snapshots, the remembered encrypted session reconnects after Activity recreation, and the
existing Companion UI renders the paired state, schema-six Live Console, Device DNA, and Ascension
Guardian boundary. Capture bounded readable screenshots where practical.

On any target ambiguity, artifact mismatch, TLS/pin/safety-code failure, test failure or skip,
fixture timeout, runtime error, or emulator failure, preserve evidence and stop without changing
the app, tests, fixture, host security, or transport contract.

Do not connect or operate a physical phone; expose the fixture beyond the local emulator path;
grant execution authority; enable Recovery; use production signing; change protected files;
merge platform branches; publish; or release. Shut down the emulator and fixture, confirm ADB is
empty, update `docs/sync/BUILD-STATUS.md`, commit and push the exact checkpoint on
`linux/stage1-desktop-readiness`, and stop for independent Product Assurance review.

### Gate status

- v0.2 Golden Foundation: **CLOSED pending remaining release gates**
- Fedora runnable development build and inert Guided journey: **VERIFIED**
- Companion debug and instrumentation APK artifact readiness: **VERIFIED**
- Companion standalone API-35 emulator runtime: **VERIFIED**
- Contained Desktop/Companion Link integration: **NEXT APPROVED BOUNDED TASK**
- Companion physical-device verification: outstanding; not authorized
- Windows runnable development build and inert journey: separate Windows correction track
- Production Recovery, signing, publication, and release: outstanding and not authorized
