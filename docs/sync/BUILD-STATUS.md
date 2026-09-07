# ROMVERSE Build Status

## Authoritative checkpoint

- Product Assurance authorization/base: `292cd09131c3b788c88a2ef66041e358c8615494`.
- Evidence checkpoint: `ac22e2d57226069a8959ef93b43067fa3d539e57`.
- Final handoff checkpoint: the follow-up commit containing this resolved status document on
  `linux/stage1-desktop-readiness`.
- Stage: Stage 1 — v0.2 Golden Foundation, Companion first-run/offline acceptance.
- Working tree at checkpoint: clean apart from ignored local Gradle/emulator output.

## Exact scope and outcome

- Attempted the approved fresh no-phone journey with the existing repository-managed API 35
  `romverse_api35_clean` emulator and the existing debug APK baseline.
- The emulator initialized its virtual hardware but exited before registering
  `emulator-5556` with ADB. No APK was installed, launched, rebuilt or changed.
- Per the approved fallback, exercised the existing production Companion presentation/state
  policies through focused JVM tests and inspected their `MainActivity` wiring read-only.
- Home is the safe default route. An unpaired/no-desktop state remains explicit and actionable:
  it reports discovery/network/USB-only state rather than secure pairing or readiness.
- Existing knowledge and device evidence reports explicitly carry `Execution authority: NONE`.
- Existing source shows `Companion 0.2.0-alpha.5 • Internal Alpha` in About and identifies the
  app as ROMVERSE Companion on Home.

## First concrete defect and protected overlap

- A completely new user does not see the `Internal Alpha` classification or a concise
  no-execution-authority disclosure on first entry to Home. The alpha classification exists only
  in About; authority explanations appear later in Link/knowledge/backup surfaces.
- The minimum product correction belongs in the initial Home/first-run presentation owned by
  `companion/app/src/main/kotlin/com/radforge/romverse/companion/MainActivity.kt`.
- That exact file has protected, unrelated uncommitted user work in the original authoritative
  checkout, alongside protected `CompanionNavigation.kt` and `CompanionNavigationTest.kt` changes.
- Those files were inspected read-only and were not edited, staged, discarded or committed.
  Applying a parallel UI correction now would create overlapping Companion histories, so this is
  a truthful blocker handoff rather than a competing implementation.
- Nearest non-overlapping follow-up: after the protected Companion work is reconciled into one
  authoritative branch, add one concise first-entry internal-development/no-authority disclosure
  to Home (or a one-screen first-run gate), then verify it with one focused presentation test and
  one real emulator/rendered journey.

## Result classification

- Implemented: no product-source change; evidence/handoff only.
- Simulated/Tested: yes — focused production-state JVM verification; no rendered emulator claim.
- Hardware Verified: no.
- Released: no.

## Non-double-counted verification

- `CompanionLinkReadinessTest`: **10/10 passed**.
- `CompanionNavigationTest`: **4/4 passed**.
- `DeviceAtlasKnowledgeTest`: **15/15 passed**.
- Total focused JVM result: **29/29 passed**, zero skipped/failures/errors.
- The initial attempt with Fedora's Java 25 failed before tests because the Android Gradle
  toolchain requires the repository-managed Java 17. The exact same focused invocation passed
  with the existing JDK 17; this was a host-toolchain setup failure, not a product-test failure.
- Emulator rendered journey: **not completed**; the existing virtual device exited before ADB
  registration. No emulator/system image was downloaded or installed.
- Existing debug APK remained byte-identical at SHA-256
  `62bc530d5f077e3e34ad71002caa24303a584bf4661f56d2cc338c976bfb5a2b`, size `9060239`
  bytes. It was not rebuilt.
- No full Companion suite, instrumentation suite or APK build was run.

## Guided friction and remaining dead ends

- Verified in production state policy: disconnected Link state does not masquerade as paired,
  secure, synced or execution-ready; it provides a concrete discovery or network action.
- Verified in navigation policy: invalid or absent saved route state falls safely to Home.
- Remaining friction: the new-user internal-alpha and zero-execution-authority message is not
  presented at initial Home entry. It requires the protected UI reconciliation above.
- No pairing loop or false live-sync claim was found in the focused offline state path.

## Guardian, Recovery and safety implications

- Companion remains evidence/diagnosis only and receives no flash, root, wipe, unlock, relock,
  command or Recovery execution authority.
- Guardian-only authority, exact-device evidence, consent separation, UNKNOWN-on-uncertainty,
  no blind retry, same-incident Recovery and independent verification remain unchanged.
- Bootloader locking/relocking remains permanently prohibited with no override.

## Platform and version-gate status

- Fedora/Linux JVM state verification: genuinely passed with the existing repository-managed
  JDK 17 and Android/Gradle toolchain.
- Fedora Android emulator: unavailable for a rendered claim because it exited before exposing its
  virtual serial. This is a host/emulator limitation, not Hardware Verified evidence.
- Windows: unchanged; no Windows claim is made.
- Physical Android: not used; no hardware claim is made.
- 5 September 2026 feature freeze: compliant. No feature or application-source change occurred.
- v0.2 Golden Foundation remains **CLOSED**. No execution, signing, publication or release gate
  changed.

## External actions

- Physical phone, device-scoped ADB/Fastboot, Recovery, flash, install, APK transfer and device
  operation: none.
- Emulator APK installation or app-data mutation: none.
- Package/tool/system-image download or installation, production build, signing, publication,
  release, merge, history rewrite and force-push: none.
- Remote action: only normal pushes of this scoped evidence and handoff to the existing Linux
  working branch.
- The three protected Companion files, Windows launcher drafts, website, assets and unrelated user
  work were untouched.

## Next proposed Build task

Stop for independent Product Assurance review. Do not begin another Companion UI slice until the
protected Companion work is reconciled into the authoritative repository history.

## Product Assurance Review Requested

- Confirm the 29 focused production-state checks are sufficient evidence for the non-rendered
  portions of this bounded offline journey.
- Confirm the missing first-entry internal-alpha/no-authority disclosure is the first concrete
  defect and that implementation must wait for protected `MainActivity.kt` reconciliation.
- Decide which task owns that reconciliation and the later one-screen rendered acceptance journey.
