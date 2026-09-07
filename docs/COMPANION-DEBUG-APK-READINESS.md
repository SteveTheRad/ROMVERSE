# Companion debug APK readiness

## Checkpoint scope

This checkpoint assembles and verifies the committed ROMVERSE Companion baseline as a local,
development-signed debug APK. It changes no Companion behavior, source, version, branding, signing
policy, or release configuration. It does not install or run the APK on a phone or emulator.

## Pinned build environment

- Host: Fedora Linux 44, x86-64
- Java: Eclipse Temurin 17.0.20.1+1
- Gradle: 8.11.1
- Android Gradle Plugin: 8.7.3
- Kotlin Android plugin: 2.0.21
- Android SDK platform: 35
- Android SDK build tools: 35.0.0
- Dependency resolution: Gradle offline mode

The isolated Linux worktree uses the repository-managed tools stored alongside the recovered
repository. No system-wide tool or dependency installation is required.

## Reproduce the clean build

From the repository root:

```bash
TOOLCHAIN_ROOT=/run/media/stevetherad/Data/ROMVERSE-Recovered-2026-09-01/toolchains
JAVA_HOME="$TOOLCHAIN_ROOT/jdk-17" \
ANDROID_HOME="$TOOLCHAIN_ROOT/android-sdk" \
  "$TOOLCHAIN_ROOT/gradle-8.11.1/bin/gradle" \
  --no-daemon --offline --console=plain -p companion \
  clean testDebugUnitTest lintDebug assembleDebug
```

The output is `companion/app/build/outputs/apk/debug/app-debug.apk`.

## Verified artifact identity

- Application ID: `com.radforge.romverse.companion`
- Application label: `ROMVERSE Companion`
- Version name: `0.2.0-alpha.5`
- Version code: `8`
- Minimum SDK: `26`
- Target and compile SDK: `35`
- Artifact size: `9,060,239` bytes
- Artifact SHA-256: `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`
- APK ZIP entries: `874`
- Archive integrity: passed with no compressed-data error
- Manifest classification: `android:debuggable=true`
- Signature: one Android Debug signer; APK Signature Scheme v2 verified
- Debug certificate SHA-256:
  `b1e1bd6e1c199d6bc1649998546a20559e3b0f979cb401ef487b0cde7f993cb1`
- Production signing: not used
- Release status: not released

The approved production logo sources are unchanged, and the copies packaged in the APK are
byte-identical:

- ROMVERSE logo SHA-256:
  `ab9286ce69e77abd82fe88105df70680186a4eb992289580c23f5d362c132a18`
- RadForge Labs logo SHA-256:
  `d82ff146aab1f18474005d1a2d9ce0c3944467ae30ff7cb4fb3284387daa95cb`

## Verification results

- Gradle build: successful; 52 actionable tasks, 51 executed and 1 up-to-date.
- Companion JVM tests: **162/162 passed** across 30 suites.
- Existing ROMVERSE Link/Lifeline JVM coverage: **29/29 passed** across
  `CompanionLinkReadinessTest`, `CompanionUsbPairingAssistTest`, `DesktopLinkSecurityTest`,
  `LifelinePlanTest`, and `LifelineSessionIntegrityTest`. This is a subset of 162 and is not added
  to the total.
- Android lint: completed successfully with zero fatal/error findings. It reports 331 existing
  warnings, principally 297 `SetTextI18n` findings; this checkpoint does not conceal or reclassify
  them.
- Desktop-side Companion/Link regression: **120/120 passed** across pairing, security, telemetry,
  transport, transfer, USB assist, update-runner, visual-resource, brand-asset, Device Atlas parity,
  and Companion Center tests.

## Boundaries and remaining evidence

- This APK is a development artifact, not a public, production-signed, published, or released APK.
- No APK installation, Android runtime, Activity instrumentation, emulator, physical phone, USB
  operation, or hardware behavior was exercised.
- JVM tests prove deterministic local domain behavior; they do not prove Android lifecycle,
  manufacturer behavior, USB transport, or physical Companion Link operation.
- The existing Android instrumentation suites remain mandatory future evidence when an emulator or
  physical-hardware gate is separately authorized.
- Guardian authority, exact-device requirements, UNKNOWN/no-blind-retry semantics, and permanent
  bootloader no-relock policy are unchanged.
