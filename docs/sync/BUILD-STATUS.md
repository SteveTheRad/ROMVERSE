# ROMVERSE Build Status

## Authoritative checkpoint

- Evidence commit: `507872cb3bd8cebab8c210af7de5fb2ef00e14f5`
- Title: `Record Companion instrumentation APK readiness`
- Built source baseline and Product Assurance authorization:
  `5057d62543de32cf6a3058f77a48d54136d00b16`
- Branch: `linux/stage1-desktop-readiness`
- Stage: Stage 1 — v0.2 Golden Foundation tangible Companion artifact assembly
- Milestone: local Companion debug application plus Android instrumentation APK readiness bundle
- Build status: both artifacts assembled and verified; stop for Product Assurance review
- Working-tree target state: clean after this handoff commit. The separate original checkout's
  three protected Companion changes and pre-existing Windows launcher drafts were not edited,
  staged, discarded, built from, or committed.

## Product Assurance authorization

- Product Assurance verdict `5057d62` approved the preceding Companion debug APK checkpoint and
  authorized only the final pre-runtime instrumentation artifact gate.
- Authorization covered offline compilation of existing `androidTest` sources, assembly and
  inspection of the debug app and instrumentation APKs, and documentation of exact evidence.
- APK installation/execution, emulator or phone use, ADB, dependency download, behavior or branding
  changes, production signing, platform merge, publication, and release remained prohibited and did
  not occur.

## Exact changes

- Added `docs/COMPANION-INSTRUMENTATION-APK-READINESS.md` with the pinned build command, exact app
  and instrumentation package metadata, artifact hashes, archive integrity, signer evidence,
  compiled test inventory, brand-lock evidence, and runtime limitations.
- Updated this repository handoff with the completed checkpoint evidence.
- No Companion source, test, manifest, Gradle configuration, resource, logo, application behavior,
  Desktop source, Windows launcher, Device Pack, schema, protocol, or release behavior changed.
- The committed baseline assembled successfully; no build-readiness correction was required.

## Companion APK readiness bundle

### Debug application APK

- Path: `companion/app/build/outputs/apk/debug/app-debug.apk`
- Application ID / label: `com.radforge.romverse.companion` / `ROMVERSE Companion`
- Version name/code: `0.2.0-alpha.5` / `8`
- Minimum / target / compile SDK: `26` / `35` / `35`
- Size / ZIP entries: 9,060,239 bytes / 874
- SHA-256: `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`
- Manifest classification: debuggable
- Identity and digest: unchanged from the approved preceding checkpoint

### Debug instrumentation APK

- Path: `companion/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk`
- Instrumentation package: `com.radforge.romverse.companion.test`
- Target package: `com.radforge.romverse.companion`
- Runner: `androidx.test.runner.AndroidJUnitRunner`
- Variant: `debugAndroidTest`
- Minimum / target / compile SDK: `26` / `35` / `35`
- Size / ZIP entries: 383,843 bytes / 9
- SHA-256: `ec6776528384b26c29b748299f80285474cc64ed40fe2b2519efa6b4040a86b5`
- Manifest classification: debuggable

Both APK archives passed ZIP integrity validation without a compressed-data error.

## Signing evidence

Both APKs verify with the same local development signer:

- Signers: 1
- Certificate DN: `C=US, O=Android, CN=Android Debug`
- Certificate SHA-256:
  `b1e1bd6e1c199d6bc1649998546a20559e3b0f979cb401ef487b0cde7f993cb1`
- Key: RSA 2048
- APK Signature Scheme v2: verified
- APK Signature Schemes v1 / v3 / v3.1 / v4: not present
- SourceStamp: absent
- Production signing: not used

## Included instrumentation inventory

DEX inspection verified all committed instrumentation classes in the instrumentation APK:

- `CompanionUpgradeContinuityInstrumentedTest` — 1 committed test method
- `LinkSessionVaultInstrumentedTest` — 3 committed test methods
- `MainActivityInstrumentedTest` — 8 committed test methods

Total: 3 classes and 12 committed instrumentation test methods compiled and packaged. They were not
executed, so they are not reported as runtime test passes.

## Brand-lock evidence

- Approved ROMVERSE logo source and packaged-member SHA-256:
  `ab9286ce69e77abd82fe88105df70680186a4eb992289580c23f5d362c132a18`
- Approved RadForge Labs logo source and packaged-member SHA-256:
  `d82ff146aab1f18474005d1a2d9ce0c3944467ae30ff7cb4fb3284387daa95cb`
- Both packaged members are byte-identical to their committed approved sources. Neither logo was
  edited, regenerated, replaced, recoloured, cropped, distorted, or substituted.

## Classification

- Implemented: no new application behavior. The committed instrumentation suite compiled and both
  debug APK artifacts assembled without correction; only evidence documentation was added.
- Simulated/Tested: compilation, packaging, metadata, archive, signature, DEX-inventory, and
  brand-byte verification on the genuine Fedora host. The instrumentation tests were not run.
- Hardware Verified: no. Neither APK ran on an emulator or physical Android device.
- Released: no. Both artifacts are local Android-debug-signed development outputs.

## Verification evidence

- Pinned host: genuine Fedora Linux 44 x86-64.
- Pinned Java / Gradle: Eclipse Temurin 17.0.20.1+1 / Gradle 8.11.1.
- Android Gradle Plugin / Kotlin plugin: 8.7.3 / 2.0.21.
- Android SDK platform / build tools: 35 / 35.0.0.
- Dependency mode: offline.
- Clean Gradle gate:
  `clean compileDebugAndroidTestKotlin assembleDebug assembleDebugAndroidTest` —
  **BUILD SUCCESSFUL** in 16 seconds; **65/65 actionable tasks executed**.
- Successful relevant boundaries include `compileDebugAndroidTestKotlin`,
  `compileDebugAndroidTestJavaWithJavac`, `packageDebugAndroidTest`, and
  `assembleDebugAndroidTest`.
- Application and instrumentation package/SDK metadata were read from their built manifests.
- Both APK signatures were verified with pinned build-tools 35.0.0 `apksigner`.
- All three committed test classes were found in the packaged DEX inventory.
- Application identity and hash remained exact relative to the preceding approved checkpoint.
- Both source-to-APK approved logo hash comparisons passed.
- Git whitespace validation passed.
- The SDK emitted its existing metadata-parser version warning; compilation and packaging remained
  successful and no dependency was downloaded.

## Blockers and remaining limitations

- The 12 packaged instrumentation tests have not run. Activity lifecycle, rendering, Android
  storage, navigation continuity, accessibility, emulator, USB, manufacturer-specific, and physical
  phone behavior remain unverified by this checkpoint.
- Debug signing is not production signing. These debuggable artifacts must not be promoted or
  represented as public release packages.
- The original checkout's protected Companion changes are deliberately not part of these artifacts.
- Production Recovery adapter enrollment and controlled physical Android Recovery remain separate
  mandatory release blockers.

## Guided friction and dead ends

- This artifact checkpoint changes no Guided or Expert UI, route, warning, confirmation, state, or
  execution surface and introduces no new dead end.
- The existing committed Activity and Link/Lifeline instrumentation coverage is present in the APK,
  but its behavior cannot be inferred from compilation. Runtime verification requires a separately
  authorized emulator or hardware checkpoint.

## Guardian, Recovery, and safety implications

- Guardian remains the sole execution gate.
- Companion grants no flash, wipe, root, unlock, relock, approval, or arbitrary-command authority.
- Exact-device evidence, UNKNOWN-on-uncertainty, no blind retry, source-bound evidence, and
  independent verification remain unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override.
- Debug compilation, packaging, and signing grant no runtime, production execution, or release
  authority.

## Platform status

- Fedora Desktop: runnable development build and inert Guided Recovery journey are Product
  Assurance verified.
- Fedora Companion build host: genuine clean offline application and instrumentation APK assembly
  plus static artifact verification complete.
- Android runtime/emulator/physical phone: not used and not claimed.
- Windows: remains on its separate authorized track; no platform merge or duplicate work occurred.

## Feature-freeze and version-gate impact

- 5 September 2026 pre-v1.0 feature freeze: compliant. This is assembly of existing committed tests
  and evidence documentation only, with no feature, behavior, dependency, format, or authority
  change.
- v0.2 Golden Foundation: remains **CLOSED**.
- Companion debug application APK readiness: Product Assurance verified.
- Companion instrumentation APK artifact readiness: complete for Product Assurance review.
- Android runtime/emulator/physical verification: outstanding and not authorized by this checkpoint.
- Public release gate: unchanged; production signing, runtime instrumentation, representative
  hardware, security review, and release approval remain outstanding.

## Next proposed Build task

Stop for Product Assurance review of this exact Companion instrumentation artifact checkpoint. Do
not install or execute either APK, start an emulator, use a phone or ADB, change Companion behavior,
alter protected files, merge a platform branch, publish, or release without a new explicit verdict.

## External actions

- Physical phone connection/operation: none.
- Emulator start/operation: none.
- ADB command: none.
- APK installation/execution: none.
- System-wide package/tool installation: none.
- Dependency download: none; Gradle ran offline.
- Production signing: none.
- Production Recovery execution: none.
- Publication/release: none.
- Website change: none.
- Companion source/test/manifest/configuration/resource/asset change: none.
- Windows launcher change: none.
- Remote action: normal push of only `linux/stage1-desktop-readiness` for checkpoint review; no
  force-push and no unrelated branch push.

## Product Assurance Review Requested

- Confirm the exact application and instrumentation APK paths, hashes, metadata, signatures,
  packaged-test inventory, ZIP integrity, and brand-lock evidence satisfy the final pre-runtime
  artifact gate.
- Confirm that the 12 instrumentation test methods are correctly classified as compiled/packaged,
  not runtime passed.
- Confirm no Android runtime, emulator, phone, production signing, or release claim is implied and
  identify the next bounded master-goal task, if any.
