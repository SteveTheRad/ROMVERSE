# ROMVERSE Companion Instrumentation APK Readiness

## Scope

This checkpoint compiles the committed Companion `androidTest` sources and assembles a local debug
application APK plus a local debug instrumentation APK. It is an artifact-readiness checkpoint only:
neither APK was installed or executed, no emulator or physical phone was used, and no ADB command
was run.

Built source baseline: `5057d62543de32cf6a3058f77a48d54136d00b16` on
`linux/stage1-desktop-readiness`.

## Pinned offline toolchain

- Fedora Linux 44 x86-64 host
- Eclipse Temurin Java 17.0.20.1+1
- Gradle 8.11.1
- Android Gradle Plugin 8.7.3
- Kotlin plugin 2.0.21
- Android SDK platform 35
- Android SDK build tools 35.0.0
- Gradle dependency mode: offline

## Reproducible assembly

From the repository root, with `JAVA_HOME`, `ANDROID_HOME`, and `ANDROID_SDK_ROOT` pointing to the
pinned local toolchain:

```text
gradle --no-daemon --offline --console=plain -p companion \
  clean compileDebugAndroidTestKotlin assembleDebug assembleDebugAndroidTest
```

Result: **BUILD SUCCESSFUL** in 16 seconds; **65/65 actionable tasks executed**. This includes the
successful `compileDebugAndroidTestKotlin`, `compileDebugAndroidTestJavaWithJavac`,
`packageDebugAndroidTest`, and `assembleDebugAndroidTest` boundaries. The installed SDK emitted its
existing metadata-parser compatibility warning; it did not prevent compilation or packaging and no
download was attempted.

## Debug application APK

- Path: `companion/app/build/outputs/apk/debug/app-debug.apk`
- Application ID: `com.radforge.romverse.companion`
- Label: `ROMVERSE Companion`
- Version name/code: `0.2.0-alpha.5` / `8`
- Minimum / target / compile SDK: `26` / `35` / `35`
- Size: 9,060,239 bytes
- ZIP entries: 874
- SHA-256: `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`
- Manifest classification: debuggable
- ZIP integrity: passed with no compressed-data error

The path, identity, version, SDK bounds, size, entry count, and digest are unchanged from the
Product-Assurance-approved Companion debug APK readiness checkpoint.

## Debug instrumentation APK

- Path: `companion/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk`
- Instrumentation package: `com.radforge.romverse.companion.test`
- Target package: `com.radforge.romverse.companion`
- Runner: `androidx.test.runner.AndroidJUnitRunner`
- Variant: `debugAndroidTest`
- Minimum / target / compile SDK: `26` / `35` / `35`
- Manifest classification: debuggable
- Size: 383,843 bytes
- ZIP entries: 9
- SHA-256: `ec6776528384b26c29b748299f80285474cc64ed40fe2b2519efa6b4040a86b5`
- ZIP integrity: passed with no compressed-data error

## Signing evidence

Both APKs verify with the same local Android Debug signer:

- Signers: 1
- Certificate DN: `C=US, O=Android, CN=Android Debug`
- Certificate SHA-256:
  `b1e1bd6e1c199d6bc1649998546a20559e3b0f979cb401ef487b0cde7f993cb1`
- Key: RSA 2048
- APK Signature Scheme v1: false
- APK Signature Scheme v2: true
- APK Signature Schemes v3 / v3.1 / v4: false
- SourceStamp: absent

This is development signing only. No production signing identity or key was used.

## Included committed instrumentation tests

DEX inspection confirms that the instrumentation APK includes all three committed test classes:

- `CompanionUpgradeContinuityInstrumentedTest` — 1 committed test method
- `LinkSessionVaultInstrumentedTest` — 3 committed test methods
- `MainActivityInstrumentedTest` — 8 committed test methods

Total compiled inventory: 3 instrumentation classes and 12 committed test methods. They were
compiled and packaged but not executed; this checkpoint makes no Android-runtime test claim.

## Brand-lock evidence

The rebuilt application APK contains the committed approved brand assets byte-for-byte:

- ROMVERSE logo source and packaged-member SHA-256:
  `ab9286ce69e77abd82fe88105df70680186a4eb992289580c23f5d362c132a18`
- RadForge Labs logo source and packaged-member SHA-256:
  `d82ff146aab1f18474005d1a2d9ce0c3944467ae30ff7cb4fb3284387daa95cb`

Neither logo was edited, regenerated, replaced, recoloured, cropped, distorted, or substituted.

## Boundary and limitations

- No Companion source, test, manifest, Gradle configuration, resource, behavior, or branding was
  changed.
- No protected Companion working-tree file was edited, staged, discarded, built from, or committed.
- No APK was installed or executed.
- No emulator, physical phone, USB connection, Android runtime, or ADB command was used.
- No dependency was downloaded and no tool was installed.
- No production signing, publication, distribution, or release occurred.
- Runtime execution of the 12 instrumentation tests remains a separately authorized future gate.
- Guardian-only authority, exact-device evidence, UNKNOWN/no-blind-retry behavior, independent
  verification, and the permanent bootloader lock/relock prohibition are unchanged.
