# ROMVERSE Build Status

## Authoritative checkpoint

- Source and Product Assurance authorization commit:
  `972ab5a5b62ded74846cdec2cdf8e5465b60a00d`
- Branch: `linux/stage1-desktop-readiness`
- Stage: Stage 1 — v0.2 Golden Foundation Companion Android emulator runtime verification
- Milestone result: **BLOCKED BEFORE ANDROID BOOT / ADB TARGET ADMISSION**
- Scope result: failure evidence preserved; no Companion source or build configuration changed
- Working-tree target state: clean after this handoff commit. The separate original checkout's
  three protected Companion changes and pre-existing Windows launcher drafts were not edited,
  staged, discarded, built from, or committed.

## Product Assurance authorization

- Product Assurance verdict `972ab5a` approved the Companion instrumentation artifact checkpoint
  and authorized only a disposable API-35 Android emulator runtime verification.
- The verdict permitted installation of official Android SDK emulator components into an isolated
  non-repository directory and required a stop on runtime failure before application changes.
- Physical phone use, production Recovery execution, production signing, application or test
  changes, protected-file changes, publication, release, and platform merge remained prohibited.

## Exact external toolchain action

No compatible emulator or API-35 system image was initially installed. Build installed only the
following official Android SDK packages into the isolated data-drive directory
`/run/media/stevetherad/Data/ROMVERSE-Android-Emulator-Toolchain`:

- Android SDK Command-line Tools 23.0.0 at `cmdline-tools/latest`
- Android Emulator 37.1.11 (build 15917651) at `emulator`
- Android SDK Platform-Tools 37.0.1 at `platform-tools`
- Google APIs Intel x86-64 Android 35 system image revision 9 at
  `system-images/android-35/google_apis/x86_64`

The isolated directory occupies approximately 5.1 GiB. No system-wide package or application
dependency was installed or changed.

An isolated AVD named `romverse_api35_clean` was created with the Pixel 7 hardware profile, API 35,
Google APIs, x86-64 ABI, no Play Store, and its AVD data under the same isolated directory.

## Target-isolation evidence

- Before either launch attempt, `adb devices -l` reported no connected target.
- Intended emulator port/serial: port 5556 / `emulator-5556`.
- Neither launch reached an ADB-visible target. Post-failure `adb devices -l` also reported no
  target.
- Therefore no serial was admitted and no ADB command was directed at an Android target.
- No physical, simultaneous, unauthorized, ambiguous, or changing target was observed.

## Preserved launch failure

Two clean, snapshot-disabled, wiped-data, headless launch attempts failed before Android boot and
before ADB target admission:

1. Software SwiftShader path:
   `-port 5556 -no-window -no-audio -no-boot-anim -no-snapshot -wipe-data
   -gpu swiftshader_indirect -no-metrics`
   - Process: PID 178629
   - Outcome: `qemu-system-x86_64-headless` / `RenderThread` terminated with signal 11 (`SIGSEGV`)
   - System coredump recorded at 21:04:34 AEST; retained size 351.3 MiB
2. GPU-off/lavapipe fallback path:
   `-port 5556 -no-window -no-audio -no-boot-anim -no-snapshot -wipe-data
   -gpu off -no-metrics`
   - Process: PID 179962
   - Outcome: `qemu-system-x86_64-headless` / `RenderThread` terminated with signal 11 (`SIGSEGV`)
   - System coredump recorded at 21:05:37 AEST; retained size 353.2 MiB

For both processes, the Fedora audit journal records SELinux AVC denials for `{ execheap }` against
the emulator `RenderThread` immediately before the abnormal termination. This strongly indicates a
host emulator/SELinux execution-policy incompatibility, but is not claimed as a conclusive root
cause. No ROMVERSE process or APK had started.

The system-retained coredumps remain available through `coredumpctl` for independent review. Build
did not delete or alter them.

## Approved artifact revalidation

The exact approved artifacts remained present and were rehashed after the launch failures:

- Debug application APK:
  `companion/app/build/outputs/apk/debug/app-debug.apk`
  - SHA-256: `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`
- Debug instrumentation APK:
  `companion/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk`
  - SHA-256: `ec6776528384b26c29b748299f80285474cc64ed40fe2b2519efa6b4040a86b5`

Because no emulator target was admitted, the immediate-pre-install boundary was never reached.
Neither APK was installed or executed.

## Classification

- Implemented: no ROMVERSE implementation change.
- Simulated/Tested: genuine Fedora host emulator installation, isolated AVD creation, two bounded
  clean-start attempts, ADB target isolation, APK hash revalidation, and failure evidence capture.
- Hardware Verified: no. No physical Android device was connected or operated.
- Emulator Runtime Verified: no. Android did not boot and ROMVERSE did not launch.
- Released: no.

## Tests and runtime evidence

- Instrumentation results: **0 run / 0 pass / 0 fail / 0 skip**. This is not a passing result; the
  runner never started.
- Application launch: not reached.
- Guided shell visual smoke: not reached.
- Branding/navigation/privacy-curtain/Guided-Expert continuity runtime checks: not reached.
- No static or host-side tests were substituted for the missing Android runtime evidence.
- The previously approved artifact compilation and static verification remain valid but are not
  counted again in this checkpoint.

## Blocker

Android Emulator 37.1.11 crashes in its headless rendering process on this Fedora host before an
ADB target appears. Both SwiftShader and GPU-off/lavapipe paths encounter the same RenderThread
`SIGSEGV`, with SELinux `{ execheap }` denials recorded immediately beforehand.

Per the Product Assurance failure-stop requirement, Build made no further launch attempt and did
not alter Companion source, tests, manifest, resources, or Gradle configuration. Product Assurance
must review whether a narrowly controlled host-policy-compatible emulator invocation/environment,
an alternative official emulator revision, or another isolated runtime host is the approved next
step.

## Guided friction and dead ends

- No ROMVERSE Guided or Expert surface ran, so no new application dead end was observed or fixed.
- The runtime gate is externally blocked before app startup; it must not be presented as a ROMVERSE
  test failure or success.
- No user-facing route, warning, confirmation, state, or behavior changed.

## Guardian, Recovery, and safety implications

- Guardian remains the sole execution gate.
- Companion grants no flash, wipe, root, unlock, relock, approval, or arbitrary-command authority.
- Exact-device evidence, UNKNOWN-on-uncertainty, no blind retry, durable evidence, and independent
  verification remain unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override.
- No Recovery adapter, production trust identity, or device-changing action was reachable.

## Platform status

- Fedora Desktop: runnable development build and inert Guided Recovery journey remain Product
  Assurance verified.
- Companion Fedora artifact assembly: Product Assurance verified.
- Companion Android emulator runtime: blocked before Android boot by the recorded emulator crash.
- Physical Android hardware: not used and not claimed.
- Windows: remains on its separate track; no platform merge or duplicate work occurred.

## Feature-freeze and version-gate impact

- 5 September 2026 pre-v1.0 feature freeze: preserved. No ROMVERSE source, test, dependency,
  behavior, feature, format, authority, or brand change occurred.
- v0.2 Golden Foundation: remains **CLOSED**.
- Companion emulator runtime verification: not satisfied.
- Physical-device, production signing, production Recovery, publication, and release gates:
  unchanged and outstanding.

## Next proposed Build task

Stop for Product Assurance review of this exact host-runtime blocker. Do not change Companion
source or tests, weaken or skip instrumentation, alter host security policy, install or execute an
APK elsewhere, use a phone, or attempt additional emulator variants without a new explicit verdict.

## External actions

- Official isolated Android SDK packages downloaded: yes, exactly those listed above.
- Isolated AVD created: yes.
- System-wide installation or package change: none.
- Physical phone connection/operation: none.
- Admitted ADB target: none.
- Target-directed ADB command: none.
- APK installation/execution: none.
- Instrumentation runner execution: none.
- Production signing or Recovery execution: none.
- Companion source/test/manifest/configuration/resource/asset change: none.
- Protected Companion file change: none.
- Windows launcher change: none.
- Website change: none.
- Publication/release: none.
- Remote action: normal push of only this `docs/sync/BUILD-STATUS.md` handoff on
  `linux/stage1-desktop-readiness`; no force-push and no unrelated branch push.

## Product Assurance Review Requested

- Review the two pre-ADB RenderThread crashes, Fedora SELinux `{ execheap }` evidence, and retained
  coredumps.
- Decide the narrow approved remediation path for obtaining a disposable API-35 emulator runtime
  without weakening host security or changing ROMVERSE application code.
- Confirm this is an external runtime blocker and that no Companion runtime/test claim may be made.
