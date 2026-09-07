# ROMVERSE Build Status

## Authoritative checkpoint

- Evidence commit: `67ff3a29a3f06b84c3b43989b61cd37e9dcff587`
- Title: `Record Companion debug APK readiness`
- Built source baseline: `550a27563aeca4b52a1f519291eefe84e481a431`
- Branch: `linux/stage1-desktop-readiness`
- Stage: Stage 1 — v0.2 Golden Foundation tangible Companion artifact assembly
- Milestone: clean development-signed Companion debug APK readiness
- Build status: artifact assembled and verified; stop for Product Assurance review
- Working tree target state: clean after this handoff commit. The separate original checkout's
  three protected Companion modifications and pre-existing Windows launcher drafts were not edited,
  staged, discarded, built, or committed.

## Product Assurance authorization

- Fedora runnable checkpoint `b76843c` / implementation `1300dde` was approved by verdict
  `550a275`.
- The verdict authorized only a clean Companion debug APK readiness checkpoint from the committed
  baseline, using pinned local tools and non-hardware tests.
- No behavior, branding, version, production signing, installation, emulator, phone, publication,
  release, platform merge, or production execution change was authorized or performed.

## Exact changes

- Added `docs/COMPANION-DEBUG-APK-READINESS.md` with the pinned toolchain, reproducible clean build
  command, exact package/version/signature/artifact evidence, non-overlapping test results, and
  remaining hardware/release boundaries.
- Updated this repository handoff with the completed checkpoint evidence.
- No Companion source, test, manifest, Gradle configuration, resource, logo, Desktop application
  source, Windows launcher, Device Pack, protocol, schema, or release behavior changed.
- No build-readiness correction was required.

## Runnable Companion artifact

- Artifact: `companion/app/build/outputs/apk/debug/app-debug.apk`
- Application ID: `com.radforge.romverse.companion`
- Label: `ROMVERSE Companion`
- Version name/code: `0.2.0-alpha.5` / `8`
- Minimum / target / compile SDK: `26` / `35` / `35`
- Size: 9,060,239 bytes
- APK entries: 874
- SHA-256: `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`
- Manifest classification: `android:debuggable=true`
- Signing classification: one Android Debug signer, RSA 2048, APK Signature Scheme v2 verified
- Debug certificate SHA-256:
  `b1e1bd6e1c199d6bc1649998546a20559e3b0f979cb401ef487b0cde7f993cb1`
- Production signed: no
- Installed: no
- Released: no

## Brand-lock evidence

- Approved ROMVERSE logo source and APK member SHA-256:
  `ab9286ce69e77abd82fe88105df70680186a4eb992289580c23f5d362c132a18`
- Approved RadForge Labs logo source and APK member SHA-256:
  `d82ff146aab1f18474005d1a2d9ce0c3944467ae30ff7cb4fb3284387daa95cb`
- Each packaged member is byte-identical to its committed approved source. Neither logo was
  replaced, regenerated, redrawn, recoloured, cropped, distorted, or substituted.

## Classification

- Implemented: no new product behavior. The committed Companion baseline assembled without a
  correction; only reproducible readiness documentation and this handoff were added.
- Simulated/Tested: Companion domain behavior through JVM and Desktop-side non-hardware tests,
  including committed ROMVERSE Link and Lifeline state.
- Hardware Verified: no. No APK ran on Android, an emulator, or a physical phone.
- Released: no. This is a local Android-debug-signed development artifact.

## Verification evidence

- Pinned build host: genuine Fedora Linux 44 x86-64.
- Pinned Java: Eclipse Temurin 17.0.20.1+1.
- Pinned Gradle: 8.11.1.
- Android Gradle Plugin / Kotlin plugin: 8.7.3 / 2.0.21.
- Android SDK platform / build tools: 35 / 35.0.0.
- Dependency mode: offline.
- Clean Gradle gate:
  `clean testDebugUnitTest lintDebug assembleDebug` — **BUILD SUCCESSFUL** in 34 seconds;
  52 actionable tasks, 51 executed and 1 up-to-date.
- Companion JVM tests: **162/162 passed** across 30 suites.
- ROMVERSE Link/Lifeline JVM evidence: **29/29 passed** across
  `CompanionLinkReadinessTest`, `CompanionUsbPairingAssistTest`,
  `DesktopLinkSecurityTest`, `LifelinePlanTest`, and `LifelineSessionIntegrityTest`.
  These 29 are a subset of 162 and are not added to it.
- Desktop-side Companion/Link regression: **120/120 passed** across 11 Python suites. This is a
  distinct host-side suite and is reported separately rather than combined with JVM totals.
- Android lint: completed successfully with **0 fatal/error findings** and 331 existing warnings.
  The warnings are retained honestly: 297 `SetTextI18n`, 17 `DrawAllocation`, 5
  `ViewConstructor`, 3 `ApplySharedPref`, 2 each `IconLocation`,
  `MonochromeLauncherIcon`, `ObsoleteSdkInt`, and `UnusedResources`, and 1
  `CustomX509TrustManager`.
- APK ZIP integrity: passed with no compressed-data error.
- APK package identity and SDK/version metadata: independently read from the built manifest.
- APK signature: verified with pinned build-tools 35.0.0 `apksigner`; exactly one Android Debug
  signer and no SourceStamp.
- Approved logo bytes: compared between source and APK; exact SHA-256 matches.
- Git whitespace check: passed.

## Blockers and remaining limitations

- The APK has not run on Android. Activity instrumentation, Android lifecycle, rendering,
  accessibility, emulator, USB, manufacturer-specific, and physical hardware evidence remain
  unverified in this checkpoint.
- Debug signing is not production signing. The debug certificate and `debuggable=true` APK must
  never be promoted or represented as a public release.
- Android lint has 331 warnings, although no fatal/error finding and no build failure. They remain
  visible technical debt rather than being suppressed or reclassified.
- The Android SDK printed a metadata-version compatibility warning because installed SDK metadata is
  newer than this command-line parser understands. Compilation, lint, packaging, signature
  validation, and archive validation still completed successfully; no SDK download was attempted.
- The separate original checkout's protected Companion modifications are not part of this artifact.
  Their ownership must be resolved before any later feature checkpoint uses them.
- Production Recovery adapter enrollment and controlled physical Android Recovery remain separate
  release blockers.

## Guided friction and dead ends

- This artifact-only checkpoint changes no Guided or Expert UI behavior and introduces no new
  confirmation, route, gate, or dead end.
- Existing inert Link readiness, USB-assist decision state, Desktop trust classification, Lifeline
  plan progression, and Lifeline session-integrity behavior all passed their committed JVM tests.
- Hardware pairing, Activity navigation, and live Lifeline behavior are deliberately not inferred
  from JVM results; they require separately authorized Android runtime evidence.

## Guardian, Recovery, and safety implications

- Guardian remains the only execution gate.
- Companion state grants no flash, wipe, root, unlock, relock, or arbitrary command authority.
- Exact-device evidence, UNKNOWN/no-blind-retry behavior, independent verification, and
  source-bound Recovery evidence are unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override.
- Debug assembly and debug signing grant no production execution or release authority.

## Platform status

- Fedora Desktop: runnable development build and inert Guided Recovery journey are Product
  Assurance approved.
- Fedora Companion build host: genuine clean offline build, JVM/lint/package/signature/archive
  verification complete.
- Android runtime/emulator/physical phone: not used and not claimed.
- Windows: remains on its separate authorized branch; no platform merge or duplicate work occurred.

## Feature-freeze and version-gate impact

- 5 September 2026 pre-v1.0 feature freeze: compliant. This is artifact assembly and existing
  behavior verification, with no product feature or runtime change.
- v0.2 Golden Foundation: remains **CLOSED**.
- Companion debug APK readiness: completed for Product Assurance review.
- Public release gate: unchanged; production signing, Android runtime/instrumentation, representative
  physical hardware, and release review remain outstanding.

## Next proposed Build task

Stop for Product Assurance review of this exact Companion debug APK readiness checkpoint. Do not
install or distribute the APK, start a Companion feature slice, alter the protected Companion
files, merge a platform branch, or begin hardware testing without the next explicit authorization.

## External actions

- Physical phone connection/operation: none.
- Emulator connection/operation: none.
- ADB command: none.
- APK installation: none.
- System-wide package/tool installation: none.
- Dependency download: none; Gradle ran offline.
- Production signing: none.
- Production Recovery execution: none.
- Publication/release: none.
- Website change: none.
- Companion source/resource/asset change: none.
- Windows launcher change: none.
- Remote action: normal push of only `linux/stage1-desktop-readiness` for checkpoint review; no
  force-push and no unrelated branch push.

## Product Assurance Review Requested

- Confirm that the exact debug APK identity, signing classification, archive integrity, brand-lock
  evidence, JVM/lint/host-side results, and SHA-256 satisfy the bounded readiness milestone.
- Confirm that the 331 warning-only lint findings may remain visible technical debt for this
  artifact checkpoint rather than requiring an unapproved behavior/UI cleanup.
- Confirm that no Android runtime or hardware claim is implied and identify the next bounded
  master-goal task, if any, after this checkpoint.
