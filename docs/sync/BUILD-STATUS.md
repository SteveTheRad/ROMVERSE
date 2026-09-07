# ROMVERSE Build Status

## Authoritative checkpoint

- Source and Product Assurance authorization commit:
  `1bc798bbca7a0f6a88dfa2514a25f130245c3d33`
- Branch: `linux/stage1-desktop-readiness`
- Stage: Stage 1 — v0.2 Golden Foundation contained Desktop-to-Companion Link integration
- Milestone result: **FAILED EXISTING LINK INSTRUMENTATION — 11 PASS / 1 FAIL / 0 SKIP**
- Scope result: approved environment correction worked; fixture reached `ready`; existing Link test
  failed before pairing; all evidence preserved and no retry or product change attempted
- Working-tree target state: clean after this handoff commit. The separate original checkout's
  three protected Companion changes and pre-existing Windows launcher drafts were not edited,
  staged, discarded, built from, or committed.

## Product Assurance authorization

- Product Assurance verdict `1bc798b` validated the prior pre-endpoint environment stop and
  authorized one repeat using only the existing verified ROMVERSE virtual-environment interpreter.
- The required result was 12 passes, zero failures, and zero skips with two fresh health snapshots,
  encrypted-session reconnection, paired-state UI evidence, and `execution_authority: none`.
- Any source-resolution, dependency, target, artifact, TLS, pin, safety-code, test, fixture, runtime,
  or emulator failure required an immediate evidence-preserving stop without another retry or any
  app, test, fixture, environment, protocol, or host-security change.

## Source and dependency resolution proof

The exact approved invocation context was verified before starting the emulator:

- Interpreter:
  `/run/media/stevetherad/Data/ROMVERSE-Recovered-2026-09-01/source/.venv/bin/python`
- Python: 3.14.7
- User-site packages: disabled with `PYTHONNOUSERSITE=1`
- Explicit `PYTHONPATH`:
  `/run/media/stevetherad/Data/ROMVERSE-Linux-Desktop-Readiness/src`
- `cryptography`: exactly 46.0.7, resolved from the existing virtual environment's `site-packages`
- `romverse`, `romverse.companion.pairing`, `security`, `telemetry`, and `transport`: all resolved
  beneath the clean `ROMVERSE-Linux-Desktop-Readiness/src` directory
- No ROMVERSE application module resolved from the separate protected original checkout
- Exact fixture script:
  `/run/media/stevetherad/Data/ROMVERSE-Linux-Desktop-Readiness/scripts/companion_link_emulator_fixture.py`

No package was installed, removed, upgraded, downgraded, or otherwise modified. No environment was
created or mutated.

## Emulator, target, and artifact admission

- Existing isolated AVD: `romverse_api35_clean`, Android 15 / API 35 / x86-64, Pixel 7 profile
- Launch: visible window, host GPU, port 5556, wiped data, snapshots disabled, no audio, no metrics
- Host renderer: AMD Radeon RX 9070 XT through RADV/Mesa
- Host SELinux: Enforcing and unchanged
- Boot result: successful in 16,917 ms
- Sole admitted target: `emulator-5556:device`
- Guest before shutdown: `ro.kernel.qemu=1`, `sys.boot_completed=1`

Before launch, ADB reported no target. The emulator remained the sole target for the complete
bounded run. After controlled shutdown, ADB again reported no target. No physical, simultaneous,
ambiguous, unauthorized, or changing target appeared.

The exact approved APK hashes were revalidated immediately before successful emulator installation:

- Application APK SHA-256:
  `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`
- Instrumentation APK SHA-256:
  `ec6776528384b26c29b748299f80285474cc64ed40fe2b2519efa6b4040a86b5`

## Contained fixture evidence

The exact committed fixture started with the approved environment and emitted:

- State: `ready`
- Emulator endpoint: `10.0.2.2:8765`
- Pairing-code lifetime: 3 minutes
- Ephemeral certificate SHA-256:
  `82abd2d7c8d47c7d42f203752f47e7987f065d50ea34f143d4aaf7a8c427d072`
- Safety code: `82AB-D2D7-C8D4-7C7D-42F2-0375`
- Execution authority: `none`

The one-time pairing code remains only in the external short-lived log and is not copied into the
repository. No reusable bearer credential was created.

The fixture remained at `ready`; it emitted no `approved`, `first-health-snapshot`, `complete`, or
`timeout` state. It received no pairing request and no health snapshot. It was interrupted and
closed immediately after the test failure, and no process or TCP listener remained.

Full fixture log:

- Path:
  `/run/media/stevetherad/Data/ROMVERSE-Android-Emulator-Toolchain/romverse-link-fixture-success.log`
- Size / lines: 237 bytes / 1 line
- SHA-256: `07d6cbdb23d72d8b22e98841a9afcd579e81016ac742eb1d142dfc95b0d19632`

Containment limitation requiring review: the committed `CompanionTransport` bound its short-lived
listener to `0.0.0.0:8765` and starts its existing discovery broadcaster. No pairing request or
external connection was observed, the ephemeral endpoint lived only for this bounded run, and it
was closed immediately on failure; however, the binding is broader than loopback and must not be
misrepresented as network-namespace isolation. Build did not change the committed fixture or host
firewall to narrow it.

## Exact instrumentation result

The runner received only the ephemeral `romverseLinkHost`, `romverseLinkCode`, and
`romverseLinkFingerprint` values from that fixture.

- Runner:
  `com.radforge.romverse.companion.test/androidx.test.runner.AndroidJUnitRunner`
- Complete inventory: 12 tests
- Passed: 11
- Failed: 1
- Skipped: 0
- Duration: 8.464 seconds
- Final result: `FAILURES!!!` / `Tests run: 12, Failures: 1`
- Failure:
  `tlsPinnedLinkCarriesLiveConsoleAndReconnectsAfterRecreation`
- Exception: `java.util.NoSuchElementException: Collection contains no element matching the predicate`
- Boundary: failure occurred while locating the expected pairing input in the launched Activity,
  before any fixture pairing request, approval, health snapshot, TLS-pinned telemetry exchange, or
  encrypted remembered session existed

Full runner log:

- Path:
  `/run/media/stevetherad/Data/ROMVERSE-Android-Emulator-Toolchain/romverse-link-instrumentation-runner.log`
- Size / lines: 13,562 bytes / 236 lines
- SHA-256: `ca19e7914c5ef971c1080697c6f62aa132e513e7e307370fc80d78f1c8fae7bd`
- Raw terminal status codes: 11 success (`0`), 1 failure (`-2`), 0 assumption skips (`-4`)

The AndroidRuntime error-only log is empty (0 bytes; SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`).
The failure is an instrumentation assertion/setup failure, not an Android process crash.

## Unmet acceptance criteria

- 12 passes / zero failures / zero skips: not met.
- Fixture pairing approval: not reached.
- Two fresh Companion health snapshots: not reached.
- TLS pin and safety-code runtime exchange: not reached.
- Encrypted-session reconnect after Activity recreation: not reached.
- Paired Link, schema-six Live Console, Device DNA, and Ascension UI evidence: not reached.
- `execution_authority: none`: positively emitted by the fixture; no execution authority existed,
  but the post-pairing UI boundary was not reached.

No visual paired-state evidence was captured because the failure-stop boundary preceded pairing.
No standalone static or host-side test was substituted for the failed integration result.

## Classification

- Implemented: no ROMVERSE implementation change.
- Simulated/Tested: genuine API-35 emulator, exact debug APKs, real ephemeral TLS fixture startup,
  and complete 12-test instrumentation execution with one genuine failure.
- Hardware Verified: no physical Android hardware was used.
- Contained Link Runtime Verified: no.
- Released: no.

## Blocker and next decision

The approved Python-environment correction is successful. The remaining blocker is inside the
existing contained Link instrumentation path: the Link test launches `MainActivity` and cannot find
the expected pairing input before it can contact the ready fixture.

Build did not rerun the suite, isolate or skip the failing test, change its order, modify Activity
state, navigate manually, alter the app/test/fixture, or weaken the 12/12 acceptance target. Product
Assurance must inspect the committed UI/test contract and authorize a specific bounded correction
or additional read-only diagnosis before any further attempt.

## Guided friction and safety implications

- The integration test encountered a pre-pairing UI reachability dead end: the expected pairing
  input was absent from the Activity view hierarchy used by the test.
- No end user flow was changed, and this checkpoint does not yet prove whether the dead end affects
  interactive user navigation or only the committed instrumentation setup.
- Guardian remains the sole execution gate.
- Fixture authority remained `none`; no flash, wipe, root, unlock, relock, approval, Recovery, or
  arbitrary-command authority existed.
- Exact-device evidence, UNKNOWN-on-uncertainty, no blind retry, consent separation, durable
  evidence, and independent verification remain unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and gate status

- Fedora Desktop runnable build and inert Guided journey: Product Assurance verified.
- Companion standalone API-35 emulator runtime: Product Assurance verified.
- Contained Desktop/Companion Link integration: failed before pairing; not verified.
- Physical Android, production trust, production signing, production Recovery, publication, and
  release: outstanding and not authorized.
- Windows: remains on its separate track; no platform merge or duplicate work occurred.
- v0.2 Golden Foundation: remains **CLOSED**.
- 5 September 2026 pre-v1.0 feature freeze: preserved; no source, dependency, behavior, protocol,
  test, asset, or authority change occurred.

## Next proposed Build task

Stop for Product Assurance review. Do not rerun instrumentation, change navigation or pairing state,
modify or weaken the test, fixture, app, protocol, environment, or host security, use a phone,
enable Recovery, merge platforms, publish, or release without a new explicit verdict.

## External actions

- Existing verified Python environment: used read-only; no package/environment mutation.
- Visible host-GPU emulator launch: one successful bounded session.
- Exact approved APK installation: emulator only.
- Fixture endpoint: one short-lived ephemeral instance; closed immediately on failure.
- Instrumentation: one complete 12-test run with 11 pass / 1 fail / 0 skip.
- Physical phone connection/operation: none.
- Emulator shutdown: controlled; post-run ADB inventory empty.
- Host security or SELinux change: none.
- ROMVERSE source/test/fixture/config/resource/asset change: none.
- Protected Companion file or Windows launcher change: none.
- Production signing, production trust, or Recovery execution: none.
- Website change: none.
- Publication/release: none.
- Remote action: normal push of only this `docs/sync/BUILD-STATUS.md` handoff on
  `linux/stage1-desktop-readiness`; no force-push and no unrelated branch push.

## Product Assurance Review Requested

- Review the precise pre-pairing `NoSuchElementException`, test/UI route expectations, and whether
  the correct bounded fix belongs in app navigation state, test setup, or an existing fixture input.
- Review the committed fixture's `0.0.0.0` listener/discovery behavior against the intended contained
  emulator-only scope before authorizing another runtime attempt.
- Confirm no Link integration, snapshot, reconnect, physical-hardware, Recovery, production trust,
  signing, release, or publication claim is permitted from this result.
