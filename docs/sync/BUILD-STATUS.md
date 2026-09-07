# ROMVERSE Build Status

## Authoritative checkpoint

- Source and Product Assurance authorization commit:
  `74da8577b09e5cccd33c2128f56e41b12189311c`
- Branch: `linux/stage1-desktop-readiness`
- Stage: Stage 1 — v0.2 Golden Foundation Companion Android emulator runtime verification
- Milestone result: **COMPLETE — API-35 EMULATOR RUNTIME VERIFIED**
- Scope result: exact approved APKs installed and exercised only on one isolated emulator; no
  ROMVERSE source, test, build configuration, behavior, or branding changed
- Working-tree target state: clean after this handoff commit. The separate original checkout's
  three protected Companion changes and pre-existing Windows launcher drafts were not edited,
  staged, discarded, built from, or committed.

## Product Assurance authorization

- Product Assurance verdict `74da857` validated the prior external headless-renderer blocker and
  authorized exactly one visible-window `-gpu host` launch of the existing clean API-35 AVD.
- A successful boot was authorized to continue directly through exact-target admission, approved
  APK installation, the complete existing instrumentation suite, app launch, and bounded visual
  smoke.
- SELinux weakening, host-policy changes, another renderer/revision, a physical phone, Recovery
  execution, production signing, app/test changes, protected-file changes, publication, release,
  and platform merge remained prohibited and did not occur.

## Exact emulator launch and isolation

- Isolated SDK root:
  `/run/media/stevetherad/Data/ROMVERSE-Android-Emulator-Toolchain`
- Command-line tools / emulator / platform-tools: 23.0.0 / 37.1.11 / 37.0.1
- System image: Google APIs Android 35 x86-64 revision 9
- AVD: `romverse_api35_clean`, Pixel 7 profile, no Play Store
- Launch command:
  `emulator @romverse_api35_clean -port 5556 -no-audio -no-snapshot -wipe-data -gpu host -no-metrics`
- Host renderer: AMD Radeon RX 9070 XT, RADV/Mesa 26.1.8
- Clean state: wiped data; snapshot loading and saving disabled
- SELinux: host remained Enforcing; guest reported Enforcing
- Android boot: completed in 17,124 ms
- Exact admitted target: `emulator-5556`; it was the sole ADB target for the entire authorized
  runtime session
- Guest identity: Android 15 / API 35 / x86-64; model `sdk_gphone64_x86_64`
- Build fingerprint:
  `google/sdk_gphone64_x86_64/emu64xa:15/AE3A.240806.043/12960925:userdebug/dev-keys`
- `ro.kernel.qemu=1` and `sys.boot_completed=1` were recorded before shutdown.

Before launch, `adb devices -l` reported no targets. Every consequential target action required the
sole exact `emulator-5556:device` state. After the controlled emulator shutdown, ADB again reported
no target. No physical, simultaneous, ambiguous, unauthorized, or changing target appeared.

## Exact APK admission and installation

Both approved artifacts were rehashed immediately before installation:

- Debug application APK:
  `companion/app/build/outputs/apk/debug/app-debug.apk`
  - SHA-256: `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`
  - Install result: `Success`
- Debug instrumentation APK:
  `companion/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk`
  - SHA-256: `ec6776528384b26c29b748299f80285474cc64ed40fe2b2519efa6b4040a86b5`
  - Install result: `Success`

The installed application reported package `com.radforge.romverse.companion`, version name
`0.2.0-alpha.5`, version code 8, minimum SDK 26, and target SDK 35. The only other installed
ROMVERSE package was the approved `com.radforge.romverse.companion.test` instrumentation package.

## Instrumentation runtime result

Exact runner:
`com.radforge.romverse.companion.test/androidx.test.runner.AndroidJUnitRunner`

- Complete inventory: 12 tests
- Passed: 11
- Failed: 0
- Assumption-skipped: 1
- Runner duration: 7.496 seconds
- Final runner result: `OK (12 tests)` / `INSTRUMENTATION_CODE: -1`
- Full runner log:
  `/run/media/stevetherad/Data/ROMVERSE-Android-Emulator-Toolchain/romverse-instrumentation-runner.log`
- Log size / lines: 11,760 bytes / 217 lines
- Log SHA-256: `fffa36efb5fa3d4a456de165f0fb4be37c3bdd120e9400dc7d5b006be383d51f`

The assumption-skipped test was the existing
`tlsPinnedLinkCarriesLiveConsoleAndReconnectsAfterRecreation` contract. It requires the contained
Desktop Link fixture and explicitly self-skipped with `AssumptionViolatedException`; it was not
weakened, rewritten, hidden, or counted as a pass. All other committed instrumentation tests passed.

## App launch and bounded visible smoke

- `MainActivity` cold launch: successful in 359 ms.
- Installed application process was alive at evidence capture; the activity remained the focused,
  top-resumed application.
- AndroidRuntime error-only log for the session was empty: 0 bytes, SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- The initial UI-tree dump could not obtain an idle state because the app's existing visual shell
  remains animated. This did not crash or stall the app and was not used as pass authority;
  screenshots, focus/process evidence, the exact instrumentation suite, and `FLAG_SECURE` evidence
  were used instead. No app change was made for the capture tool.

Readable runtime evidence was preserved outside the repository under
`/run/media/stevetherad/Data/ROMVERSE-Android-Emulator-Toolchain/evidence`:

- Guided Command Deck shell and approved branding:
  `companion-guided-shell.png`, SHA-256
  `d630356ddbcc3f87c321eb209b7cac047e8ae07016593b998d7bb6a2b871e22b`
- Navigation drawer with existing destinations:
  `companion-navigation.png`, SHA-256
  `6f33647d3355b2e73d520865c221e55a4c068d3a29300f6348fdaf07bdcf6453`
- Guided Settings state:
  `companion-settings-guided.png`, SHA-256
  `97e3f4e3fe45a1817cebdae59e1ec3bc2f8a7d6001e3555c45b0a5bec8549117`
- Expert Settings selection and permanent relock warning:
  `companion-settings-expert.png`, SHA-256
  `0f577b6331ac77f31271d1d6c953d29322e45390ea075fca7d77327736c40143`
- Persisted Expert mode on Vitalis with full technical evidence open:
  `companion-vitalis-expert.png`, SHA-256
  `ea1dc1604ed29f95ac7a0feb5d98c92157b473cf40b6732336d374176bd968d9`
- Privacy Curtain secure-capture result:
  `companion-privacy-curtain-secure-capture.png`, SHA-256
  `f55b1c467f1c191df314d51e05b3b0ff405d741a47f2f37f2d77a8031a44a657`

The Privacy Curtain was enabled through the existing UI, the app was backgrounded and brought back,
and Android reported `SECURE` on the focused Companion window. Its capture intentionally contains
only black protected app content with system bars visible, proving the existing screenshot-blocking
boundary rather than a rendering failure.

## Classification

- Implemented: no new ROMVERSE behavior; this checkpoint changes only the repository evidence
  handoff.
- Simulated/Tested: genuine API-35 Android emulator runtime, exact debug APK installation, 12-test
  instrumentation run, app launch, navigation, branding, Guided/Expert continuity, and privacy
  protection.
- Hardware Verified: no physical Android hardware was used. Host-GPU emulator execution is runtime
  evidence, not physical-phone evidence.
- Released: no. The artifacts remain local development-debug packages.

## Guided friction and remaining limitations

- No Guided dead end or circular flow appeared in the bounded emulator smoke.
- The existing shell, navigation, Guided/Expert continuity, technical-evidence behavior, privacy
  curtain, and safety copy behaved as designed.
- The single fixture-dependent Desktop Link integration test remains assumption-skipped in this
  standalone emulator session; genuine paired Desktop/Companion integration remains a separate
  future gate.
- Emulator rendering required the approved visible host-GPU path on this Fedora host. The two prior
  headless software-rendering failures remain valid external-tool evidence and were not erased.
- Physical-device, manufacturer-specific, USB, production-trust, and production-signing behavior
  remain unverified and are not inferred from emulator results.

## Guardian, Recovery, and safety implications

- Guardian remains the sole execution gate.
- Companion grants no flash, wipe, root, unlock, relock, approval, or arbitrary-command authority.
- Exact-device evidence, UNKNOWN-on-uncertainty, no blind retry, durable evidence, consent
  separation, and independent verification remain unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override; both Guided and
  Expert runtime screens visibly retain that boundary.
- No ROMVERSE Desktop Link, Recovery adapter, production trust identity, physical-device channel,
  or mutating Recovery action was configured or reachable in the isolated session.

## Platform status

- Fedora Desktop: runnable development build and inert Guided Recovery journey remain Product
  Assurance verified.
- Companion Fedora artifact assembly: Product Assurance verified.
- Companion Android emulator runtime: genuinely verified on one clean API-35 x86-64 emulator.
- Physical Android hardware: not used and not claimed.
- Windows: remains on its separate track; no platform merge or duplicate work occurred.

## Feature-freeze and version-gate impact

- 5 September 2026 pre-v1.0 feature freeze: preserved. No application source, tests, dependency,
  behavior, feature, format, authority, or brand asset changed.
- v0.2 Golden Foundation: remains **CLOSED** pending remaining release gates.
- Companion emulator runtime verification: complete for Product Assurance review.
- Paired Desktop Link, representative physical hardware, production signing, production Recovery,
  publication, and release gates remain outstanding and were not authorized here.

## Next proposed Build task

Stop for Product Assurance review of this exact emulator runtime checkpoint. Do not start a paired
Link fixture, physical-device run, source fix, production signing, Recovery execution, platform
merge, publication, or release without a new explicit verdict.

## External actions

- One visible-window host-GPU emulator attempt: successful and complete.
- Physical phone connection/operation: none.
- ADB target: only exact disposable `emulator-5556` during the bounded session.
- APK installation: exact approved debug app and instrumentation APKs on that emulator only.
- Instrumentation execution: exact existing 12-test runner suite only.
- Emulator shutdown: controlled `emu kill`; post-shutdown ADB inventory empty.
- SELinux or host-policy change: none; enforcing retained.
- System-wide package/tool installation: none.
- ROMVERSE source/test/config/resource/asset change: none.
- Protected Companion file or Windows launcher change: none.
- Production signing or Recovery execution: none.
- Website change: none.
- Publication/release: none.
- Remote action: normal push of only this `docs/sync/BUILD-STATUS.md` handoff on
  `linux/stage1-desktop-readiness`; no force-push and no unrelated branch push.

## Product Assurance Review Requested

- Confirm the exact-target and APK-hash admission, 11-pass/0-fail/1-assumption-skip result, runner
  log, app launch, visual evidence, and privacy `FLAG_SECURE` behavior satisfy the approved emulator
  runtime gate.
- Confirm the Desktop Link fixture skip remains a visible separate integration limitation rather
  than an instrumentation failure or pass.
- Confirm no physical-hardware, production-trust, Recovery, signing, release, or publication claim
  is implied and identify the next bounded master-goal task, if any.
