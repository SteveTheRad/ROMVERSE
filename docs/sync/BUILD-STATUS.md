# ROMVERSE Build Status

## Authoritative checkpoint

- Source and Product Assurance authorization commit:
  `14468a5ed96ef8e63eeab5d227317808999dad11`
- Branch: `linux/stage1-desktop-readiness`
- Stage: Stage 1 — v0.2 Golden Foundation contained Desktop-to-Companion Link integration
- Milestone result: **BLOCKED BEFORE FIXTURE ENDPOINT / INSTRUMENTATION**
- Scope result: exact emulator and APK admission succeeded; committed fixture import failed in the
  invoked Python environment; failure evidence preserved and no workaround attempted
- Working-tree target state: clean after this handoff commit. The separate original checkout's
  three protected Companion changes and pre-existing Windows launcher drafts were not edited,
  staged, discarded, built from, or committed.

## Product Assurance authorization

- Product Assurance verdict `14468a5` approved the standalone API-35 Companion runtime checkpoint
  and authorized one contained encrypted Desktop-to-Companion Link runtime using the already
  committed `scripts/companion_link_emulator_fixture.py`.
- The required target was 12 passes, zero failures, and zero skips with two fresh health snapshots,
  encrypted session reconnection, paired UI evidence, and `execution_authority: none`.
- Any fixture, target, hash, TLS, pin, safety-code, test, runtime, or emulator failure required an
  evidence-preserving stop before changing the app, tests, fixture, host security, or transport.

## Emulator and exact-target admission

- Existing isolated SDK root:
  `/run/media/stevetherad/Data/ROMVERSE-Android-Emulator-Toolchain`
- AVD: `romverse_api35_clean`, Pixel 7 profile, Android 15 / API 35, Google APIs, x86-64
- Launch: visible window, host GPU, port 5556, wiped data, snapshots disabled, no audio, no metrics
- Host renderer: AMD Radeon RX 9070 XT through RADV/Mesa
- Host SELinux: Enforcing and unchanged
- Boot result: successful in 17,017 ms
- Sole admitted target: `emulator-5556:device`
- Guest evidence before shutdown: `ro.kernel.qemu=1`, `sys.boot_completed=1`

Before launch, ADB reported no target. The emulator was the sole target throughout the bounded
session. After the controlled `emu kill`, ADB again reported no target. No physical, simultaneous,
ambiguous, unauthorized, or changing target appeared.

## Exact APK admission

The approved artifacts were rehashed immediately before emulator installation:

- Debug application APK:
  `companion/app/build/outputs/apk/debug/app-debug.apk`
  - SHA-256: `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`
  - Emulator install result: `Success`
- Debug instrumentation APK:
  `companion/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk`
  - SHA-256: `ec6776528384b26c29b748299f80285474cc64ed40fe2b2519efa6b4040a86b5`
  - Emulator install result: `Success`

Only `com.radforge.romverse.companion` and its approved
`com.radforge.romverse.companion.test` package were installed for this run.

## Fixture launch failure

The exact committed fixture was invoked from the repository root with:

```text
PYTHONPATH=src python scripts/companion_link_emulator_fixture.py
```

Invoked environment:

- Python executable: `/usr/bin/python`
- Python version: 3.14.7
- `cryptography` module discovery: `None`
- Repository declaration: `cryptography>=46,<47` in `pyproject.toml`

The process failed during import before creating `CompanionTransport`:

```text
File "src/romverse/companion/security.py", line 11, in <module>
    from cryptography import x509
ModuleNotFoundError: No module named 'cryptography'
```

Preserved evidence outside the repository:

- Exact error log:
  `/run/media/stevetherad/Data/ROMVERSE-Android-Emulator-Toolchain/romverse-link-fixture-error.log`
  - 10 lines / 843 bytes
  - SHA-256: `550e2d72b964a80a1c464e76f8fe0321e9111bd2993e78ac8478c7bf6b2864eb`
- Fixture stdout log:
  `/run/media/stevetherad/Data/ROMVERSE-Android-Emulator-Toolchain/romverse-link-fixture.log`
  - 0 lines / 0 bytes
  - SHA-256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

No fixture endpoint opened on port 8765. The process emitted no `ready`, `approved`, snapshot, or
completion state; no pairing code, certificate fingerprint, safety code, bearer token, or reusable
credential was created or logged. No fixture process remained after failure.

## Test and runtime result

- Contained Link instrumentation: **0 run / 0 pass / 0 fail / 0 skip**.
- The expected 12/12 zero-skip target was not attempted and is not satisfied.
- No instrumentation runner arguments were generated or passed.
- No TLS, certificate pin, safety-code, pairing approval, health snapshot, encrypted-session,
  Activity-recreation, Live Console, Device DNA, or Ascension runtime claim is made.
- The application was not launched for a paired visual smoke.
- The preceding Product-Assurance-approved standalone emulator result remains valid but is not
  counted again here.

## Classification

- Implemented: no ROMVERSE implementation change.
- Simulated/Tested: clean API-35 emulator boot, exact-target admission, exact APK revalidation and
  installation, fixture invocation, and failure-boundary verification.
- Hardware Verified: no physical Android hardware was used.
- Contained Link Runtime Verified: no; blocked before the endpoint existed.
- Released: no.

## Blocker and next decision

The default source invocation selected `/usr/bin/python` 3.14.7, which does not contain the
repository-declared `cryptography` dependency. The committed fixture therefore cannot import the
existing TLS identity layer in that environment.

Build did not install the dependency, create or select another Python environment, reuse a packaged
runtime, alter `PYTHONPATH`, modify the fixture, or rerun it. Product Assurance must approve the
narrow environment correction—such as a verified isolated environment containing the exact
committed project dependencies—before the contained Link runtime is attempted again.

## Guided friction and safety implications

- The block occurred before ROMVERSE Link UI or pairing began, so no new Guided dead end was
  observed or fixed.
- No endpoint, pairing credential, production trust, Recovery adapter, or device-changing action
  became reachable.
- `execution_authority: none` was not emitted because the fixture never started; no contrary
  authority was created or inferred.
- Guardian remains the sole execution gate.
- Exact-device evidence, UNKNOWN-on-uncertainty, no blind retry, consent separation, durable
  evidence, and independent verification remain unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and gate status

- Fedora Desktop runnable build and inert Guided journey: Product Assurance verified.
- Companion standalone API-35 emulator runtime: Product Assurance verified.
- Contained Desktop/Companion Link integration: blocked before fixture startup.
- Physical Android, production trust, production signing, production Recovery, publication, and
  release: outstanding and not authorized.
- Windows: remains on its separate track; no platform merge or duplicate work occurred.
- v0.2 Golden Foundation: remains **CLOSED**.
- 5 September 2026 pre-v1.0 feature freeze: preserved; no product source, dependency declaration,
  behavior, protocol, test, asset, or authority change occurred.

## Next proposed Build task

Stop for Product Assurance review. Do not install Python dependencies, create/select another
environment, rerun the fixture, substitute a mock endpoint, change Companion or fixture code, use a
phone, enable Recovery, merge a platform branch, publish, or release without a new explicit verdict.

## External actions

- Visible host-GPU emulator launch: one successful bounded session.
- Exact approved APK installation: emulator only.
- Fixture invocation: one failed pre-endpoint import attempt.
- Network endpoint or discovery broadcast created: none.
- Pairing or reusable credential created: none.
- Physical phone connection/operation: none.
- Instrumentation or app runtime after fixture failure: none.
- Emulator shutdown: controlled; post-run ADB inventory empty.
- Python dependency/tool/system package installation: none.
- Host security or SELinux change: none.
- ROMVERSE source/test/fixture/config/resource/asset change: none.
- Protected Companion file or Windows launcher change: none.
- Production signing or Recovery execution: none.
- Website change: none.
- Publication/release: none.
- Remote action: normal push of only this `docs/sync/BUILD-STATUS.md` handoff on
  `linux/stage1-desktop-readiness`; no force-push and no unrelated branch push.

## Product Assurance Review Requested

- Confirm the pre-endpoint failure stop and exact evidence classification.
- Authorize or reject a specific isolated Python environment containing the committed dependency
  set for one repeat of this same contained Link runtime.
- Confirm no Link, physical-device, Recovery, production-trust, signing, or release claim is
  implied by this checkpoint.
